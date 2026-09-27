from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Opportunity
from app.schemas.opportunity_schema import (
    OpportunityCreateDiscoveryJobRequest,
    OpportunityConvertToCampaignRequest,
    OpportunityCreate,
    OpportunityGenerateRequest,
    OpportunityUpdate,
)
from app.services.opportunity_service import (
    OpportunityServiceError,
    VALID_OPPORTUNITY_STATUSES,
    convert_opportunity_to_campaign,
    create_discovery_job_from_opportunity,
    generate_opportunity_strategy,
)
from app.utils.time_utils import utc_now

router = APIRouter(
    prefix="/opportunities",
    tags=["Opportunities"],
)


def clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


def nullable_text(value):
    text = clean_text(value)
    return text or None


def get_opportunity_or_404(opportunity_id: int, db: Session):
    opportunity = db.get(Opportunity, opportunity_id)

    if not opportunity:
        raise HTTPException(
            status_code=404,
            detail=f"Opportunity with id {opportunity_id} was not found",
        )

    return opportunity


def serialize_opportunity(opportunity: Opportunity):
    return {
        "id": opportunity.id,
        "title": opportunity.title,
        "raw_goal": opportunity.raw_goal,
        "target_domain": opportunity.target_domain,
        "target_location": opportunity.target_location,
        "offer": opportunity.offer,
        "status": opportunity.status,
        "ai_summary": opportunity.ai_summary,
        "target_audience": opportunity.target_audience,
        "ideal_roles": opportunity.ideal_roles,
        "industries": opportunity.industries,
        "locations": opportunity.locations,
        "pain_points": opportunity.pain_points,
        "value_proposition": opportunity.value_proposition,
        "outreach_angle": opportunity.outreach_angle,
        "search_keywords": opportunity.search_keywords,
        "lead_source_ideas": opportunity.lead_source_ideas,
        "email_script": opportunity.email_script,
        "call_script": opportunity.call_script,
        "follow_up_sequence": opportunity.follow_up_sequence,
        "qualification_criteria": opportunity.qualification_criteria,
        "risk_flags": opportunity.risk_flags,
        "suggested_campaign_name": opportunity.suggested_campaign_name,
        "suggested_campaign_industry": opportunity.suggested_campaign_industry,
        "suggested_campaign_location": opportunity.suggested_campaign_location,
        "suggested_campaign_target_role": opportunity.suggested_campaign_target_role,
        "suggested_campaign_offer": opportunity.suggested_campaign_offer,
        "suggested_discovery_target_type": opportunity.suggested_discovery_target_type,
        "suggested_discovery_department": opportunity.suggested_discovery_department,
        "suggested_discovery_role": opportunity.suggested_discovery_role,
        "suggested_discovery_queries": opportunity.suggested_discovery_queries,
        "ai_model": opportunity.ai_model,
        "created_at": opportunity.created_at,
        "updated_at": opportunity.updated_at,
        "converted_campaign_id": opportunity.converted_campaign_id,
    }


def save_opportunity(db: Session, opportunity: Opportunity, error_message: str):
    try:
        db.add(opportunity)
        db.commit()
        db.refresh(opportunity)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=error_message) from exc


@router.get("/")
def list_opportunities(db: Session = Depends(get_db)):
    opportunities = (
        db.query(Opportunity)
        .filter(Opportunity.status != "archived")
        .order_by(Opportunity.created_at.desc(), Opportunity.id.desc())
        .all()
    )

    return {
        "status": "success",
        "data": [serialize_opportunity(opportunity) for opportunity in opportunities],
    }


@router.post("/")
def create_opportunity(payload: OpportunityCreate, db: Session = Depends(get_db)):
    title = clean_text(payload.title)
    raw_goal = clean_text(payload.raw_goal)

    if not title:
        raise HTTPException(status_code=400, detail="Title is required.")

    if not raw_goal:
        raise HTTPException(status_code=400, detail="Raw goal is required.")

    opportunity = Opportunity(
        title=title[:255],
        raw_goal=raw_goal,
        target_domain=nullable_text(payload.target_domain),
        target_location=nullable_text(payload.target_location),
        offer=nullable_text(payload.offer),
        status="draft",
    )
    save_opportunity(db, opportunity, "Opportunity could not be created.")

    return {
        "status": "success",
        "message": "Opportunity created successfully",
        "data": serialize_opportunity(opportunity),
    }


@router.get("/{opportunity_id}")
def get_opportunity(opportunity_id: int, db: Session = Depends(get_db)):
    opportunity = get_opportunity_or_404(opportunity_id, db)

    return {
        "status": "success",
        "data": serialize_opportunity(opportunity),
    }


@router.patch("/{opportunity_id}")
def update_opportunity(opportunity_id: int, payload: OpportunityUpdate, db: Session = Depends(get_db)):
    opportunity = get_opportunity_or_404(opportunity_id, db)
    update_data = payload.model_dump(exclude_unset=True)

    if "title" in update_data:
        title = clean_text(update_data["title"])
        if not title:
            raise HTTPException(status_code=400, detail="Title cannot be empty.")
        opportunity.title = title[:255]

    if "raw_goal" in update_data:
        raw_goal = clean_text(update_data["raw_goal"])
        if not raw_goal:
            raise HTTPException(status_code=400, detail="Raw goal cannot be empty.")
        opportunity.raw_goal = raw_goal

    if "target_domain" in update_data:
        opportunity.target_domain = nullable_text(update_data["target_domain"])
    if "target_location" in update_data:
        opportunity.target_location = nullable_text(update_data["target_location"])
    if "offer" in update_data:
        opportunity.offer = nullable_text(update_data["offer"])

    if "status" in update_data:
        status = clean_text(update_data["status"]).lower()
        if status not in VALID_OPPORTUNITY_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid opportunity status.")
        opportunity.status = status

    opportunity.updated_at = utc_now()
    save_opportunity(db, opportunity, "Opportunity could not be updated.")

    return {
        "status": "success",
        "message": "Opportunity updated successfully",
        "data": serialize_opportunity(opportunity),
    }


@router.delete("/{opportunity_id}")
def archive_opportunity(opportunity_id: int, db: Session = Depends(get_db)):
    opportunity = get_opportunity_or_404(opportunity_id, db)
    opportunity.status = "archived"
    opportunity.updated_at = utc_now()
    save_opportunity(db, opportunity, "Opportunity could not be archived.")

    return {
        "status": "success",
        "message": "Opportunity archived successfully",
    }


@router.post("/{opportunity_id}/generate")
def generate_opportunity(
    opportunity_id: int,
    payload: OpportunityGenerateRequest | None = None,
    db: Session = Depends(get_db),
):
    opportunity = get_opportunity_or_404(opportunity_id, db)

    if opportunity.status == "generated" and payload and not payload.force:
        return {
            "status": "success",
            "message": "Existing strategy returned",
            "data": serialize_opportunity(opportunity),
        }

    try:
        generated_opportunity = generate_opportunity_strategy(db, opportunity_id)
    except OpportunityServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Opportunity strategy generation failed. Please try again.") from exc

    return {
        "status": "success",
        "message": "Opportunity strategy generated successfully",
        "data": serialize_opportunity(generated_opportunity),
    }


@router.post("/{opportunity_id}/convert-to-campaign")
def convert_to_campaign(
    opportunity_id: int,
    payload: OpportunityConvertToCampaignRequest | None = None,
    db: Session = Depends(get_db),
):
    opportunity = get_opportunity_or_404(opportunity_id, db)

    try:
        campaign, already_converted = convert_opportunity_to_campaign(
            db,
            opportunity,
            force_new=bool(payload.force_new) if payload else False,
        )
    except OpportunityServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Campaign could not be created from opportunity.") from exc

    return {
        "status": "success",
        "message": "Campaign already exists for this opportunity" if already_converted else "Campaign created from opportunity",
        "opportunity_id": opportunity.id,
        "campaign_id": campaign.id,
        "already_converted": already_converted,
    }


@router.post("/{opportunity_id}/create-discovery-job")
def create_discovery_job(
    opportunity_id: int,
    payload: OpportunityCreateDiscoveryJobRequest | None = None,
    db: Session = Depends(get_db),
):
    opportunity = get_opportunity_or_404(opportunity_id, db)

    try:
        job = create_discovery_job_from_opportunity(
            db,
            opportunity,
            campaign_id=payload.campaign_id if payload else None,
        )
    except OpportunityServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Discovery job could not be created from opportunity.") from exc

    return {
        "status": "success",
        "message": "Lead discovery job created from opportunity",
        "opportunity_id": opportunity.id,
        "discovery_job_id": job.id,
    }
