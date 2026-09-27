from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
from app.db.models import Campaign, EmailDraft, FollowUpDraft, GmailToken, Lead, ReplyResponseDraft

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)


def count_rows(db: Session, model, *filters):
    query = db.query(func.count(model.id))

    if filters:
        query = query.filter(*filters)

    return query.scalar() or 0


def rate_percentage(numerator: int, denominator: int):
    if denominator <= 0:
        return 0.0

    return round((numerator / denominator) * 100, 1)


def serialize_campaign(campaign: Campaign):
    return {
        "id": campaign.id,
        "campaign_name": campaign.campaign_name,
        "industry": campaign.industry,
        "location": campaign.location,
        "target_role": campaign.target_role,
        "offer": campaign.offer,
        "created_at": campaign.created_at,
    }


def serialize_recent_email_draft(email_draft: EmailDraft):
    lead = email_draft.lead
    campaign = email_draft.campaign

    return {
        "id": email_draft.id,
        "campaign_id": email_draft.campaign_id,
        "lead_id": email_draft.lead_id,
        "subject": email_draft.subject,
        "status": email_draft.status,
        "sent_at": email_draft.sent_at,
        "send_error": email_draft.send_error,
        "gmail_message_id": email_draft.gmail_message_id,
        "reply_intent": email_draft.reply_intent,
        "reply_sentiment": email_draft.reply_sentiment,
        "reply_priority": email_draft.reply_priority,
        "reply_summary": email_draft.reply_summary,
        "reply_next_action": email_draft.reply_next_action,
        "reply_classified_at": email_draft.reply_classified_at,
        "created_at": email_draft.created_at,
        "campaign_name": campaign.campaign_name if campaign else None,
        "lead_company_name": lead.company_name if lead else None,
        "lead_email": lead.email if lead else None,
    }


def serialize_top_ai_lead(lead: Lead):
    campaign = lead.campaign

    return {
        "lead_id": lead.id,
        "campaign_id": lead.campaign_id,
        "company_name": lead.company_name,
        "lead_email": lead.email,
        "ai_score": lead.ai_score,
        "ai_fit_score": lead.ai_fit_score,
        "ai_contact_confidence_score": lead.ai_contact_confidence_score,
        "ai_priority": lead.ai_priority,
        "ai_qualification": lead.ai_qualification,
        "campaign_name": campaign.campaign_name if campaign else None,
    }


@router.get("/stats")
def get_dashboard_stats(db: Session = Depends(get_db)):
    emails_sent = count_rows(db, EmailDraft, EmailDraft.status.in_(("sent", "replied")))
    emails_replied = count_rows(db, EmailDraft, EmailDraft.status == "replied")
    total_classified_replies = count_rows(
        db,
        EmailDraft,
        EmailDraft.status == "replied",
        EmailDraft.reply_intent.isnot(None),
    )
    high_priority_replies = count_rows(
        db,
        EmailDraft,
        EmailDraft.status == "replied",
        EmailDraft.reply_priority == "High",
    )
    interested_replies = count_rows(
        db,
        EmailDraft,
        EmailDraft.status == "replied",
        EmailDraft.reply_intent == "Interested",
    )
    pricing_replies = count_rows(
        db,
        EmailDraft,
        EmailDraft.status == "replied",
        EmailDraft.reply_intent == "Asked for Pricing",
    )
    meeting_request_replies = count_rows(
        db,
        EmailDraft,
        EmailDraft.status == "replied",
        EmailDraft.reply_intent == "Meeting Request",
    )
    average_ai_score = (
        db.query(func.avg(Lead.ai_score))
        .filter(Lead.ai_score.isnot(None))
        .scalar()
    )
    average_research_confidence = (
        db.query(func.avg(Lead.research_confidence))
        .filter(Lead.research_confidence.isnot(None))
        .scalar()
    )
    latest_campaigns = (
        db.query(Campaign)
        .order_by(Campaign.created_at.desc(), Campaign.id.desc())
        .limit(5)
        .all()
    )
    recent_email_drafts = (
        db.query(EmailDraft)
        .options(joinedload(EmailDraft.lead), joinedload(EmailDraft.campaign))
        .order_by(EmailDraft.created_at.desc(), EmailDraft.id.desc())
        .limit(5)
        .all()
    )
    top_ai_leads = (
        db.query(Lead)
        .options(joinedload(Lead.campaign))
        .filter(Lead.ai_score.isnot(None))
        .order_by(Lead.ai_score.desc(), Lead.ai_scored_at.desc(), Lead.id.desc())
        .limit(5)
        .all()
    )

    return {
        "status": "success",
        "data": {
            "total_campaigns": count_rows(db, Campaign),
            "total_leads": count_rows(db, Lead),
            "emails_generated": count_rows(db, EmailDraft, EmailDraft.status == "generated"),
            "emails_approved": count_rows(db, EmailDraft, EmailDraft.status == "approved"),
            "emails_sent": emails_sent,
            "emails_failed": count_rows(db, EmailDraft, EmailDraft.status == "failed"),
            "emails_replied": emails_replied,
            "reply_rate": rate_percentage(emails_replied, emails_sent),
            "total_classified_replies": total_classified_replies,
            "high_priority_replies": high_priority_replies,
            "interested_replies": interested_replies,
            "pricing_replies": pricing_replies,
            "meeting_request_replies": meeting_request_replies,
            "total_followups_generated": count_rows(db, FollowUpDraft, FollowUpDraft.status == "generated"),
            "total_followups_sent": count_rows(db, FollowUpDraft, FollowUpDraft.status == "sent"),
            "total_response_drafts": count_rows(db, ReplyResponseDraft),
            "response_drafts_sent": count_rows(db, ReplyResponseDraft, ReplyResponseDraft.status == "sent"),
            "total_scored_leads": count_rows(db, Lead, Lead.ai_score.isnot(None)),
            "average_ai_score": round(float(average_ai_score), 1) if average_ai_score is not None else 0.0,
            "researched_leads": count_rows(db, Lead, Lead.research_status == "researched"),
            "research_failed": count_rows(db, Lead, Lead.research_status == "failed"),
            "average_research_confidence": round(float(average_research_confidence), 1) if average_research_confidence is not None else 0.0,
            "high_priority_leads": count_rows(db, Lead, Lead.ai_priority == "High"),
            "hot_leads": count_rows(db, Lead, Lead.ai_qualification == "Hot"),
            "gmail_connected": db.query(GmailToken.id).first() is not None,
            "latest_campaigns": [serialize_campaign(campaign) for campaign in latest_campaigns],
            "recent_email_drafts": [
                serialize_recent_email_draft(email_draft)
                for email_draft in recent_email_drafts
            ],
            "top_ai_leads": [serialize_top_ai_lead(lead) for lead in top_ai_leads],
        }
    }
