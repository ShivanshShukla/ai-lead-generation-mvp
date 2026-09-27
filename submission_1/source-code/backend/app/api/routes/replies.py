from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
from app.db.models import Campaign, EmailDraft
from app.services.gmail_service import (
    GmailConfigurationError,
    GmailConnectionError,
    GmailPermissionError,
    check_reply_for_draft,
)

router = APIRouter(
    prefix="/replies",
    tags=["Replies"]
)

DEFAULT_REPLY_CHECK_LIMIT = 5
MAX_REPLY_CHECK_LIMIT = 10
REPLY_CHECKABLE_STATUSES = ("sent", "replied")


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


def handle_reply_check_error(exc: Exception):
    if isinstance(exc, GmailConfigurationError):
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if isinstance(exc, (GmailPermissionError, GmailConnectionError)):
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    raise HTTPException(status_code=500, detail="Reply check failed. Please try again.") from exc


def serialize_campaign_reply_result(email_draft: EmailDraft, result: dict):
    lead = email_draft.lead

    return {
        "email_draft_id": email_draft.id,
        "lead_id": email_draft.lead_id,
        "lead_email": lead.email if lead else None,
        "replied": bool(result.get("replied")),
        "reply_snippet": result.get("reply_snippet"),
    }


@router.post("/check-draft/{email_draft_id}")
def check_email_draft_reply(
    email_draft_id: int,
    db: Session = Depends(get_db),
):
    email_draft = get_email_draft_or_404(email_draft_id, db)

    if email_draft.status not in REPLY_CHECKABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="Only sent drafts can be checked for replies."
        )

    try:
        result = check_reply_for_draft(db, email_draft)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        handle_reply_check_error(exc)

    return {
        "status": "success",
        "message": "Reply check completed",
        "email_draft_id": email_draft.id,
        "replied": bool(result.get("replied")),
        "reply_snippet": result.get("reply_snippet"),
    }


@router.post("/check-campaign/{campaign_id}")
def check_campaign_replies(
    campaign_id: int,
    limit: int = Query(DEFAULT_REPLY_CHECK_LIMIT, ge=1),
    db: Session = Depends(get_db),
):
    get_campaign_or_404(campaign_id, db)
    effective_limit = min(limit, MAX_REPLY_CHECK_LIMIT)
    eligible_filters = (
        EmailDraft.campaign_id == campaign_id,
        EmailDraft.status.in_(REPLY_CHECKABLE_STATUSES),
    )
    eligible_count = (
        db.query(func.count(EmailDraft.id))
        .filter(*eligible_filters)
        .scalar()
        or 0
    )
    email_drafts = (
        db.query(EmailDraft)
        .options(joinedload(EmailDraft.lead))
        .filter(*eligible_filters)
        .order_by(
            case((EmailDraft.reply_checked_at.is_(None), 0), else_=1),
            EmailDraft.reply_checked_at.asc(),
            EmailDraft.sent_at.asc(),
            EmailDraft.id.asc(),
        )
        .limit(effective_limit)
        .all()
    )

    results = []
    replied_count = 0
    no_reply_count = 0
    failed_count = 0

    for email_draft in email_drafts:
        try:
            result = check_reply_for_draft(db, email_draft)
        except ValueError:
            failed_count += 1
            results.append({
                "email_draft_id": email_draft.id,
                "lead_id": email_draft.lead_id,
                "lead_email": email_draft.lead.email if email_draft.lead else None,
                "replied": False,
                "error": "Only sent drafts can be checked for replies.",
            })
            continue
        except Exception as exc:
            handle_reply_check_error(exc)

        if result.get("replied"):
            replied_count += 1
        else:
            no_reply_count += 1

        results.append(serialize_campaign_reply_result(email_draft, result))

    return {
        "status": "success",
        "message": "Campaign reply check completed",
        "campaign_id": campaign_id,
        "processed": len(email_drafts),
        "replied": replied_count,
        "no_reply": no_reply_count,
        "failed": failed_count,
        "remaining_to_check": max(eligible_count - len(email_drafts), 0),
        "results": results,
    }
