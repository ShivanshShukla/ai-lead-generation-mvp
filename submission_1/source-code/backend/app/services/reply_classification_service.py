import json
import re
from datetime import timezone

from google import genai
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import EmailDraft
from app.services.ai_service import clean_value
from app.utils.time_utils import utc_now

ALLOWED_REPLY_INTENTS = (
    "Interested",
    "Asked for Pricing",
    "Asked for More Info",
    "Meeting Request",
    "Not Interested",
    "Wrong Person",
    "Out of Office",
    "Unsubscribe",
    "Neutral",
    "Spam/Irrelevant",
    "Unknown",
)
ALLOWED_REPLY_SENTIMENTS = ("Positive", "Neutral", "Negative")
ALLOWED_REPLY_PRIORITIES = ("High", "Medium", "Low")
FALLBACK_CLASSIFICATION_ERROR = "Gemini reply classification failed. Fallback classification was used."
FALLBACK_CLASSIFICATION_MODEL = "fallback-keyword"


class ReplyClassificationError(RuntimeError):
    pass


class ReplyClassificationRuleError(ValueError):
    pass


def _truncate(value, max_length: int | None = None):
    text = clean_value(value)

    if max_length and len(text) > max_length:
        return text[:max_length].rstrip()

    return text


def _is_classified(email_draft: EmailDraft):
    return bool(email_draft.reply_classified_at or email_draft.reply_intent)


def _contains_any(text: str, keywords):
    return any(keyword in text for keyword in keywords)


def _sortable_datetime(value):
    if not value:
        return 0

    if value.tzinfo:
        return value.astimezone(timezone.utc).timestamp()

    return value.replace(tzinfo=timezone.utc).timestamp()


def _strip_markdown_code_block(text: str):
    cleaned_text = clean_value(text)

    code_block_match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned_text, flags=re.IGNORECASE | re.DOTALL)
    if code_block_match:
        return code_block_match.group(1).strip()

    return cleaned_text


def extract_first_json_object(text: str):
    cleaned_text = _strip_markdown_code_block(text)

    try:
        parsed = json.loads(cleaned_text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", cleaned_text):
        try:
            parsed, _ = decoder.raw_decode(cleaned_text[match.start():])
        except json.JSONDecodeError:
            continue

        if isinstance(parsed, dict):
            return parsed

    raise ValueError("No valid JSON object found in Gemini reply classification response.")


def _normalize_choice(value, allowed_values, default_value):
    value_text = clean_value(value)
    value_key = value_text.lower()

    for allowed_value in allowed_values:
        if value_key == allowed_value.lower():
            return allowed_value

    aliases = {
        "pricing": "Asked for Pricing",
        "price": "Asked for Pricing",
        "cost": "Asked for Pricing",
        "more info": "Asked for More Info",
        "information request": "Asked for More Info",
        "info": "Asked for More Info",
        "meeting": "Meeting Request",
        "demo request": "Meeting Request",
        "call request": "Meeting Request",
        "not interested": "Not Interested",
        "wrong contact": "Wrong Person",
        "out-of-office": "Out of Office",
        "ooo": "Out of Office",
        "spam": "Spam/Irrelevant",
        "irrelevant": "Spam/Irrelevant",
    }

    return aliases.get(value_key, default_value)


def fallback_classify_reply(email_draft: EmailDraft):
    reply_text = clean_value(email_draft.reply_snippet).lower()

    if _contains_any(reply_text, ("unsubscribe", "do not contact", "don't contact", "stop contacting", "remove me")):
        return {
            "intent": "Unsubscribe",
            "sentiment": "Negative",
            "priority": "Low",
            "summary": "The reply asks to stop future outreach.",
            "next_action": "Stop contacting this lead and mark them as do-not-contact.",
            "suggested_response_direction": "Do not send further sales follow-ups. Respect the opt-out request.",
        }

    if _contains_any(reply_text, ("pricing", "price", "cost", "budget", "quote", "commercials", "rates")):
        return {
            "intent": "Asked for Pricing",
            "sentiment": "Positive",
            "priority": "High",
            "summary": "The reply asks about pricing or budget details.",
            "next_action": "Send pricing overview and offer a short demo or call.",
            "suggested_response_direction": "Share concise pricing context, clarify package fit, and suggest a demo.",
        }

    if _contains_any(reply_text, ("meeting", "call", "schedule", "calendar", "book", "demo", "connect")):
        return {
            "intent": "Meeting Request",
            "sentiment": "Positive",
            "priority": "High",
            "summary": "The reply indicates interest in a meeting, call, or demo.",
            "next_action": "Offer a few meeting slots and confirm the best contact details.",
            "suggested_response_direction": "Respond with availability and a simple agenda for the call.",
        }

    if _contains_any(reply_text, ("not interested", "no thanks", "no thank you", "not required", "not needed")):
        return {
            "intent": "Not Interested",
            "sentiment": "Negative",
            "priority": "Low",
            "summary": "The reply declines the outreach.",
            "next_action": "Stop active follow-up for this lead.",
            "suggested_response_direction": "Acknowledge politely if needed and avoid further outreach.",
        }

    if _contains_any(reply_text, ("wrong person", "right person", "not the right", "contact hr", "contact our hr", "contact our", "reach out to")):
        return {
            "intent": "Wrong Person",
            "sentiment": "Neutral",
            "priority": "Medium",
            "summary": "The reply suggests this is not the correct contact.",
            "next_action": "Ask for or find the correct decision-maker before continuing.",
            "suggested_response_direction": "Thank them and ask for the appropriate HR, training, or operations contact.",
        }

    if _contains_any(reply_text, ("out of office", "ooo", "vacation", "leave", "unavailable", "returning", "back on")):
        return {
            "intent": "Out of Office",
            "sentiment": "Neutral",
            "priority": "Medium",
            "summary": "The reply appears to be an out-of-office or unavailable message.",
            "next_action": "Wait until the contact returns, then follow up manually if appropriate.",
            "suggested_response_direction": "Do not respond immediately unless there is an alternate contact.",
        }

    if _contains_any(reply_text, ("interested", "details", "information", "info", "share", "brochure", "document", "video")):
        priority = "High" if "interested" in reply_text else "Medium"

        return {
            "intent": "Asked for More Info",
            "sentiment": "Positive",
            "priority": priority,
            "summary": "The reply asks for more information about the offer.",
            "next_action": "Share concise details and suggest a relevant next step.",
            "suggested_response_direction": "Send the requested information, keep the response brief, and include a soft CTA.",
        }

    if _contains_any(reply_text, ("spam", "irrelevant", "blocked")):
        return {
            "intent": "Spam/Irrelevant",
            "sentiment": "Negative",
            "priority": "Low",
            "summary": "The reply is not a useful sales conversation.",
            "next_action": "Do not continue outreach for this lead.",
            "suggested_response_direction": "No response is needed unless required for compliance.",
        }

    return {
        "intent": "Neutral",
        "sentiment": "Neutral",
        "priority": "Medium",
        "summary": "The reply is unclear or does not show a strong buying signal.",
        "next_action": "Review the reply manually and decide whether a short clarification is useful.",
        "suggested_response_direction": "If responding, ask one concise clarifying question.",
    }


def _format_follow_ups(email_draft: EmailDraft):
    follow_ups = sorted(
        email_draft.follow_up_drafts or [],
        key=lambda follow_up: (
            follow_up.follow_up_number or 0,
            _sortable_datetime(follow_up.created_at),
            follow_up.id or 0,
        ),
    )

    if not follow_ups:
        return "No follow-ups are recorded."

    return "\n".join(
        (
            f"- Follow-up #{follow_up.follow_up_number}: status={clean_value(follow_up.status)}, "
            f"subject={clean_value(follow_up.subject)}, body={_truncate(follow_up.body, 500)}, "
            f"sent_at={clean_value(follow_up.sent_at)}"
        )
        for follow_up in follow_ups
    )


def build_reply_classification_prompt(email_draft: EmailDraft):
    campaign = email_draft.campaign
    lead = email_draft.lead

    return f"""
You are a B2B sales reply classification assistant.
Classify the reply for B2B sales outreach.
Return valid JSON only. Do not include markdown, prose, or explanation outside JSON.
Do not write or send an automatic reply. Only suggest the next human-controlled action.

Campaign:
- campaign_name: {clean_value(campaign.campaign_name if campaign else "")}
- industry: {clean_value(campaign.industry if campaign else "")}
- location: {clean_value(campaign.location if campaign else "")}
- target_role: {clean_value(campaign.target_role if campaign else "")}
- offer: {clean_value(campaign.offer if campaign else "")}

Lead:
- company_name: {clean_value(lead.company_name if lead else "")}
- industry: {clean_value(lead.industry if lead else "")}
- location: {clean_value(lead.location if lead else "")}
- contact_name: {clean_value(lead.contact_name if lead else "")}
- contact_role: {clean_value(lead.contact_role if lead else "")}
- email: {clean_value(lead.email if lead else "")}

Original email:
- subject: {clean_value(email_draft.subject)}
- body: {clean_value(email_draft.body)}

Follow-up history:
{_format_follow_ups(email_draft)}

Reply:
- reply_snippet: {clean_value(email_draft.reply_snippet)}
- replied_at: {clean_value(email_draft.replied_at)}

Task:
Classify the reply for B2B sales outreach.

Expected JSON:
{{
  "intent": "Interested|Asked for Pricing|Asked for More Info|Meeting Request|Not Interested|Wrong Person|Out of Office|Unsubscribe|Neutral|Spam/Irrelevant|Unknown",
  "sentiment": "Positive|Neutral|Negative",
  "priority": "High|Medium|Low",
  "summary": "...",
  "next_action": "...",
  "suggested_response_direction": "..."
}}

Guidelines:
- If reply asks price, cost, quote, commercial details, or budget, intent = Asked for Pricing.
- If reply asks details, info, document, or demo video, intent = Asked for More Info or Interested.
- If reply asks for call, meeting, demo, or schedule, intent = Meeting Request.
- If reply says not interested, intent = Not Interested.
- If reply asks not to contact again, intent = Unsubscribe.
- If reply says wrong person, intent = Wrong Person.
- If reply says out of office, vacation, or unavailable, intent = Out of Office.
- If reply is unclear, intent = Neutral or Unknown.
- High priority for pricing, meeting, and strong interest.
- Medium priority for more info, wrong person, and out of office.
- Low priority for not interested, unsubscribe, and spam.
""".strip()


def parse_reply_classification_response(response_text: str, email_draft: EmailDraft):
    fallback_result = fallback_classify_reply(email_draft)
    parsed_response = extract_first_json_object(response_text)

    intent = _normalize_choice(parsed_response.get("intent"), ALLOWED_REPLY_INTENTS, fallback_result["intent"])
    sentiment = _normalize_choice(parsed_response.get("sentiment"), ALLOWED_REPLY_SENTIMENTS, fallback_result["sentiment"])
    priority = _normalize_choice(parsed_response.get("priority"), ALLOWED_REPLY_PRIORITIES, fallback_result["priority"])

    return {
        "intent": intent,
        "sentiment": sentiment,
        "priority": priority,
        "summary": _truncate(parsed_response.get("summary")) or fallback_result["summary"],
        "next_action": _truncate(parsed_response.get("next_action")) or fallback_result["next_action"],
        "suggested_response_direction": (
            _truncate(parsed_response.get("suggested_response_direction")) or
            fallback_result["suggested_response_direction"]
        ),
    }


def serialize_reply_classification(email_draft: EmailDraft):
    return {
        "email_draft_id": email_draft.id,
        "reply_intent": email_draft.reply_intent,
        "reply_sentiment": email_draft.reply_sentiment,
        "reply_priority": email_draft.reply_priority,
        "reply_summary": email_draft.reply_summary,
        "reply_next_action": email_draft.reply_next_action,
        "reply_suggested_response_direction": email_draft.reply_suggested_response_direction,
        "reply_classified_at": email_draft.reply_classified_at,
        "reply_classification_model": email_draft.reply_classification_model,
        "reply_classification_error": email_draft.reply_classification_error,
    }


def save_reply_classification(
    db: Session,
    email_draft: EmailDraft,
    result: dict,
    model_used: str | None,
    error_message: str | None = None,
):
    email_draft.reply_intent = _truncate(result["intent"], 100)
    email_draft.reply_sentiment = _truncate(result["sentiment"], 50)
    email_draft.reply_priority = _truncate(result["priority"], 50)
    email_draft.reply_summary = _truncate(result["summary"])
    email_draft.reply_next_action = _truncate(result["next_action"])
    email_draft.reply_suggested_response_direction = _truncate(result["suggested_response_direction"])
    email_draft.reply_classified_at = utc_now()
    email_draft.reply_classification_model = _truncate(model_used, 255) if model_used else None
    email_draft.reply_classification_error = error_message

    try:
        db.commit()
        db.refresh(email_draft)
    except SQLAlchemyError as exc:
        db.rollback()
        raise ReplyClassificationError("Reply classification could not be saved.") from exc


def classify_reply_for_draft(db: Session, email_draft: EmailDraft, force: bool = False) -> dict:
    if email_draft.status != "replied":
        raise ReplyClassificationRuleError("Only replied drafts can be classified.")

    if not clean_value(email_draft.reply_snippet):
        raise ReplyClassificationRuleError("No reply text available for classification.")

    if _is_classified(email_draft) and not force:
        return {
            "created": False,
            "message": "Existing reply classification returned",
            "data": serialize_reply_classification(email_draft),
        }

    result = None
    model_used = settings.GEMINI_MODEL
    error_message = None

    if settings.GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=build_reply_classification_prompt(email_draft),
            )
            response_text = clean_value(getattr(response, "text", ""))
            if not response_text:
                raise ValueError("Gemini reply classification response was empty.")
            result = parse_reply_classification_response(response_text, email_draft)
        except Exception:
            error_message = FALLBACK_CLASSIFICATION_ERROR
            result = fallback_classify_reply(email_draft)
            model_used = FALLBACK_CLASSIFICATION_MODEL
    else:
        error_message = FALLBACK_CLASSIFICATION_ERROR
        result = fallback_classify_reply(email_draft)
        model_used = FALLBACK_CLASSIFICATION_MODEL

    save_reply_classification(db, email_draft, result, model_used=model_used, error_message=error_message)

    return {
        "created": True,
        "message": "Reply classified successfully",
        "data": serialize_reply_classification(email_draft),
    }
