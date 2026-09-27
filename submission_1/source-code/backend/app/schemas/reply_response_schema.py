from datetime import datetime

from pydantic import BaseModel


class ReplyResponseDraftResponse(BaseModel):
    id: int
    original_email_draft_id: int
    campaign_id: int
    lead_id: int
    subject: str
    body: str
    status: str
    intent_used: str | None = None
    next_action_used: str | None = None
    knowledge_used: str | None = None
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


class ReplyResponseGenerateResponse(BaseModel):
    status: str
    message: str
    data: ReplyResponseDraftResponse


class ReplyResponseStatusUpdateRequest(BaseModel):
    status: str


class ReplyResponseContentUpdateRequest(BaseModel):
    subject: str
    body: str


class ReplyResponseSendResponse(BaseModel):
    status: str
    message: str
    data: ReplyResponseDraftResponse
