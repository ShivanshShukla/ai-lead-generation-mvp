"""
Apollo.io API routes for lead email enrichment.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.database import get_db
from app.db.models import Lead
from app.services import apollo_service

router = APIRouter(prefix="/apollo", tags=["Apollo"])


class BulkApolloRequest(BaseModel):
    campaign_id: int
    limit: int = 20


@router.get("/status")
def apollo_status():
    """Check if Apollo is configured."""
    return {
        "configured": apollo_service.is_configured(),
        "message": "Apollo.io configured" if apollo_service.is_configured() 
                   else "Apollo.io not configured — set APOLLO_API_KEY"
    }


@router.post("/enrich-lead/{lead_id}")
async def enrich_lead(lead_id: int, db: Session = Depends(get_db)):
    """Enrich a single lead with Apollo email data."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if lead.email:
        return {"message": "Lead already has email", "email": lead.email, "updated": False}

    if not lead.website:
        return {"message": "No website — cannot search Apollo", "updated": False}

    result = await apollo_service.enrich_lead_email(lead.website)

    if not result.get("email"):
        return {"message": "No email found via Apollo", "updated": False}

    lead.email = result["email"]
    lead.status = "email_found"
    if result.get("name") and not lead.contact_name:
        lead.contact_name = result["name"]
    if result.get("title") and not lead.contact_role:
        lead.contact_role = result["title"]

    db.commit()
    db.refresh(lead)

    return {
        "message": "Email found via Apollo",
        "email": lead.email,
        "name": result.get("name"),
        "title": result.get("title"),
        "updated": True
    }


@router.post("/bulk-enrich")
async def bulk_enrich(payload: BulkApolloRequest, db: Session = Depends(get_db)):
    """Bulk enrich leads without emails using Apollo."""
    leads = (
        db.query(Lead)
        .filter(
            Lead.campaign_id == payload.campaign_id,
            Lead.email == None,
            Lead.website != None,
            Lead.website != ""
        )
        .limit(payload.limit)
        .all()
    )

    if not leads:
        return {"message": "No leads need enrichment", "enriched": 0}

    enriched = 0
    skipped = 0
    results = []

    for lead in leads:
        result = await apollo_service.enrich_lead_email(lead.website)

        if not result.get("email"):
            skipped += 1
            results.append({
                "lead_id": lead.id,
                "company": lead.company_name,
                "status": "not_found"
            })
            continue

        lead.email = result["email"]
        lead.status = "email_found"
        if result.get("name") and not lead.contact_name:
            lead.contact_name = result["name"]
        if result.get("title") and not lead.contact_role:
            lead.contact_role = result["title"]

        enriched += 1
        results.append({
            "lead_id": lead.id,
            "company": lead.company_name,
            "email": result["email"],
            "status": "found"
        })

    db.commit()

    return {
        "enriched": enriched,
        "skipped": skipped,
        "total_processed": len(leads),
        "results": results
    }
