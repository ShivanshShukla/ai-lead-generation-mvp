from datetime import datetime

from pydantic import BaseModel


class OpportunityCreate(BaseModel):
    title: str
    raw_goal: str
    target_domain: str | None = None
    target_location: str | None = None
    offer: str | None = None


class OpportunityUpdate(BaseModel):
    title: str | None = None
    raw_goal: str | None = None
    target_domain: str | None = None
    target_location: str | None = None
    offer: str | None = None
    status: str | None = None


class OpportunityGenerateRequest(BaseModel):
    force: bool = False


class OpportunityConvertToCampaignRequest(BaseModel):
    force_new: bool = False


class OpportunityCreateDiscoveryJobRequest(BaseModel):
    campaign_id: int | None = None


class OpportunityResponse(BaseModel):
    id: int
    title: str
    raw_goal: str
    target_domain: str | None = None
    target_location: str | None = None
    offer: str | None = None
    status: str
    ai_summary: str | None = None
    target_audience: str | None = None
    ideal_roles: str | None = None
    industries: str | None = None
    locations: str | None = None
    pain_points: str | None = None
    value_proposition: str | None = None
    outreach_angle: str | None = None
    search_keywords: str | None = None
    lead_source_ideas: str | None = None
    email_script: str | None = None
    call_script: str | None = None
    follow_up_sequence: str | None = None
    qualification_criteria: str | None = None
    risk_flags: str | None = None
    suggested_campaign_name: str | None = None
    suggested_campaign_industry: str | None = None
    suggested_campaign_location: str | None = None
    suggested_campaign_target_role: str | None = None
    suggested_campaign_offer: str | None = None
    suggested_discovery_target_type: str | None = None
    suggested_discovery_department: str | None = None
    suggested_discovery_role: str | None = None
    suggested_discovery_queries: str | None = None
    ai_model: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    converted_campaign_id: int | None = None

    class Config:
        from_attributes = True


class OpportunityGenerateResponse(BaseModel):
    status: str
    message: str
    data: OpportunityResponse


class OpportunityConvertToCampaignResponse(BaseModel):
    status: str
    message: str
    opportunity_id: int
    campaign_id: int
    already_converted: bool = False


class OpportunityCreateDiscoveryJobResponse(BaseModel):
    status: str
    message: str
    opportunity_id: int
    discovery_job_id: int
