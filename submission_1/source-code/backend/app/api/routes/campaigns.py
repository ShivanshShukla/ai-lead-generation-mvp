import logging
import time
from datetime import timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db.database import SessionLocal, get_db
from app.db.models import Campaign, EmailDraft, Lead, LeadResearchJob
from app.schemas.campaign_schema import CampaignCreate
from app.services.lead_research_service import research_lead
from app.utils.time_utils import utc_now

router = APIRouter(
    prefix="/campaigns",
    tags=["Campaigns"]
)

logger = logging.getLogger(__name__)
RUNNING_RESEARCH_STATUSES = {"pending", "running"}
STALE_RESEARCH_JOB_AGE = timedelta(hours=2)
DEFAULT_RESEARCH_ASYNC_LIMIT = 100
MAX_RESEARCH_ASYNC_LIMIT = 500

@router.post("/create")
def create_campaign(campaign: CampaignCreate, db: Session = Depends(get_db)):
    new_campaign = Campaign(
        campaign_name=campaign.campaign_name,
        industry=campaign.industry,
        location=campaign.location,
        target_role=campaign.target_role,
        offer=campaign.offer,
    )

    db.add(new_campaign)
    db.commit()
    db.refresh(new_campaign)

    return {
        "status": "success",
        "message": "Campaign created successfully",
        "campaign_id": new_campaign.id
    }

@router.get("/")
def get_campaigns(db: Session = Depends(get_db)):
    campaigns = db.query(Campaign).all()

    return {
        "status": "success",
        "data": campaigns
    }


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


def count_rows(db: Session, model, *filters):
    query = db.query(func.count(model.id))

    if filters:
        query = query.filter(*filters)

    return query.scalar() or 0


def lead_needs_research_filters(campaign_id: int):
    return (
        Lead.campaign_id == campaign_id,
        Lead.research_status.in_(("not_researched", "failed")),
    )


def serialize_research_job(job: LeadResearchJob):
    total = job.total_leads or 0
    processed = job.processed or 0
    percentage = round((processed / total) * 100) if total else 0

    return {
        "job_id": job.id,
        "campaign_id": job.campaign_id,
        "status": job.status,
        "total": total,
        "total_leads": total,
        "processed": processed,
        "researched": job.researched or 0,
        "skipped": job.skipped or 0,
        "failed": job.failed or 0,
        "percentage": min(100, percentage),
        "remaining": max(total - processed, 0),
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "error": job.error,
    }


def get_research_job_or_404(job_id: int, db: Session):
    job = db.get(LeadResearchJob, job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Lead research job not found")

    return job


def mark_stale_research_jobs_failed(db: Session, campaign_id: int):
    cutoff = utc_now() - STALE_RESEARCH_JOB_AGE
    jobs = (
        db.query(LeadResearchJob)
        .filter(
            LeadResearchJob.campaign_id == campaign_id,
            LeadResearchJob.status.in_(RUNNING_RESEARCH_STATUSES),
        )
        .all()
    )
    changed = False

    for job in jobs:
        started_at = job.started_at
        if started_at and started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)

        if not started_at or started_at < cutoff:
            job.status = "failed"
            job.finished_at = utc_now()
            job.error = job.error or "Lead research stopped before completing. Start a new research job."
            changed = True

    if changed:
        db.commit()


def _run_research_job(job_id: int, campaign_id: int, limit: int):
    db = SessionLocal()
    job = None

    try:
        job = db.get(LeadResearchJob, job_id)
        if not job:
            logger.warning("Lead research job %s disappeared before it could start.", job_id)
            return

        job.status = "running"
        db.commit()

        leads = (
            db.query(Lead)
            .filter(*lead_needs_research_filters(campaign_id))
            .order_by(Lead.created_at.desc(), Lead.id.desc())
            .limit(limit)
            .all()
        )

        job.total_leads = len(leads)
        db.commit()

        if not leads:
            job.status = "completed"
            job.finished_at = utc_now()
            db.commit()
            return

        for lead in leads:
            try:
                result = research_lead(db, lead.id)
                research_status = result.get("research_status")

                if research_status == "researched":
                    job.researched = (job.researched or 0) + 1
                elif research_status == "failed":
                    job.failed = (job.failed or 0) + 1
                else:
                    job.skipped = (job.skipped or 0) + 1
            except Exception as exc:
                logger.exception("Lead research failed for lead %s in job %s", lead.id, job_id)
                job.failed = (job.failed or 0) + 1
                if not job.error:
                    job.error = str(exc)
            finally:
                job.processed = (job.processed or 0) + 1
                db.commit()
                time.sleep(1)

        job.status = "completed"
        job.finished_at = utc_now()
        db.commit()
    except Exception as exc:
        logger.exception("Lead research job %s failed", job_id)
        db.rollback()

        if job:
            job.status = "failed"
            job.error = str(exc)
            job.finished_at = utc_now()
            db.commit()
    finally:
        db.close()


@router.post("/{campaign_id}/research-leads")
def research_campaign_leads(
    campaign_id: int,
    limit: int = Query(5, ge=1),
    db: Session = Depends(get_db),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail=f"Campaign with id {campaign_id} was not found"
        )

    effective_limit = min(limit, 10)
    leads = (
        db.query(Lead)
        .filter(
            Lead.campaign_id == campaign_id,
            Lead.research_status.in_(("not_researched", "failed")),
        )
        .order_by(Lead.created_at.desc(), Lead.id.desc())
        .limit(effective_limit)
        .all()
    )
    results = []
    researched_count = 0
    failed_count = 0

    for lead in leads:
        try:
            result = research_lead(db, lead.id)
            researched_count += 1 if result.get("research_status") == "researched" else 0
            failed_count += 1 if result.get("research_status") == "failed" else 0
            results.append({
                "lead_id": lead.id,
                "company_name": lead.company_name,
                "research_status": result.get("research_status"),
                "research_confidence": result.get("research_confidence"),
                "error": result.get("research_error"),
            })
        except Exception:
            failed_count += 1
            results.append({
                "lead_id": lead.id,
                "company_name": lead.company_name,
                "research_status": "failed",
                "error": "Lead research failed. Please try again.",
            })

    return {
        "status": "success",
        "message": "Campaign lead research completed",
        "campaign_id": campaign_id,
        "processed": len(leads),
        "researched": researched_count,
        "failed": failed_count,
        "remaining": count_rows(
            db,
            Lead,
            Lead.campaign_id == campaign_id,
            Lead.research_status.in_(("not_researched", "failed")),
        ),
        "results": results,
    }


@router.post("/{campaign_id}/research-leads-async")
def research_campaign_leads_async(
    campaign_id: int,
    background_tasks: BackgroundTasks,
    limit: int = Query(default=DEFAULT_RESEARCH_ASYNC_LIMIT, ge=1, le=MAX_RESEARCH_ASYNC_LIMIT),
    db: Session = Depends(get_db),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail=f"Campaign with id {campaign_id} was not found"
        )

    mark_stale_research_jobs_failed(db, campaign_id)

    running_job = (
        db.query(LeadResearchJob)
        .filter(
            LeadResearchJob.campaign_id == campaign_id,
            LeadResearchJob.status.in_(RUNNING_RESEARCH_STATUSES),
        )
        .order_by(LeadResearchJob.started_at.desc(), LeadResearchJob.id.desc())
        .first()
    )

    if running_job:
        return {
            "status": running_job.status,
            "message": "Lead research is already running for this campaign.",
            "poll_url": f"/api/campaigns/research-job/{running_job.id}",
            **serialize_research_job(running_job),
        }

    total = db.query(Lead).filter(*lead_needs_research_filters(campaign_id)).count()

    if total == 0:
        return {
            "job_id": None,
            "campaign_id": campaign_id,
            "message": "No leads need research.",
            "total": 0,
            "total_leads": 0,
            "processed": 0,
            "researched": 0,
            "skipped": 0,
            "failed": 0,
            "percentage": 100,
            "remaining": 0,
            "status": "nothing_to_do",
        }

    actual_limit = min(limit, total)
    job = LeadResearchJob(
        campaign_id=campaign_id,
        status="running",
        total_leads=actual_limit,
        processed=0,
        researched=0,
        skipped=0,
        failed=0,
        error=None,
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(
        _run_research_job,
        job_id=job.id,
        campaign_id=campaign_id,
        limit=actual_limit,
    )

    return {
        "status": "running",
        "message": f"Lead research started for {actual_limit} leads.",
        "poll_url": f"/api/campaigns/research-job/{job.id}",
        **serialize_research_job(job),
    }


@router.get("/research-job/{job_id}")
def get_campaign_research_job(job_id: int, db: Session = Depends(get_db)):
    job = get_research_job_or_404(job_id, db)
    return serialize_research_job(job)


@router.get("/{campaign_id}/summary")
def get_campaign_summary(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail=f"Campaign with id {campaign_id} was not found"
        )

    return {
        "status": "success",
        "data": {
            "campaign": serialize_campaign(campaign),
            "lead_count": count_rows(db, Lead, Lead.campaign_id == campaign_id),
            "researched_leads": count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.research_status == "researched"),
            "research_failed": count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.research_status == "failed"),
            "average_research_confidence": round(
                float(
                    db.query(func.avg(Lead.research_confidence))
                    .filter(
                        Lead.campaign_id == campaign_id,
                        Lead.research_confidence.isnot(None),
                    )
                    .scalar() or 0
                ),
                1,
            ),
            "emails_found": count_rows(
                db,
                Lead,
                Lead.campaign_id == campaign_id,
                Lead.email.isnot(None),
                Lead.email != "",
            ),
            "draft_count": count_rows(db, EmailDraft, EmailDraft.campaign_id == campaign_id),
            "generated_count": count_rows(
                db,
                EmailDraft,
                EmailDraft.campaign_id == campaign_id,
                EmailDraft.status == "generated",
            ),
            "approved_count": count_rows(
                db,
                EmailDraft,
                EmailDraft.campaign_id == campaign_id,
                EmailDraft.status == "approved",
            ),
            "sent_count": count_rows(
                db,
                EmailDraft,
                EmailDraft.campaign_id == campaign_id,
                EmailDraft.status.in_(("sent", "replied")),
            ),
            "failed_count": count_rows(
                db,
                EmailDraft,
                EmailDraft.campaign_id == campaign_id,
                EmailDraft.status == "failed",
            ),
            "replied_count": count_rows(
                db,
                EmailDraft,
                EmailDraft.campaign_id == campaign_id,
                EmailDraft.status == "replied",
            ),
        }
    }
