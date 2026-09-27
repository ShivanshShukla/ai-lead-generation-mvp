from datetime import datetime

from pydantic import BaseModel


class FollowUpDraftResponse(BaseModel):
    id: int
    original_email_draft_id: int
    campaign_id: int
    lead_id: int
    follow_up_number: int
    subject: str
    body: str
    status: str
    model_used: str | None = None
    generated_at: datetime | None = None
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    sent_at: datetime | None = None
    gmail_message_id: str | None = None
    gmail_thread_id: str | None = None
    send_error: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    lead_company_name: str | None = None
    lead_contact_name: str | None = None
    lead_contact_role: str | None = None
    lead_email: str | None = None

    class Config:
        from_attributes = True


class FollowUpGenerateResponse(BaseModel):
    status: str
    message: str
    data: FollowUpDraftResponse


class FollowUpBatchGenerateResponse(BaseModel):
    status: str
    message: str
    campaign_id: int
    processed: int
    generated: int
    skipped: int
    failed: int
    remaining: int
    results: list[dict]


class FollowUpStatusUpdateRequest(BaseModel):
    status: str


class FollowUpContentUpdateRequest(BaseModel):
    subject: str
    body: str


class FollowUpSendResponse(BaseModel):
    status: str
    message: str
    data: FollowUpDraftResponse
