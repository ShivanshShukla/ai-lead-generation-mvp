from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
from app.db.models import Campaign, DiscoveredLead, DiscoveryJob, Opportunity
from app.schemas.discovery_schema import (
    DiscoveryImportRequest,
    DiscoveryJobCreate,
    DiscoveryJobUpdate,
    DiscoveryQueryGenerateRequest,
    DiscoveryResultUpdate,
    DiscoverySelectionRequest,
)
from app.services.lead_discovery_service import (
    IMPORTED_RESULT_STATUSES,
    LeadDiscoveryError,
    VALID_JOB_STATUSES,
    VALID_RESULT_STATUSES,
    VALID_SOURCE_MODES,
    VALID_TARGET_TYPES,
    approve_or_reject_results,
    generate_search_queries,
    import_selected_results,
    research_imported_leads,
    run_discovery_job,
)
from app.utils.time_utils import utc_now

router = APIRouter(
    prefix="/discovery",
    tags=["Lead Discovery"],
)


def clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


def nullable_text(value):
    text = clean_text(value)
    return text or None


def normalize_limit(value):
    try:
        return max(1, min(int(value or 20), 50))
    except (TypeError, ValueError):
        return 20


def get_job_or_404(job_id: int, db: Session):
    job = (
        db.query(DiscoveryJob)
        .options(
            joinedload(DiscoveryJob.campaign),
            joinedload(DiscoveryJob.opportunity),
        )
        .filter(DiscoveryJob.id == job_id)
        .first()
    )

    if not job:
        raise HTTPException(status_code=404, detail=f"Discovery job with id {job_id} was not found")

    return job


def get_result_or_404(result_id: int, db: Session):
    result = db.query(DiscoveredLead).filter(DiscoveredLead.id == result_id).first()

    if not result:
        raise HTTPException(status_code=404, detail=f"Discovery result with id {result_id} was not found")

    return result


def validate_optional_refs(db: Session, campaign_id: int | None, opportunity_id: int | None):
    if campaign_id and not db.get(Campaign, campaign_id):
        raise HTTPException(status_code=404, detail=f"Campaign with id {campaign_id} was not found")

    if opportunity_id and not db.get(Opportunity, opportunity_id):
        raise HTTPException(status_code=404, detail=f"Opportunity with id {opportunity_id} was not found")


def serialize_job(job: DiscoveryJob):
    return {
        "id": job.id,
        "opportunity_id": job.opportunity_id,
        "campaign_id": job.campaign_id,
        "campaign_name": job.campaign.campaign_name if job.campaign else None,
        "opportunity_title": job.opportunity.title if job.opportunity else None,
        "title": job.title,
        "target_type": job.target_type,
        "department": job.department,
        "location": job.location,
        "target_role": job.target_role,
        "query_goal": job.query_goal,
        "source_mode": job.source_mode,
        "source_urls": job.source_urls,
        "generated_queries": job.generated_queries,
        "status": job.status,
        "limit": job.limit,
        "pages_attempted": job.pages_attempted,
        "contacts_found": job.contacts_found,
        "errors": job.errors,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def serialize_result(result: DiscoveredLead):
    return {
        "id": result.id,
        "discovery_job_id": result.discovery_job_id,
        "campaign_id": result.campaign_id,
        "name": result.name,
        "organization": result.organization,
        "department": result.department,
        "designation": result.designation,
        "email": result.email,
        "phone": result.phone,
        "website": result.website,
        "profile_url": result.profile_url,
        "source_url": result.source_url,
        "lead_type": result.lead_type,
        "location": result.location,
        "confidence": result.confidence,
        "fit_reason": result.fit_reason,
        "risk_flags": result.risk_flags,
        "raw_context": result.raw_context,
        "status": result.status,
        "imported_lead_id": result.imported_lead_id,
        "created_at": result.created_at,
        "updated_at": result.updated_at,
    }


def save_job(db: Session, job: DiscoveryJob, error_message: str):
    try:
        db.add(job)
        db.commit()
        db.refresh(job)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=error_message) from exc


@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db)):
    jobs = (
        db.query(DiscoveryJob)
        .options(joinedload(DiscoveryJob.campaign), joinedload(DiscoveryJob.opportunity))
        .order_by(DiscoveryJob.created_at.desc(), DiscoveryJob.id.desc())
        .all()
    )

    return {
        "status": "success",
        "data": [serialize_job(job) for job in jobs],
    }


@router.post("/jobs")
def create_job(payload: DiscoveryJobCreate, db: Session = Depends(get_db)):
    title = clean_text(payload.title)
    if not title:
        raise HTTPException(status_code=400, detail="Title is required.")

    validate_optional_refs(db, payload.campaign_id, payload.opportunity_id)

    target_type = clean_text(payload.target_type).lower() or None
    if target_type and target_type not in VALID_TARGET_TYPES:
        target_type = "general"

    source_mode = clean_text(payload.source_mode).lower() or "manual_urls"
    if source_mode not in VALID_SOURCE_MODES:
        source_mode = "manual_urls"

    job = DiscoveryJob(
        opportunity_id=payload.opportunity_id,
        campaign_id=payload.campaign_id,
        title=title[:255],
        target_type=target_type,
        department=nullable_text(payload.department),
        location=nullable_text(payload.location),
        target_role=nullable_text(payload.target_role),
        query_goal=nullable_text(payload.query_goal),
        source_mode=source_mode,
        source_urls=nullable_text(payload.source_urls),
        generated_queries=nullable_text(payload.generated_queries),
        limit=normalize_limit(payload.limit),
        status="draft",
    )
    save_job(db, job, "Discovery job could not be created.")

    return {
        "status": "success",
        "message": "Discovery job created successfully",
        "data": serialize_job(get_job_or_404(job.id, db)),
    }


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = get_job_or_404(job_id, db)

    return {
        "status": "success",
        "data": serialize_job(job),
    }


@router.patch("/jobs/{job_id}")
def update_job(job_id: int, payload: DiscoveryJobUpdate, db: Session = Depends(get_db)):
    job = get_job_or_404(job_id, db)
    update_data = payload.model_dump(exclude_unset=True)

    if "campaign_id" in update_data or "opportunity_id" in update_data:
        validate_optional_refs(
            db,
            update_data.get("campaign_id", job.campaign_id),
            update_data.get("opportunity_id", job.opportunity_id),
        )

    if "title" in update_data:
        title = clean_text(update_data["title"])
        if not title:
            raise HTTPException(status_code=400, detail="Title cannot be empty.")
        job.title = title[:255]

    for field_name in ("opportunity_id", "campaign_id"):
        if field_name in update_data:
            setattr(job, field_name, update_data[field_name])

    for field_name in ("department", "location", "target_role", "query_goal", "source_urls", "generated_queries"):
        if field_name in update_data:
            setattr(job, field_name, nullable_text(update_data[field_name]))

    if "target_type" in update_data:
        target_type = clean_text(update_data["target_type"]).lower()
        job.target_type = target_type if target_type in VALID_TARGET_TYPES else "general"

    if "source_mode" in update_data:
        source_mode = clean_text(update_data["source_mode"]).lower()
        job.source_mode = source_mode if source_mode in VALID_SOURCE_MODES else "manual_urls"

    if "status" in update_data:
        status = clean_text(update_data["status"]).lower()
        if status not in VALID_JOB_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid discovery job status.")
        job.status = status

    if "limit" in update_data:
        job.limit = normalize_limit(update_data["limit"])

    job.updated_at = utc_now()
    save_job(db, job, "Discovery job could not be updated.")

    return {
        "status": "success",
        "message": "Discovery job updated successfully",
        "data": serialize_job(get_job_or_404(job.id, db)),
    }


@router.post("/generate-queries")
def generate_queries(payload: DiscoveryQueryGenerateRequest):
    queries = generate_search_queries(payload.model_dump())

    return {
        "status": "success",
        "message": "Search queries generated successfully",
        "queries": queries,
    }


@router.post("/jobs/{job_id}/generate-queries")
def generate_queries_for_job(job_id: int, db: Session = Depends(get_db)):
    job = get_job_or_404(job_id, db)
    queries = generate_search_queries({
        "title": job.title,
        "target_type": job.target_type,
        "department": job.department,
        "location": job.location,
        "target_role": job.target_role,
        "query_goal": job.query_goal,
    })
    job.generated_queries = "\n".join(queries)
    job.source_mode = "generated_queries"
    job.updated_at = utc_now()
    save_job(db, job, "Generated queries could not be saved.")

    return {
        "status": "success",
        "message": "Search queries generated successfully",
        "queries": queries,
        "data": serialize_job(get_job_or_404(job.id, db)),
    }


@router.post("/jobs/{job_id}/run")
def run_job(job_id: int, db: Session = Depends(get_db)):
    try:
        result = run_discovery_job(db, job_id)
    except LeadDiscoveryError as exc:
        raise HTTPException(status_code=500, detail=str(exc) or "Discovery failed. Please try again.") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Discovery failed. Please try again.") from exc

    return {
        "status": "success",
        "message": "Discovery run completed",
        **result,
    }


@router.get("/jobs/{job_id}/results")
def get_results(job_id: int, db: Session = Depends(get_db)):
    get_job_or_404(job_id, db)
    results = (
        db.query(DiscoveredLead)
        .filter(DiscoveredLead.discovery_job_id == job_id)
        .order_by(DiscoveredLead.created_at.desc(), DiscoveredLead.id.desc())
        .all()
    )

    return {
        "status": "success",
        "data": [serialize_result(result) for result in results],
    }


@router.patch("/results/{result_id}")
def update_result(result_id: int, payload: DiscoveryResultUpdate, db: Session = Depends(get_db)):
    result = get_result_or_404(result_id, db)

    if payload.status is not None:
        status = clean_text(payload.status).lower()
        if status not in VALID_RESULT_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid discovery result status.")
        if result.status not in IMPORTED_RESULT_STATUSES:
            result.status = status

    result.updated_at = utc_now()

    try:
        db.commit()
        db.refresh(result)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Discovery result could not be updated.") from exc

    return {
        "status": "success",
        "message": "Discovery result updated successfully",
        "data": serialize_result(result),
    }


@router.post("/jobs/{job_id}/approve-selected")
def approve_selected(job_id: int, payload: DiscoverySelectionRequest, db: Session = Depends(get_db)):
    get_job_or_404(job_id, db)
    count = approve_or_reject_results(db, payload.result_ids, "approved")

    return {
        "status": "success",
        "message": "Selected contacts approved",
        "updated": count,
    }


@router.post("/jobs/{job_id}/reject-selected")
def reject_selected(job_id: int, payload: DiscoverySelectionRequest, db: Session = Depends(get_db)):
    get_job_or_404(job_id, db)
    count = approve_or_reject_results(db, payload.result_ids, "rejected")

    return {
        "status": "success",
        "message": "Selected contacts rejected",
        "updated": count,
    }


@router.post("/jobs/{job_id}/import-selected")
def import_selected(job_id: int, payload: DiscoveryImportRequest, db: Session = Depends(get_db)):
    try:
        result = import_selected_results(db, job_id, payload.result_ids, payload.allow_no_email)
    except LeadDiscoveryError as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "Discovered leads could not be imported.") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Discovered leads could not be imported.") from exc

    return {
        "status": "success",
        "message": "Import completed",
        **result,
    }


@router.post("/jobs/{job_id}/research-imported")
def research_imported(
    job_id: int,
    limit: int = Query(5, ge=1),
    db: Session = Depends(get_db),
):
    get_job_or_404(job_id, db)
    result = research_imported_leads(db, job_id, limit=limit)

    return {
        "status": "success",
        "message": "Imported lead research completed",
        **result,
    }
