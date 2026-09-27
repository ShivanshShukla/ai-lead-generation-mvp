from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.db.models import Campaign, EmailDraft, Lead
from app.services.ai_service import AIConfigurationError, AIServiceError, generate_cold_email

router = APIRouter(
    prefix="/ai",
    tags=["AI"]
)

ACTIVE_DRAFT_STATUSES = ("generated", "approved", "sending", "sent", "replied")
DEFAULT_CAMPAIGN_GENERATION_LIMIT = 5
MAX_CAMPAIGN_GENERATION_LIMIT = 10


def serialize_email_draft(email_draft: EmailDraft):
    lead = email_draft.lead

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
    }


def get_lead_or_404(lead_id: int, db: Session):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()

    if not lead:
        raise HTTPException(
            status_code=404,
            detail=f"Lead with id {lead_id} was not found"
        )

    return lead


def get_campaign_or_404(campaign_id: int, db: Session):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail=f"Campaign with id {campaign_id} was not found"
        )

    return campaign


def get_existing_active_draft_for_lead(lead_id: int, db: Session):
    return (
        db.query(EmailDraft)
        .filter(
            EmailDraft.lead_id == lead_id,
            EmailDraft.status.in_(ACTIVE_DRAFT_STATUSES),
        )
        .order_by(EmailDraft.created_at.desc(), EmailDraft.id.desc())
        .first()
    )


def create_email_draft(campaign: Campaign, lead: Lead, db: Session):
    generated_email = generate_cold_email(campaign, lead, db=db)

    email_draft = EmailDraft(
        campaign_id=campaign.id,
        lead_id=lead.id,
        subject=generated_email["subject"],
        body=generated_email["body"],
        status="generated",
        ai_model=settings.GEMINI_MODEL,
    )

    db.add(email_draft)
    db.commit()
    db.refresh(email_draft)

    return email_draft


@router.post("/generate-email/{lead_id}")
def generate_email_for_lead(
    lead_id: int,
    force: bool = Query(False),
    db: Session = Depends(get_db)
):
    lead = get_lead_or_404(lead_id, db)

    campaign = lead.campaign or db.query(Campaign).filter(Campaign.id == lead.campaign_id).first()

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail=f"Campaign with id {lead.campaign_id} was not found"
        )

    if not force:
        existing_email_draft = get_existing_active_draft_for_lead(lead.id, db)

        if existing_email_draft:
            return {
                "status": "success",
                "message": "Existing email draft returned",
                "email_draft": serialize_email_draft(existing_email_draft)
            }

    try:
        email_draft = create_email_draft(campaign, lead, db)
    except AIConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except AIServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Email draft could not be saved."
        ) from exc

    return {
        "status": "success",
        "message": "Email generated successfully",
        "email_draft": serialize_email_draft(email_draft)
    }


@router.post("/generate-emails/campaign/{campaign_id}")
def generate_emails_for_campaign(
    campaign_id: int,
    limit: int = Query(DEFAULT_CAMPAIGN_GENERATION_LIMIT, ge=1),
    force: bool = Query(False),
    db: Session = Depends(get_db)
):
    campaign = get_campaign_or_404(campaign_id, db)
    effective_limit = min(limit, MAX_CAMPAIGN_GENERATION_LIMIT)

    leads = (
        db.query(Lead)
        .filter(Lead.campaign_id == campaign_id)
        .order_by(Lead.created_at.desc())
        .all()
    )

    if not leads:
        return {
            "status": "success",
            "message": "No leads found for this campaign",
            "campaign_id": campaign_id,
            "total_leads": 0,
            "processed": 0,
            "generated": 0,
            "skipped": 0,
            "failed": 0,
            "remaining": 0,
            "limit": effective_limit,
            "results": []
        }

    existing_active_lead_ids = set()

    if not force:
        existing_active_lead_ids = {
            lead_id
            for (lead_id,) in (
                db.query(EmailDraft.lead_id)
                .filter(
                    EmailDraft.campaign_id == campaign_id,
                    EmailDraft.status.in_(ACTIVE_DRAFT_STATUSES)
                )
                .all()
            )
        }

    pending_leads = []
    skipped_count = 0
    results = []

    for lead in leads:
        if not force and lead.id in existing_active_lead_ids:
            skipped_count += 1
            results.append({
                "lead_id": lead.id,
                "company_name": lead.company_name,
                "skipped": True,
                "reason": "Active email draft already exists"
            })
            continue

        pending_leads.append(lead)

    leads_to_process = pending_leads[:effective_limit]
    remaining_count = max(len(pending_leads) - len(leads_to_process), 0)

    if leads_to_process and not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API key is not configured.")

    generated_count = 0
    failed_count = 0

    for lead in leads_to_process:
        if not lead.company_name:
            skipped_count += 1
            results.append({
                "lead_id": lead.id,
                "company_name": lead.company_name,
                "skipped": True,
                "reason": "Missing company name"
            })
            continue

        try:
            email_draft = create_email_draft(campaign, lead, db)
            generated_count += 1
            results.append({
                "lead_id": lead.id,
                "company_name": lead.company_name,
                "email_draft_id": email_draft.id,
                "subject": email_draft.subject
            })
        except AIConfigurationError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except AIServiceError as exc:
            failed_count += 1
            results.append({
                "lead_id": lead.id,
                "company_name": lead.company_name,
                "failed": True,
                "error": str(exc)
            })
        except SQLAlchemyError:
            db.rollback()
            failed_count += 1
            results.append({
                "lead_id": lead.id,
                "company_name": lead.company_name,
                "failed": True,
                "error": "Email draft could not be saved."
            })

    return {
        "status": "success",
        "message": "Campaign email generation completed",
        "campaign_id": campaign_id,
        "total_leads": len(leads),
        "processed": len(leads_to_process),
        "generated": generated_count,
        "skipped": skipped_count,
        "failed": failed_count,
        "remaining": remaining_count,
        "limit": effective_limit,
        "results": results
    }
