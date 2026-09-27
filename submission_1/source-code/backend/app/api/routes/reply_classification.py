from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
from app.db.models import Campaign, EmailDraft
from app.services.reply_classification_service import (
    ReplyClassificationError,
    ReplyClassificationRuleError,
    classify_reply_for_draft,
)

router = APIRouter(
    prefix="/reply-classification",
    tags=["Reply Classification"]
)

DEFAULT_CLASSIFICATION_LIMIT = 5
MAX_CLASSIFICATION_LIMIT = 10


def get_email_draft_or_404(email_draft_id: int, db: Session):
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


def get_campaign_or_404(campaign_id: int, db: Session):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail=f"Campaign with id {campaign_id} was not found"
        )

    return campaign


def count_rows(db: Session, model, *filters):
    query = db.query(func.count(model.id))

    if filters:
        query = query.filter(*filters)

    return query.scalar() or 0


def is_classified_filter():
    return EmailDraft.reply_intent.isnot(None)


def is_unclassified_filter():
    return EmailDraft.reply_intent.is_(None)


def serialize_classified_reply(email_draft: EmailDraft):
    lead = email_draft.lead

    return {
        "email_draft_id": email_draft.id,
        "campaign_id": email_draft.campaign_id,
        "lead_id": email_draft.lead_id,
        "lead_company_name": lead.company_name if lead else None,
        "lead_contact_name": lead.contact_name if lead else None,
        "lead_contact_role": lead.contact_role if lead else None,
        "lead_email": lead.email if lead else None,
        "subject": email_draft.subject,
        "status": email_draft.status,
        "reply_snippet": email_draft.reply_snippet,
        "replied_at": email_draft.replied_at,
        "reply_intent": email_draft.reply_intent,
        "reply_sentiment": email_draft.reply_sentiment,
        "reply_priority": email_draft.reply_priority,
        "reply_summary": email_draft.reply_summary,
        "reply_next_action": email_draft.reply_next_action,
        "reply_suggested_response_direction": email_draft.reply_suggested_response_direction,
        "reply_classified_at": email_draft.reply_classified_at,
        "reply_classification_model": email_draft.reply_classification_model,
        "reply_classification_error": email_draft.reply_classification_error,
    }


def build_classification_response(email_draft: EmailDraft):
    return {
        "email_draft_id": email_draft.id,
        "reply_intent": email_draft.reply_intent,
        "reply_sentiment": email_draft.reply_sentiment,
        "reply_priority": email_draft.reply_priority,
        "reply_summary": email_draft.reply_summary,
        "reply_next_action": email_draft.reply_next_action,
        "reply_suggested_response_direction": email_draft.reply_suggested_response_direction,
    }


def count_intent(db: Session, campaign_id: int, intent: str):
    return count_rows(
        db,
        EmailDraft,
        EmailDraft.campaign_id == campaign_id,
        EmailDraft.status == "replied",
        EmailDraft.reply_intent == intent,
    )


@router.post("/classify/{email_draft_id}")
def classify_email_draft_reply(
    email_draft_id: int,
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    email_draft = get_email_draft_or_404(email_draft_id, db)

    try:
        classify_reply_for_draft(db, email_draft, force=force)
    except ReplyClassificationRuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ReplyClassificationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "status": "success",
        "message": "Reply classified successfully",
        "data": build_classification_response(email_draft),
    }


@router.post("/classify-campaign/{campaign_id}")
def classify_campaign_replies(
    campaign_id: int,
    limit: int = Query(DEFAULT_CLASSIFICATION_LIMIT, ge=1),
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    get_campaign_or_404(campaign_id, db)
    effective_limit = min(limit, MAX_CLASSIFICATION_LIMIT)
    filters = [
        EmailDraft.campaign_id == campaign_id,
        EmailDraft.status == "replied",
    ]

    if not force:
        filters.append(is_unclassified_filter())

    email_drafts = (
        db.query(EmailDraft)
        .options(
            joinedload(EmailDraft.campaign),
            joinedload(EmailDraft.lead),
            joinedload(EmailDraft.follow_up_drafts),
        )
        .filter(*filters)
        .order_by(
            case((EmailDraft.reply_classified_at.is_(None), 0), else_=1),
            EmailDraft.replied_at.desc(),
            EmailDraft.updated_at.desc(),
            EmailDraft.id.desc(),
        )
        .limit(effective_limit)
        .all()
    )

    results = []
    classified_count = 0
    skipped_count = 0
    failed_count = 0

    for email_draft in email_drafts:
        try:
            classify_reply_for_draft(db, email_draft, force=force)
            classified_count += 1
            results.append({
                **build_classification_response(email_draft),
                "status": "classified",
            })
        except ReplyClassificationRuleError as exc:
            skipped_count += 1
            results.append({
                "email_draft_id": email_draft.id,
                "status": "skipped",
                "error": str(exc),
            })
        except Exception as exc:
            failed_count += 1
            results.append({
                "email_draft_id": email_draft.id,
                "status": "failed",
                "error": str(exc) or "Reply classification failed.",
            })

    remaining_unclassified = count_rows(
        db,
        EmailDraft,
        EmailDraft.campaign_id == campaign_id,
        EmailDraft.status == "replied",
        is_unclassified_filter(),
    )

    return {
        "status": "success",
        "message": "Campaign reply classification completed",
        "campaign_id": campaign_id,
        "processed": len(email_drafts),
        "classified": classified_count,
        "skipped": skipped_count,
        "failed": failed_count,
        "remaining_unclassified": remaining_unclassified,
        "results": results,
    }


@router.get("/campaign/{campaign_id}")
def get_campaign_classified_replies(
    campaign_id: int,
    intent: str | None = None,
    priority: str | None = None,
    sentiment: str | None = None,
    db: Session = Depends(get_db),
):
    get_campaign_or_404(campaign_id, db)
    filters = [
        EmailDraft.campaign_id == campaign_id,
        EmailDraft.status == "replied",
        is_classified_filter(),
    ]

    if intent:
        filters.append(EmailDraft.reply_intent == intent)
    if priority:
        filters.append(EmailDraft.reply_priority == priority)
    if sentiment:
        filters.append(EmailDraft.reply_sentiment == sentiment)

    email_drafts = (
        db.query(EmailDraft)
        .options(joinedload(EmailDraft.lead))
        .filter(*filters)
        .order_by(EmailDraft.reply_classified_at.desc(), EmailDraft.replied_at.desc(), EmailDraft.id.desc())
        .all()
    )

    return {
        "status": "success",
        "data": [serialize_classified_reply(email_draft) for email_draft in email_drafts],
    }


@router.get("/campaign/{campaign_id}/summary")
def get_campaign_reply_classification_summary(
    campaign_id: int,
    db: Session = Depends(get_db),
):
    get_campaign_or_404(campaign_id, db)
    total_replies = count_rows(
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
        is_classified_filter(),
    )
    top_replies = (
        db.query(EmailDraft)
        .options(joinedload(EmailDraft.lead))
        .filter(
            EmailDraft.campaign_id == campaign_id,
            EmailDraft.status == "replied",
            is_classified_filter(),
        )
        .order_by(
            case((EmailDraft.reply_priority == "High", 0), (EmailDraft.reply_priority == "Medium", 1), else_=2),
            EmailDraft.reply_classified_at.desc(),
            EmailDraft.replied_at.desc(),
            EmailDraft.id.desc(),
        )
        .limit(5)
        .all()
    )

    return {
        "status": "success",
        "data": {
            "campaign_id": campaign_id,
            "total_replies": total_replies,
            "classified_replies": classified_replies,
            "unclassified_replies": max(total_replies - classified_replies, 0),
            "high_priority_replies": count_rows(
                db,
                EmailDraft,
                EmailDraft.campaign_id == campaign_id,
                EmailDraft.status == "replied",
                EmailDraft.reply_priority == "High",
            ),
            "interested_count": count_intent(db, campaign_id, "Interested"),
            "pricing_count": count_intent(db, campaign_id, "Asked for Pricing"),
            "meeting_request_count": count_intent(db, campaign_id, "Meeting Request"),
            "not_interested_count": count_intent(db, campaign_id, "Not Interested"),
            "unsubscribe_count": count_intent(db, campaign_id, "Unsubscribe"),
            "wrong_person_count": count_intent(db, campaign_id, "Wrong Person"),
            "out_of_office_count": count_intent(db, campaign_id, "Out of Office"),
            "top_replies": [serialize_classified_reply(email_draft) for email_draft in top_replies],
        }
    }
