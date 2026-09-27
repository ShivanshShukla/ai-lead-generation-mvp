import json
import logging
import os
from typing import Any

import requests
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Campaign, DiscoveredLead, DiscoveryJob, Lead

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/lead-agent",
    tags=["Lead Agent"],
)


class LeadAgentStartRequest(BaseModel):
    campaign_id: int
    target_leads: int = Field(default=100, ge=1, le=500)
    max_results: int | None = Field(default=None, ge=1, le=500)
    queries_per_day: int = Field(default=1, ge=1, le=3)
    sectors: list[str] | None = None
    cities: list[str] | None = None
    custom_sectors: list[str] | None = None
    custom_cities: list[str] | None = None
    notes: str | None = None


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _split_terms(value: str) -> list[str]:
    separators = [",", "/", "|", "\n", ";"]
    text = _clean_text(value)

    for separator in separators:
        text = text.replace(separator, ",")

    terms = []
    seen = set()

    for part in text.split(","):
        term = part.strip()
        key = term.lower()

        if not term or key in seen:
            continue

        seen.add(key)
        terms.append(term)

    return terms


def _generate_sectors(campaign: Campaign) -> list[str]:
    combined_text = " ".join([
        _clean_text(campaign.industry),
        _clean_text(campaign.target_role),
        _clean_text(campaign.offer),
    ]).lower()

    sectors = _split_terms(campaign.industry)

    keyword_sectors = [
        ("mechanical", ["Mechanical Engineering", "Manufacturing", "Product Design", "Industrial Automation"]),
        ("manufacturing", ["Manufacturing", "Industrial Automation", "Fabrication"]),
        ("robot", ["Robotics", "Industrial Automation", "Hardware Startups"]),
        ("ev", ["Electric Vehicles", "Battery Tech", "Automotive"]),
        ("electric vehicle", ["Electric Vehicles", "Battery Tech", "Automotive"]),
        ("aerospace", ["Aerospace", "Drones", "Defence Tech"]),
        ("drone", ["Drones", "Aerospace", "Robotics"]),
        ("startup", ["Startups", "Hardware Startups"]),
        ("hardware", ["Hardware Startups", "IoT", "Product Design"]),
        ("cad", ["CAD/CAM", "Mechanical Design", "Product Design"]),
    ]

    for keyword, matched_sectors in keyword_sectors:
        if keyword in combined_text:
            sectors.extend(matched_sectors)

    if not sectors:
        sectors = ["Startups", "SMEs", "Technology Companies"]

    deduped = []
    seen = set()

    for sector in sectors:
        key = sector.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(sector)

    return deduped[:10]


def _generate_cities(campaign: Campaign) -> list[str]:
    location = _clean_text(campaign.location)
    cities = _split_terms(location)
    location_lower = location.lower()

    region_city_map = {
        "hyderabad": ["Hyderabad", "Secunderabad", "Ranga Reddy"],
        "telangana": ["Hyderabad", "Secunderabad", "Warangal", "Ranga Reddy"],
        "bangalore": ["Bengaluru", "Bangalore"],
        "bengaluru": ["Bengaluru", "Bangalore"],
        "mumbai": ["Mumbai", "Navi Mumbai", "Thane"],
        "delhi": ["Delhi", "Noida", "Gurugram", "Faridabad"],
        "ncr": ["Delhi", "Noida", "Gurugram", "Faridabad"],
        "pune": ["Pune", "Pimpri-Chinchwad"],
        "chennai": ["Chennai"],
        "india": ["Hyderabad", "Bengaluru", "Pune", "Chennai", "Mumbai", "Delhi NCR"],
    }

    for keyword, mapped_cities in region_city_map.items():
        if keyword in location_lower:
            cities.extend(mapped_cities)

    if not cities:
        cities = ["India"]

    deduped = []
    seen = set()

    for city in cities:
        key = city.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(city)

    return deduped[:10]


def _generate_search_queries(campaign: Campaign, sectors: list[str], cities: list[str], queries_per_day: int) -> list[str]:
    role = _clean_text(campaign.target_role) or "Founder OR CTO OR Operations"
    generated_queries = []

    for city in cities:
        for sector in sectors:
            generated_queries.extend([
                f'"{city}" "{sector}" "startup" "contact"',
                f'"{city}" "{sector}" "{role}" "email"',
                f'site:.in "{city}" "{sector}" "contact"',
            ])

    deduped = []
    seen = set()

    for query in generated_queries:
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(query)

    return deduped[: max(1, queries_per_day) * 5]


def _fallback_search_queries(industry: str, location: str, queries_count: int = 3) -> list[str]:
    places = _split_terms(location) or ["India"]
    clean_industry = _clean_text(industry) or "business"
    industry_lower = clean_industry.lower()

    if "mechanical" in industry_lower or "manufacturing" in industry_lower:
        business_types = [
            "manufacturing company",
            "industrial automation company",
            "mechanical engineering company",
            "machine parts manufacturer",
            "fabrication company",
        ]
    elif "college" in industry_lower or "education" in industry_lower:
        business_types = [
            "engineering college",
            "technology institute",
            "polytechnic college",
            "university engineering department",
        ]
    else:
        business_types = [
            clean_industry,
            f"{clean_industry} company",
            f"{clean_industry} business",
        ]

    queries = []

    for index in range(max(1, queries_count)):
        business_type = business_types[index % len(business_types)]
        place = places[index % len(places)]
        queries.append(f"{business_type} {place}")

    return queries


def _ensure_query_count(
    queries: list[str],
    industry: str,
    location: str,
    queries_count: int,
) -> list[str]:
    expected_count = max(1, queries_count)
    fallback_queries = _fallback_search_queries(industry, location, expected_count)
    cleaned_queries = []
    seen = set()

    for query in [*queries, *fallback_queries]:
        cleaned_query = _clean_text(query)
        key = cleaned_query.lower()

        if not cleaned_query or key in seen:
            continue

        seen.add(key)
        cleaned_queries.append(cleaned_query)

        if len(cleaned_queries) == expected_count:
            break

    return cleaned_queries


async def _generate_search_queries_with_ai(
    campaign_name: str,
    industry: str,
    location: str,
    target_role: str,
    offer: str,
    queries_count: int = 3,
) -> list[str]:
    """
    Uses Gemini to generate smart Google Maps search queries based on campaign details.
    Falls back to basic generation if Gemini fails or is unavailable.
    """
    gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"

    if not gemini_api_key:
        logger.warning("GEMINI_API_KEY not set. Using fallback Lead Agent search queries.")
        return _fallback_search_queries(industry, location, queries_count)

    prompt = f"""
You are a senior B2B lead generation researcher building Google Maps searches.

Generate exactly {queries_count} Google Maps search queries for finding companies that match this campaign:

Campaign: {campaign_name}
Industry: {industry}
Location: {location}
Target Role: {target_role}
What we offer: {offer}

Rules:
- Each query must be a realistic Google Maps search, not a Google web search.
- Use 3-7 words per query.
- Format each query as: business category + area/city.
- Use buyer/company categories, not people, jobs, blogs, PDFs, or generic keywords.
- Use the target role only to understand the buyer; do not put role titles in the query unless it is naturally part of the business category.
- All queries must be in or near this location: {location}.
- Prefer specific areas, industrial zones, neighborhoods, or nearby cities from the location.
- Avoid duplicates and avoid tiny wording changes of the same query.
- Do not include quotes, boolean operators, "site:", "email", "contact", "near me", or punctuation.
- Optimize for companies likely to benefit from: {offer}

Return only a valid JSON array of {queries_count} strings.
No explanation, no markdown, no code blocks.
Example output: ["manufacturing company Nagpur", "industrial automation Hingna", "fabrication company Butibori"]
""".strip()

    try:
        from google import genai

        client = genai.Client(api_key=gemini_api_key)
        response = client.models.generate_content(
            model=gemini_model,
            contents=prompt,
        )
        text = _clean_text(getattr(response, "text", ""))
        text = text.replace("```json", "").replace("```", "").strip()
        queries = json.loads(text)

        if not isinstance(queries, list):
            raise ValueError("Gemini returned a non-list response.")

        cleaned_queries = []
        seen = set()

        for query in queries:
            cleaned_query = _clean_text(query)
            key = cleaned_query.lower()

            if not cleaned_query or key in seen:
                continue

            seen.add(key)
            cleaned_queries.append(cleaned_query)

        cleaned_queries = _ensure_query_count(cleaned_queries, industry, location, queries_count)

        if not cleaned_queries:
            raise ValueError("Gemini returned an empty query list.")

        logger.info("Gemini generated Lead Agent search queries: %s", cleaned_queries)
        return cleaned_queries
    except json.JSONDecodeError as exc:
        logger.error("Gemini returned invalid Lead Agent query JSON: %s", exc)
    except Exception as exc:
        logger.error("Gemini Lead Agent query generation failed: %s", exc)

    return _ensure_query_count([], industry, location, queries_count)


def _trigger_n8n(payload: dict):
    webhook_url = os.getenv("N8N_WEBHOOK_URL", "").strip()

    if not webhook_url:
        logger.warning("N8N_WEBHOOK_URL is not configured. Lead Agent trigger skipped.")
        return

    try:
        response = requests.post(webhook_url, json=payload, timeout=20)
        response.raise_for_status()
        logger.info(
            "Lead Agent n8n workflow triggered for campaign %s.",
            payload.get("campaign_id"),
        )
    except requests.RequestException as exc:
        logger.exception(
            "Lead Agent n8n workflow failed for campaign %s: %s",
            payload.get("campaign_id"),
            exc,
        )


@router.post("/start")
async def start_lead_agent(
    payload: LeadAgentStartRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    webhook_url = os.getenv("N8N_WEBHOOK_URL", "").strip()

    if not webhook_url:
        raise HTTPException(
            status_code=500,
            detail="N8N_WEBHOOK_URL is not configured in the backend environment.",
        )

    campaign = db.get(Campaign, payload.campaign_id)

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    max_results = payload.max_results or payload.target_leads
    custom_sectors = payload.custom_sectors or payload.sectors
    custom_cities = payload.custom_cities or payload.cities
    city = (custom_cities or _split_terms(campaign.location) or [campaign.location or "India"])[0]

    if custom_sectors:
        search_queries = [
            f"{_clean_text(sector)} {_clean_text(city)}".strip()
            for sector in custom_sectors[:payload.queries_per_day]
            if _clean_text(sector)
        ] or _fallback_search_queries(campaign.industry, campaign.location, payload.queries_per_day)
        ai_generated = False
    else:
        search_queries = await _generate_search_queries_with_ai(
            campaign_name=campaign.campaign_name,
            industry=campaign.industry,
            location=campaign.location,
            target_role=campaign.target_role or "",
            offer=campaign.offer or "",
            queries_count=payload.queries_per_day,
        )
        ai_generated = True

    total_target = max_results * len(search_queries)

    n8n_payload = {
        "campaign_id": campaign.id,
        "campaign_name": campaign.campaign_name,
        "industry": campaign.industry,
        "location": campaign.location,
        "target_role": campaign.target_role,
        "offer": campaign.offer,
        "target_leads": max_results,
        "max_results": max_results,
        "max_results_per_search": max_results,
        "total_target": total_target,
        "queries_per_day": payload.queries_per_day,
        "sectors": custom_sectors or [],
        "cities": custom_cities or [city],
        "search_queries": search_queries,
        "searches": search_queries,
        "ai_generated": ai_generated,
        "notes": payload.notes,
    }

    background_tasks.add_task(_trigger_n8n, n8n_payload)

    return {
        "status": "running",
        "message": "Lead Agent started successfully",
        "campaign_id": campaign.id,
        "campaign_name": campaign.campaign_name,
        "target_leads": max_results,
        "max_results": max_results,
        "max_results_per_search": max_results,
        "total_target": total_target,
        "queries_per_day": payload.queries_per_day,
        "search_queries": search_queries,
        "searches": search_queries,
        "ai_generated": ai_generated,
    }


@router.get("/status/{campaign_id}")
def get_lead_agent_status(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.get(Campaign, campaign_id)

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    total_leads = db.query(func.count(Lead.id)).filter(Lead.campaign_id == campaign_id).scalar() or 0
    leads_with_email = (
        db.query(func.count(Lead.id))
        .filter(
            Lead.campaign_id == campaign_id,
            Lead.email.is_not(None),
            Lead.email != "",
        )
        .scalar()
        or 0
    )
    leads_missing_email = max(total_leads - leads_with_email, 0)
    discovery_jobs = db.query(func.count(DiscoveryJob.id)).filter(DiscoveryJob.campaign_id == campaign_id).scalar() or 0
    discovered_contacts = (
        db.query(func.count(DiscoveredLead.id))
        .filter(DiscoveredLead.campaign_id == campaign_id)
        .scalar()
        or 0
    )
    imported_contacts = (
        db.query(func.count(DiscoveredLead.id))
        .filter(
            DiscoveredLead.campaign_id == campaign_id,
            DiscoveredLead.imported_lead_id.is_not(None),
        )
        .scalar()
        or 0
    )
    latest_job = (
        db.query(DiscoveryJob)
        .filter(DiscoveryJob.campaign_id == campaign_id)
        .order_by(DiscoveryJob.created_at.desc(), DiscoveryJob.id.desc())
        .first()
    )

    return {
        "campaign_id": campaign_id,
        "campaign_name": campaign.campaign_name,
        "n8n_configured": bool(os.getenv("N8N_WEBHOOK_URL", "").strip()),
        "total_leads": total_leads,
        "leads_with_email": leads_with_email,
        "leads_missing_email": leads_missing_email,
        "email_coverage_percent": round((leads_with_email / total_leads * 100) if total_leads else 0),
        "discovery_jobs": discovery_jobs,
        "discovered_contacts": discovered_contacts,
        "imported_contacts": imported_contacts,
        "latest_discovery_job": {
            "id": latest_job.id,
            "title": latest_job.title,
            "status": latest_job.status,
            "pages_attempted": latest_job.pages_attempted,
            "contacts_found": latest_job.contacts_found,
            "created_at": latest_job.created_at,
            "updated_at": latest_job.updated_at,
        } if latest_job else None,
    }
