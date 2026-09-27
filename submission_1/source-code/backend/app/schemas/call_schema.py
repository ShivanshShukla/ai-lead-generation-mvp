from datetime import datetime

from pydantic import BaseModel


class CallLogResponse(BaseModel):
    id: int
    lead_id: int | None = None
    campaign_id: int | None = None
    provider: str
    provider_call_id: str | None = None
    provider_assistant_id: str | None = None
    provider_phone_number_id: str | None = None
    direction: str
    phone_number: str | None = None
    called_number: str | None = None
    call_mode: str | None = None
    lead_phone_used: bool | None = None
    status: str
    outcome: str | None = None
    sentiment: str | None = None
    priority: str | None = None
    transcript: str | None = None
    summary: str | None = None
    next_action: str | None = None
    call_script: str | None = None
    recording_url: str | None = None
    duration_seconds: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    lead_name: str | None = None
    lead_company_name: str | None = None
    lead_contact_role: str | None = None
    campaign_name: str | None = None

    class Config:
        from_attributes = True


class StartVapiCallRequest(BaseModel):
    lead_id: int
    phone_number: str | None = None
    use_test_number: bool = True
    test_phone_number: str | None = None
    call_mode: str | None = None
    campaign_id: int | None = None


class StartVapiCallResponse(BaseModel):
    status: str
    message: str
    call_log_id: int
    provider_call_id: str | None = None


class GenerateCallScriptRequest(BaseModel):
    lead_id: int
    campaign_id: int | None = None


class GenerateCallScriptResponse(BaseModel):
    status: str
    message: str
    lead_id: int
    campaign_id: int
    opener: str
    purpose: str | None = None
    questions: str
    objection_handling: str
    closing: str
    script: str


class ManualCallLogCreate(BaseModel):
    lead_id: int
    campaign_id: int | None = None
    phone_number: str | None = None
    outcome: str
    notes: str | None = None
    summary: str | None = None
    next_action: str | None = None
    sentiment: str | None = None
    priority: str | None = None


class CallOutcomeUpdate(BaseModel):
    status: str | None = None
    outcome: str | None = None
    sentiment: str | None = None
    priority: str | None = None
    summary: str | None = None
    next_action: str | None = None
    transcript: str | None = None
    do_not_call: bool | None = None


class VapiWebhookResponse(BaseModel):
    status: str
    message: str
