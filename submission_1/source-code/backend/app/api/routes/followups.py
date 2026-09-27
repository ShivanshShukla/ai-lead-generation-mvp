import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.database import get_db
from app.db.models import Campaign, EmailDraft, FollowUpDraft, ReplyResponseDraft
from app.schemas.followup_schema import FollowUpContentUpdateRequest, FollowUpStatusUpdateRequest
from app.services.ai_service import AIConfigurationError, AIServiceError
from app.services.followup_service import (
    FollowUpRuleError,
    FollowUpSaveError,
    generate_follow_up_for_draft,
)
from app.services.gmail_service import (
    GmailConfigurationError,
    GmailConnectionError,
    get_gmail_message_thread_id,
    get_gmail_service,
    send_email_via_gmail,
)
from app.utils.time_utils import utc_now
from app.utils.draft_safety import PLACEHOLDER_SEND_ERROR, contains_blocked_placeholder

router = APIRouter(
    prefix="/followups",
    tags=["Follow-ups"]
)

DEFAULT_FOLLOW_UP_LIMIT = 5
MAX_FOLLOW_UP_LIMIT = 10
SEND_DELAY_SECONDS = 2
ALLOWED_STATUS_TRANSITIONS = {
    "generated": {"approved", "rejected"},
    "approved": {"rejected"},
}
EDITABLE_FOLLOW_UP_STATUSES = {"generated", "approved", "failed"}
MAX_FOLLOW_UP_BODY_LENGTH = 10000


def clean_email(value):
    if value is None:
        return None

    value = str(value).strip()
    return value or None


def get_campaign_or_404(campaign_id: int, db: Session):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail=f"Campaign with id {campaign_id} was not found"
        )

    return campaign


def get_original_email_draft_or_404(email_draft_id: int, db: Session):
    email_draft = (
        db.query(EmailDraft)
        .options(
            joinedload(EmailDraft.campaign),
            joinedload(EmailDraft.lead),
            joinedload(EmailDraft.follow_up_drafts),
        )
        .filter(EmailDraft.id == email_draft_id)
        .first()
    )

    if not email_draft:
        raise HTTPException(
            status_code=404,
            detail=f"Email draft with id {email_draft_id} was not found"
        )

    return email_draft


def get_follow_up_or_404(followup_id: int, db: Session):
    follow_up = (
        db.query(FollowUpDraft)
        .options(
            joinedload(FollowUpDraft.lead),
            joinedload(FollowUpDraft.campaign),
            joinedload(FollowUpDraft.original_email_draft),
        )
        .filter(FollowUpDraft.id == followup_id)
        .first()
    )

    if not follow_up:
        raise HTTPException(
            status_code=404,
            detail=f"Follow-up draft with id {followup_id} was not found"
        )

    return follow_up


def serialize_follow_up(follow_up: FollowUpDraft):
    lead = follow_up.lead

    return {
        "id": follow_up.id,
        "original_email_draft_id": follow_up.original_email_draft_id,
        "campaign_id": follow_up.campaign_id,
        "lead_id": follow_up.lead_id,
        "follow_up_number": follow_up.follow_up_number,
        "subject": follow_up.subject,
        "body": follow_up.body,
        "status": follow_up.status,
        "model_used": follow_up.model_used,
        "generated_at": follow_up.generated_at,
        "approved_at": follow_up.approved_at,
        "rejected_at": follow_up.rejected_at,
        "sent_at": follow_up.sent_at,
        "gmail_message_id": follow_up.gmail_message_id,
        "gmail_thread_id": follow_up.gmail_thread_id,
        "send_error": follow_up.send_error,
        "created_at": follow_up.created_at,
        "updated_at": follow_up.updated_at,
        "lead_company_name": lead.company_name if lead else None,
        "lead_contact_name": lead.contact_name if lead else None,
        "lead_contact_role": lead.contact_role if lead else None,
        "lead_email": lead.email if lead else None,
    }


def follow_up_query(db: Session):
    return (
        db.query(FollowUpDraft)
        .options(
            joinedload(FollowUpDraft.lead),
            joinedload(FollowUpDraft.campaign),
            joinedload(FollowUpDraft.original_email_draft),
        )
    )


def commit_follow_up_update(db: Session, follow_up: FollowUpDraft, message: str):
    try:
        db.commit()
        db.refresh(follow_up)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=message) from exc


def handle_generation_error(exc: Exception):
    if isinstance(exc, FollowUpRuleError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if isinstance(exc, AIConfigurationError):
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if isinstance(exc, AIServiceError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if isinstance(exc, FollowUpSaveError):
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    raise HTTPException(status_code=500, detail="Follow-up draft could not be generated.") from exc


def ensure_gmail_ready(db: Session):
    try:
        get_gmail_service(db)
    except GmailConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except GmailConnectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def count_daily_sent_emails(db: Session):
    start_of_day = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    original_sent_count = (
        db.query(func.count(EmailDraft.id))
        .filter(
            EmailDraft.status.in_(("sent", "replied")),
            EmailDraft.sent_at >= start_of_day,
        )
        .scalar()
        or 0
    )
    follow_up_sent_count = (
        db.query(func.count(FollowUpDraft.id))
        .filter(
            FollowUpDraft.status == "sent",
            FollowUpDraft.sent_at >= start_of_day,
        )
        .scalar()
        or 0
    )
    response_sent_count = (
        db.query(func.count(ReplyResponseDraft.id))
        .filter(
            ReplyResponseDraft.status == "sent",
            ReplyResponseDraft.sent_at >= start_of_day,
        )
        .scalar()
        or 0
    )

    return original_sent_count + follow_up_sent_count + response_sent_count


def get_remaining_daily_capacity(db: Session):
    daily_limit = max(settings.GMAIL_DAILY_LIMIT, 0)
    sent_today = count_daily_sent_emails(db)

    return daily_limit, sent_today, max(daily_limit - sent_today, 0)


def count_remaining_approved_follow_ups(campaign_id: int, db: Session):
    return (
        db.query(func.count(FollowUpDraft.id))
        .filter(
            FollowUpDraft.campaign_id == campaign_id,
            FollowUpDraft.status == "approved",
        )
        .scalar()
        or 0
    )


def get_thread_id_for_follow_up(db: Session, follow_up: FollowUpDraft):
    existing_thread_row = (
        db.query(FollowUpDraft.gmail_thread_id)
        .filter(
            FollowUpDraft.original_email_draft_id == follow_up.original_email_draft_id,
            FollowUpDraft.gmail_thread_id.isnot(None),
            FollowUpDraft.gmail_thread_id != "",
        )
        .order_by(FollowUpDraft.sent_at.desc(), FollowUpDraft.id.desc())
        .first()
    )

    if existing_thread_row:
        return existing_thread_row[0]

    original_email = follow_up.original_email_draft

    if not original_email:
        return None

    return get_gmail_message_thread_id(db, original_email.gmail_message_id)


def normalize_follow_up_subject(follow_up: FollowUpDraft):
    subject = (follow_up.subject or "").strip()

    if subject.lower().startswith("re:"):
        return subject

    original_subject = (
        follow_up.original_email_draft.subject
        if follow_up.original_email_draft
        else subject
    )

    return f"Re: {(original_subject or subject or 'Follow-up').strip()}"


def original_email_has_reply(follow_up: FollowUpDraft):
    original_email = follow_up.original_email_draft

    if not original_email:
        return False

    return (
        original_email.status == "replied"
        or bool(original_email.replied_at)
        or bool(original_email.reply_message_id)
    )


def mark_follow_up_failed(db: Session, follow_up: FollowUpDraft, error_message: str):
    follow_up.status = "failed"
    follow_up.send_error = error_message
    commit_follow_up_update(db, follow_up, "Follow-up send status could not be updated.")


def send_approved_follow_up(db: Session, follow_up: FollowUpDraft):
    lead_email = clean_email(follow_up.lead.email if follow_up.lead else None)

    if not lead_email:
        mark_follow_up_failed(db, follow_up, "Lead email is missing.")
        return serialize_follow_up(follow_up)

    follow_up.status = "sending"
    follow_up.send_error = None
    commit_follow_up_update(db, follow_up, "Follow-up send status could not be updated.")

    send_result = send_email_via_gmail(
        db,
        lead_email,
        normalize_follow_up_subject(follow_up),
        follow_up.body,
        thread_id=get_thread_id_for_follow_up(db, follow_up),
    )

    if send_result.get("success"):
        follow_up.status = "sent"
        follow_up.sent_at = utc_now()
        follow_up.gmail_message_id = send_result.get("gmail_message_id")
        follow_up.gmail_thread_id = send_result.get("gmail_thread_id")
        follow_up.send_error = None
    else:
        follow_up.status = "failed"
        follow_up.send_error = send_result.get("error") or "Follow-up sending failed. Please try again."

    commit_follow_up_update(db, follow_up, "Follow-up send status could not be updated.")

    return serialize_follow_up(follow_up)


@router.get("/")
def get_follow_ups(
    campaign_id: int | None = None,
    lead_id: int | None = None,
    original_email_draft_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    query = follow_up_query(db)

    if campaign_id is not None:
        query = query.filter(FollowUpDraft.campaign_id == campaign_id)
    if lead_id is not None:
        query = query.filter(FollowUpDraft.lead_id == lead_id)
    if original_email_draft_id is not None:
        query = query.filter(FollowUpDraft.original_email_draft_id == original_email_draft_id)
    if status:
        query = query.filter(FollowUpDraft.status == status)

    follow_ups = (
        query
        .order_by(FollowUpDraft.created_at.desc(), FollowUpDraft.id.desc())
        .all()
    )

    return {
        "status": "success",
        "data": [serialize_follow_up(follow_up) for follow_up in follow_ups],
    }


@router.get("/campaign/{campaign_id}")
def get_campaign_follow_ups(campaign_id: int, db: Session = Depends(get_db)):
    get_campaign_or_404(campaign_id, db)
    follow_ups = (
        follow_up_query(db)
        .filter(FollowUpDraft.campaign_id == campaign_id)
        .order_by(
            FollowUpDraft.original_email_draft_id.asc(),
            FollowUpDraft.follow_up_number.asc(),
            FollowUpDraft.created_at.asc(),
        )
        .all()
    )

    return {
        "status": "success",
        "data": [serialize_follow_up(follow_up) for follow_up in follow_ups],
    }


@router.post("/generate/{email_draft_id}")
def generate_follow_up(
    email_draft_id: int,
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    original_email_draft = get_original_email_draft_or_404(email_draft_id, db)

    try:
        result = generate_follow_up_for_draft(db, original_email_draft, force=force)
    except Exception as exc:
        handle_generation_error(exc)

    return {
        "status": "success",
        "message": result["message"],
        "data": serialize_follow_up(result["follow_up_draft"]),
    }


@router.post("/generate-campaign/{campaign_id}")
def generate_campaign_follow_ups(
    campaign_id: int,
    limit: int = Query(DEFAULT_FOLLOW_UP_LIMIT, ge=1),
    db: Session = Depends(get_db),
):
    get_campaign_or_404(campaign_id, db)
    effective_limit = min(limit, MAX_FOLLOW_UP_LIMIT)
    original_email_drafts = (
        db.query(EmailDraft)
        .options(
            joinedload(EmailDraft.campaign),
            joinedload(EmailDraft.lead),
            joinedload(EmailDraft.follow_up_drafts),
        )
        .filter(
            EmailDraft.campaign_id == campaign_id,
            EmailDraft.status == "sent",
        )
        .order_by(EmailDraft.sent_at.asc(), EmailDraft.id.asc())
        .all()
    )
    drafts_to_process = original_email_drafts[:effective_limit]
    results = []
    generated_count = 0
    skipped_count = 0
    failed_count = 0

    for original_email_draft in drafts_to_process:
        try:
            result = generate_follow_up_for_draft(db, original_email_draft)
            follow_up = result["follow_up_draft"]

            if result["created"]:
                generated_count += 1
            else:
                skipped_count += 1

            results.append({
                "email_draft_id": original_email_draft.id,
                "lead_id": original_email_draft.lead_id,
                "company_name": original_email_draft.lead.company_name if original_email_draft.lead else None,
                "generated": bool(result["created"]),
                "follow_up_id": follow_up.id,
                "follow_up_number": follow_up.follow_up_number,
                "reason": None if result["created"] else result["message"],
            })
        except FollowUpRuleError as exc:
            skipped_count += 1
            results.append({
                "email_draft_id": original_email_draft.id,
                "lead_id": original_email_draft.lead_id,
                "company_name": original_email_draft.lead.company_name if original_email_draft.lead else None,
                "skipped": True,
                "reason": str(exc),
            })
        except (AIConfigurationError, AIServiceError, FollowUpSaveError) as exc:
            failed_count += 1
            results.append({
                "email_draft_id": original_email_draft.id,
                "lead_id": original_email_draft.lead_id,
                "company_name": original_email_draft.lead.company_name if original_email_draft.lead else None,
                "failed": True,
                "error": str(exc),
            })

    return {
        "status": "success",
        "message": "Campaign follow-up generation completed",
        "campaign_id": campaign_id,
        "processed": len(drafts_to_process),
        "generated": generated_count,
        "skipped": skipped_count,
        "failed": failed_count,
        "remaining": max(len(original_email_drafts) - len(drafts_to_process), 0),
        "results": results,
    }


@router.patch("/{followup_id}")
def update_follow_up_content(
    followup_id: int,
    followup_update: FollowUpContentUpdateRequest,
    db: Session = Depends(get_db),
):
    subject = (followup_update.subject or "").strip()
    body = (followup_update.body or "").strip()

    if not subject or not body:
        raise HTTPException(status_code=400, detail="Subject and body are required.")

    if len(body) > MAX_FOLLOW_UP_BODY_LENGTH:
        raise HTTPException(status_code=400, detail="Follow-up body is too long.")

    follow_up = get_follow_up_or_404(followup_id, db)

    if follow_up.status not in EDITABLE_FOLLOW_UP_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="Cannot edit a sent draft."
        )

    follow_up.subject = subject[:255]
    follow_up.body = body
    follow_up.updated_at = utc_now()

    if follow_up.status in {"approved", "failed"}:
        follow_up.status = "generated"
        follow_up.approved_at = None
        follow_up.send_error = None

    commit_follow_up_update(db, follow_up, "Failed to update draft. Please try again.")

    return {
        "status": "success",
        "message": "Follow-up draft updated successfully",
        "data": serialize_follow_up(follow_up),
    }


@router.patch("/{followup_id}/status")
def update_follow_up_status(
    followup_id: int,
    followup_update: FollowUpStatusUpdateRequest,
    db: Session = Depends(get_db),
):
    follow_up = get_follow_up_or_404(followup_id, db)
    next_status = followup_update.status
    allowed_next_statuses = ALLOWED_STATUS_TRANSITIONS.get(follow_up.status, set())

    if next_status not in allowed_next_statuses:
        raise HTTPException(
            status_code=400,
            detail="Invalid follow-up status transition."
        )

    now = utc_now()
    follow_up.status = next_status

    if next_status == "approved":
        follow_up.approved_at = now
        follow_up.rejected_at = None
    elif next_status == "rejected":
        follow_up.rejected_at = now

    commit_follow_up_update(db, follow_up, "Follow-up status could not be updated.")

    return {
        "status": "success",
        "message": "Follow-up status updated successfully",
        "data": serialize_follow_up(follow_up),
    }


@router.post("/send/{followup_id}")
def send_one_follow_up(
    followup_id: int,
    db: Session = Depends(get_db),
):
    follow_up = get_follow_up_or_404(followup_id, db)

    if follow_up.status != "approved":
        raise HTTPException(
            status_code=400,
            detail="Approve the follow-up before sending."
        )

    if original_email_has_reply(follow_up):
        raise HTTPException(
            status_code=400,
            detail="Cannot send follow-up because this lead has already replied."
        )

    if contains_blocked_placeholder(follow_up.subject, follow_up.body):
        raise HTTPException(
            status_code=400,
            detail=PLACEHOLDER_SEND_ERROR
        )

    _, _, remaining_daily_capacity = get_remaining_daily_capacity(db)

    if remaining_daily_capacity <= 0:
        raise HTTPException(
            status_code=429,
            detail=f"Gmail daily limit reached ({settings.GMAIL_DAILY_LIMIT} emails)."
        )

    ensure_gmail_ready(db)
    result = send_approved_follow_up(db, follow_up)

    return {
        "status": "success",
        "message": (
            "Follow-up sent successfully"
            if result["status"] == "sent"
            else "Follow-up sending failed. Please try again."
        ),
        "data": result,
    }


@router.post("/send-approved/campaign/{campaign_id}")
def send_approved_campaign_follow_ups(
    campaign_id: int,
    limit: int = Query(DEFAULT_FOLLOW_UP_LIMIT, ge=1),
    db: Session = Depends(get_db),
):
    get_campaign_or_404(campaign_id, db)
    effective_limit = min(limit, MAX_FOLLOW_UP_LIMIT)
    follow_ups = (
        follow_up_query(db)
        .filter(
            FollowUpDraft.campaign_id == campaign_id,
            FollowUpDraft.status == "approved",
        )
        .order_by(FollowUpDraft.approved_at.asc(), FollowUpDraft.created_at.asc(), FollowUpDraft.id.asc())
        .limit(effective_limit)
        .all()
    )
    daily_limit, sent_today, remaining_daily_capacity = get_remaining_daily_capacity(db)

    if not follow_ups:
        return {
            "status": "success",
            "message": "No approved follow-up drafts found for this campaign",
            "campaign_id": campaign_id,
            "processed": 0,
            "sent": 0,
            "failed": 0,
            "skipped": 0,
            "remaining_approved": 0,
            "daily_limit": daily_limit,
            "sent_today": sent_today,
            "results": [],
        }

    if remaining_daily_capacity <= 0:
        return {
            "status": "success",
            "message": "Gmail daily sending limit reached",
            "campaign_id": campaign_id,
            "processed": 0,
            "sent": 0,
            "failed": 0,
            "skipped": len(follow_ups),
            "remaining_approved": count_remaining_approved_follow_ups(campaign_id, db),
            "daily_limit": daily_limit,
            "sent_today": sent_today,
            "results": [],
        }

    follow_ups_to_send = follow_ups[:remaining_daily_capacity]
    skipped_count = max(len(follow_ups) - len(follow_ups_to_send), 0)
    results = []
    sent_count = 0
    failed_count = 0

    if follow_ups_to_send:
        ensure_gmail_ready(db)

    for index, follow_up in enumerate(follow_ups_to_send):
        if original_email_has_reply(follow_up):
            skipped_count += 1
            results.append({
                **serialize_follow_up(follow_up),
                "error": "Cannot send follow-up because this lead has already replied.",
            })
            continue

        if contains_blocked_placeholder(follow_up.subject, follow_up.body):
            skipped_count += 1
            results.append({
                **serialize_follow_up(follow_up),
                "error": PLACEHOLDER_SEND_ERROR,
            })
            continue

        result = send_approved_follow_up(db, follow_up)
        results.append(result)

        if result["status"] == "sent":
            sent_count += 1
        elif result["status"] == "failed":
            failed_count += 1

        if index < len(follow_ups_to_send) - 1:
            time.sleep(SEND_DELAY_SECONDS)

    return {
        "status": "success",
        "message": "Approved follow-up sending completed",
        "campaign_id": campaign_id,
        "processed": len(results),
        "sent": sent_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "remaining_approved": count_remaining_approved_follow_ups(campaign_id, db),
        "daily_limit": daily_limit,
        "sent_today": sent_today + sent_count,
        "results": results,
    }
