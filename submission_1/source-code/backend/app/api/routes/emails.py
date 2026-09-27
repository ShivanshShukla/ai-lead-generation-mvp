from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
from app.db.models import EmailDraft
from app.schemas.email_schema import EmailDraftContentUpdate, EmailDraftUpdate
from app.utils.time_utils import utc_now

router = APIRouter(
    prefix="/emails",
    tags=["Email Drafts"]
)

ALLOWED_EMAIL_STATUSES = {"generated", "approved", "rejected", "failed", "replied"}
EDITABLE_EMAIL_STATUSES = {"generated", "approved", "failed"}
MAX_EMAIL_BODY_LENGTH = 10000


def serialize_email_draft(email_draft: EmailDraft):
    lead = email_draft.lead
    call_log = email_draft.call_log

    return {
        "id": email_draft.id,
        "campaign_id": email_draft.campaign_id,
        "lead_id": email_draft.lead_id,
        "call_log_id": email_draft.call_log_id,
        "subject": email_draft.subject,
        "body": email_draft.body,
        "status": email_draft.status,
        "source_type": email_draft.source_type,
        "knowledge_used": email_draft.knowledge_used,
        "ai_model": email_draft.ai_model,
        "sent_at": email_draft.sent_at,
        "send_error": email_draft.send_error,
        "gmail_message_id": email_draft.gmail_message_id,
        "reply_checked_at": email_draft.reply_checked_at,
        "reply_message_id": email_draft.reply_message_id,
        "reply_snippet": email_draft.reply_snippet,
        "replied_at": email_draft.replied_at,
        "reply_intent": email_draft.reply_intent,
        "reply_sentiment": email_draft.reply_sentiment,
        "reply_priority": email_draft.reply_priority,
        "reply_next_action": email_draft.reply_next_action,
        "reply_summary": email_draft.reply_summary,
        "reply_suggested_response_direction": email_draft.reply_suggested_response_direction,
        "reply_classified_at": email_draft.reply_classified_at,
        "reply_classification_model": email_draft.reply_classification_model,
        "reply_classification_error": email_draft.reply_classification_error,
        "created_at": email_draft.created_at,
        "lead_company_name": lead.company_name if lead else None,
        "lead_contact_name": lead.contact_name if lead else None,
        "lead_contact_role": lead.contact_role if lead else None,
        "lead_email": lead.email if lead else None,
        "lead_ai_score": lead.ai_score if lead else None,
        "lead_ai_fit_score": lead.ai_fit_score if lead else None,
        "lead_ai_contact_confidence_score": lead.ai_contact_confidence_score if lead else None,
        "lead_ai_priority": lead.ai_priority if lead else None,
        "lead_ai_qualification": lead.ai_qualification if lead else None,
        "call_created_at": call_log.created_at if call_log else None,
        "call_started_at": call_log.started_at if call_log else None,
        "call_outcome": call_log.outcome if call_log else None,
    }


def email_draft_query(db: Session):
    return db.query(EmailDraft).options(joinedload(EmailDraft.lead), joinedload(EmailDraft.call_log))


@router.get("/")
def get_email_drafts(db: Session = Depends(get_db)):
    email_drafts = (
        email_draft_query(db)
        .order_by(EmailDraft.created_at.desc())
        .all()
    )

    return {
        "status": "success",
        "data": [serialize_email_draft(email_draft) for email_draft in email_drafts]
    }


@router.get("/campaign/{campaign_id}")
def get_campaign_email_drafts(campaign_id: int, db: Session = Depends(get_db)):
    email_drafts = (
        email_draft_query(db)
        .filter(EmailDraft.campaign_id == campaign_id)
        .order_by(EmailDraft.created_at.desc())
        .all()
    )

    return {
        "status": "success",
        "data": [serialize_email_draft(email_draft) for email_draft in email_drafts]
    }


@router.get("/lead/{lead_id}")
def get_lead_email_drafts(lead_id: int, db: Session = Depends(get_db)):
    email_drafts = (
        email_draft_query(db)
        .filter(EmailDraft.lead_id == lead_id)
        .order_by(EmailDraft.created_at.desc())
        .all()
    )

    return {
        "status": "success",
        "data": [serialize_email_draft(email_draft) for email_draft in email_drafts]
    }


@router.patch("/{email_id}")
def update_email_draft_content(
    email_id: int,
    email_update: EmailDraftContentUpdate,
    db: Session = Depends(get_db),
):
    subject = (email_update.subject or "").strip()
    body = (email_update.body or "").strip()

    if not subject or not body:
        raise HTTPException(status_code=400, detail="Subject and body are required.")

    if len(body) > MAX_EMAIL_BODY_LENGTH:
        raise HTTPException(status_code=400, detail="Email body is too long.")

    email_draft = (
        email_draft_query(db)
        .filter(EmailDraft.id == email_id)
        .first()
    )

    if not email_draft:
        raise HTTPException(
            status_code=404,
            detail=f"Email draft with id {email_id} was not found"
        )

    if email_draft.status not in EDITABLE_EMAIL_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="Cannot edit a sent draft."
        )

    email_draft.subject = subject[:255]
    email_draft.body = body
    email_draft.updated_at = utc_now()

    if email_draft.status in {"approved", "failed"}:
        email_draft.status = "generated"
        email_draft.send_error = None

    try:
        db.commit()
        db.refresh(email_draft)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to update draft. Please try again."
        ) from exc

    return {
        "status": "success",
        "message": "Email draft updated successfully",
        "data": serialize_email_draft(email_draft)
    }


@router.patch("/{email_id}/status")
def update_email_draft_status(
    email_id: int,
    email_update: EmailDraftUpdate,
    db: Session = Depends(get_db)
):
    if email_update.status not in ALLOWED_EMAIL_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="Status must be one of: generated, approved, rejected, failed, replied"
        )

    email_draft = (
        email_draft_query(db)
        .filter(EmailDraft.id == email_id)
        .first()
    )

    if not email_draft:
        raise HTTPException(
            status_code=404,
            detail=f"Email draft with id {email_id} was not found"
        )

    if email_draft.status in {"sending", "sent", "replied"}:
        raise HTTPException(
            status_code=400,
            detail="Sending, sent, or replied email drafts cannot be manually updated."
        )

    if email_update.status == "replied":
        raise HTTPException(
            status_code=400,
            detail="Use reply checking to mark sent drafts as replied."
        )

    email_draft.status = email_update.status

    try:
        db.commit()
        db.refresh(email_draft)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Email status could not be updated."
        ) from exc

    return {
        "status": "success",
        "message": "Email status updated successfully",
        "data": serialize_email_draft(email_draft)
    }
