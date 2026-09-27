import time

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.database import get_db
from app.db.models import Campaign, EmailDraft, FollowUpDraft, ReplyResponseDraft
from app.services.gmail_service import (
    GmailConfigurationError,
    GmailConnectionError,
    GMAIL_READONLY_SCOPE,
    build_gmail_oauth_url,
    exchange_code_for_token,
    get_connected_gmail_scopes,
    get_connected_gmail_token,
    get_gmail_service,
    send_email_via_gmail,
)
from app.utils.time_utils import utc_now
from app.utils.draft_safety import PLACEHOLDER_SEND_ERROR, contains_blocked_placeholder

router = APIRouter(
    prefix="/gmail",
    tags=["Gmail"]
)

DEFAULT_SEND_LIMIT = 5
MAX_SEND_LIMIT = 10
SEND_DELAY_SECONDS = 2


def clean_email(value):
    if value is None:
        return None

    value = str(value).strip()
    return value or None


def get_email_draft_or_404(email_draft_id: int, db: Session):
    email_draft = (
        db.query(EmailDraft)
        .options(joinedload(EmailDraft.lead))
        .filter(EmailDraft.id == email_draft_id)
        .first()
    )

    if not email_draft:
        raise HTTPException(
            status_code=404,
            detail=f"Email draft with id {email_draft_id} was not found"
        )

    return email_draft


def get_campaign_or_404(campaign_id: int, db: Session):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail=f"Campaign with id {campaign_id} was not found"
        )

    return campaign


def serialize_send_result(email_draft: EmailDraft):
    lead = email_draft.lead

    return {
        "email_draft_id": email_draft.id,
        "lead_id": email_draft.lead_id,
        "to": lead.email if lead else None,
        "status": email_draft.status,
        "gmail_message_id": email_draft.gmail_message_id,
        "sent_at": email_draft.sent_at,
        "error": email_draft.send_error,
    }


def commit_email_draft_update(db: Session, email_draft: EmailDraft):
    try:
        db.commit()
        db.refresh(email_draft)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Email draft send status could not be updated."
        ) from exc


def mark_email_draft_failed(db: Session, email_draft: EmailDraft, error_message: str):
    email_draft.status = "failed"
    email_draft.send_error = error_message
    commit_email_draft_update(db, email_draft)


def get_daily_sent_count(db: Session):
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
    sent_today = get_daily_sent_count(db)

    return daily_limit, sent_today, max(daily_limit - sent_today, 0)


def ensure_gmail_ready(db: Session):
    try:
        get_gmail_service(db)
    except GmailConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except GmailConnectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def send_approved_email_draft(db: Session, email_draft: EmailDraft):
    lead_email = clean_email(email_draft.lead.email if email_draft.lead else None)

    if not lead_email:
        mark_email_draft_failed(db, email_draft, "Lead email is missing.")
        return serialize_send_result(email_draft)

    email_draft.status = "sending"
    email_draft.send_error = None
    commit_email_draft_update(db, email_draft)

    send_result = send_email_via_gmail(
        db,
        lead_email,
        email_draft.subject,
        email_draft.body,
    )

    if send_result.get("success"):
        email_draft.status = "sent"
        email_draft.sent_at = utc_now()
        email_draft.gmail_message_id = send_result.get("gmail_message_id")
        email_draft.send_error = None
    else:
        email_draft.status = "failed"
        email_draft.send_error = send_result.get("error") or "Gmail send failed."

    commit_email_draft_update(db, email_draft)

    return serialize_send_result(email_draft)


def count_remaining_approved(campaign_id: int, db: Session):
    return (
        db.query(func.count(EmailDraft.id))
        .filter(
            EmailDraft.campaign_id == campaign_id,
            EmailDraft.status == "approved",
        )
        .scalar()
        or 0
    )


@router.get("/status")
def get_gmail_status(db: Session = Depends(get_db)):
    token_record = get_connected_gmail_token(db)
    scopes = get_connected_gmail_scopes(db)

    if not token_record:
        return {
            "status": "success",
            "connected": False,
            "reply_tracking_available": False,
        }

    return {
        "status": "success",
        "connected": True,
        "email": token_record.email or settings.GMAIL_SENDER_EMAIL or None,
        "reply_tracking_available": GMAIL_READONLY_SCOPE in scopes,
    }


@router.get("/oauth/start")
def start_gmail_oauth(db: Session = Depends(get_db)):
    try:
        auth_url = build_gmail_oauth_url(db)
    except GmailConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except GmailConnectionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "status": "success",
        "auth_url": auth_url,
    }


@router.get("/oauth/callback", response_class=HTMLResponse)
def gmail_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    if error:
        raise HTTPException(status_code=400, detail=f"Gmail OAuth failed: {error}")

    if not code:
        raise HTTPException(status_code=400, detail="Gmail OAuth code is missing.")

    try:
        exchange_code_for_token(code, state, db)
    except GmailConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except GmailConnectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return HTMLResponse(
        """
        <html>
          <body style="font-family: system-ui, sans-serif; padding: 32px;">
            <h2>Gmail connected successfully.</h2>
            <p>You can close this tab and return to the app.</p>
          </body>
        </html>
        """
    )


@router.post("/send-draft/{email_draft_id}")
def send_one_approved_email_draft(
    email_draft_id: int,
    db: Session = Depends(get_db),
):
    email_draft = get_email_draft_or_404(email_draft_id, db)

    if email_draft.status != "approved":
        raise HTTPException(
            status_code=400,
            detail="Only approved drafts can be sent."
        )

    lead_email = clean_email(email_draft.lead.email if email_draft.lead else None)

    if not lead_email:
        mark_email_draft_failed(db, email_draft, "Lead email is missing.")
        return {
            "status": "success",
            "message": "Email draft could not be sent.",
            "data": serialize_send_result(email_draft),
        }

    if contains_blocked_placeholder(email_draft.subject, email_draft.body):
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
    result = send_approved_email_draft(db, email_draft)
    message = (
        "Email draft sent successfully"
        if result["status"] == "sent"
        else "Email draft could not be sent."
    )

    return {
        "status": "success",
        "message": message,
        "data": result,
    }


@router.post("/send-approved/campaign/{campaign_id}")
def send_approved_campaign_email_drafts(
    campaign_id: int,
    limit: int = Query(DEFAULT_SEND_LIMIT, ge=1),
    db: Session = Depends(get_db),
):
    get_campaign_or_404(campaign_id, db)

    effective_limit = min(limit, MAX_SEND_LIMIT)
    email_drafts = (
        db.query(EmailDraft)
        .options(joinedload(EmailDraft.lead))
        .filter(
            EmailDraft.campaign_id == campaign_id,
            EmailDraft.status == "approved",
        )
        .order_by(EmailDraft.created_at.asc(), EmailDraft.id.asc())
        .limit(effective_limit)
        .all()
    )

    daily_limit, sent_today, remaining_daily_capacity = get_remaining_daily_capacity(db)

    if not email_drafts:
        return {
            "status": "success",
            "message": "No approved email drafts found for this campaign",
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

    results = []
    sent_count = 0
    failed_count = 0
    skipped_count = 0
    actual_send_attempts = 0
    sendable_drafts = []

    for email_draft in email_drafts:
        has_lead_email = bool(clean_email(email_draft.lead.email if email_draft.lead else None))

        if contains_blocked_placeholder(email_draft.subject, email_draft.body):
            skipped_count += 1
            results.append({
                **serialize_send_result(email_draft),
                "error": PLACEHOLDER_SEND_ERROR,
            })
            continue

        if has_lead_email:
            sendable_drafts.append(email_draft)
            continue

        result = send_approved_email_draft(db, email_draft)
        results.append(result)
        failed_count += 1

    if remaining_daily_capacity <= 0:
        remaining_approved = count_remaining_approved(campaign_id, db)

        return {
            "status": "success",
            "message": "Gmail daily sending limit reached",
            "campaign_id": campaign_id,
            "processed": len(results),
            "sent": sent_count,
            "failed": failed_count,
            "skipped": len(sendable_drafts),
            "remaining_approved": remaining_approved,
            "daily_limit": daily_limit,
            "sent_today": sent_today,
            "results": results,
        }

    drafts_to_send = sendable_drafts[:remaining_daily_capacity]
    skipped_count += max(len(sendable_drafts) - len(drafts_to_send), 0)

    if drafts_to_send:
        ensure_gmail_ready(db)

    for index, email_draft in enumerate(drafts_to_send):
        result = send_approved_email_draft(db, email_draft)
        results.append(result)

        if result["status"] == "sent":
            sent_count += 1
        elif result["status"] == "failed":
            failed_count += 1

        actual_send_attempts += 1

        if index < len(drafts_to_send) - 1 and actual_send_attempts < remaining_daily_capacity:
            time.sleep(SEND_DELAY_SECONDS)

    remaining_approved = count_remaining_approved(campaign_id, db)

    return {
        "status": "success",
        "message": "Approved email sending completed",
        "campaign_id": campaign_id,
        "processed": len(results),
        "sent": sent_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "remaining_approved": remaining_approved,
        "daily_limit": daily_limit,
        "sent_today": sent_today + sent_count,
        "results": results,
    }
