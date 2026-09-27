from datetime import datetime

from pydantic import BaseModel


class EmailDraftResponse(BaseModel):
    id: int
    campaign_id: int
    lead_id: int
    call_log_id: int | None = None
    subject: str
    body: str
    status: str
    source_type: str | None = None
    knowledge_used: str | None = None
    ai_model: str | None = None
    sent_at: datetime | None = None
    send_error: str | None = None
    gmail_message_id: str | None = None
    reply_checked_at: datetime | None = None
    reply_message_id: str | None = None
    reply_snippet: str | None = None
    replied_at: datetime | None = None
    reply_intent: str | None = None
    reply_sentiment: str | None = None
    reply_priority: str | None = None
    reply_next_action: str | None = None
    reply_summary: str | None = None
    reply_suggested_response_direction: str | None = None
    reply_classified_at: datetime | None = None
    reply_classification_model: str | None = None
    reply_classification_error: str | None = None
    created_at: datetime
    lead_company_name: str | None = None
    lead_contact_name: str | None = None
    lead_contact_role: str | None = None
    lead_email: str | None = None
    lead_ai_score: int | None = None
    lead_ai_fit_score: int | None = None
    lead_ai_contact_confidence_score: int | None = None
    lead_ai_priority: str | None = None
    lead_ai_qualification: str | None = None

    class Config:
        from_attributes = True


class GenerateEmailResponse(BaseModel):
    status: str
    message: str
    email_draft: EmailDraftResponse


class EmailDraftUpdate(BaseModel):
    status: str


class EmailDraftContentUpdate(BaseModel):
    subject: str
    body: str
