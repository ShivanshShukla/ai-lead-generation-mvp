from datetime import datetime

from pydantic import BaseModel


class DiscoveryJobCreate(BaseModel):
    opportunity_id: int | None = None
    campaign_id: int | None = None
    title: str
    target_type: str | None = None
    department: str | None = None
    location: str | None = None
    target_role: str | None = None
    query_goal: str | None = None
    source_mode: str | None = "manual_urls"
    source_urls: str | None = None
    generated_queries: str | None = None
    limit: int | None = 20


class DiscoveryJobUpdate(BaseModel):
    opportunity_id: int | None = None
    campaign_id: int | None = None
    title: str | None = None
    target_type: str | None = None
    department: str | None = None
    location: str | None = None
    target_role: str | None = None
    query_goal: str | None = None
    source_mode: str | None = None
    source_urls: str | None = None
    generated_queries: str | None = None
    status: str | None = None
    limit: int | None = None


class DiscoverySelectionRequest(BaseModel):
    result_ids: list[int]


class DiscoveryImportRequest(DiscoverySelectionRequest):
    allow_no_email: bool = False


class DiscoveryQueryGenerateRequest(BaseModel):
    title: str | None = None
    target_type: str | None = None
    department: str | None = None
    location: str | None = None
    target_role: str | None = None
    query_goal: str | None = None
    offer: str | None = None


class DiscoveryResultUpdate(BaseModel):
    status: str | None = None


class DiscoveryJobResponse(BaseModel):
    id: int
    opportunity_id: int | None = None
    campaign_id: int | None = None
    title: str
    target_type: str | None = None
    department: str | None = None
    location: str | None = None
    target_role: str | None = None
    query_goal: str | None = None
    source_mode: str
    source_urls: str | None = None
    generated_queries: str | None = None
    status: str
    limit: int
    pages_attempted: int
    contacts_found: int
    errors: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class DiscoveredLeadResponse(BaseModel):
    id: int
    discovery_job_id: int
    campaign_id: int | None = None
    name: str | None = None
    organization: str | None = None
    department: str | None = None
    designation: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    profile_url: str | None = None
    source_url: str
    lead_type: str | None = None
    location: str | None = None
    confidence: int | None = None
    fit_reason: str | None = None
    risk_flags: str | None = None
    raw_context: str | None = None
    status: str
    imported_lead_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
