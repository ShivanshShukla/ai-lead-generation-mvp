from datetime import datetime

from pydantic import BaseModel


class LeadBase(BaseModel):
    company_name: str
    website: str | None = None
    industry: str | None = None
    location: str | None = None
    contact_name: str | None = None
    contact_role: str | None = None
    email: str | None = None
    phone: str | None = None
    source_url: str | None = None
    profile_url: str | None = None
    source: str | None = None


class LeadCreate(LeadBase):
    campaign_id: int


class LeadCSVRow(LeadBase):
    source: str | None = "CSV"


class LeadResponse(LeadBase):
    id: int
    campaign_id: int
    source: str
    status: str
    call_status: str | None = None
    last_call_outcome: str | None = None
    last_called_at: datetime | None = None
    do_not_call: bool | None = None
    ai_score: int | None = None
    ai_fit_score: int | None = None
    ai_contact_confidence_score: int | None = None
    ai_priority: str | None = None
    ai_qualification: str | None = None
    ai_score_reason: str | None = None
    ai_contact_confidence_reason: str | None = None
    ai_outreach_angle: str | None = None
    ai_pain_point: str | None = None
    ai_recommended_cta: str | None = None
    ai_final_priority_reason: str | None = None
    ai_scored_at: datetime | None = None
    ai_model_used: str | None = None
    ai_score_error: str | None = None
    research_status: str | None = None
    research_summary: str | None = None
    research_business_type: str | None = None
    research_target_customers: str | None = None
    research_products_services: str | None = None
    research_pain_points: str | None = None
    research_use_case_fit: str | None = None
    research_outreach_angle: str | None = None
    research_risk_flags: str | None = None
    research_confidence: int | None = None
    research_sources: str | None = None
    research_error: str | None = None
    research_used_fallback: bool | None = None
    researched_at: datetime | None = None
    created_at: datetime

    class Config:
        from_attributes = True
