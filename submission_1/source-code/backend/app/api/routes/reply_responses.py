import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.database import get_db
from app.db.models import Campaign, EmailDraft, FollowUpDraft, ReplyResponseDraft
from app.schemas.reply_response_schema import (
    ReplyResponseContentUpdateRequest,
    ReplyResponseStatusUpdateRequest,
)
from app.services.gmail_service import (
    GmailConfigurationError,
    GmailConnectionError,
    get_gmail_message_thread_id,
    get_gmail_service,
    send_email_via_gmail,
)
from app.services.reply_response_service import (
    ACTIVE_RESPONSE_DRAFT_STATUSES,
    ReplyResponseRuleError,
    ReplyResponseSaveError,
    generate_response_draft_for_reply,
    get_active_response_draft,
)
from app.utils.time_utils import utc_now
from app.utils.draft_safety import PLACEHOLDER_SEND_ERROR, contains_blocked_placeholder

router = APIRouter(
    prefix="/reply-responses",
    tags=["Reply Responses"]
)

DEFAULT_REPLY_RESPONSE_LIMIT = 5
MAX_REPLY_RESPONSE_LIMIT = 10
SEND_DELAY_SECONDS = 2
ALLOWED_STATUS_TRANSITIONS = {
    "generated": {"approved", "rejected"},
    "approved": {"rejected"},
}
EDITABLE_RESPONSE_STATUSES = {"generated", "approved", "failed"}
MAX_RESPONSE_BODY_LENGTH = 10000


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
            joinedload(EmailDraft.reply_response_drafts),
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


def get_response_draft_or_404(response_draft_id: int, db: Session):
    response_draft = (
        response_draft_query(db)
        .filter(ReplyResponseDraft.id == response_draft_id)
        .first()
    )

    if not response_draft:
        raise HTTPException(
            status_code=404,
            detail=f"Response draft with id {response_draft_id} was not found"
        )

    return response_draft


def response_draft_query(db: Session):
    return (
        db.query(ReplyResponseDraft)
        .options(
            joinedload(ReplyResponseDraft.lead),
            joinedload(ReplyResponseDraft.campaign),
            joinedload(ReplyResponseDraft.original_email_draft),
        )
    )


def serialize_response_draft(response_draft: ReplyResponseDraft):
    lead = response_draft.lead

    return {
        "id": response_draft.id,
        "original_email_draft_id": response_draft.original_email_draft_id,
        "campaign_id": response_draft.campaign_id,
        "lead_id": response_draft.lead_id,
        "subject": response_draft.subject,
        "body": response_draft.body,
        "status": response_draft.status,
        "intent_used": response_draft.intent_used,
        "next_action_used": response_draft.next_action_used,
        "knowledge_used": response_draft.knowledge_used,
        "model_used": response_draft.model_used,
        "generated_at": response_draft.generated_at,
        "approved_at": response_draft.approved_at,
        "rejected_at": response_draft.rejected_at,
        "sent_at": response_draft.sent_at,
        "gmail_message_id": response_draft.gmail_message_id,
        "gmail_thread_id": response_draft.gmail_thread_id,
        "send_error": response_draft.send_error,
        "created_at": response_draft.created_at,
        "updated_at": response_draft.updated_at,
        "lead_company_name": lead.company_name if lead else None,
        "lead_contact_name": lead.contact_name if lead else None,
        "lead_contact_role": lead.contact_role if lead else None,
        "lead_email": lead.email if lead else None,
    }


def commit_response_draft_update(db: Session, response_draft: ReplyResponseDraft, message: str):
    try:
        db.commit()
        db.refresh(response_draft)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=message) from exc


def handle_generation_error(exc: Exception):
    if isinstance(exc, ReplyResponseRuleError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if isinstance(exc, ReplyResponseSaveError):
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    raise HTTPException(status_code=500, detail="Response draft generation failed. Please try again.") from exc


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


def count_remaining_approved_responses(campaign_id: int, db: Session):
    return (
        db.query(func.count(ReplyResponseDraft.id))
        .filter(
            ReplyResponseDraft.campaign_id == campaign_id,
            ReplyResponseDraft.status == "approved",
        )
        .scalar()
        or 0
    )


def count_remaining_generatable_replies(campaign_id: int, db: Session):
    classified_reply_ids = (
        db.query(EmailDraft.id)
        .filter(
            EmailDraft.campaign_id == campaign_id,
            EmailDraft.status == "replied",
            EmailDraft.reply_intent.isnot(None),
        )
        .subquery()
    )
    active_response_ids = (
        db.query(ReplyResponseDraft.original_email_draft_id)
        .filter(
            ReplyResponseDraft.campaign_id == campaign_id,
            ReplyResponseDraft.status.in_(ACTIVE_RESPONSE_DRAFT_STATUSES),
        )
        .subquery()
    )

    return (
        db.query(func.count(classified_reply_ids.c.id))
        .filter(~classified_reply_ids.c.id.in_(active_response_ids))
        .scalar()
        or 0
    )


def mark_response_failed(db: Session, response_draft: ReplyResponseDraft, error_message: str):
    response_draft.status = "failed"
    response_draft.send_error = error_message
    commit_response_draft_update(db, response_draft, "Response send status could not be updated.")


def get_thread_id_for_response(db: Session, response_draft: ReplyResponseDraft):
    if response_draft.gmail_thread_id:
        return response_draft.gmail_thread_id

    original_email = response_draft.original_email_draft

    if not original_email:
        return None

    return (
        get_gmail_message_thread_id(db, original_email.reply_message_id)
        or get_gmail_message_thread_id(db, original_email.gmail_message_id)
    )


def normalize_response_subject(response_draft: ReplyResponseDraft):
    subject = (response_draft.subject or "").strip()

    if subject.lower().startswith("re:"):
        return subject

    original_subject = (
        response_draft.original_email_draft.subject
        if response_draft.original_email_draft
        else subject
    )

    return f"Re: {(original_subject or subject or 'Your reply').strip()}"


def send_approved_response_draft(db: Session, response_draft: ReplyResponseDraft):
    lead_email = clean_email(response_draft.lead.email if response_draft.lead else None)

    if not lead_email:
        mark_response_failed(db, response_draft, "Lead email is missing.")
        return serialize_response_draft(response_draft)

    response_draft.status = "sending"
    response_draft.send_error = None
    commit_response_draft_update(db, response_draft, "Response send status could not be updated.")

    send_result = send_email_via_gmail(
        db,
        lead_email,
        normalize_response_subject(response_draft),
        response_draft.body,
        thread_id=get_thread_id_for_response(db, response_draft),
    )

    if send_result.get("success"):
        response_draft.status = "sent"
        response_draft.sent_at = utc_now()
        response_draft.gmail_message_id = send_result.get("gmail_message_id")
        response_draft.gmail_thread_id = send_result.get("gmail_thread_id")
        response_draft.send_error = None
    else:
        response_draft.status = "failed"
        response_draft.send_error = send_result.get("error") or "Response sending failed. Please try again."

    commit_response_draft_update(db, response_draft, "Response send status could not be updated.")

    return serialize_response_draft(response_draft)


@router.get("/")
def get_reply_response_drafts(
    campaign_id: int | None = None,
    lead_id: int | None = None,
    original_email_draft_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    query = response_draft_query(db)

    if campaign_id is not None:
        query = query.filter(ReplyResponseDraft.campaign_id == campaign_id)
    if lead_id is not None:
        query = query.filter(ReplyResponseDraft.lead_id == lead_id)
    if original_email_draft_id is not None:
        query = query.filter(ReplyResponseDraft.original_email_draft_id == original_email_draft_id)
    if status:
        query = query.filter(ReplyResponseDraft.status == status)

    response_drafts = (
        query
        .order_by(ReplyResponseDraft.created_at.desc(), ReplyResponseDraft.id.desc())
        .all()
    )

    return {
        "status": "success",
        "data": [serialize_response_draft(response_draft) for response_draft in response_drafts],
    }


@router.get("/campaign/{campaign_id}")
def get_campaign_reply_response_drafts(campaign_id: int, db: Session = Depends(get_db)):
    get_campaign_or_404(campaign_id, db)
    response_drafts = (
        response_draft_query(db)
        .filter(ReplyResponseDraft.campaign_id == campaign_id)
        .order_by(
            ReplyResponseDraft.original_email_draft_id.asc(),
            ReplyResponseDraft.created_at.desc(),
            ReplyResponseDraft.id.desc(),
        )
        .all()
    )

    return {
        "status": "success",
        "data": [serialize_response_draft(response_draft) for response_draft in response_drafts],
    }


@router.post("/generate/{email_draft_id}")
def generate_reply_response_draft(
    email_draft_id: int,
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    email_draft = get_original_email_draft_or_404(email_draft_id, db)

    try:
        result = generate_response_draft_for_reply(db, email_draft, force=force)
    except Exception as exc:
        handle_generation_error(exc)

    return {
        "status": "success",
        "message": result["message"],
        "data": serialize_response_draft(result["response_draft"]),
    }


@router.post("/generate-campaign/{campaign_id}")
def generate_campaign_reply_response_drafts(
    campaign_id: int,
    limit: int = Query(DEFAULT_REPLY_RESPONSE_LIMIT, ge=1),
    db: Session = Depends(get_db),
):
    get_campaign_or_404(campaign_id, db)
    effective_limit = min(limit, MAX_REPLY_RESPONSE_LIMIT)
    email_drafts = (
        db.query(EmailDraft)
        .options(
            joinedload(EmailDraft.campaign),
            joinedload(EmailDraft.lead),
            joinedload(EmailDraft.reply_response_drafts),
        )
        .filter(
            EmailDraft.campaign_id == campaign_id,
            EmailDraft.status == "replied",
            EmailDraft.reply_intent.isnot(None),
        )
        .order_by(EmailDraft.replied_at.desc(), EmailDraft.updated_at.desc(), EmailDraft.id.desc())
        .all()
    )
    drafts_to_process = email_drafts[:effective_limit]
    results = []
    generated_count = 0
    skipped_count = 0
    failed_count = 0

    for email_draft in drafts_to_process:
        try:
            if get_active_response_draft(db, email_draft.id):
                skipped_count += 1
                results.append({
                    "email_draft_id": email_draft.id,
                    "lead_id": email_draft.lead_id,
                    "company_name": email_draft.lead.company_name if email_draft.lead else None,
                    "skipped": True,
                    "reason": "Active response draft already exists.",
                })
                continue

            result = generate_response_draft_for_reply(db, email_draft)
            response_draft = result["response_draft"]

            if result["created"]:
                generated_count += 1
            else:
                skipped_count += 1

            results.append({
                "email_draft_id": email_draft.id,
                "lead_id": email_draft.lead_id,
                "company_name": email_draft.lead.company_name if email_draft.lead else None,
                "generated": bool(result["created"]),
                "response_draft_id": response_draft.id,
                "reason": None if result["created"] else result["message"],
            })
        except ReplyResponseRuleError as exc:
            skipped_count += 1
            results.append({
                "email_draft_id": email_draft.id,
                "lead_id": email_draft.lead_id,
                "company_name": email_draft.lead.company_name if email_draft.lead else None,
                "skipped": True,
                "reason": str(exc),
            })
        except ReplyResponseSaveError as exc:
            failed_count += 1
            results.append({
                "email_draft_id": email_draft.id,
                "lead_id": email_draft.lead_id,
                "company_name": email_draft.lead.company_name if email_draft.lead else None,
                "failed": True,
                "error": str(exc),
            })

    return {
        "status": "success",
        "message": "Campaign response draft generation completed",
        "campaign_id": campaign_id,
        "processed": len(drafts_to_process),
        "generated": generated_count,
        "skipped": skipped_count,
        "failed": failed_count,
        "remaining": count_remaining_generatable_replies(campaign_id, db),
        "results": results,
    }


@router.patch("/{response_draft_id}")
def update_reply_response_draft_content(
    response_draft_id: int,
    response_update: ReplyResponseContentUpdateRequest,
    db: Session = Depends(get_db),
):
    subject = (response_update.subject or "").strip()
    body = (response_update.body or "").strip()

    if not subject or not body:
        raise HTTPException(status_code=400, detail="Subject and body are required.")

    if len(body) > MAX_RESPONSE_BODY_LENGTH:
        raise HTTPException(status_code=400, detail="Response draft body is too long.")

    response_draft = get_response_draft_or_404(response_draft_id, db)

    if response_draft.status not in EDITABLE_RESPONSE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="Cannot edit a sent draft."
        )

    response_draft.subject = subject[:255]
    response_draft.body = body
    response_draft.updated_at = utc_now()

    if response_draft.status in {"approved", "failed"}:
        response_draft.status = "generated"
        response_draft.approved_at = None
        response_draft.send_error = None

    commit_response_draft_update(db, response_draft, "Failed to update draft. Please try again.")

    return {
        "status": "success",
        "message": "Response draft updated successfully",
        "data": serialize_response_draft(response_draft),
    }


@router.patch("/{response_draft_id}/status")
def update_reply_response_status(
    response_draft_id: int,
    response_update: ReplyResponseStatusUpdateRequest,
    db: Session = Depends(get_db),
):
    response_draft = get_response_draft_or_404(response_draft_id, db)
    next_status = response_update.status
    allowed_next_statuses = ALLOWED_STATUS_TRANSITIONS.get(response_draft.status, set())

    if next_status not in allowed_next_statuses:
        raise HTTPException(
            status_code=400,
            detail="Invalid response draft status transition."
        )

    now = utc_now()
    response_draft.status = next_status

    if next_status == "approved":
        response_draft.approved_at = now
        response_draft.rejected_at = None
    elif next_status == "rejected":
        response_draft.rejected_at = now

    commit_response_draft_update(db, response_draft, "Response draft status could not be updated.")

    return {
        "status": "success",
        "message": "Response draft status updated successfully",
        "data": serialize_response_draft(response_draft),
    }


@router.post("/send/{response_draft_id}")
def send_one_reply_response_draft(
    response_draft_id: int,
    db: Session = Depends(get_db),
):
    response_draft = get_response_draft_or_404(response_draft_id, db)

    if response_draft.status != "approved":
        raise HTTPException(
            status_code=400,
            detail="Approve the response draft before sending."
        )

    if contains_blocked_placeholder(response_draft.subject, response_draft.body):
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
    result = send_approved_response_draft(db, response_draft)

    return {
        "status": "success",
        "message": (
            "Response draft sent successfully"
            if result["status"] == "sent"
            else "Response sending failed. Please try again."
        ),
        "data": result,
    }


@router.post("/send-approved/campaign/{campaign_id}")
def send_approved_campaign_reply_response_drafts(
    campaign_id: int,
    limit: int = Query(DEFAULT_REPLY_RESPONSE_LIMIT, ge=1),
    db: Session = Depends(get_db),
):
    get_campaign_or_404(campaign_id, db)
    effective_limit = min(limit, MAX_REPLY_RESPONSE_LIMIT)
    response_drafts = (
        response_draft_query(db)
        .filter(
            ReplyResponseDraft.campaign_id == campaign_id,
            ReplyResponseDraft.status == "approved",
        )
        .order_by(ReplyResponseDraft.approved_at.asc(), ReplyResponseDraft.created_at.asc(), ReplyResponseDraft.id.asc())
        .limit(effective_limit)
        .all()
    )
    daily_limit, sent_today, remaining_daily_capacity = get_remaining_daily_capacity(db)

    if not response_drafts:
        return {
            "status": "success",
            "message": "No approved response drafts found for this campaign",
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
            "skipped": len(response_drafts),
            "remaining_approved": count_remaining_approved_responses(campaign_id, db),
            "daily_limit": daily_limit,
            "sent_today": sent_today,
            "results": [],
        }

    response_drafts_to_send = response_drafts[:remaining_daily_capacity]
    skipped_count = max(len(response_drafts) - len(response_drafts_to_send), 0)
    results = []
    sent_count = 0
    failed_count = 0

    if response_drafts_to_send:
        ensure_gmail_ready(db)

    for index, response_draft in enumerate(response_drafts_to_send):
        if contains_blocked_placeholder(response_draft.subject, response_draft.body):
            skipped_count += 1
            results.append({
                **serialize_response_draft(response_draft),
                "error": PLACEHOLDER_SEND_ERROR,
            })
            continue

        result = send_approved_response_draft(db, response_draft)
        results.append(result)

        if result["status"] == "sent":
            sent_count += 1
        elif result["status"] == "failed":
            failed_count += 1

        if index < len(response_drafts_to_send) - 1:
            time.sleep(SEND_DELAY_SECONDS)

    return {
        "status": "success",
        "message": "Approved response draft sending completed",
        "campaign_id": campaign_id,
        "processed": len(results),
        "sent": sent_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "remaining_approved": count_remaining_approved_responses(campaign_id, db),
        "daily_limit": daily_limit,
        "sent_today": sent_today + sent_count,
        "results": results,
    }
