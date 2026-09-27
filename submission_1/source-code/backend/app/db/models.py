from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.database import Base
from app.utils.time_utils import utc_now


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    campaign_name = Column(String(255), nullable=False)
    industry = Column(String(255), nullable=False)
    location = Column(String(255), nullable=False)
    target_role = Column(String(255), nullable=False)
    offer = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_now)

    leads = relationship("Lead", back_populates="campaign", cascade="all, delete-orphan")
    email_drafts = relationship("EmailDraft", back_populates="campaign", cascade="all, delete-orphan")
    follow_up_drafts = relationship("FollowUpDraft", back_populates="campaign", cascade="all, delete-orphan")
    reply_response_drafts = relationship("ReplyResponseDraft", back_populates="campaign", cascade="all, delete-orphan")
    converted_opportunities = relationship("Opportunity", back_populates="converted_campaign")
    discovery_jobs = relationship("DiscoveryJob", back_populates="campaign")
    discovered_leads = relationship("DiscoveredLead", back_populates="campaign")
    call_logs = relationship("CallLog", back_populates="campaign")
    call_scripts = relationship("CallScript", back_populates="campaign")
    email_extraction_jobs = relationship("EmailExtractionJob", back_populates="campaign", cascade="all, delete-orphan")
    lead_research_jobs = relationship("LeadResearchJob", back_populates="campaign", cascade="all, delete-orphan")
    lead_scoring_jobs = relationship("LeadScoringJob", back_populates="campaign", cascade="all, delete-orphan")


class Opportunity(Base):
    __tablename__ = "opportunities"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    raw_goal = Column(Text, nullable=False)
    target_domain = Column(String(255), nullable=True)
    target_location = Column(String(255), nullable=True)
    offer = Column(Text, nullable=True)
    status = Column(String(50), default="draft", nullable=False)
    ai_summary = Column(Text, nullable=True)
    target_audience = Column(Text, nullable=True)
    ideal_roles = Column(Text, nullable=True)
    industries = Column(Text, nullable=True)
    locations = Column(Text, nullable=True)
    pain_points = Column(Text, nullable=True)
    value_proposition = Column(Text, nullable=True)
    outreach_angle = Column(Text, nullable=True)
    search_keywords = Column(Text, nullable=True)
    lead_source_ideas = Column(Text, nullable=True)
    email_script = Column(Text, nullable=True)
    call_script = Column(Text, nullable=True)
    follow_up_sequence = Column(Text, nullable=True)
    qualification_criteria = Column(Text, nullable=True)
    risk_flags = Column(Text, nullable=True)
    suggested_campaign_name = Column(String(255), nullable=True)
    suggested_campaign_industry = Column(String(255), nullable=True)
    suggested_campaign_location = Column(String(255), nullable=True)
    suggested_campaign_target_role = Column(String(255), nullable=True)
    suggested_campaign_offer = Column(Text, nullable=True)
    suggested_discovery_target_type = Column(String(100), nullable=True)
    suggested_discovery_department = Column(String(255), nullable=True)
    suggested_discovery_role = Column(String(255), nullable=True)
    suggested_discovery_queries = Column(Text, nullable=True)
    ai_model = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, nullable=True, onupdate=utc_now)
    converted_campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=True, index=True)

    converted_campaign = relationship("Campaign", back_populates="converted_opportunities")
    discovery_jobs = relationship("DiscoveryJob", back_populates="opportunity")


class DiscoveryJob(Base):
    __tablename__ = "discovery_jobs"

    id = Column(Integer, primary_key=True, index=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id"), nullable=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    target_type = Column(String(100), nullable=True)
    department = Column(String(255), nullable=True)
    location = Column(String(255), nullable=True)
    target_role = Column(String(255), nullable=True)
    query_goal = Column(Text, nullable=True)
    source_mode = Column(String(50), default="manual_urls", nullable=False)
    source_urls = Column(Text, nullable=True)
    generated_queries = Column(Text, nullable=True)
    status = Column(String(50), default="draft", nullable=False)
    limit = Column(Integer, default=20, nullable=False)
    pages_attempted = Column(Integer, default=0, nullable=False)
    contacts_found = Column(Integer, default=0, nullable=False)
    errors = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, nullable=True, onupdate=utc_now)

    opportunity = relationship("Opportunity", back_populates="discovery_jobs")
    campaign = relationship("Campaign", back_populates="discovery_jobs")
    discovered_leads = relationship("DiscoveredLead", back_populates="discovery_job", cascade="all, delete-orphan")


class DiscoveredLead(Base):
    __tablename__ = "discovered_leads"

    id = Column(Integer, primary_key=True, index=True)
    discovery_job_id = Column(Integer, ForeignKey("discovery_jobs.id"), nullable=False, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=True, index=True)
    name = Column(String(255), nullable=True)
    organization = Column(String(255), nullable=True)
    department = Column(String(255), nullable=True)
    designation = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True, index=True)
    phone = Column(String(100), nullable=True)
    website = Column(String(500), nullable=True)
    profile_url = Column(String(500), nullable=True)
    source_url = Column(Text, nullable=False)
    lead_type = Column(String(100), nullable=True)
    location = Column(String(255), nullable=True)
    confidence = Column(Integer, nullable=True)
    fit_reason = Column(Text, nullable=True)
    risk_flags = Column(Text, nullable=True)
    raw_context = Column(Text, nullable=True)
    status = Column(String(50), default="pending", nullable=False)
    imported_lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, nullable=True, onupdate=utc_now)

    discovery_job = relationship("DiscoveryJob", back_populates="discovered_leads")
    campaign = relationship("Campaign", back_populates="discovered_leads")
    imported_lead = relationship("Lead")


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False, index=True)
    company_name = Column(String(255), nullable=False)
    website = Column(String(255), nullable=True)
    industry = Column(String(255), nullable=True)
    location = Column(String(255), nullable=True)
    contact_name = Column(String(255), nullable=True)
    contact_role = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(100), nullable=True)
    source_url = Column(Text, nullable=True)
    profile_url = Column(Text, nullable=True)
    source = Column(String(100), default="CSV")
    status = Column(String(100), default="new")
    call_status = Column(String(100), nullable=True)
    last_call_outcome = Column(String(100), nullable=True)
    last_called_at = Column(DateTime, nullable=True)
    do_not_call = Column(Boolean, default=False, nullable=False)
    ai_score = Column(Integer, nullable=True)
    ai_fit_score = Column(Integer, nullable=True)
    ai_contact_confidence_score = Column(Integer, nullable=True)
    ai_priority = Column(String(50), nullable=True)
    ai_qualification = Column(String(50), nullable=True)
    ai_score_reason = Column(Text, nullable=True)
    ai_contact_confidence_reason = Column(Text, nullable=True)
    ai_outreach_angle = Column(Text, nullable=True)
    ai_pain_point = Column(Text, nullable=True)
    ai_recommended_cta = Column(Text, nullable=True)
    ai_final_priority_reason = Column(Text, nullable=True)
    ai_scored_at = Column(DateTime, nullable=True)
    ai_model_used = Column(String(255), nullable=True)
    ai_score_error = Column(Text, nullable=True)
    research_status = Column(String(50), default="not_researched", nullable=False)
    research_summary = Column(Text, nullable=True)
    research_business_type = Column(String(255), nullable=True)
    research_target_customers = Column(Text, nullable=True)
    research_products_services = Column(Text, nullable=True)
    research_pain_points = Column(Text, nullable=True)
    research_use_case_fit = Column(Text, nullable=True)
    research_outreach_angle = Column(Text, nullable=True)
    research_risk_flags = Column(Text, nullable=True)
    research_confidence = Column(Integer, nullable=True)
    research_sources = Column(Text, nullable=True)
    research_error = Column(Text, nullable=True)
    research_used_fallback = Column(Boolean, default=False, nullable=False)
    researched_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    campaign = relationship("Campaign", back_populates="leads")
    email_drafts = relationship("EmailDraft", back_populates="lead", cascade="all, delete-orphan")
    follow_up_drafts = relationship("FollowUpDraft", back_populates="lead", cascade="all, delete-orphan")
    reply_response_drafts = relationship("ReplyResponseDraft", back_populates="lead", cascade="all, delete-orphan")
    call_logs = relationship("CallLog", back_populates="lead")
    call_scripts = relationship("CallScript", back_populates="lead")


class EmailExtractionJob(Base):
    __tablename__ = "email_extraction_jobs"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False, index=True)
    status = Column(String(50), default="pending", nullable=False)
    total_leads = Column(Integer, default=0, nullable=False)
    processed = Column(Integer, default=0, nullable=False)
    found = Column(Integer, default=0, nullable=False)
    skipped = Column(Integer, default=0, nullable=False)
    failed = Column(Integer, default=0, nullable=False)
    started_at = Column(DateTime, default=utc_now)
    finished_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)

    campaign = relationship("Campaign", back_populates="email_extraction_jobs")


class LeadResearchJob(Base):
    __tablename__ = "lead_research_jobs"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False, index=True)
    status = Column(String(50), default="pending", nullable=False)
    total_leads = Column(Integer, default=0, nullable=False)
    processed = Column(Integer, default=0, nullable=False)
    researched = Column(Integer, default=0, nullable=False)
    skipped = Column(Integer, default=0, nullable=False)
    failed = Column(Integer, default=0, nullable=False)
    started_at = Column(DateTime, default=utc_now)
    finished_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)

    campaign = relationship("Campaign", back_populates="lead_research_jobs")


class LeadScoringJob(Base):
    __tablename__ = "lead_scoring_jobs"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False, index=True)
    status = Column(String(50), default="pending", nullable=False)
    total_leads = Column(Integer, default=0, nullable=False)
    processed = Column(Integer, default=0, nullable=False)
    scored = Column(Integer, default=0, nullable=False)
    skipped = Column(Integer, default=0, nullable=False)
    failed = Column(Integer, default=0, nullable=False)
    started_at = Column(DateTime, default=utc_now)
    finished_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    force = Column(Boolean, default=False, nullable=False)

    campaign = relationship("Campaign", back_populates="lead_scoring_jobs")


class CallLog(Base):
    __tablename__ = "call_logs"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=True, index=True)
    provider = Column(String(50), default="vapi", nullable=False)
    provider_call_id = Column(String(255), nullable=True, index=True)
    provider_assistant_id = Column(String(255), nullable=True)
    provider_phone_number_id = Column(String(255), nullable=True)
    direction = Column(String(50), default="outbound", nullable=False)
    phone_number = Column(String(100), nullable=True)
    called_number = Column(String(100), nullable=True)
    call_mode = Column(String(50), nullable=True)
    lead_phone_used = Column(Boolean, nullable=True)
    status = Column(String(50), default="created", nullable=False)
    outcome = Column(String(100), nullable=True)
    sentiment = Column(String(50), nullable=True)
    priority = Column(String(50), nullable=True)
    transcript = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    next_action = Column(Text, nullable=True)
    call_script = Column(Text, nullable=True)
    recording_url = Column(Text, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    raw_vapi_payload = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, nullable=True, onupdate=utc_now)

    lead = relationship("Lead", back_populates="call_logs")
    campaign = relationship("Campaign", back_populates="call_logs")
    email_drafts = relationship("EmailDraft", back_populates="call_log")


class CallScript(Base):
    __tablename__ = "call_scripts"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False, index=True)
    script = Column(Text, nullable=False)
    opener = Column(Text, nullable=True)
    questions = Column(Text, nullable=True)
    objection_handling = Column(Text, nullable=True)
    closing = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    lead = relationship("Lead", back_populates="call_scripts")
    campaign = relationship("Campaign", back_populates="call_scripts")


class EmailDraft(Base):
    __tablename__ = "email_drafts"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    call_log_id = Column(Integer, ForeignKey("call_logs.id"), nullable=True, index=True)
    subject = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String(100), default="generated", nullable=False)
    source_type = Column(String(100), default="cold_email", nullable=False)
    knowledge_used = Column(Text, nullable=True)
    ai_model = Column(String(255), nullable=True)
    sent_at = Column(DateTime, nullable=True)
    send_error = Column(Text, nullable=True)
    gmail_message_id = Column(String(255), nullable=True)
    reply_checked_at = Column(DateTime, nullable=True)
    reply_message_id = Column(String(255), nullable=True)
    reply_snippet = Column(Text, nullable=True)
    replied_at = Column(DateTime, nullable=True)
    reply_intent = Column(String(100), nullable=True)
    reply_sentiment = Column(String(50), nullable=True)
    reply_priority = Column(String(50), nullable=True)
    reply_next_action = Column(Text, nullable=True)
    reply_summary = Column(Text, nullable=True)
    reply_suggested_response_direction = Column(Text, nullable=True)
    reply_classified_at = Column(DateTime, nullable=True)
    reply_classification_model = Column(String(255), nullable=True)
    reply_classification_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    campaign = relationship("Campaign", back_populates="email_drafts")
    lead = relationship("Lead", back_populates="email_drafts")
    call_log = relationship("CallLog", back_populates="email_drafts")
    follow_up_drafts = relationship("FollowUpDraft", back_populates="original_email_draft", cascade="all, delete-orphan")
    reply_response_drafts = relationship("ReplyResponseDraft", back_populates="original_email_draft", cascade="all, delete-orphan")


class FollowUpDraft(Base):
    __tablename__ = "follow_up_drafts"

    id = Column(Integer, primary_key=True, index=True)
    original_email_draft_id = Column(Integer, ForeignKey("email_drafts.id"), nullable=False, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    follow_up_number = Column(Integer, default=1, nullable=False)
    subject = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String(100), default="generated", nullable=False)
    model_used = Column(String(255), nullable=True)
    generated_at = Column(DateTime, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    gmail_message_id = Column(String(255), nullable=True)
    gmail_thread_id = Column(String(255), nullable=True)
    send_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    original_email_draft = relationship("EmailDraft", back_populates="follow_up_drafts")
    campaign = relationship("Campaign", back_populates="follow_up_drafts")
    lead = relationship("Lead", back_populates="follow_up_drafts")


class ReplyResponseDraft(Base):
    __tablename__ = "reply_response_drafts"

    id = Column(Integer, primary_key=True, index=True)
    original_email_draft_id = Column(Integer, ForeignKey("email_drafts.id"), nullable=False, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    subject = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String(100), default="generated", nullable=False)
    intent_used = Column(String(100), nullable=True)
    next_action_used = Column(Text, nullable=True)
    knowledge_used = Column(Text, nullable=True)
    model_used = Column(String(255), nullable=True)
    generated_at = Column(DateTime, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    gmail_message_id = Column(String(255), nullable=True)
    gmail_thread_id = Column(String(255), nullable=True)
    send_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    original_email_draft = relationship("EmailDraft", back_populates="reply_response_drafts")
    campaign = relationship("Campaign", back_populates="reply_response_drafts")
    lead = relationship("Lead", back_populates="reply_response_drafts")


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)
    category = Column(String(100), nullable=True)
    tags = Column(String(500), nullable=True)
    status = Column(String(50), default="processed", nullable=False)
    error_message = Column(Text, nullable=True)
    total_chunks = Column(Integer, default=0, nullable=False)
    uploaded_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, nullable=True, onupdate=utc_now)

    knowledge_entries = relationship("CompanyKnowledge", back_populates="document")


class CompanyKnowledge(Base):
    __tablename__ = "company_knowledge"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("knowledge_documents.id"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    tags = Column(String(500), nullable=True)
    chunk_index = Column(Integer, nullable=True)
    source_type = Column(String(50), default="manual", nullable=False)
    embedding_model = Column(String(255), nullable=True)
    embedding_updated_at = Column(DateTime, nullable=True)
    embedding_error = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, nullable=True, onupdate=utc_now)

    document = relationship("KnowledgeDocument", back_populates="knowledge_entries")


class GmailToken(Base):
    __tablename__ = "gmail_tokens"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=True)
    token_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


class GmailOAuthState(Base):
    __tablename__ = "gmail_oauth_states"

    id = Column(Integer, primary_key=True, index=True)
    state = Column(String(255), unique=True, nullable=False, index=True)
    code_verifier = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
