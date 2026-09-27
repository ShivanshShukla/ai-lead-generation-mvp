import json
import logging
import re
from datetime import datetime

import requests
from google import genai
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.models import CallLog, CallScript, Campaign, EmailDraft, Lead
from app.services.ai_service import clean_value, extract_json_from_text
from app.services.knowledge_service import build_knowledge_context, search_relevant_knowledge
from app.utils.time_utils import utc_now

VALID_CALL_STATUSES = {"created", "queued", "ringing", "in_progress", "completed", "failed", "no_answer", "canceled"}
VALID_CALL_OUTCOMES = {
    "interested",
    "asked_details",
    "call_later",
    "not_interested",
    "wrong_person",
    "no_answer",
    "do_not_call",
    "failed",
    "unknown",
}
VALID_CALL_SENTIMENTS = {"positive", "neutral", "negative", "unknown"}
VALID_CALL_PRIORITIES = {"high", "medium", "low"}
VAPI_TIMEOUT_SECONDS = 20
MAX_CONTEXT_CHARS = 6000

logger = logging.getLogger(__name__)


class VapiConfigurationError(RuntimeError):
    pass


class VapiServiceError(RuntimeError):
    pass


def _truncate(value, max_length: int | None = None):
    text = clean_value(value)

    if max_length and len(text) > max_length:
        return text[:max_length].rstrip()

    return text


def _safe_error_message(exc_or_message):
    text = clean_value(exc_or_message)

    if settings.VAPI_API_KEY:
        text = text.replace(settings.VAPI_API_KEY, "[redacted]")

    text = re.sub(r"Bearer\s+[0-9A-Za-z._-]+", "Bearer [redacted]", text, flags=re.IGNORECASE)
    text = re.sub(r"sk-[0-9A-Za-z_-]+", "[redacted]", text)

    return text[:500] or "Vapi request failed. Please try again."


def _json_dumps(payload):
    try:
        return json.dumps(payload, ensure_ascii=True, default=str)
    except TypeError:
        return json.dumps({"unserializable_payload": True}, ensure_ascii=True)


def is_vapi_configured():
    return bool(
        settings.VAPI_ENABLED
        and settings.VAPI_API_KEY
        and settings.VAPI_ASSISTANT_ID
        and settings.VAPI_PHONE_NUMBER_ID
    )


def vapi_config_status():
    return {
        "vapi_enabled": settings.VAPI_ENABLED,
        "configured": is_vapi_configured(),
        "assistant_configured": bool(settings.VAPI_ASSISTANT_ID),
        "phone_configured": bool(settings.VAPI_PHONE_NUMBER_ID),
        "test_phone_configured": bool(settings.VAPI_DEFAULT_TEST_PHONE),
        "default_test_phone": settings.VAPI_DEFAULT_TEST_PHONE,
    }


def _get_lead_and_campaign(db: Session, lead_id: int, campaign_id: int | None = None):
    lead = (
        db.query(Lead)
        .options(joinedload(Lead.campaign))
        .filter(Lead.id == lead_id)
        .first()
    )

    if not lead:
        raise VapiServiceError("Lead was not found.")

    campaign = None
    if campaign_id:
        campaign = db.get(Campaign, campaign_id)
        if not campaign:
            raise VapiServiceError("Campaign was not found.")

    campaign = campaign or lead.campaign or db.get(Campaign, lead.campaign_id)

    if not campaign:
        raise VapiServiceError("Campaign was not found.")

    return lead, campaign


def _lead_display_name(lead: Lead):
    return clean_value(lead.contact_name) or clean_value(lead.company_name) or "the lead"


def _build_knowledge_context(db: Session, campaign: Campaign, lead: Lead):
    try:
        query = " ".join(
            part
            for part in [
                clean_value(campaign.offer),
                clean_value(campaign.industry),
                clean_value(campaign.target_role),
                clean_value(lead.company_name),
                clean_value(lead.industry),
                clean_value(lead.contact_role),
                clean_value(getattr(lead, "research_summary", "")),
                clean_value(getattr(lead, "research_pain_points", "")),
            ]
            if part
        )
        entries = search_relevant_knowledge(db, query, limit=3)
        return build_knowledge_context(entries)
    except Exception:
        return ""


def build_lead_call_context(db: Session, lead_id: int, campaign_id: int | None = None):
    lead, campaign = _get_lead_and_campaign(db, lead_id, campaign_id)
    knowledge_context = _build_knowledge_context(db, campaign, lead)

    context = f"""
Campaign:
- Name: {clean_value(campaign.campaign_name)}
- Industry: {clean_value(campaign.industry)}
- Location: {clean_value(campaign.location)}
- Target role: {clean_value(campaign.target_role)}
- Offer: {clean_value(campaign.offer)}

Lead:
- Company/organization: {clean_value(lead.company_name)}
- Website: {clean_value(lead.website)}
- Contact name: {clean_value(lead.contact_name)}
- Contact role: {clean_value(lead.contact_role)}
- Email: {clean_value(lead.email)}
- Phone: {clean_value(getattr(lead, "phone", ""))}
- Source: {clean_value(lead.source)}
- Do not call: {bool(getattr(lead, "do_not_call", False))}

AI research:
- Status: {clean_value(getattr(lead, "research_status", ""))}
- Summary: {clean_value(getattr(lead, "research_summary", ""))}
- Business type: {clean_value(getattr(lead, "research_business_type", ""))}
- Pain points: {clean_value(getattr(lead, "research_pain_points", ""))}
- Use case fit: {clean_value(getattr(lead, "research_use_case_fit", ""))}
- Outreach angle: {clean_value(getattr(lead, "research_outreach_angle", ""))}
- Risk flags: {clean_value(getattr(lead, "research_risk_flags", ""))}
- Confidence: {clean_value(getattr(lead, "research_confidence", ""))}

AI scoring:
- Final score: {clean_value(getattr(lead, "ai_score", ""))}
- Fit score: {clean_value(getattr(lead, "ai_fit_score", ""))}
- Contact confidence: {clean_value(getattr(lead, "ai_contact_confidence_score", ""))}
- Priority: {clean_value(getattr(lead, "ai_priority", ""))}
- Qualification: {clean_value(getattr(lead, "ai_qualification", ""))}
- Outreach angle: {clean_value(getattr(lead, "ai_outreach_angle", ""))}
- Pain point: {clean_value(getattr(lead, "ai_pain_point", ""))}
- Recommended CTA: {clean_value(getattr(lead, "ai_recommended_cta", ""))}

Relevant company knowledge:
{knowledge_context or "No relevant company knowledge found."}
""".strip()

    return _truncate(context, MAX_CONTEXT_CHARS), lead, campaign


def _fallback_call_script(campaign: Campaign, lead: Lead):
    name = clean_value(lead.contact_name) or "there"
    organization = clean_value(lead.company_name) or "your organization"
    role = clean_value(lead.contact_role) or clean_value(campaign.target_role) or "your team"
    offer = clean_value(campaign.offer) or "our offer"
    goal_text = f"{campaign.campaign_name} {campaign.industry} {campaign.target_role} {campaign.offer}".lower()
    academic = any(keyword in goal_text for keyword in ("professor", "faculty", "hod", "college", "research", "student", "sip", "final-year", "prototype"))

    if academic:
        opener = f"Hello {name}, this is a quick call regarding possible research or student project support for {organization}. Is this a good time?"
        purpose = f"Briefly understand whether students or faculty may need support around {offer}."
        questions = "\n".join([
            "Are students currently looking for support with SIP, final-year projects, prototypes, or technical mentorship?",
            "Which department or coordinator usually handles project implementation support?",
            "Would it be useful if I shared a short proposal or overview by email?",
        ])
        objection = "If now is not convenient, politely ask whether there is a better time or the right coordinator to contact."
        closing = "Thank them for their time and offer to send details for review."
    else:
        opener = f"Hi {name}, this is a quick call about {offer} for {organization}. Is this a good time?"
        purpose = f"Check whether {offer} is relevant for {role}."
        questions = "\n".join([
            "How are you currently handling this area?",
            "Is improving this a priority in the next few months?",
            "Who would be the right person to review details?",
            "Would a short follow-up email be helpful?",
        ])
        objection = "Acknowledge the concern, keep it brief, and offer to send details only if useful."
        closing = "Thank them and confirm the next step before ending the call."

    script = "\n\n".join([
        f"Opener:\n{opener}",
        f"Purpose:\n{purpose}",
        f"Questions:\n{questions}",
        f"Objection handling:\n{objection}",
        f"Closing:\n{closing}",
    ])

    return {
        "opener": opener,
        "purpose": purpose,
        "questions": questions,
        "objection_handling": objection,
        "closing": closing,
        "script": script,
    }


def _campaign_goal_type(campaign: Campaign):
    goal_text = " ".join(
        part
        for part in [
            clean_value(campaign.campaign_name),
            clean_value(campaign.industry),
            clean_value(campaign.target_role),
            clean_value(campaign.offer),
        ]
        if part
    ).lower()

    if any(keyword in goal_text for keyword in ("professor", "faculty", "hod", "college", "research", "student", "sip", "final-year", "prototype")):
        return "professor"
    if "restaurant" in goal_text or "food" in goal_text:
        return "restaurant"
    if any(keyword in goal_text for keyword in ("clinic", "doctor", "hospital", "patient", "appointment", "medical")):
        return "clinic"

    return "generic"


def build_dynamic_first_message(campaign: Campaign, lead: Lead):
    name = clean_value(lead.contact_name) or "there"
    organization = clean_value(lead.company_name) or "your organization"
    offer = clean_value(campaign.offer)
    goal_type = _campaign_goal_type(campaign)

    if goal_type == "professor":
        return (
            f"Hello {name}, this is a brief call regarding research and project implementation assistance "
            f"for {organization}. Is this a good time to speak for a minute?"
        )

    if goal_type == "restaurant":
        return (
            f"Hi {name}, this is a quick call about helping {organization} improve local reach, "
            "Google reviews, and digital visibility. Is this a good time?"
        )

    if goal_type == "clinic":
        return (
            f"Hi {name}, this is a quick call about clinic management support around appointments, "
            "patient records, and admin workflows. Is this a good time?"
        )

    if offer:
        return f"Hi {name}, this is a quick call about {offer} for {organization}. Is this a good time?"

    return f"Hi {name}, this is a brief outreach call for {organization}. Is this a good time?"


def _build_script_prompt(context: str):
    return f"""
Generate a short, professional manual/AI phone call script using only the context below.
Return strict JSON only.

Context:
{context}

Rules:
- Do not hardcode any specific product.
- Use the current campaign offer and lead context.
- Keep the tone polite, respectful, and not pushy.
- Start by asking if this is a good time.
- Do not invent pricing, guarantees, partnerships, or facts.
- For professor/research campaigns, use a respectful academic tone and mention SIP, final-year projects, prototype support, technical mentorship, or documentation only if the campaign offer includes those ideas.
- For company campaigns, use the campaign-specific offer and lead research.
- Include 3 to 5 discovery questions.
- Include safe objection handling and a closing.

Return JSON:
{{
  "opener": "...",
  "purpose": "...",
  "questions": ["..."],
  "objection_handling": "...",
  "closing": "...",
  "script": "..."
}}
""".strip()


def generate_call_script(db: Session, lead_id: int, campaign_id: int | None = None):
    context, lead, campaign = build_lead_call_context(db, lead_id, campaign_id)
    fallback = _fallback_call_script(campaign, lead)
    payload = fallback

    if settings.GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=_build_script_prompt(context),
            )
            parsed = extract_json_from_text(clean_value(getattr(response, "text", "")))
            questions = parsed.get("questions") or fallback["questions"]
            if isinstance(questions, list):
                questions = "\n".join(clean_value(item) for item in questions if clean_value(item))
            payload = {
                "opener": _truncate(parsed.get("opener") or fallback["opener"], 2000),
                "purpose": _truncate(parsed.get("purpose") or fallback["purpose"], 2000),
                "questions": _truncate(questions or fallback["questions"], 3000),
                "objection_handling": _truncate(parsed.get("objection_handling") or fallback["objection_handling"], 3000),
                "closing": _truncate(parsed.get("closing") or fallback["closing"], 2000),
                "script": _truncate(parsed.get("script") or fallback["script"], 6000),
            }
        except Exception:
            payload = fallback

    script = payload.get("script") or "\n\n".join([
        f"Opener:\n{payload.get('opener')}",
        f"Purpose:\n{payload.get('purpose')}",
        f"Questions:\n{payload.get('questions')}",
        f"Objection handling:\n{payload.get('objection_handling')}",
        f"Closing:\n{payload.get('closing')}",
    ])
    payload["script"] = script

    call_script = CallScript(
        lead_id=lead.id,
        campaign_id=campaign.id,
        script=script,
        opener=payload.get("opener"),
        questions=payload.get("questions"),
        objection_handling=payload.get("objection_handling"),
        closing=payload.get("closing"),
    )
    db.add(call_script)

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()

    return {
        "lead_id": lead.id,
        "campaign_id": campaign.id,
        **payload,
    }


def _normalize_phone(phone_number: str):
    phone = clean_value(phone_number)

    if not phone:
        return ""

    phone = re.sub(r"[^\d+]", "", phone)
    return phone


def _extract_call_id(response_payload: dict):
    return (
        clean_value(response_payload.get("id"))
        or clean_value(response_payload.get("call", {}).get("id") if isinstance(response_payload.get("call"), dict) else "")
        or clean_value(response_payload.get("callId"))
    )


def start_outbound_call(
    db: Session,
    lead_id: int,
    phone_number: str,
    campaign_id: int | None = None,
    call_mode: str = "test",
    lead_phone_used: bool = False,
):
    if not is_vapi_configured():
        raise VapiConfigurationError("Vapi is not configured.")

    context, lead, campaign = build_lead_call_context(db, lead_id, campaign_id)

    if lead.do_not_call:
        raise VapiServiceError("This lead is marked do-not-call.")

    phone = _normalize_phone(phone_number)
    if not phone:
        raise VapiServiceError("Phone number is required.")

    script_payload = generate_call_script(db, lead.id, campaign.id)
    first_message = build_dynamic_first_message(campaign, lead)
    call_log = CallLog(
        lead_id=lead.id,
        campaign_id=campaign.id,
        provider="vapi",
        provider_assistant_id=settings.VAPI_ASSISTANT_ID,
        provider_phone_number_id=settings.VAPI_PHONE_NUMBER_ID,
        direction="outbound",
        phone_number=phone,
        called_number=phone,
        call_mode=call_mode if call_mode in {"test", "actual"} else "test",
        lead_phone_used=lead_phone_used,
        status="created",
        call_script=script_payload.get("script"),
        raw_vapi_payload=None,
    )
    db.add(call_log)
    db.flush()

    metadata = {
        "lead_id": str(lead.id),
        "campaign_id": str(campaign.id),
        "app_call_log_id": str(call_log.id),
        "call_mode": call_log.call_mode,
        "lead_phone_used": str(bool(call_log.lead_phone_used)).lower(),
    }
    variable_values = {
        "lead_id": str(lead.id),
        "campaign_id": str(campaign.id),
        "app_call_log_id": str(call_log.id),
        "lead_name": _lead_display_name(lead),
        "lead_role": clean_value(lead.contact_role),
        "lead_email": clean_value(lead.email),
        "organization": clean_value(lead.company_name),
        "campaign_name": clean_value(campaign.campaign_name),
        "campaign_offer": clean_value(campaign.offer),
        "campaign_industry": clean_value(campaign.industry),
        "campaign_target_role": clean_value(campaign.target_role),
        "call_goal": clean_value(script_payload.get("purpose")),
        "research_summary": clean_value(getattr(lead, "research_summary", "")),
        "first_message": first_message,
        "lead_context": context,
    }
    payload = {
        "assistantId": settings.VAPI_ASSISTANT_ID,
        "phoneNumberId": settings.VAPI_PHONE_NUMBER_ID,
        "customer": {"number": phone},
        "metadata": metadata,
        "assistantOverrides": {
            "firstMessage": first_message,
            "variableValues": variable_values,
        },
    }

    try:
        logger.info(
            "Starting Vapi call assistant_id=%s lead_id=%s campaign_id=%s campaign_name=%s",
            settings.VAPI_ASSISTANT_ID,
            lead.id,
            campaign.id,
            clean_value(campaign.campaign_name),
        )
        response = requests.post(
            f"{settings.VAPI_BASE_URL}/call",
            headers={
                "Authorization": f"Bearer {settings.VAPI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=VAPI_TIMEOUT_SECONDS,
        )
        response_payload = response.json() if response.content else {}

        if response.status_code in {400, 422} and "firstMessage" in payload.get("assistantOverrides", {}):
            fallback_payload = json.loads(json.dumps(payload))
            fallback_payload.get("assistantOverrides", {}).pop("firstMessage", None)
            logger.info(
                "Retrying Vapi call without direct firstMessage override assistant_id=%s lead_id=%s campaign_id=%s campaign_name=%s",
                settings.VAPI_ASSISTANT_ID,
                lead.id,
                campaign.id,
                clean_value(campaign.campaign_name),
            )
            response = requests.post(
                f"{settings.VAPI_BASE_URL}/call",
                headers={
                    "Authorization": f"Bearer {settings.VAPI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=fallback_payload,
                timeout=VAPI_TIMEOUT_SECONDS,
            )
            response_payload = response.json() if response.content else {}

        if response.status_code >= 400:
            raise VapiServiceError(_safe_error_message(response_payload or response.text))

        provider_call_id = _extract_call_id(response_payload)
        call_log.provider_call_id = provider_call_id or None
        call_log.status = "queued"
        call_log.raw_vapi_payload = _json_dumps(response_payload)
        call_log.started_at = utc_now()
        call_log.updated_at = utc_now()
        lead.call_status = "queued"
        lead.last_called_at = utc_now()
        db.commit()
        db.refresh(call_log)
        logger.info(
            "Vapi call queued assistant_id=%s lead_id=%s campaign_id=%s campaign_name=%s provider_call_id=%s",
            settings.VAPI_ASSISTANT_ID,
            lead.id,
            campaign.id,
            clean_value(campaign.campaign_name),
            provider_call_id,
        )
    except Exception as exc:
        call_log.status = "failed"
        call_log.outcome = "failed"
        call_log.error_message = _safe_error_message(exc)
        call_log.updated_at = utc_now()
        lead.call_status = "failed"
        lead.last_call_outcome = "failed"
        lead.last_called_at = utc_now()
        db.commit()
        logger.warning(
            "Vapi call failed assistant_id=%s lead_id=%s campaign_id=%s campaign_name=%s error=%s",
            settings.VAPI_ASSISTANT_ID,
            lead.id,
            campaign.id,
            clean_value(campaign.campaign_name),
            call_log.error_message,
        )
        raise VapiServiceError(call_log.error_message) from exc

    return call_log


def _find_call_log(db: Session, payload: dict):
    message = payload.get("message") if isinstance(payload.get("message"), dict) else payload
    call = message.get("call") if isinstance(message.get("call"), dict) else {}
    metadata = call.get("metadata") if isinstance(call.get("metadata"), dict) else message.get("metadata") or {}
    call_log_id = clean_value(metadata.get("app_call_log_id") or message.get("app_call_log_id"))

    if call_log_id.isdigit():
        call_log = db.get(CallLog, int(call_log_id))
        if call_log:
            return call_log

    provider_call_id = clean_value(
        call.get("id")
        or message.get("callId")
        or message.get("call_id")
        or message.get("id")
    )
    if provider_call_id:
        call_log = (
            db.query(CallLog)
            .filter(CallLog.provider_call_id == provider_call_id)
            .order_by(CallLog.created_at.desc(), CallLog.id.desc())
            .first()
        )
        if call_log:
            return call_log

    lead_id = clean_value(metadata.get("lead_id") or message.get("lead_id"))
    if lead_id.isdigit():
        return (
            db.query(CallLog)
            .filter(CallLog.lead_id == int(lead_id))
            .order_by(CallLog.created_at.desc(), CallLog.id.desc())
            .first()
        )

    return None


def _message_from_payload(payload: dict):
    return payload.get("message") if isinstance(payload.get("message"), dict) else payload


def _extract_message_type(payload: dict):
    message = _message_from_payload(payload)
    return clean_value(message.get("type") or payload.get("type") or message.get("messageType"))


def _extract_transcript(message: dict):
    parts = []

    for key in ("transcript", "transcriptText", "text"):
        if clean_value(message.get(key)):
            parts.append(clean_value(message.get(key)))

    transcript_array = message.get("transcript")
    if isinstance(transcript_array, list):
        parts = []
        for item in transcript_array:
            if not isinstance(item, dict):
                continue
            role = clean_value(item.get("role") or item.get("speaker"))
            text = clean_value(item.get("text") or item.get("message") or item.get("content"))
            if text:
                parts.append(f"{role}: {text}" if role else text)

    messages = message.get("messages")
    if isinstance(messages, list):
        for item in messages:
            if not isinstance(item, dict):
                continue
            role = clean_value(item.get("role") or item.get("speaker"))
            text = clean_value(item.get("message") or item.get("text") or item.get("content"))
            if text:
                parts.append(f"{role}: {text}" if role else text)

    return "\n".join(part for part in parts if part)


def _normalize_status(status: str):
    normalized = clean_value(status).lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "started": "in_progress",
        "in_progress": "in_progress",
        "inprogress": "in_progress",
        "ringing": "ringing",
        "queued": "queued",
        "ended": "completed",
        "completed": "completed",
        "failed": "failed",
        "no_answer": "no_answer",
        "noanswer": "no_answer",
        "canceled": "canceled",
        "cancelled": "canceled",
    }
    return mapping.get(normalized, normalized if normalized in VALID_CALL_STATUSES else None)


def _update_lead_from_call(call_log: CallLog):
    lead = call_log.lead
    if not lead:
        return

    lead.call_status = call_log.status
    if call_log.outcome:
        lead.last_call_outcome = call_log.outcome
    if call_log.started_at or call_log.created_at:
        lead.last_called_at = call_log.started_at or call_log.created_at
    if call_log.outcome == "do_not_call":
        lead.do_not_call = True


def _generate_summary_from_transcript(transcript: str, fallback_summary: str = ""):
    if not clean_value(transcript):
        return fallback_summary or ""

    if not settings.GEMINI_API_KEY:
        return fallback_summary or _truncate(transcript, 700)

    prompt = f"""
Summarize this outreach call and classify outcome.
Return strict JSON only:
{{
  "summary": "...",
  "outcome": "interested|asked_details|call_later|not_interested|wrong_person|no_answer|do_not_call|failed|unknown",
  "sentiment": "positive|neutral|negative|unknown",
  "priority": "high|medium|low",
  "next_action": "..."
}}

Transcript:
{_truncate(transcript, 7000)}
""".strip()

    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
        )
        parsed = extract_json_from_text(clean_value(getattr(response, "text", "")))
        return parsed
    except Exception:
        return fallback_summary or _truncate(transcript, 700)


def handle_vapi_webhook(db: Session, payload: dict):
    message = _message_from_payload(payload)
    message_type = _extract_message_type(payload)
    call_log = _find_call_log(db, payload)

    if message_type in {"tool-calls", "function-call", "function_call"}:
        return handle_tool_call(db, payload)

    if not call_log:
        call_log = CallLog(
            provider="vapi",
            provider_call_id=clean_value(message.get("call", {}).get("id") if isinstance(message.get("call"), dict) else message.get("callId")) or None,
            direction="outbound",
            status="created",
        )
        db.add(call_log)
        db.flush()

    if isinstance(message.get("call"), dict):
        provider_call_id = clean_value(message["call"].get("id"))
        if provider_call_id and not call_log.provider_call_id:
            call_log.provider_call_id = provider_call_id

    call_log.raw_vapi_payload = _json_dumps(payload)
    call_log.updated_at = utc_now()

    status = _normalize_status(message.get("status") or message.get("callStatus") or message_type)
    if status:
        call_log.status = status

    transcript_text = _extract_transcript(message)
    if transcript_text:
        existing = clean_value(call_log.transcript)
        call_log.transcript = f"{existing}\n{transcript_text}".strip() if existing else transcript_text

    if clean_value(message.get("summary")):
        call_log.summary = clean_value(message.get("summary"))
    if clean_value(message.get("recordingUrl") or message.get("recording_url")):
        call_log.recording_url = clean_value(message.get("recordingUrl") or message.get("recording_url"))

    duration = message.get("durationSeconds") or message.get("duration_seconds") or message.get("duration")
    try:
        if duration is not None:
            call_log.duration_seconds = int(float(duration))
    except (TypeError, ValueError):
        pass

    if message_type in {"end-of-call-report", "hang", "call.ended"} or call_log.status == "completed":
        call_log.status = call_log.status if call_log.status in {"failed", "no_answer", "canceled"} else "completed"
        call_log.ended_at = call_log.ended_at or utc_now()
        analysis = message.get("analysis") if isinstance(message.get("analysis"), dict) else {}
        if analysis:
            call_log.summary = clean_value(analysis.get("summary")) or call_log.summary
            call_log.outcome = clean_value(analysis.get("successEvaluation")) or call_log.outcome

        if call_log.transcript and not call_log.summary:
            summary_payload = _generate_summary_from_transcript(call_log.transcript)
            if isinstance(summary_payload, dict):
                call_log.summary = clean_value(summary_payload.get("summary")) or call_log.summary
                outcome = clean_value(summary_payload.get("outcome")).lower()
                sentiment = clean_value(summary_payload.get("sentiment")).lower()
                priority = clean_value(summary_payload.get("priority")).lower()
                call_log.outcome = outcome if outcome in VALID_CALL_OUTCOMES else call_log.outcome or "unknown"
                call_log.sentiment = sentiment if sentiment in VALID_CALL_SENTIMENTS else call_log.sentiment
                call_log.priority = priority if priority in VALID_CALL_PRIORITIES else call_log.priority
                call_log.next_action = clean_value(summary_payload.get("next_action")) or call_log.next_action
            elif summary_payload:
                call_log.summary = clean_value(summary_payload)

        if not call_log.outcome:
            call_log.outcome = "unknown"

    _update_lead_from_call(call_log)
    db.commit()
    db.refresh(call_log)

    return {
        "status": "success",
        "message": "Webhook processed",
        "call_log_id": call_log.id,
    }


def _latest_call_log_for_tool(db: Session, lead_id: int | None = None, provider_call_id: str | None = None):
    if provider_call_id:
        call_log = (
            db.query(CallLog)
            .filter(CallLog.provider_call_id == provider_call_id)
            .order_by(CallLog.created_at.desc(), CallLog.id.desc())
            .first()
        )
        if call_log:
            return call_log

    if lead_id:
        return (
            db.query(CallLog)
            .filter(CallLog.lead_id == lead_id)
            .order_by(CallLog.created_at.desc(), CallLog.id.desc())
            .first()
        )

    return None


def _knowledge_used_labels(entries):
    labels = []
    seen = set()

    for entry in entries or []:
        title = clean_value(getattr(entry, "title", ""))
        if not title:
            continue

        source_type = clean_value(getattr(entry, "source_type", "")).lower()
        source_label = "Document" if source_type == "document" else "Manual"
        label = f"{title} ({source_label})"

        if label not in seen:
            labels.append(label)
            seen.add(label)

    return ", ".join(labels[:5])


def _build_call_followup_knowledge(db: Session, call_log: CallLog, lead: Lead, campaign: Campaign):
    query = " ".join(
        part
        for part in [
            clean_value(campaign.offer),
            clean_value(campaign.campaign_name),
            clean_value(campaign.industry),
            clean_value(campaign.target_role),
            clean_value(call_log.summary),
            clean_value(call_log.next_action),
            clean_value(call_log.transcript),
            clean_value(lead.company_name),
            clean_value(lead.contact_role),
            clean_value(getattr(lead, "research_summary", "")),
            clean_value(getattr(lead, "research_pain_points", "")),
            clean_value(getattr(lead, "research_use_case_fit", "")),
        ]
        if part
    )

    if not query:
        return "", ""

    try:
        entries = search_relevant_knowledge(db, query, limit=4)
        return build_knowledge_context(entries), _knowledge_used_labels(entries)
    except Exception:
        return "", ""


def _previous_email_context(db: Session, lead: Lead, call_log_id: int | None = None):
    drafts = (
        db.query(EmailDraft)
        .filter(EmailDraft.lead_id == lead.id)
        .order_by(EmailDraft.created_at.desc(), EmailDraft.id.desc())
        .limit(4)
        .all()
    )
    lines = []

    for draft in drafts:
        if call_log_id and draft.call_log_id == call_log_id:
            continue

        parts = [
            f"Subject: {clean_value(draft.subject)}",
            f"Status: {clean_value(draft.status)}",
        ]
        if clean_value(draft.reply_summary):
            parts.append(f"Reply summary: {clean_value(draft.reply_summary)}")
        if clean_value(draft.reply_next_action):
            parts.append(f"Reply next action: {clean_value(draft.reply_next_action)}")
        lines.append(" | ".join(parts))

    return _truncate("\n".join(lines), 1600)


def _call_followup_subject(campaign: Campaign):
    goal_type = _campaign_goal_type(campaign)

    if goal_type == "professor":
        return "Follow-up: Research and Project Implementation Support"
    if goal_type == "restaurant":
        return "Follow-up: Digital Marketing and Local Reach"
    if goal_type == "clinic":
        return "Follow-up: Clinic Management Support"

    campaign_name = clean_value(campaign.campaign_name)
    if campaign_name:
        return f"Follow-up: {campaign_name}"[:255]

    return "Follow-up from our call"


def _call_followup_greeting(lead: Lead):
    name = clean_value(lead.contact_name)
    role = clean_value(lead.contact_role).lower()

    if not name:
        return "Hi,"

    if "professor" in role or name.lower().startswith(("dr.", "prof.")):
        return f"Dear {name},"

    return f"Hi {name},"


def _format_call_followup_body(
    lead: Lead,
    campaign: Campaign,
    call_summary: str,
    next_action: str,
    requested_topic: str,
):
    greeting = _call_followup_greeting(lead)
    offer = clean_value(campaign.offer)
    organization = clean_value(lead.company_name)
    role = clean_value(lead.contact_role)
    topic = clean_value(requested_topic) or clean_value(call_summary) or clean_value(next_action)

    intro_details = (
        f"how we can support {organization} with {offer}"
        if organization and offer
        else f"how we can support you with {offer}"
        if offer
        else "the details we discussed"
    )

    body_parts = [
        greeting,
        "",
        f"Thank you for your time on the call. As discussed, I am sharing details about {intro_details}.",
    ]

    if role or organization:
        context_parts = [part for part in [role, organization] if part]
        body_parts.append(f"I have kept the context in mind for {' at '.join(context_parts)}.")

    if call_summary:
        body_parts.append(f"On the call, I understood that {clean_value(call_summary)}.")

    if topic and topic != clean_value(call_summary):
        body_parts.append(f"Based on your requested topic, we can share more detail on {topic}.")

    if next_action:
        body_parts.append(f"For the next step, {clean_value(next_action)}.")

    body_parts.extend([
        "",
        "Would it be convenient to continue over email or schedule a short discussion?",
        "",
        "Regards,",
        "Team",
    ])

    return "\n\n".join(part for part in body_parts if part is not None).strip()


def _call_followup_fallback(lead: Lead, campaign: Campaign, call_log: CallLog):
    subject = _call_followup_subject(campaign)
    summary = clean_value(call_log.summary)
    next_action = clean_value(call_log.next_action)
    offer = clean_value(campaign.offer)
    cleaned_summary = _clean_internal_call_text(summary)
    cleaned_next_action = _clean_internal_call_text(next_action)

    if "spintronics" in summary.lower() or "spintronics" in clean_value(call_log.transcript).lower():
        subject = "Follow-up: Technical Assistance for Spintronics Research Work"

    if "send follow-up email" in next_action.lower() or "send follow up email" in next_action.lower():
        cleaned_next_action = "please share the specific requirement, research direction, or problem statement so we can suggest the right support approach"

    body = _format_call_followup_body(
        lead,
        campaign,
        call_summary=cleaned_summary,
        next_action=cleaned_next_action,
        requested_topic=cleaned_summary or cleaned_next_action,
    )

    if not offer and not summary:
        body = (
            f"{_call_followup_greeting(lead)}\n\n"
            "Thank you for your time on the call.\n\n"
            "I am sharing the details we discussed for your review. "
            "Please let me know the best way to continue from here.\n\n"
            "Regards,\nTeam"
        )

    return {"subject": subject[:255], "body": body}


def _clean_internal_call_text(value: str):
    text = clean_value(value)
    if not text:
        return ""

    text = re.sub(r"(?i)\bsend\s+(?:a\s+)?follow[-\s]?up\s+email\s+(?:with|about|for)?", "", text)
    text = re.sub(r"(?i)\bcontext\s*:\s*", "", text)
    text = re.sub(r"(?i)\bnext\s+action\s*:\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip(" .:-")

    return text


def _has_internal_note_leak(subject: str, body: str):
    combined = f"{subject}\n{body}".lower()
    blocked_phrases = [
        "send follow-up email",
        "send follow up email",
        "context:",
        "next action:",
        "internal note",
    ]

    return any(phrase in combined for phrase in blocked_phrases)


def _build_call_followup_prompt(
    call_log: CallLog,
    lead: Lead,
    campaign: Campaign,
    knowledge_context: str,
    previous_email_context: str,
):
    academic = _campaign_goal_type(campaign) == "professor"
    academic_rules = """
Professor/research campaign rules:
- Address the professor respectfully.
- Mention research/project implementation assistance.
- Mention SIP, final-year project, prototype, simulation, planning, documentation, or mentorship only if supported by campaign/knowledge/call context.
- If a specific domain was mentioned, such as spintronics, include it carefully as "spintronics-related research work".
- Ask for the exact requirement, research direction, or problem statement before promising support.
""".strip() if academic else "Use the campaign-specific tone and offer. Do not assume an academic use case unless the campaign or call says so."

    return f"""
You are writing a professional follow-up email after a phone call.
Return strict JSON only.

Call context:
- Outcome: {clean_value(call_log.outcome)}
- Sentiment: {clean_value(call_log.sentiment)}
- Summary: {clean_value(call_log.summary)}
- Next action: {clean_value(call_log.next_action)}
- Transcript: {_truncate(call_log.transcript, 3500)}

Lead:
- Name: {clean_value(lead.contact_name)}
- Role: {clean_value(lead.contact_role)}
- Organization: {clean_value(lead.company_name)}
- Email: {clean_value(lead.email)}

Campaign:
- Name: {clean_value(campaign.campaign_name)}
- Industry: {clean_value(campaign.industry)}
- Target role: {clean_value(campaign.target_role)}
- Offer: {clean_value(campaign.offer)}

Lead research:
- Summary: {clean_value(getattr(lead, "research_summary", ""))}
- Pain points: {clean_value(getattr(lead, "research_pain_points", ""))}
- Use case fit: {clean_value(getattr(lead, "research_use_case_fit", ""))}
- Outreach angle: {clean_value(getattr(lead, "research_outreach_angle", ""))}

Lead scoring:
- Score: {clean_value(getattr(lead, "ai_score", ""))}
- Outreach angle: {clean_value(getattr(lead, "ai_outreach_angle", ""))}
- Pain point: {clean_value(getattr(lead, "ai_pain_point", ""))}
- Recommended CTA: {clean_value(getattr(lead, "ai_recommended_cta", ""))}

Relevant company knowledge:
{knowledge_context or "No relevant company knowledge found."}

Previous email/reply context:
{previous_email_context or "No previous email context found."}

Rules:
- Write as a real email, not internal notes.
- Do not include labels like "Context:" or "Next action:" in the body.
- Do not copy the next_action sentence directly.
- Do not say "Send follow-up email".
- Do not use generic filler like "Please let me know if you would like me to share a short overview".
- Do not include raw call-summary labels.
- Do not invent fake pricing, fake guarantees, fake case studies, or fake team details.
- Use the exact call context.
- Keep it concise but specific.
- Mention the requested topic from the call.
- End with a clear next step.
- Do not send the email; only draft it for review.
- Sign off as "Team".
{academic_rules}

Return JSON:
{{
  "subject": "...",
  "body": "..."
}}
""".strip()


def _generate_call_followup_payload(db: Session, call_log: CallLog, lead: Lead, campaign: Campaign):
    knowledge_context, knowledge_used = _build_call_followup_knowledge(db, call_log, lead, campaign)
    previous_context = _previous_email_context(db, lead, call_log.id)
    fallback = _call_followup_fallback(lead, campaign, call_log)
    model_used = "vapi-call-followup-fallback"

    if settings.GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=_build_call_followup_prompt(call_log, lead, campaign, knowledge_context, previous_context),
            )
            parsed = extract_json_from_text(clean_value(getattr(response, "text", "")))
            subject = _truncate(parsed.get("subject"), 255)
            body = clean_value(parsed.get("body"))

            if subject and body and not _has_internal_note_leak(subject, body):
                model_used = settings.GEMINI_MODEL
                return {
                    "subject": subject,
                    "body": body,
                    "ai_model": model_used,
                    "knowledge_used": knowledge_used,
                }
        except Exception:
            pass

    return {
        "subject": fallback["subject"],
        "body": fallback["body"],
        "ai_model": model_used,
        "knowledge_used": knowledge_used,
    }


def _existing_call_followup_draft(db: Session, call_log_id: int | None):
    if not call_log_id:
        return None

    return (
        db.query(EmailDraft)
        .filter(
            EmailDraft.call_log_id == call_log_id,
            EmailDraft.source_type == "call_follow_up",
        )
        .order_by(EmailDraft.created_at.desc(), EmailDraft.id.desc())
        .first()
    )


def create_call_followup_email_draft(db: Session, call_log: CallLog):
    if not call_log.lead or not call_log.campaign:
        raise VapiServiceError("Call log must be linked to a lead and campaign.")

    existing_draft = _existing_call_followup_draft(db, call_log.id)
    if existing_draft:
        return existing_draft, False

    payload = _generate_call_followup_payload(db, call_log, call_log.lead, call_log.campaign)
    draft = EmailDraft(
        campaign_id=call_log.campaign.id,
        lead_id=call_log.lead.id,
        call_log_id=call_log.id,
        subject=payload["subject"],
        body=payload["body"],
        status="generated",
        source_type="call_follow_up",
        knowledge_used=payload.get("knowledge_used") or None,
        ai_model=payload.get("ai_model"),
    )
    db.add(draft)
    db.flush()
    call_log.next_action = call_log.next_action or "Follow-up email draft created for review."
    call_log.updated_at = utc_now()
    return draft, True


def generate_call_followup_email(db: Session, call_log_id: int):
    call_log = (
        db.query(CallLog)
        .options(joinedload(CallLog.lead), joinedload(CallLog.campaign))
        .filter(CallLog.id == call_log_id)
        .first()
    )

    if not call_log:
        raise VapiServiceError("Call log was not found.")

    return create_call_followup_email_draft(db, call_log)


def _tool_success(tool_call_id: str | None, result: dict):
    if tool_call_id:
        return {
            "results": [
                {
                    "toolCallId": tool_call_id,
                    "result": result,
                }
            ]
        }

    return {
        "status": "success",
        "result": result,
    }


def _tool_error(tool_call_id: str | None, message: str):
    result = {"status": "error", "message": message}
    if tool_call_id:
        return {
            "results": [
                {
                    "toolCallId": tool_call_id,
                    "result": result,
                }
            ]
        }
    return result


def _extract_tool_calls(payload: dict):
    message = _message_from_payload(payload)
    tool_calls = message.get("toolCalls") or message.get("tool_calls")

    if isinstance(tool_calls, list):
        return tool_calls

    if message.get("functionCall"):
        return [message["functionCall"]]

    if message.get("function"):
        return [message]

    return []


def _tool_name_and_args(tool_call: dict):
    tool_call_id = clean_value(tool_call.get("id") or tool_call.get("toolCallId"))
    function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else tool_call
    name = clean_value(function.get("name") or tool_call.get("name"))
    args = function.get("arguments") or tool_call.get("arguments") or tool_call.get("args") or {}

    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}

    if not isinstance(args, dict):
        args = {}

    return tool_call_id, name, args


def handle_tool_call(db: Session, payload: dict):
    tool_calls = _extract_tool_calls(payload)
    responses = []

    for tool_call in tool_calls:
        tool_call_id, name, args = _tool_name_and_args(tool_call)

        try:
            result = _handle_single_tool_call(db, name, args, payload)
            responses.append({
                "toolCallId": tool_call_id,
                "result": result,
            })
        except Exception as exc:
            responses.append({
                "toolCallId": tool_call_id,
                "result": {
                    "status": "error",
                    "message": _safe_error_message(exc),
                },
            })

    if responses:
        return {"results": responses}

    return _tool_error(None, "No tool calls found.")


def _handle_single_tool_call(db: Session, name: str, args: dict, payload: dict):
    message = _message_from_payload(payload)
    call = message.get("call") if isinstance(message.get("call"), dict) else {}
    metadata = call.get("metadata") if isinstance(call.get("metadata"), dict) else message.get("metadata") or {}
    lead_id = args.get("lead_id") or metadata.get("lead_id")
    campaign_id = args.get("campaign_id") or metadata.get("campaign_id")
    provider_call_id = clean_value(args.get("provider_call_id") or call.get("id") or message.get("callId"))
    lead_id = int(lead_id) if clean_value(lead_id).isdigit() else None
    campaign_id = int(campaign_id) if clean_value(campaign_id).isdigit() else None

    if name == "get_lead_context":
        if not lead_id:
            raise VapiServiceError("lead_id is required.")
        context, lead, campaign = build_lead_call_context(db, lead_id, campaign_id)
        return {
            "status": "success",
            "lead": {
                "id": lead.id,
                "name": clean_value(lead.contact_name),
                "role": clean_value(lead.contact_role),
                "email": clean_value(lead.email),
                "phone": clean_value(getattr(lead, "phone", "")),
                "organization": clean_value(lead.company_name),
                "research_summary": clean_value(getattr(lead, "research_summary", "")),
                "do_not_call": bool(lead.do_not_call),
            },
            "campaign": {
                "id": campaign.id,
                "name": clean_value(campaign.campaign_name),
                "offer": clean_value(campaign.offer),
                "industry": clean_value(campaign.industry),
                "location": clean_value(campaign.location),
                "target_role": clean_value(campaign.target_role),
            },
            "first_message": build_dynamic_first_message(campaign, lead),
            "context": context,
        }

    call_log = _latest_call_log_for_tool(db, lead_id=lead_id, provider_call_id=provider_call_id)
    lead = db.get(Lead, lead_id) if lead_id else call_log.lead if call_log else None
    campaign = db.get(Campaign, args.get("campaign_id")) if clean_value(args.get("campaign_id")).isdigit() else None
    campaign = campaign or (lead.campaign if lead else None) or (call_log.campaign if call_log else None)

    if name == "update_call_outcome":
        if not call_log:
            raise VapiServiceError("Call log was not found.")
        outcome = clean_value(args.get("outcome")).lower() or "unknown"
        sentiment = clean_value(args.get("sentiment")).lower() or "unknown"
        priority = clean_value(args.get("priority")).lower()
        call_log.outcome = outcome if outcome in VALID_CALL_OUTCOMES else "unknown"
        call_log.summary = _truncate(args.get("summary"), 3000) or call_log.summary
        call_log.next_action = _truncate(args.get("next_action") or args.get("callback_time"), 3000) or call_log.next_action
        call_log.sentiment = sentiment if sentiment in VALID_CALL_SENTIMENTS else "unknown"
        call_log.priority = priority if priority in VALID_CALL_PRIORITIES else call_log.priority
        call_log.updated_at = utc_now()
        if call_log.status in {"created", "queued", "ringing"}:
            call_log.status = "in_progress"
        _update_lead_from_call(call_log)
        db.commit()
        return {"status": "success", "call_log_id": call_log.id, "outcome": call_log.outcome}

    if name == "save_call_summary":
        if not call_log:
            raise VapiServiceError("Call log was not found.")
        transcript = clean_value(args.get("transcript"))
        if transcript:
            call_log.transcript = transcript
        call_log.summary = _truncate(args.get("summary"), 3000) or call_log.summary
        call_log.updated_at = utc_now()
        db.commit()
        return {"status": "success", "call_log_id": call_log.id}

    if name == "create_followup_email_draft":
        if not lead or not campaign:
            raise VapiServiceError("Lead and campaign are required.")
        try:
            if not call_log:
                call_log = CallLog(
                    lead_id=lead.id,
                    campaign_id=campaign.id,
                    provider="vapi",
                    provider_call_id=provider_call_id or None,
                    direction="outbound",
                    status="completed",
                    outcome=clean_value(args.get("outcome")).lower() or "asked_details",
                    summary=_truncate(args.get("reason") or args.get("summary"), 3000) or None,
                    next_action=_truncate(args.get("suggested_message") or args.get("next_action"), 3000) or None,
                    started_at=utc_now(),
                    ended_at=utc_now(),
                )
                db.add(call_log)
                db.flush()
                call_log.lead = lead
                call_log.campaign = campaign

            draft, created = create_call_followup_email_draft(db, call_log)
            db.commit()
            return {
                "success": True,
                "email_draft_id": draft.id,
                "message": (
                    "Follow-up email draft created for review. It was not sent."
                    if created
                    else "Follow-up email draft already exists for review. It was not sent."
                ),
            }
        except Exception as exc:
            db.rollback()
            if call_log:
                call_log.error_message = _safe_error_message(exc)
                call_log.updated_at = utc_now()
                try:
                    db.commit()
                except SQLAlchemyError:
                    db.rollback()
            raise VapiServiceError("Follow-up email draft could not be created.") from exc

    if name == "mark_do_not_call":
        if not lead:
            raise VapiServiceError("Lead is required.")
        lead.do_not_call = True
        lead.call_status = "completed"
        lead.last_call_outcome = "do_not_call"
        lead.last_called_at = utc_now()
        if call_log:
            call_log.outcome = "do_not_call"
            call_log.status = "completed"
            call_log.summary = _truncate(args.get("reason"), 3000) or call_log.summary
            call_log.updated_at = utc_now()
        db.commit()
        return {"status": "success", "lead_id": lead.id, "do_not_call": True}

    if name == "schedule_callback_note":
        if not call_log:
            raise VapiServiceError("Call log was not found.")
        callback_time = clean_value(args.get("callback_time"))
        note = clean_value(args.get("note"))
        call_log.outcome = "call_later"
        call_log.next_action = "\n".join(part for part in [f"Callback: {callback_time}" if callback_time else "", note] if part)
        call_log.updated_at = utc_now()
        _update_lead_from_call(call_log)
        db.commit()
        return {"status": "success", "call_log_id": call_log.id, "next_action": call_log.next_action}

    raise VapiServiceError(f"Unsupported tool: {name}")


def create_manual_call_log(
    db: Session,
    lead_id: int,
    campaign_id: int | None,
    phone_number: str | None,
    outcome: str,
    notes: str | None,
    summary: str | None,
    next_action: str | None,
    sentiment: str | None = None,
    priority: str | None = None,
):
    lead, campaign = _get_lead_and_campaign(db, lead_id, campaign_id)
    normalized_outcome = clean_value(outcome).lower()
    normalized_sentiment = clean_value(sentiment).lower()
    normalized_priority = clean_value(priority).lower()

    call_log = CallLog(
        lead_id=lead.id,
        campaign_id=campaign.id,
        provider="manual",
        direction="outbound",
        phone_number=_normalize_phone(phone_number) or clean_value(lead.phone),
        status="completed",
        outcome=normalized_outcome if normalized_outcome in VALID_CALL_OUTCOMES else "unknown",
        sentiment=normalized_sentiment if normalized_sentiment in VALID_CALL_SENTIMENTS else None,
        priority=normalized_priority if normalized_priority in VALID_CALL_PRIORITIES else None,
        summary=_truncate(summary or notes, 3000) or None,
        next_action=_truncate(next_action, 3000) or None,
        transcript=_truncate(notes, 6000) or None,
        started_at=utc_now(),
        ended_at=utc_now(),
    )
    db.add(call_log)
    lead.call_status = "completed"
    lead.last_call_outcome = call_log.outcome
    lead.last_called_at = utc_now()
    if call_log.outcome == "do_not_call":
        lead.do_not_call = True

    try:
        db.commit()
        db.refresh(call_log)
    except SQLAlchemyError as exc:
        db.rollback()
        raise VapiServiceError("Manual call log could not be saved.") from exc

    return call_log


def update_call_outcome(
    db: Session,
    call_log: CallLog,
    status: str | None = None,
    outcome: str | None = None,
    sentiment: str | None = None,
    priority: str | None = None,
    summary: str | None = None,
    next_action: str | None = None,
    transcript: str | None = None,
    do_not_call: bool | None = None,
):
    if status:
        normalized_status = _normalize_status(status)
        if normalized_status:
            call_log.status = normalized_status

    if outcome:
        normalized_outcome = clean_value(outcome).lower()
        call_log.outcome = normalized_outcome if normalized_outcome in VALID_CALL_OUTCOMES else "unknown"

    if sentiment:
        normalized_sentiment = clean_value(sentiment).lower()
        call_log.sentiment = normalized_sentiment if normalized_sentiment in VALID_CALL_SENTIMENTS else "unknown"

    if priority:
        normalized_priority = clean_value(priority).lower()
        call_log.priority = normalized_priority if normalized_priority in VALID_CALL_PRIORITIES else None

    if summary is not None:
        call_log.summary = _truncate(summary, 3000) or None
    if next_action is not None:
        call_log.next_action = _truncate(next_action, 3000) or None
    if transcript is not None:
        call_log.transcript = _truncate(transcript, 10000) or None

    if call_log.status == "completed" and not call_log.ended_at:
        call_log.ended_at = utc_now()

    if do_not_call and call_log.lead:
        call_log.lead.do_not_call = True
        call_log.outcome = "do_not_call"

    call_log.updated_at = utc_now()
    _update_lead_from_call(call_log)
    db.commit()
    db.refresh(call_log)
    return call_log
