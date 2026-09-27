import logging

from sqlalchemy import inspect, text

from app.core.config import settings


logger = logging.getLogger(__name__)


def ensure_email_extraction_job_columns(engine):
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    dialect_name = engine.dialect.name
    datetime_type = "TIMESTAMP" if dialect_name == "postgresql" else "DATETIME"
    id_type = "SERIAL PRIMARY KEY" if dialect_name == "postgresql" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    current_timestamp = "NOW()" if dialect_name == "postgresql" else "CURRENT_TIMESTAMP"

    required_columns = {
        "id": "INTEGER",
        "campaign_id": "INTEGER",
        "status": "VARCHAR(50)",
        "total_leads": "INTEGER",
        "processed": "INTEGER",
        "found": "INTEGER",
        "skipped": "INTEGER",
        "failed": "INTEGER",
        "started_at": datetime_type,
        "finished_at": datetime_type,
        "error": "TEXT",
    }

    if "email_extraction_jobs" not in table_names:
        with engine.begin() as connection:
            connection.execute(
                text(f"""
                    CREATE TABLE IF NOT EXISTS email_extraction_jobs (
                        id {id_type},
                        campaign_id INTEGER NOT NULL,
                        status VARCHAR(50) DEFAULT 'pending' NOT NULL,
                        total_leads INTEGER DEFAULT 0 NOT NULL,
                        processed INTEGER DEFAULT 0 NOT NULL,
                        found INTEGER DEFAULT 0 NOT NULL,
                        skipped INTEGER DEFAULT 0 NOT NULL,
                        failed INTEGER DEFAULT 0 NOT NULL,
                        started_at {datetime_type} DEFAULT {current_timestamp},
                        finished_at {datetime_type},
                        error TEXT
                    )
                """)
            )
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_email_extraction_jobs_campaign_id ON email_extraction_jobs (campaign_id)")
            )
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("email_extraction_jobs")
    }
    missing_columns = [
        (column_name, column_type)
        for column_name, column_type in required_columns.items()
        if column_name not in existing_columns and column_name != "id"
    ]

    if not missing_columns:
        return

    with engine.begin() as connection:
        for column_name, column_type in missing_columns:
            default_clause = ""
            if column_name == "status":
                default_clause = " DEFAULT 'pending'"
            if column_name in {"total_leads", "processed", "found", "skipped", "failed"}:
                default_clause = " DEFAULT 0"
            connection.execute(
                text(f"ALTER TABLE email_extraction_jobs ADD COLUMN {column_name} {column_type}{default_clause}")
            )

        connection.execute(text("UPDATE email_extraction_jobs SET status = 'pending' WHERE status IS NULL"))
        for column_name in ("total_leads", "processed", "found", "skipped", "failed"):
            connection.execute(text(f"UPDATE email_extraction_jobs SET {column_name} = 0 WHERE {column_name} IS NULL"))


def ensure_lead_research_job_columns(engine):
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    dialect_name = engine.dialect.name
    datetime_type = "TIMESTAMP" if dialect_name == "postgresql" else "DATETIME"
    id_type = "SERIAL PRIMARY KEY" if dialect_name == "postgresql" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    current_timestamp = "NOW()" if dialect_name == "postgresql" else "CURRENT_TIMESTAMP"

    required_columns = {
        "id": "INTEGER",
        "campaign_id": "INTEGER",
        "status": "VARCHAR(50)",
        "total_leads": "INTEGER",
        "processed": "INTEGER",
        "researched": "INTEGER",
        "skipped": "INTEGER",
        "failed": "INTEGER",
        "started_at": datetime_type,
        "finished_at": datetime_type,
        "error": "TEXT",
    }

    if "lead_research_jobs" not in table_names:
        with engine.begin() as connection:
            connection.execute(
                text(f"""
                    CREATE TABLE IF NOT EXISTS lead_research_jobs (
                        id {id_type},
                        campaign_id INTEGER NOT NULL,
                        status VARCHAR(50) DEFAULT 'pending' NOT NULL,
                        total_leads INTEGER DEFAULT 0 NOT NULL,
                        processed INTEGER DEFAULT 0 NOT NULL,
                        researched INTEGER DEFAULT 0 NOT NULL,
                        skipped INTEGER DEFAULT 0 NOT NULL,
                        failed INTEGER DEFAULT 0 NOT NULL,
                        started_at {datetime_type} DEFAULT {current_timestamp},
                        finished_at {datetime_type},
                        error TEXT
                    )
                """)
            )
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_lead_research_jobs_campaign_id ON lead_research_jobs (campaign_id)")
            )
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("lead_research_jobs")
    }
    missing_columns = [
        (column_name, column_type)
        for column_name, column_type in required_columns.items()
        if column_name not in existing_columns and column_name != "id"
    ]

    if not missing_columns:
        return

    with engine.begin() as connection:
        for column_name, column_type in missing_columns:
            default_clause = ""
            if column_name == "status":
                default_clause = " DEFAULT 'pending'"
            if column_name in {"total_leads", "processed", "researched", "skipped", "failed"}:
                default_clause = " DEFAULT 0"
            connection.execute(
                text(f"ALTER TABLE lead_research_jobs ADD COLUMN {column_name} {column_type}{default_clause}")
            )

        connection.execute(text("UPDATE lead_research_jobs SET status = 'pending' WHERE status IS NULL"))
        for column_name in ("total_leads", "processed", "researched", "skipped", "failed"):
            connection.execute(text(f"UPDATE lead_research_jobs SET {column_name} = 0 WHERE {column_name} IS NULL"))


def ensure_lead_scoring_job_columns(engine):
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    dialect_name = engine.dialect.name
    datetime_type = "TIMESTAMP" if dialect_name == "postgresql" else "DATETIME"
    id_type = "SERIAL PRIMARY KEY" if dialect_name == "postgresql" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    current_timestamp = "NOW()" if dialect_name == "postgresql" else "CURRENT_TIMESTAMP"
    boolean_type = "BOOLEAN"

    required_columns = {
        "id": "INTEGER",
        "campaign_id": "INTEGER",
        "status": "VARCHAR(50)",
        "total_leads": "INTEGER",
        "processed": "INTEGER",
        "scored": "INTEGER",
        "skipped": "INTEGER",
        "failed": "INTEGER",
        "started_at": datetime_type,
        "finished_at": datetime_type,
        "error": "TEXT",
        "force": boolean_type,
    }

    if "lead_scoring_jobs" not in table_names:
        with engine.begin() as connection:
            connection.execute(
                text(f"""
                    CREATE TABLE IF NOT EXISTS lead_scoring_jobs (
                        id {id_type},
                        campaign_id INTEGER NOT NULL,
                        status VARCHAR(50) DEFAULT 'pending' NOT NULL,
                        total_leads INTEGER DEFAULT 0 NOT NULL,
                        processed INTEGER DEFAULT 0 NOT NULL,
                        scored INTEGER DEFAULT 0 NOT NULL,
                        skipped INTEGER DEFAULT 0 NOT NULL,
                        failed INTEGER DEFAULT 0 NOT NULL,
                        started_at {datetime_type} DEFAULT {current_timestamp},
                        finished_at {datetime_type},
                        error TEXT,
                        force {boolean_type} DEFAULT FALSE NOT NULL
                    )
                """)
            )
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_lead_scoring_jobs_campaign_id ON lead_scoring_jobs (campaign_id)")
            )
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("lead_scoring_jobs")
    }
    missing_columns = [
        (column_name, column_type)
        for column_name, column_type in required_columns.items()
        if column_name not in existing_columns and column_name != "id"
    ]

    if not missing_columns:
        return

    with engine.begin() as connection:
        for column_name, column_type in missing_columns:
            default_clause = ""
            if column_name == "status":
                default_clause = " DEFAULT 'pending'"
            if column_name in {"total_leads", "processed", "scored", "skipped", "failed"}:
                default_clause = " DEFAULT 0"
            if column_name == "force":
                default_clause = " DEFAULT FALSE"
            connection.execute(
                text(f"ALTER TABLE lead_scoring_jobs ADD COLUMN {column_name} {column_type}{default_clause}")
            )

        connection.execute(text("UPDATE lead_scoring_jobs SET status = 'pending' WHERE status IS NULL"))
        for column_name in ("total_leads", "processed", "scored", "skipped", "failed"):
            connection.execute(text(f"UPDATE lead_scoring_jobs SET {column_name} = 0 WHERE {column_name} IS NULL"))
        connection.execute(text("UPDATE lead_scoring_jobs SET force = FALSE WHERE force IS NULL"))


def ensure_email_draft_columns(engine):
    inspector = inspect(engine)

    if "email_drafts" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("email_drafts")
    }

    dialect_name = engine.dialect.name
    datetime_type = "TIMESTAMP" if dialect_name == "postgresql" else "DATETIME"

    required_columns = {
        "call_log_id": "INTEGER",
        "sent_at": datetime_type,
        "send_error": "TEXT",
        "gmail_message_id": "VARCHAR(255)",
        "source_type": "VARCHAR(100)",
        "knowledge_used": "TEXT",
        "reply_checked_at": datetime_type,
        "reply_message_id": "VARCHAR(255)",
        "reply_snippet": "TEXT",
        "replied_at": datetime_type,
        "reply_intent": "VARCHAR(100)",
        "reply_sentiment": "VARCHAR(50)",
        "reply_priority": "VARCHAR(50)",
        "reply_next_action": "TEXT",
        "reply_summary": "TEXT",
        "reply_suggested_response_direction": "TEXT",
        "reply_classified_at": datetime_type,
        "reply_classification_model": "VARCHAR(255)",
        "reply_classification_error": "TEXT",
    }

    missing_columns = [
        (column_name, column_type)
        for column_name, column_type in required_columns.items()
        if column_name not in existing_columns
    ]

    if not missing_columns:
        return

    with engine.begin() as connection:
        for column_name, column_type in missing_columns:
            default_clause = " DEFAULT 'cold_email'" if column_name == "source_type" else ""
            connection.execute(
                text(f"ALTER TABLE email_drafts ADD COLUMN {column_name} {column_type}{default_clause}")
            )

        if "source_type" in existing_columns or any(column_name == "source_type" for column_name, _ in missing_columns):
            connection.execute(
                text("UPDATE email_drafts SET source_type = 'cold_email' WHERE source_type IS NULL")
            )


def ensure_lead_ai_scoring_columns(engine):
    inspector = inspect(engine)

    if "leads" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("leads")
    }

    dialect_name = engine.dialect.name
    datetime_type = "TIMESTAMP" if dialect_name == "postgresql" else "DATETIME"

    required_columns = {
        "ai_score": "INTEGER",
        "ai_fit_score": "INTEGER",
        "ai_contact_confidence_score": "INTEGER",
        "ai_priority": "VARCHAR(50)",
        "ai_qualification": "VARCHAR(50)",
        "ai_score_reason": "TEXT",
        "ai_contact_confidence_reason": "TEXT",
        "ai_outreach_angle": "TEXT",
        "ai_pain_point": "TEXT",
        "ai_recommended_cta": "TEXT",
        "ai_final_priority_reason": "TEXT",
        "ai_scored_at": datetime_type,
        "ai_model_used": "VARCHAR(255)",
        "ai_score_error": "TEXT",
    }

    missing_columns = [
        (column_name, column_type)
        for column_name, column_type in required_columns.items()
        if column_name not in existing_columns
    ]

    if not missing_columns:
        return

    with engine.begin() as connection:
        for column_name, column_type in missing_columns:
            connection.execute(
                text(f"ALTER TABLE leads ADD COLUMN {column_name} {column_type}")
            )


def ensure_lead_research_columns(engine):
    inspector = inspect(engine)

    if "leads" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("leads")
    }

    dialect_name = engine.dialect.name
    datetime_type = "TIMESTAMP" if dialect_name == "postgresql" else "DATETIME"

    required_columns = {
        "research_status": "VARCHAR(50)",
        "research_summary": "TEXT",
        "research_business_type": "VARCHAR(255)",
        "research_target_customers": "TEXT",
        "research_products_services": "TEXT",
        "research_pain_points": "TEXT",
        "research_use_case_fit": "TEXT",
        "research_outreach_angle": "TEXT",
        "research_risk_flags": "TEXT",
        "research_confidence": "INTEGER",
        "research_sources": "TEXT",
        "research_error": "TEXT",
        "research_used_fallback": "BOOLEAN",
        "researched_at": datetime_type,
    }

    missing_columns = [
        (column_name, column_type)
        for column_name, column_type in required_columns.items()
        if column_name not in existing_columns
    ]

    with engine.begin() as connection:
        for column_name, column_type in missing_columns:
            default_clause = " DEFAULT 'not_researched'" if column_name == "research_status" else ""
            if column_name == "research_used_fallback":
                default_clause = " DEFAULT FALSE"
            connection.execute(
                text(f"ALTER TABLE leads ADD COLUMN {column_name} {column_type}{default_clause}")
            )

        if "research_status" in existing_columns or any(column_name == "research_status" for column_name, _ in missing_columns):
            connection.execute(
                text("UPDATE leads SET research_status = 'not_researched' WHERE research_status IS NULL")
            )

        if "research_used_fallback" in existing_columns or any(column_name == "research_used_fallback" for column_name, _ in missing_columns):
            connection.execute(
                text("UPDATE leads SET research_used_fallback = FALSE WHERE research_used_fallback IS NULL")
            )


def ensure_lead_discovery_source_columns(engine):
    inspector = inspect(engine)

    if "leads" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("leads")
    }

    required_columns = {
        "source_url": "TEXT",
        "profile_url": "TEXT",
    }

    missing_columns = [
        (column_name, column_type)
        for column_name, column_type in required_columns.items()
        if column_name not in existing_columns
    ]

    if not missing_columns:
        return

    with engine.begin() as connection:
        for column_name, column_type in missing_columns:
            connection.execute(
                text(f"ALTER TABLE leads ADD COLUMN {column_name} {column_type}")
            )


def ensure_lead_call_columns(engine):
    inspector = inspect(engine)

    if "leads" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("leads")
    }

    dialect_name = engine.dialect.name
    datetime_type = "TIMESTAMP" if dialect_name == "postgresql" else "DATETIME"

    required_columns = {
        "phone": "VARCHAR(100)",
        "call_status": "VARCHAR(100)",
        "last_call_outcome": "VARCHAR(100)",
        "last_called_at": datetime_type,
        "do_not_call": "BOOLEAN",
    }

    missing_columns = [
        (column_name, column_type)
        for column_name, column_type in required_columns.items()
        if column_name not in existing_columns
    ]

    with engine.begin() as connection:
        for column_name, column_type in missing_columns:
            default_clause = " DEFAULT FALSE" if column_name == "do_not_call" else ""
            connection.execute(
                text(f"ALTER TABLE leads ADD COLUMN {column_name} {column_type}{default_clause}")
            )

        if "do_not_call" in existing_columns or any(column_name == "do_not_call" for column_name, _ in missing_columns):
            connection.execute(
                text("UPDATE leads SET do_not_call = FALSE WHERE do_not_call IS NULL")
            )


def ensure_opportunity_columns(engine):
    inspector = inspect(engine)
    dialect_name = engine.dialect.name
    datetime_type = "TIMESTAMP" if dialect_name == "postgresql" else "DATETIME"

    required_columns = {
        "id": "INTEGER",
        "title": "VARCHAR(255)",
        "raw_goal": "TEXT",
        "target_domain": "VARCHAR(255)",
        "target_location": "VARCHAR(255)",
        "offer": "TEXT",
        "status": "VARCHAR(50)",
        "ai_summary": "TEXT",
        "target_audience": "TEXT",
        "ideal_roles": "TEXT",
        "industries": "TEXT",
        "locations": "TEXT",
        "pain_points": "TEXT",
        "value_proposition": "TEXT",
        "outreach_angle": "TEXT",
        "search_keywords": "TEXT",
        "lead_source_ideas": "TEXT",
        "email_script": "TEXT",
        "call_script": "TEXT",
        "follow_up_sequence": "TEXT",
        "qualification_criteria": "TEXT",
        "risk_flags": "TEXT",
        "suggested_campaign_name": "VARCHAR(255)",
        "suggested_campaign_industry": "VARCHAR(255)",
        "suggested_campaign_location": "VARCHAR(255)",
        "suggested_campaign_target_role": "VARCHAR(255)",
        "suggested_campaign_offer": "TEXT",
        "suggested_discovery_target_type": "VARCHAR(100)",
        "suggested_discovery_department": "VARCHAR(255)",
        "suggested_discovery_role": "VARCHAR(255)",
        "suggested_discovery_queries": "TEXT",
        "ai_model": "VARCHAR(255)",
        "created_at": datetime_type,
        "updated_at": datetime_type,
        "converted_campaign_id": "INTEGER",
    }

    if "opportunities" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("opportunities")
    }
    missing_columns = [
        (column_name, column_type)
        for column_name, column_type in required_columns.items()
        if column_name not in existing_columns and column_name != "id"
    ]

    with engine.begin() as connection:
        for column_name, column_type in missing_columns:
            default_clause = " DEFAULT 'draft'" if column_name == "status" else ""
            connection.execute(
                text(f"ALTER TABLE opportunities ADD COLUMN {column_name} {column_type}{default_clause}")
            )

        if "status" in existing_columns or any(column_name == "status" for column_name, _ in missing_columns):
            connection.execute(
                text("UPDATE opportunities SET status = 'draft' WHERE status IS NULL")
            )


def ensure_discovery_columns(engine):
    inspector = inspect(engine)
    dialect_name = engine.dialect.name
    datetime_type = "TIMESTAMP" if dialect_name == "postgresql" else "DATETIME"

    discovery_job_columns = {
        "id": "INTEGER",
        "opportunity_id": "INTEGER",
        "campaign_id": "INTEGER",
        "title": "VARCHAR(255)",
        "target_type": "VARCHAR(100)",
        "department": "VARCHAR(255)",
        "location": "VARCHAR(255)",
        "target_role": "VARCHAR(255)",
        "query_goal": "TEXT",
        "source_mode": "VARCHAR(50)",
        "source_urls": "TEXT",
        "generated_queries": "TEXT",
        "status": "VARCHAR(50)",
        "limit": "INTEGER",
        "pages_attempted": "INTEGER",
        "contacts_found": "INTEGER",
        "errors": "TEXT",
        "created_at": datetime_type,
        "updated_at": datetime_type,
    }
    discovered_lead_columns = {
        "id": "INTEGER",
        "discovery_job_id": "INTEGER",
        "campaign_id": "INTEGER",
        "name": "VARCHAR(255)",
        "organization": "VARCHAR(255)",
        "department": "VARCHAR(255)",
        "designation": "VARCHAR(255)",
        "email": "VARCHAR(255)",
        "phone": "VARCHAR(100)",
        "website": "VARCHAR(500)",
        "profile_url": "VARCHAR(500)",
        "source_url": "TEXT",
        "lead_type": "VARCHAR(100)",
        "location": "VARCHAR(255)",
        "confidence": "INTEGER",
        "fit_reason": "TEXT",
        "risk_flags": "TEXT",
        "raw_context": "TEXT",
        "status": "VARCHAR(50)",
        "imported_lead_id": "INTEGER",
        "created_at": datetime_type,
        "updated_at": datetime_type,
    }
    table_columns = {
        "discovery_jobs": discovery_job_columns,
        "discovered_leads": discovered_lead_columns,
    }

    table_names = inspector.get_table_names()

    for table_name, required_columns in table_columns.items():
        if table_name not in table_names:
            continue

        existing_columns = {
            column["name"]
            for column in inspector.get_columns(table_name)
        }
        missing_columns = [
            (column_name, column_type)
            for column_name, column_type in required_columns.items()
            if column_name not in existing_columns and column_name != "id"
        ]

        with engine.begin() as connection:
            for column_name, column_type in missing_columns:
                column_sql = f'"{column_name}"' if column_name == "limit" else column_name
                default_clause = ""
                if table_name == "discovery_jobs" and column_name == "source_mode":
                    default_clause = " DEFAULT 'manual_urls'"
                if table_name == "discovery_jobs" and column_name == "status":
                    default_clause = " DEFAULT 'draft'"
                if table_name == "discovery_jobs" and column_name in {"limit", "pages_attempted", "contacts_found"}:
                    default_value = 20 if column_name == "limit" else 0
                    default_clause = f" DEFAULT {default_value}"
                if table_name == "discovered_leads" and column_name == "status":
                    default_clause = " DEFAULT 'pending'"
                connection.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN {column_sql} {column_type}{default_clause}")
                )

            if table_name == "discovery_jobs":
                connection.execute(text("UPDATE discovery_jobs SET source_mode = 'manual_urls' WHERE source_mode IS NULL"))
                connection.execute(text("UPDATE discovery_jobs SET status = 'draft' WHERE status IS NULL"))
                connection.execute(text('UPDATE discovery_jobs SET "limit" = 20 WHERE "limit" IS NULL'))
                connection.execute(text("UPDATE discovery_jobs SET pages_attempted = 0 WHERE pages_attempted IS NULL"))
                connection.execute(text("UPDATE discovery_jobs SET contacts_found = 0 WHERE contacts_found IS NULL"))
            if table_name == "discovered_leads":
                connection.execute(text("UPDATE discovered_leads SET status = 'pending' WHERE status IS NULL"))


def ensure_call_columns(engine):
    inspector = inspect(engine)
    dialect_name = engine.dialect.name
    datetime_type = "TIMESTAMP" if dialect_name == "postgresql" else "DATETIME"

    call_log_columns = {
        "id": "INTEGER",
        "lead_id": "INTEGER",
        "campaign_id": "INTEGER",
        "provider": "VARCHAR(50)",
        "provider_call_id": "VARCHAR(255)",
        "provider_assistant_id": "VARCHAR(255)",
        "provider_phone_number_id": "VARCHAR(255)",
        "direction": "VARCHAR(50)",
        "phone_number": "VARCHAR(100)",
        "called_number": "VARCHAR(100)",
        "call_mode": "VARCHAR(50)",
        "lead_phone_used": "BOOLEAN",
        "status": "VARCHAR(50)",
        "outcome": "VARCHAR(100)",
        "sentiment": "VARCHAR(50)",
        "priority": "VARCHAR(50)",
        "transcript": "TEXT",
        "summary": "TEXT",
        "next_action": "TEXT",
        "call_script": "TEXT",
        "recording_url": "TEXT",
        "duration_seconds": "INTEGER",
        "started_at": datetime_type,
        "ended_at": datetime_type,
        "raw_vapi_payload": "TEXT",
        "error_message": "TEXT",
        "created_at": datetime_type,
        "updated_at": datetime_type,
    }
    call_script_columns = {
        "id": "INTEGER",
        "lead_id": "INTEGER",
        "campaign_id": "INTEGER",
        "script": "TEXT",
        "opener": "TEXT",
        "questions": "TEXT",
        "objection_handling": "TEXT",
        "closing": "TEXT",
        "created_at": datetime_type,
    }
    table_columns = {
        "call_logs": call_log_columns,
        "call_scripts": call_script_columns,
    }

    table_names = inspector.get_table_names()

    for table_name, required_columns in table_columns.items():
        if table_name not in table_names:
            continue

        existing_columns = {
            column["name"]
            for column in inspector.get_columns(table_name)
        }
        missing_columns = [
            (column_name, column_type)
            for column_name, column_type in required_columns.items()
            if column_name not in existing_columns and column_name != "id"
        ]

        with engine.begin() as connection:
            for column_name, column_type in missing_columns:
                default_clause = ""
                if table_name == "call_logs" and column_name == "provider":
                    default_clause = " DEFAULT 'vapi'"
                if table_name == "call_logs" and column_name == "direction":
                    default_clause = " DEFAULT 'outbound'"
                if table_name == "call_logs" and column_name == "status":
                    default_clause = " DEFAULT 'created'"
                connection.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}{default_clause}")
                )

            if table_name == "call_logs":
                connection.execute(text("UPDATE call_logs SET provider = 'vapi' WHERE provider IS NULL"))
                connection.execute(text("UPDATE call_logs SET direction = 'outbound' WHERE direction IS NULL"))
                connection.execute(text("UPDATE call_logs SET status = 'created' WHERE status IS NULL"))


def ensure_reply_response_draft_columns(engine):
    inspector = inspect(engine)

    if "reply_response_drafts" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("reply_response_drafts")
    }

    dialect_name = engine.dialect.name
    datetime_type = "TIMESTAMP" if dialect_name == "postgresql" else "DATETIME"

    required_columns = {
        "original_email_draft_id": "INTEGER",
        "campaign_id": "INTEGER",
        "lead_id": "INTEGER",
        "subject": "VARCHAR(255)",
        "body": "TEXT",
        "status": "VARCHAR(100)",
        "intent_used": "VARCHAR(100)",
        "next_action_used": "TEXT",
        "knowledge_used": "TEXT",
        "model_used": "VARCHAR(255)",
        "generated_at": datetime_type,
        "approved_at": datetime_type,
        "rejected_at": datetime_type,
        "sent_at": datetime_type,
        "gmail_message_id": "VARCHAR(255)",
        "gmail_thread_id": "VARCHAR(255)",
        "send_error": "TEXT",
        "created_at": datetime_type,
        "updated_at": datetime_type,
    }

    missing_columns = [
        (column_name, column_type)
        for column_name, column_type in required_columns.items()
        if column_name not in existing_columns
    ]

    if not missing_columns:
        return

    with engine.begin() as connection:
        for column_name, column_type in missing_columns:
            connection.execute(
                text(f"ALTER TABLE reply_response_drafts ADD COLUMN {column_name} {column_type}")
            )


def ensure_company_knowledge_columns(engine):
    inspector = inspect(engine)

    if "company_knowledge" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("company_knowledge")
    }

    dialect_name = engine.dialect.name
    datetime_type = "TIMESTAMP" if dialect_name == "postgresql" else "DATETIME"
    boolean_type = "BOOLEAN"

    required_columns = {
        "document_id": "INTEGER",
        "title": "VARCHAR(255)",
        "category": "VARCHAR(100)",
        "content": "TEXT",
        "tags": "VARCHAR(500)",
        "chunk_index": "INTEGER",
        "source_type": "VARCHAR(50)",
        "embedding_model": "VARCHAR(255)",
        "embedding_updated_at": datetime_type,
        "embedding_error": "TEXT",
        "is_active": boolean_type,
        "created_at": datetime_type,
        "updated_at": datetime_type,
    }

    missing_columns = [
        (column_name, column_type)
        for column_name, column_type in required_columns.items()
        if column_name not in existing_columns
    ]

    with engine.begin() as connection:
        for column_name, column_type in missing_columns:
            default_clause = " DEFAULT TRUE" if column_name == "is_active" else ""
            if column_name == "source_type":
                default_clause = " DEFAULT 'manual'"
            connection.execute(
                text(f"ALTER TABLE company_knowledge ADD COLUMN {column_name} {column_type}{default_clause}")
            )

        if "source_type" in existing_columns or any(column_name == "source_type" for column_name, _ in missing_columns):
            connection.execute(
                text("UPDATE company_knowledge SET source_type = 'manual' WHERE source_type IS NULL")
            )


def ensure_company_knowledge_embedding_columns(engine):
    inspector = inspect(engine)

    if "company_knowledge" not in inspector.get_table_names():
        return

    dialect_name = engine.dialect.name

    if dialect_name != "postgresql":
        logger.warning("Semantic RAG pgvector setup skipped because database dialect is %s.", dialect_name)
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("company_knowledge")
    }

    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    except Exception as exc:
        logger.warning("Could not enable pgvector extension. Keyword fallback will remain available. %s", exc)
        return

    desired_vector_type = f"vector({settings.EMBEDDING_DIMENSION})"

    if "embedding" not in existing_columns:
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(f"ALTER TABLE company_knowledge ADD COLUMN embedding vector({settings.EMBEDDING_DIMENSION})")
                )
        except Exception as exc:
            logger.warning("Could not add company_knowledge.embedding vector column. Keyword fallback will remain available. %s", exc)
            return
    else:
        try:
            with engine.begin() as connection:
                current_vector_type = connection.execute(
                    text(
                        "SELECT format_type(a.atttypid, a.atttypmod) "
                        "FROM pg_attribute a "
                        "JOIN pg_class c ON a.attrelid = c.oid "
                        "WHERE c.relname = 'company_knowledge' "
                        "AND a.attname = 'embedding' "
                        "AND a.attnum > 0 "
                        "AND NOT a.attisdropped"
                    )
                ).scalar()

                if current_vector_type and current_vector_type != desired_vector_type:
                    logger.warning(
                        "company_knowledge.embedding is %s but configured dimension is %s. "
                        "Clearing stored embeddings and updating column dimension.",
                        current_vector_type,
                        desired_vector_type,
                    )
                    connection.execute(
                        text(
                            f"ALTER TABLE company_knowledge "
                            f"ALTER COLUMN embedding TYPE vector({settings.EMBEDDING_DIMENSION}) "
                            "USING NULL"
                        )
                    )
                    connection.execute(
                        text(
                            "UPDATE company_knowledge "
                            "SET embedding_model = NULL, embedding_updated_at = NULL "
                            "WHERE embedding IS NULL"
                        )
                    )
        except Exception as exc:
            logger.warning("Could not verify or update embedding column dimension. Keyword fallback will remain available. %s", exc)
            return

    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS company_knowledge_embedding_idx "
                    "ON company_knowledge "
                    "USING ivfflat (embedding vector_cosine_ops) "
                    "WITH (lists = 100)"
                )
            )
    except Exception as exc:
        logger.warning("Could not create company_knowledge embedding index. Semantic search can still run without it. %s", exc)


def ensure_knowledge_document_columns(engine):
    inspector = inspect(engine)

    if "knowledge_documents" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("knowledge_documents")
    }

    dialect_name = engine.dialect.name
    datetime_type = "TIMESTAMP" if dialect_name == "postgresql" else "DATETIME"

    required_columns = {
        "filename": "VARCHAR(255)",
        "original_filename": "VARCHAR(255)",
        "file_type": "VARCHAR(50)",
        "category": "VARCHAR(100)",
        "tags": "VARCHAR(500)",
        "status": "VARCHAR(50)",
        "error_message": "TEXT",
        "total_chunks": "INTEGER",
        "uploaded_at": datetime_type,
        "updated_at": datetime_type,
    }

    missing_columns = [
        (column_name, column_type)
        for column_name, column_type in required_columns.items()
        if column_name not in existing_columns
    ]

    if not missing_columns:
        return

    with engine.begin() as connection:
        for column_name, column_type in missing_columns:
            default_clause = ""
            if column_name == "status":
                default_clause = " DEFAULT 'processed'"
            if column_name == "total_chunks":
                default_clause = " DEFAULT 0"
            connection.execute(
                text(f"ALTER TABLE knowledge_documents ADD COLUMN {column_name} {column_type}{default_clause}")
            )
