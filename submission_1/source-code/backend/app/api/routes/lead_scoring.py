import logging
import time
from datetime import timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.db.database import SessionLocal, get_db
from app.db.models import Campaign, Lead, LeadScoringJob
from app.services.lead_scoring_service import score_lead_safely, score_lead_with_ai
from app.utils.time_utils import utc_now

router = APIRouter(
    prefix="/lead-scoring",
    tags=["Lead Scoring"]
)

DEFAULT_SCORE_LIMIT = 5
MAX_SCORE_LIMIT = 10
DEFAULT_ASYNC_SCORE_LIMIT = 10
MAX_ASYNC_SCORE_LIMIT = 100
RUNNING_SCORING_STATUSES = {"pending", "running"}
STALE_SCORING_JOB_AGE = timedelta(hours=2)
SCORING_JOB_DELAY_SECONDS = 1

logger = logging.getLogger(__name__)


def get_campaign_or_404(campaign_id: int, db: Session):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail=f"Campaign with id {campaign_id} was not found"
        )

    return campaign


def get_lead_or_404(lead_id: int, db: Session):
    lead = (
        db.query(Lead)
        .options(joinedload(Lead.campaign))
        .filter(Lead.id == lead_id)
        .first()
    )

    if not lead:
        raise HTTPException(
            status_code=404,
            detail=f"Lead with id {lead_id} was not found"
        )

    return lead


def serialize_scored_lead(lead: Lead):
    campaign = lead.campaign

    return {
        "id": lead.id,
        "lead_id": lead.id,
        "campaign_id": lead.campaign_id,
        "campaign_name": campaign.campaign_name if campaign else None,
        "company_name": lead.company_name,
        "website": lead.website,
        "industry": lead.industry,
        "location": lead.location,
        "contact_name": lead.contact_name,
        "contact_role": lead.contact_role,
        "email": lead.email,
        "source": lead.source,
        "status": lead.status,
        "ai_score": lead.ai_score,
        "ai_fit_score": lead.ai_fit_score,
        "ai_contact_confidence_score": lead.ai_contact_confidence_score,
        "ai_priority": lead.ai_priority,
        "ai_qualification": lead.ai_qualification,
        "ai_score_reason": lead.ai_score_reason,
        "ai_contact_confidence_reason": lead.ai_contact_confidence_reason,
        "ai_outreach_angle": lead.ai_outreach_angle,
        "ai_pain_point": lead.ai_pain_point,
        "ai_recommended_cta": lead.ai_recommended_cta,
        "ai_final_priority_reason": lead.ai_final_priority_reason,
        "ai_scored_at": lead.ai_scored_at,
        "ai_model_used": lead.ai_model_used,
        "ai_score_error": lead.ai_score_error,
        "research_status": lead.research_status,
        "research_summary": lead.research_summary,
        "research_outreach_angle": lead.research_outreach_angle,
        "research_risk_flags": lead.research_risk_flags,
        "research_confidence": lead.research_confidence,
        "research_used_fallback": lead.research_used_fallback,
        "researched_at": lead.researched_at,
        "created_at": lead.created_at,
    }


def serialize_score_result(lead: Lead):
    return {
        "lead_id": lead.id,
        "ai_score": lead.ai_score,
        "ai_fit_score": lead.ai_fit_score,
        "ai_contact_confidence_score": lead.ai_contact_confidence_score,
        "ai_priority": lead.ai_priority,
        "ai_qualification": lead.ai_qualification,
        "ai_score_reason": lead.ai_score_reason,
        "ai_contact_confidence_reason": lead.ai_contact_confidence_reason,
        "ai_outreach_angle": lead.ai_outreach_angle,
        "ai_pain_point": lead.ai_pain_point,
        "ai_recommended_cta": lead.ai_recommended_cta,
        "ai_final_priority_reason": lead.ai_final_priority_reason,
        "ai_scored_at": lead.ai_scored_at,
        "ai_model_used": lead.ai_model_used,
        "ai_score_error": lead.ai_score_error,
        "research_status": lead.research_status,
        "research_summary": lead.research_summary,
        "research_outreach_angle": lead.research_outreach_angle,
        "research_risk_flags": lead.research_risk_flags,
        "research_confidence": lead.research_confidence,
        "research_used_fallback": lead.research_used_fallback,
        "researched_at": lead.researched_at,
    }


def count_rows(db: Session, model, *filters):
    query = db.query(func.count(model.id))

    if filters:
        query = query.filter(*filters)

    return query.scalar() or 0


def serialize_scoring_job(job: LeadScoringJob):
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
        "scored": job.scored or 0,
        "skipped": job.skipped or 0,
        "failed": job.failed or 0,
        "percentage": min(100, percentage),
        "remaining": max(total - processed, 0),
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "error": job.error,
        "force": bool(job.force),
    }


def get_scoring_job_or_404(job_id: int, db: Session):
    job = db.get(LeadScoringJob, job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Lead scoring job not found")

    return job


def mark_stale_scoring_jobs_failed(db: Session, campaign_id: int):
    cutoff = utc_now() - STALE_SCORING_JOB_AGE
    jobs = (
        db.query(LeadScoringJob)
        .filter(
            LeadScoringJob.campaign_id == campaign_id,
            LeadScoringJob.status.in_(RUNNING_SCORING_STATUSES),
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
            job.error = job.error or "Lead scoring stopped before completing. Start a new scoring job."
            changed = True

    if changed:
        db.commit()


def build_scoring_query(db: Session, campaign_id: int, force: bool):
    query = (
        db.query(Lead)
        .filter(Lead.campaign_id == campaign_id)
        .order_by(Lead.created_at.desc(), Lead.id.desc())
    )

    if not force:
        query = query.filter(Lead.ai_score.is_(None))

    return query


def _run_scoring_job(job_id: int, campaign_id: int, limit: int, force: bool):
    db = SessionLocal()
    job = None

    try:
        job = db.get(LeadScoringJob, job_id)
        if not job:
            logger.warning("Lead scoring job %s disappeared before it could start.", job_id)
            return

        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            job.status = "failed"
            job.error = f"Campaign with id {campaign_id} was not found"
            job.finished_at = utc_now()
            db.commit()
            return

        job.status = "running"
        db.commit()

        leads = build_scoring_query(db, campaign_id, force).limit(limit).all()
        job.total_leads = len(leads)
        db.commit()

        if not leads:
            job.status = "completed"
            job.finished_at = utc_now()
            db.commit()
            return

        for lead in leads:
            try:
                result = score_lead_safely(db, lead, campaign, force=force)

                if result.get("failed"):
                    job.failed = (job.failed or 0) + 1
                elif result.get("created"):
                    job.scored = (job.scored or 0) + 1
                else:
                    job.skipped = (job.skipped or 0) + 1
            except Exception as exc:
                logger.exception("Lead scoring failed for lead %s in job %s", lead.id, job_id)
                job.failed = (job.failed or 0) + 1
                if not job.error:
                    job.error = str(exc)
            finally:
                job.processed = (job.processed or 0) + 1
                db.commit()
                time.sleep(SCORING_JOB_DELAY_SECONDS)

        job.status = "completed"
        job.finished_at = utc_now()
        db.commit()
    except Exception as exc:
        logger.exception("Lead scoring job %s failed", job_id)
        db.rollback()

        if job:
            job.status = "failed"
            job.error = str(exc)
            job.finished_at = utc_now()
            db.commit()
    finally:
        db.close()


@router.post("/score/{lead_id}")
def score_one_lead(
    lead_id: int,
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    lead = get_lead_or_404(lead_id, db)
    campaign = lead.campaign or get_campaign_or_404(lead.campaign_id, db)

    try:
        result = score_lead_with_ai(db, lead, campaign, force=force)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="AI lead scoring failed. Please try again."
        )

    return {
        "status": "success",
        "message": "Lead scored successfully",
        "data": result["data"],
    }


@router.post("/score-campaign-async/{campaign_id}")
def score_campaign_leads_async(
    campaign_id: int,
    background_tasks: BackgroundTasks,
    limit: int = Query(DEFAULT_ASYNC_SCORE_LIMIT, ge=1, le=MAX_ASYNC_SCORE_LIMIT),
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    get_campaign_or_404(campaign_id, db)
    mark_stale_scoring_jobs_failed(db, campaign_id)

    running_job = (
        db.query(LeadScoringJob)
        .filter(
            LeadScoringJob.campaign_id == campaign_id,
            LeadScoringJob.status.in_(RUNNING_SCORING_STATUSES),
        )
        .order_by(LeadScoringJob.started_at.desc(), LeadScoringJob.id.desc())
        .first()
    )

    if running_job:
        return {
            "status": running_job.status,
            "message": "Lead scoring is already running for this campaign.",
            "poll_url": f"/api/lead-scoring/scoring-job/{running_job.id}",
            **serialize_scoring_job(running_job),
        }

    total = build_scoring_query(db, campaign_id, force).count()

    if total == 0:
        return {
            "job_id": None,
            "campaign_id": campaign_id,
            "message": "No leads need scoring." if not force else "This campaign has no leads to score.",
            "total": 0,
            "total_leads": 0,
            "processed": 0,
            "scored": 0,
            "skipped": 0,
            "failed": 0,
            "percentage": 100,
            "remaining": 0,
            "remaining_unscored": count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.ai_score.is_(None)),
            "status": "nothing_to_do",
            "force": force,
        }

    actual_limit = min(limit, total)
    job = LeadScoringJob(
        campaign_id=campaign_id,
        status="running",
        total_leads=actual_limit,
        processed=0,
        scored=0,
        skipped=0,
        failed=0,
        error=None,
        force=force,
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(
        _run_scoring_job,
        job_id=job.id,
        campaign_id=campaign_id,
        limit=actual_limit,
        force=force,
    )

    return {
        "status": "running",
        "message": f"Lead scoring started for {actual_limit} leads.",
        "poll_url": f"/api/lead-scoring/scoring-job/{job.id}",
        "remaining_unscored": count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.ai_score.is_(None)),
        **serialize_scoring_job(job),
    }


@router.get("/scoring-job/{job_id}")
def get_scoring_job(job_id: int, db: Session = Depends(get_db)):
    job = get_scoring_job_or_404(job_id, db)
    return {
        **serialize_scoring_job(job),
        "remaining_unscored": count_rows(db, Lead, Lead.campaign_id == job.campaign_id, Lead.ai_score.is_(None)),
    }


@router.post("/score-campaign/{campaign_id}")
def score_campaign_leads(
    campaign_id: int,
    limit: int = Query(DEFAULT_SCORE_LIMIT, ge=1),
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    campaign = get_campaign_or_404(campaign_id, db)
    effective_limit = min(limit, MAX_SCORE_LIMIT)
    query = (
        db.query(Lead)
        .filter(Lead.campaign_id == campaign_id)
        .order_by(Lead.created_at.desc(), Lead.id.desc())
    )

    if not force:
        query = query.filter(Lead.ai_score.is_(None))

    candidate_leads = query.all()
    leads_to_process = candidate_leads[:effective_limit]

    if not leads_to_process:
        return {
            "status": "success",
            "message": "No unscored leads found" if not force else "This campaign has no leads to score",
            "campaign_id": campaign_id,
            "processed": 0,
            "scored": 0,
            "skipped": 0,
            "failed": 0,
            "remaining_unscored": count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.ai_score.is_(None)),
            "results": [],
        }

    results = []
    scored_count = 0
    skipped_count = 0
    failed_count = 0

    for lead in leads_to_process:
        result = score_lead_safely(db, lead, campaign, force=force)

        if result.get("failed"):
            failed_count += 1
        elif result.get("created"):
            scored_count += 1
        else:
            skipped_count += 1

        results.append({
            "lead_id": lead.id,
            "company_name": lead.company_name,
            "scored": bool(result.get("created")),
            "failed": bool(result.get("failed")),
            "message": result.get("message"),
            "data": result.get("data"),
        })

    return {
        "status": "success",
        "message": (
            "Lead scoring completed with some failures"
            if failed_count
            else "Campaign lead scoring completed"
        ),
        "campaign_id": campaign_id,
        "processed": len(leads_to_process),
        "scored": scored_count,
        "skipped": skipped_count,
        "failed": failed_count,
        "remaining_unscored": count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.ai_score.is_(None)),
        "results": results,
    }


@router.get("/campaign/{campaign_id}")
def get_campaign_scored_leads(
    campaign_id: int,
    priority: str | None = None,
    qualification: str | None = None,
    min_score: int | None = Query(None, ge=0, le=100),
    max_score: int | None = Query(None, ge=0, le=100),
    db: Session = Depends(get_db),
):
    get_campaign_or_404(campaign_id, db)
    query = (
        db.query(Lead)
        .options(joinedload(Lead.campaign))
        .filter(
            Lead.campaign_id == campaign_id,
            Lead.ai_score.isnot(None),
        )
    )

    if priority:
        query = query.filter(Lead.ai_priority == priority)
    if qualification:
        query = query.filter(Lead.ai_qualification == qualification)
    if min_score is not None:
        query = query.filter(Lead.ai_score >= min_score)
    if max_score is not None:
        query = query.filter(Lead.ai_score <= max_score)

    leads = (
        query
        .order_by(Lead.ai_score.desc(), Lead.ai_scored_at.desc(), Lead.id.desc())
        .all()
    )

    return {
        "status": "success",
        "data": [serialize_scored_lead(lead) for lead in leads],
    }


@router.get("/campaign/{campaign_id}/summary")
def get_campaign_lead_scoring_summary(
    campaign_id: int,
    db: Session = Depends(get_db),
):
    get_campaign_or_404(campaign_id, db)
    total_leads = count_rows(db, Lead, Lead.campaign_id == campaign_id)
    scored_leads = count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.ai_score.isnot(None))
    researched_leads = count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.research_status == "researched")
    research_failed = count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.research_status == "failed")
    average_score = (
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
    top_leads = (
        db.query(Lead)
        .options(joinedload(Lead.campaign))
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
            "campaign_id": campaign_id,
            "total_leads": total_leads,
            "scored_leads": scored_leads,
            "unscored_leads": max(total_leads - scored_leads, 0),
            "average_score": round(float(average_score), 1) if average_score is not None else 0.0,
            "researched_leads": researched_leads,
            "research_failed": research_failed,
            "average_research_confidence": round(float(average_research_confidence), 1) if average_research_confidence is not None else 0.0,
            "high_priority": count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.ai_priority == "High"),
            "medium_priority": count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.ai_priority == "Medium"),
            "low_priority": count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.ai_priority == "Low"),
            "hot": count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.ai_qualification == "Hot"),
            "warm": count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.ai_qualification == "Warm"),
            "cold": count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.ai_qualification == "Cold"),
            "not_relevant": count_rows(db, Lead, Lead.campaign_id == campaign_id, Lead.ai_qualification == "Not Relevant"),
            "top_leads": [serialize_scored_lead(lead) for lead in top_leads],
        },
    }
