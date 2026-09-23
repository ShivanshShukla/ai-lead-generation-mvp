#update of api integration
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.api_router import api_router
from app.db.database import Base, engine
from app.db.database_utils import (
    ensure_company_knowledge_columns,
    ensure_company_knowledge_embedding_columns,
    ensure_call_columns,
    ensure_discovery_columns,
    ensure_email_draft_columns,
    ensure_email_extraction_job_columns,
    ensure_knowledge_document_columns,
    ensure_lead_ai_scoring_columns,
    ensure_lead_call_columns,
    ensure_lead_discovery_source_columns,
    ensure_lead_research_job_columns,
    ensure_lead_research_columns,
    ensure_lead_scoring_job_columns,
    ensure_opportunity_columns,
    ensure_reply_response_draft_columns,
)
from app.db.models import (  # noqa: F401
    Campaign,
    CallLog,
    CallScript,
    CompanyKnowledge,
    DiscoveredLead,
    DiscoveryJob,
    EmailDraft,
    EmailExtractionJob,
    FollowUpDraft,
    GmailOAuthState,
    GmailToken,
    KnowledgeDocument,
    Lead,
    LeadResearchJob,
    LeadScoringJob,
    Opportunity,
    ReplyResponseDraft,
)

# Import models above so Base.metadata includes all MVP tables before create_all.
Base.metadata.create_all(bind=engine)
ensure_email_draft_columns(engine)
ensure_email_extraction_job_columns(engine)
ensure_lead_research_job_columns(engine)
ensure_lead_scoring_job_columns(engine)
ensure_lead_ai_scoring_columns(engine)
ensure_lead_research_columns(engine)
ensure_lead_discovery_source_columns(engine)
ensure_lead_call_columns(engine)
ensure_opportunity_columns(engine)
ensure_discovery_columns(engine)
ensure_call_columns(engine)
ensure_reply_response_draft_columns(engine)
ensure_company_knowledge_columns(engine)
ensure_knowledge_document_columns(engine)
ensure_company_knowledge_embedding_columns(engine)

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.FRONTEND_URLS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

@app.get("/")
def root():
    return {
        "message": "AI Lead Generation MVP Backend is running"
    }
