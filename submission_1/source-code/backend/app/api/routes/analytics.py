from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
from app.db.models import Campaign, EmailDraft, FollowUpDraft, Lead, ReplyResponseDraft

router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"]
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


def serialize_recent_reply(email_draft: EmailDraft):
    lead = email_draft.lead

    return {
        "email_draft_id": email_draft.id,
        "lead_id": email_draft.lead_id,
        "company_name": lead.company_name if lead else None,
        "lead_email": lead.email if lead else None,
        "reply_snippet": email_draft.reply_snippet,
        "replied_at": email_draft.replied_at,
        "reply_intent": email_draft.reply_intent,
        "reply_sentiment": email_draft.reply_sentiment,
        "reply_priority": email_draft.reply_priority,
        "reply_summary": email_draft.reply_summary,
        "reply_next_action": email_draft.reply_next_action,
        "reply_suggested_response_direction": email_draft.reply_suggested_response_direction,
        "reply_classified_at": email_draft.reply_classified_at,
    }


def serialize_recent_follow_up(follow_up: FollowUpDraft):
    lead = follow_up.lead

    return {
        "follow_up_id": follow_up.id,
        "original_email_draft_id": follow_up.original_email_draft_id,
        "lead_id": follow_up.lead_id,
        "company_name": lead.company_name if lead else None,
        "lead_email": lead.email if lead else None,
        "follow_up_number": follow_up.follow_up_number,
        "status": follow_up.status,
        "sent_at": follow_up.sent_at,
    }


def serialize_top_ai_lead(lead: Lead):
    return {
        "lead_id": lead.id,
        "company_name": lead.company_name,
        "lead_email": lead.email,
        "ai_score": lead.ai_score,
        "ai_fit_score": lead.ai_fit_score,
        "ai_contact_confidence_score": lead.ai_contact_confidence_score,
        "ai_priority": lead.ai_priority,
        "ai_qualification": lead.ai_qualification,
        "ai_score_reason": lead.ai_score_reason,
        "ai_contact_confidence_reason": lead.ai_contact_confidence_reason,
        "ai_final_priority_reason": lead.ai_final_priority_reason,
    }


@router.get("/campaign/{campaign_id}")
def get_campaign_analytics(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail=f"Campaign with id {campaign_id} was not found"
        )

    lead_count = count_rows(db, Lead, Lead.campaign_id == campaign_id)
    draft_count = count_rows(db, EmailDraft, EmailDraft.campaign_id == campaign_id)
    generated_count = count_rows(
        db,
        EmailDraft,
        EmailDraft.campaign_id == campaign_id,
        EmailDraft.status == "generated",
    )
    approved_count = count_rows(
        db,
        EmailDraft,
        EmailDraft.campaign_id == campaign_id,
        EmailDraft.status == "approved",
    )
    rejected_count = count_rows(
        db,
        EmailDraft,
        EmailDraft.campaign_id == campaign_id,
        EmailDraft.status == "rejected",
    )
    sent_count = count_rows(
        db,
        EmailDraft,
        EmailDraft.campaign_id == campaign_id,
        EmailDraft.status.in_(("sent", "replied")),
    )
    failed_count = count_rows(
        db,
        EmailDraft,
        EmailDraft.campaign_id == campaign_id,
        EmailDraft.status == "failed",
    )
    replied_count = count_rows(
        db,
        EmailDraft,
        EmailDraft.campaign_id == campaign_id,
        EmailDraft.status == "replied",
    )
    classified_replies = count_rows(
        db,
        EmailDraft,
        EmailDraft.campaign_id == campaign_id,
        EmailDraft.status == "replied",
        EmailDraft.reply_intent.isnot(None),
    )
    high_priority_replies = count_rows(
        db,
        EmailDraft,
        EmailDraft.campaign_id == campaign_id,
        EmailDraft.status == "replied",
        EmailDraft.reply_priority == "High",
    )
    interested_replies = count_rows(
        db,
        EmailDraft,
        EmailDraft.campaign_id == campaign_id,
        EmailDraft.status == "replied",
        EmailDraft.reply_intent == "Interested",
    )
    pricing_replies = count_rows(
        db,
        EmailDraft,
        EmailDraft.campaign_id == campaign_id,
        EmailDraft.status == "replied",
        EmailDraft.reply_intent == "Asked for Pricing",
    )
    meeting_request_replies = count_rows(
        db,
        EmailDraft,
        EmailDraft.campaign_id == campaign_id,
        EmailDraft.status == "replied",
        EmailDraft.reply_intent == "Meeting Request",
    )
    not_interested_replies = count_rows(
        db,
        EmailDraft,
        EmailDraft.campaign_id == campaign_id,
        EmailDraft.status == "replied",
        EmailDraft.reply_intent == "Not Interested",
    )
    unsubscribe_replies = count_rows(
        db,
        EmailDraft,
        EmailDraft.campaign_id == campaign_id,
        EmailDraft.status == "replied",
        EmailDraft.reply_intent == "Unsubscribe",
    )
    wrong_person_replies = count_rows(
        db,
        EmailDraft,
        EmailDraft.campaign_id == campaign_id,
        EmailDraft.status == "replied",
        EmailDraft.reply_intent == "Wrong Person",
    )
    out_of_office_replies = count_rows(
        db,
        EmailDraft,
        EmailDraft.campaign_id == campaign_id,
        EmailDraft.status == "replied",
        EmailDraft.reply_intent == "Out of Office",
    )
    needs_follow_up_count = count_rows(
        db,
        EmailDraft,
        EmailDraft.campaign_id == campaign_id,
        EmailDraft.status == "sent",
    )
    recent_replies = (
        db.query(EmailDraft)
        .options(joinedload(EmailDraft.lead))
        .filter(
            EmailDraft.campaign_id == campaign_id,
            EmailDraft.status == "replied",
        )
        .order_by(EmailDraft.replied_at.desc(), EmailDraft.updated_at.desc(), EmailDraft.id.desc())
        .limit(5)
        .all()
    )
    followups_generated_count = count_rows(
        db,
        FollowUpDraft,
        FollowUpDraft.campaign_id == campaign_id,
        FollowUpDraft.status == "generated",
    )
    followups_approved_count = count_rows(
        db,
        FollowUpDraft,
        FollowUpDraft.campaign_id == campaign_id,
        FollowUpDraft.status == "approved",
    )
    followups_sent_count = count_rows(
        db,
        FollowUpDraft,
        FollowUpDraft.campaign_id == campaign_id,
        FollowUpDraft.status == "sent",
    )
    followups_failed_count = count_rows(
        db,
        FollowUpDraft,
        FollowUpDraft.campaign_id == campaign_id,
        FollowUpDraft.status == "failed",
    )
    followups_pending_count = count_rows(
        db,
        FollowUpDraft,
        FollowUpDraft.campaign_id == campaign_id,
        FollowUpDraft.status.in_(("generated", "approved", "sending")),
    )
    response_drafts_generated = count_rows(
        db,
        ReplyResponseDraft,
        ReplyResponseDraft.campaign_id == campaign_id,
        ReplyResponseDraft.status == "generated",
    )
    response_drafts_approved = count_rows(
        db,
        ReplyResponseDraft,
        ReplyResponseDraft.campaign_id == campaign_id,
        ReplyResponseDraft.status == "approved",
    )
    response_drafts_sent = count_rows(
        db,
        ReplyResponseDraft,
        ReplyResponseDraft.campaign_id == campaign_id,
        ReplyResponseDraft.status == "sent",
    )
    response_drafts_failed = count_rows(
        db,
        ReplyResponseDraft,
        ReplyResponseDraft.campaign_id == campaign_id,
        ReplyResponseDraft.status == "failed",
    )
    recent_followups = (
        db.query(FollowUpDraft)
        .options(joinedload(FollowUpDraft.lead))
        .filter(FollowUpDraft.campaign_id == campaign_id)
        .order_by(FollowUpDraft.created_at.desc(), FollowUpDraft.id.desc())
        .limit(5)
        .all()
    )
    scored_leads = count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.ai_score.isnot(None))
    researched_leads = count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.research_status == "researched")
    research_failed = count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.research_status == "failed")
    average_ai_score = (
        db.query(func.avg(Lead.ai_score))
        .filter(
            Lead.campaign_id == campaign_id,
            Lead.ai_score.isnot(None),
        )
        .scalar()
    )
    average_research_confidence = (
        db.query(func.avg(Lead.research_confidence))
        .filter(
            Lead.campaign_id == campaign_id,
            Lead.research_confidence.isnot(None),
        )
        .scalar()
    )
    top_ai_leads = (
        db.query(Lead)
        .filter(
            Lead.campaign_id == campaign_id,
            Lead.ai_score.isnot(None),
        )
        .order_by(Lead.ai_score.desc(), Lead.ai_scored_at.desc(), Lead.id.desc())
        .limit(5)
        .all()
    )

    return {
        "status": "success",
        "data": {
            "campaign_id": campaign.id,
            "campaign_name": campaign.campaign_name,
            "lead_count": lead_count,
            "draft_count": draft_count,
            "generated_count": generated_count,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "sent_count": sent_count,
            "failed_count": failed_count,
            "replied_count": replied_count,
            "classified_replies": classified_replies,
            "high_priority_replies": high_priority_replies,
            "interested_replies": interested_replies,
            "pricing_replies": pricing_replies,
            "meeting_request_replies": meeting_request_replies,
            "not_interested_replies": not_interested_replies,
            "unsubscribe_replies": unsubscribe_replies,
            "wrong_person_replies": wrong_person_replies,
            "out_of_office_replies": out_of_office_replies,
            "reply_rate": rate_percentage(replied_count, sent_count),
            "send_success_rate": rate_percentage(sent_count, sent_count + failed_count),
            "needs_follow_up_count": needs_follow_up_count,
            "followups_generated_count": followups_generated_count,
            "followups_approved_count": followups_approved_count,
            "followups_sent_count": followups_sent_count,
            "followups_failed_count": followups_failed_count,
            "followups_pending_count": followups_pending_count,
            "response_drafts_generated": response_drafts_generated,
            "response_drafts_approved": response_drafts_approved,
            "response_drafts_sent": response_drafts_sent,
            "response_drafts_failed": response_drafts_failed,
            "scored_leads": scored_leads,
            "unscored_leads": max(lead_count - scored_leads, 0),
            "average_ai_score": round(float(average_ai_score), 1) if average_ai_score is not None else 0.0,
            "researched_leads": researched_leads,
            "research_failed": research_failed,
            "average_research_confidence": round(float(average_research_confidence), 1) if average_research_confidence is not None else 0.0,
            "high_priority_leads": count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.ai_priority == "High"),
            "medium_priority_leads": count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.ai_priority == "Medium"),
            "low_priority_leads": count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.ai_priority == "Low"),
            "hot_leads": count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.ai_qualification == "Hot"),
            "warm_leads": count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.ai_qualification == "Warm"),
            "cold_leads": count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.ai_qualification == "Cold"),
            "not_relevant_leads": count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.ai_qualification == "Not Relevant"),
            "top_ai_leads": [
                serialize_top_ai_lead(lead)
                for lead in top_ai_leads
            ],
            "recent_replies": [
                serialize_recent_reply(email_draft)
                for email_draft in recent_replies
            ],
            "recent_followups": [
                serialize_recent_follow_up(follow_up)
                for follow_up in recent_followups
            ],
        }
    }
