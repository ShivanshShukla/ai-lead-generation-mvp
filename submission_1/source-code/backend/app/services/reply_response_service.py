import json
import re

from google import genai
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import EmailDraft, ReplyResponseDraft
from app.services.ai_service import clean_value
from app.services.knowledge_service import search_relevant_knowledge
from app.services.lead_research_service import build_research_context
from app.utils.time_utils import utc_now

ACTIVE_RESPONSE_DRAFT_STATUSES = ("generated", "approved")
FALLBACK_RESPONSE_MODEL = "fallback-template"
FALLBACK_RESPONSE_ERROR = "Gemini response draft generation failed. Fallback draft was used."
MAX_STRUCTURED_KNOWLEDGE_CHARS = 3400
MAX_STRUCTURED_KNOWLEDGE_ENTRY_CHARS = 760
MAX_RESPONSE_WORDS = 160
PRICING_FACT_GROUPS = {
    "number of employees/team size": ("employees", "employee", "team size", "team-size"),
    "number of training modules": ("modules", "module", "training modules", "training module"),
    "analytics requirements": ("analytics", "dashboard", "reporting"),
}
DEMO_FACT_GROUPS = {
    "document/SOP upload": ("document", "documents", "sop", "sops", "training material", "training materials"),
    "video lessons": ("video", "videos", "lesson", "lessons"),
    "quizzes": ("quiz", "quizzes"),
    "analytics/dashboard": ("analytics", "dashboard"),
}
PILOT_TERMS = ("pilot", "pilots", "one department", "department", "3 to 5", "3-5", "limited modules")
PILOT_MODULE_RANGE_TERMS = ("3 to 5", "3-5", "3 5")
DEMO_REQUEST_TERMS = ("demo", "video", "walkthrough", "show", "overview")


class ReplyResponseRuleError(ValueError):
    pass


class ReplyResponseSaveError(RuntimeError):
    pass


def _truncate(value, max_length: int | None = None):
    text = clean_value(value)

    if max_length and len(text) > max_length:
        return text[:max_length].rstrip()

    return text


def _lead_display_name(email_draft: EmailDraft):
    lead = email_draft.lead

    return (
        clean_value(lead.contact_name if lead else "")
        or clean_value(lead.company_name if lead else "")
        or "there"
    )


def _build_subject(email_draft: EmailDraft):
    subject = clean_value(email_draft.subject) or "Your reply"

    if subject.lower().startswith("re:"):
        return subject[:255]

    return f"Re: {subject}"[:255]


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

    raise ValueError("No valid JSON object found in Gemini response draft output.")


def _normalize_text(value):
    return clean_value(value).lower()


def _contains_any(value, terms):
    normalized_value = _normalize_text(value)

    return any(term in normalized_value for term in terms)


def _matching_fact_groups(value, fact_groups):
    return [
        label
        for label, terms in fact_groups.items()
        if _contains_any(value, terms)
    ]


def _human_join(items):
    clean_items = [clean_value(item) for item in items if clean_value(item)]

    if not clean_items:
        return ""

    if len(clean_items) == 1:
        return clean_items[0]

    return f"{', '.join(clean_items[:-1])}, and {clean_items[-1]}"


def _lead_asks_for_demo(email_draft: EmailDraft):
    search_text = " ".join(
        clean_value(value)
        for value in [
            email_draft.reply_snippet,
            email_draft.reply_summary,
            email_draft.reply_next_action,
            email_draft.reply_suggested_response_direction,
            email_draft.reply_intent,
        ]
        if clean_value(value)
    )

    return _contains_any(search_text, DEMO_REQUEST_TERMS)


def _truncate_sentence(value, max_length: int):
    text = " ".join(clean_value(value).split())

    if len(text) <= max_length:
        return text

    return f"{text[:max_length].rstrip()}..."


def _word_count(value):
    return len(re.findall(r"\S+", clean_value(value)))


def _trim_to_word_limit(value, max_words=MAX_RESPONSE_WORDS):
    text = clean_value(value)
    words = re.findall(r"\S+", text)

    if len(words) <= max_words:
        return text

    closing = "\n\nRegards,\nTeam"

    if closing in text:
        main_text, _ = text.split(closing, 1)
        closing_words = re.findall(r"\S+", closing)
        main_words = re.findall(r"\S+", main_text)
        allowed_main_words = max(max_words - len(closing_words), 1)

        return f"{' '.join(main_words[:allowed_main_words]).rstrip()}{closing}"

    return " ".join(words[:max_words]).rstrip()


def _entry_source_label(entry):
    title = clean_value(entry.title)
    document = getattr(entry, "document", None)
    document_name = clean_value(getattr(document, "original_filename", ""))

    if document_name and entry.chunk_index:
        return f"{document_name} - Chunk {entry.chunk_index}"

    if title:
        return title

    if document_name:
        return document_name

    return f"Knowledge entry {entry.id}"


def build_structured_response_knowledge(entries):
    blocks = []
    total_chars = 0

    for entry in entries:
        source = _entry_source_label(entry)
        facts = _truncate_sentence(entry.content, MAX_STRUCTURED_KNOWLEDGE_ENTRY_CHARS)

        if not source or not facts:
            continue

        block = f"- Source: {source}\n  Facts:\n  {facts}"
        remaining_chars = MAX_STRUCTURED_KNOWLEDGE_CHARS - total_chars

        if remaining_chars <= 0:
            break

        if len(block) > remaining_chars:
            block = f"{block[:remaining_chars].rstrip()}..."

        blocks.append(block)
        total_chars += len(block)

    if not blocks:
        return ""

    return "RELEVANT COMPANY KNOWLEDGE:\n" + "\n\n".join(blocks)


def _pricing_fallback_sentences(knowledge_context: str):
    factors = _matching_fact_groups(knowledge_context, PRICING_FACT_GROUPS)
    sentences = []

    if factors:
        sentences.append(f"Pricing depends on {_human_join(factors)}.")

    pilot_sentence = _build_pilot_guidance_sentence(knowledge_context)

    if pilot_sentence:
        sentences.append(pilot_sentence)

    return sentences


def _build_pilot_guidance_sentence(knowledge_context: str):
    if not _contains_any(knowledge_context, PILOT_TERMS):
        return ""

    has_mvp = _contains_any(knowledge_context, ("mvp pilot", "mvp pilots", "mvp"))
    has_one_department = _contains_any(
        knowledge_context,
        ("one department", "start with one department", "starting with one department")
    )
    has_department = has_one_department or _contains_any(knowledge_context, ("department", "departments"))
    has_module_range = _contains_any(knowledge_context, PILOT_MODULE_RANGE_TERMS)
    has_limited_modules = _contains_any(knowledge_context, ("limited modules", "limited training modules"))
    has_modules = has_module_range or has_limited_modules or _contains_any(
        knowledge_context,
        ("training modules", "modules")
    )
    pilot_intro = "For an MVP pilot" if has_mvp else "For a pilot"

    if has_one_department and has_module_range:
        return (
            f"{pilot_intro}, we usually recommend starting with one department "
            "and 3 to 5 training modules before scaling."
        )

    if has_one_department and has_limited_modules:
        return (
            f"{pilot_intro}, we usually recommend starting with one department "
            "and limited training modules before scaling."
        )

    if has_one_department:
        return f"{pilot_intro}, we usually recommend starting with one department before scaling."

    if has_module_range:
        return f"{pilot_intro}, we usually recommend starting with 3 to 5 training modules before scaling."

    if has_department and has_modules:
        return (
            f"{pilot_intro}, we usually recommend starting with one focused department "
            "and a limited set of training modules before scaling."
        )

    if has_department:
        return f"{pilot_intro}, we usually recommend starting with a focused department before scaling."

    if has_limited_modules:
        return f"{pilot_intro}, we usually recommend starting with limited training modules before scaling."

    return ""


def _pilot_guidance_covered(response_body: str, knowledge_context: str):
    pilot_sentence = _build_pilot_guidance_sentence(knowledge_context)

    if not pilot_sentence:
        return True

    checks = []

    if _contains_any(pilot_sentence, ("one department", "focused department")):
        checks.append(_contains_any(response_body, ("one department", "focused department", "department")))

    if _contains_any(pilot_sentence, PILOT_MODULE_RANGE_TERMS):
        checks.append(_contains_any(response_body, PILOT_MODULE_RANGE_TERMS))

    if _contains_any(pilot_sentence, ("limited training modules", "limited set of training modules")):
        checks.append(_contains_any(response_body, ("limited modules", "limited training modules", "limited set")))

    if not checks:
        checks.append(_contains_any(response_body, ("pilot", "pilots")))

    return all(checks)


def _append_sentence_before_signoff(body: str, sentence: str):
    clean_body = clean_value(body)
    clean_sentence = clean_value(sentence)

    if not clean_body or not clean_sentence:
        return clean_body

    if clean_sentence.lower() in clean_body.lower():
        return clean_body

    closing = "\n\nRegards,\nTeam"

    if closing in clean_body:
        main_text, rest = clean_body.split(closing, 1)
        return f"{main_text.rstrip()}\n\n{clean_sentence}{closing}{rest}"

    return f"{clean_body.rstrip()}\n\n{clean_sentence}"


def _ensure_pricing_pilot_guidance(generated_response: dict, email_draft: EmailDraft, knowledge_context: str):
    if clean_value(email_draft.reply_intent) != "Asked for Pricing":
        return generated_response

    pilot_sentence = _build_pilot_guidance_sentence(knowledge_context)

    if not pilot_sentence or _pilot_guidance_covered(generated_response.get("body"), knowledge_context):
        return generated_response

    return {
        **generated_response,
        "body": _trim_to_word_limit(
            _append_sentence_before_signoff(generated_response.get("body"), pilot_sentence)
        ),
    }


def _demo_fallback_sentence(knowledge_context: str):
    demo_facts = _matching_fact_groups(knowledge_context, DEMO_FACT_GROUPS)

    if not demo_facts:
        return ""

    return f"In a demo, we can show {_human_join(demo_facts)}."


def fallback_response_draft(email_draft: EmailDraft, knowledge_context: str = ""):
    name = _lead_display_name(email_draft)
    intent = clean_value(email_draft.reply_intent) or "Neutral"
    offer = clean_value(email_draft.campaign.offer if email_draft.campaign else "")
    has_knowledge_context = bool(clean_value(knowledge_context))
    asks_for_demo = _lead_asks_for_demo(email_draft)
    offer_sentence = (
        f"Our system helps teams with {offer}."
        if offer
        else "Our system helps teams make training and onboarding easier to manage."
    )

    if intent == "Asked for Pricing":
        knowledge_sentences = _pricing_fallback_sentences(knowledge_context) if has_knowledge_context else []
        demo_sentence = _demo_fallback_sentence(knowledge_context) if has_knowledge_context and asks_for_demo else ""
        knowledge_detail = " ".join(knowledge_sentences + ([demo_sentence] if demo_sentence else []))
        pricing_detail = (
            knowledge_detail
            if knowledge_detail
            else "Pricing usually depends on the team size, use case, and the level of setup needed, so I do not want to guess without a little more context."
        )
        body = (
            f"Hi {name},\n\n"
            f"Thanks for your reply. {pricing_detail}\n\n"
            "I can share a short demo overview and discuss the right pricing range after understanding your requirements. "
            "Would a brief call be convenient this week?\n\n"
            "Regards,\nTeam"
        )
    elif intent in {"Asked for More Info", "Interested"}:
        demo_sentence = _demo_fallback_sentence(knowledge_context) if has_knowledge_context and asks_for_demo else ""
        detail_sentence = demo_sentence or f"{offer_sentence} It can help with onboarding, SOP training, quizzes, and visibility into employee progress."
        body = (
            f"Hi {name},\n\n"
            f"Thanks for your reply. {detail_sentence}\n\n"
            "I can share a short overview and walk you through how it would fit your team. Would you like to schedule a brief demo?\n\n"
            "Regards,\nTeam"
        )
    elif intent == "Meeting Request":
        body = (
            f"Hi {name},\n\n"
            "Thanks for your reply. Happy to set up a short call to discuss this.\n\n"
            "Please share a suitable time, or I can send across a few available slots for this week.\n\n"
            "Regards,\nTeam"
        )
    elif intent in {"Not Interested", "Unsubscribe"}:
        body = (
            f"Hi {name},\n\n"
            "Thanks for letting me know. I understand, and we will not follow up further on this.\n\n"
            "Regards,\nTeam"
        )
    elif intent == "Wrong Person":
        body = (
            f"Hi {name},\n\n"
            "Thanks for letting me know. Would you be able to point me to the right HR, training, or operations contact for this discussion?\n\n"
            "If not, no problem at all.\n\n"
            "Regards,\nTeam"
        )
    elif intent == "Out of Office":
        body = (
            f"Hi {name},\n\n"
            "Thanks for the update. I will follow up later when the timing is better.\n\n"
            "Regards,\nTeam"
        )
    else:
        body = (
            f"Hi {name},\n\n"
            "Thanks for your reply. Could you let me know what information would be most helpful for you at this stage?\n\n"
            "I can keep it brief and share only the details that are relevant.\n\n"
            "Regards,\nTeam"
        )

    return {
        "subject": _build_subject(email_draft),
        "body": body,
    }


def build_response_knowledge_query(email_draft: EmailDraft):
    campaign = email_draft.campaign

    return " ".join(
        part
        for part in [
            clean_value(email_draft.reply_intent),
            clean_value(email_draft.reply_summary),
            clean_value(email_draft.reply_next_action),
            clean_value(email_draft.reply_suggested_response_direction),
            clean_value(email_draft.reply_snippet),
            clean_value(campaign.offer if campaign else ""),
            clean_value(email_draft.lead.research_summary if email_draft.lead else ""),
            clean_value(email_draft.lead.research_outreach_angle if email_draft.lead else ""),
            clean_value(email_draft.lead.research_pain_points if email_draft.lead else ""),
        ]
        if part
    )


def format_knowledge_used(entries):
    labels = []

    for entry in entries:
        title = clean_value(entry.title)

        if not title:
            continue

        source_type = clean_value(entry.source_type).lower()
        source_label = "Document" if source_type == "document" else "Manual"
        labels.append(f"{title} ({source_label})")

    return ", ".join(labels) or None


def build_response_prompt(email_draft: EmailDraft, knowledge_context: str = "", extra_instruction: str = ""):
    campaign = email_draft.campaign
    lead = email_draft.lead
    has_knowledge_context = bool(clean_value(knowledge_context))
    pilot_guidance_sentence = _build_pilot_guidance_sentence(knowledge_context)
    research_context = build_research_context(lead)
    knowledge_section = (
        knowledge_context
        if has_knowledge_context
        else "No matching company knowledge was found."
    )
    research_section = (
        research_context
        if research_context
        else "No AI lead research is available. Use only the reply, campaign, lead, and knowledge context."
    )
    grounding_instruction = (
        """
Use the retrieved company knowledge explicitly. Prefer exact facts from the knowledge context over generic wording.
If the lead asks pricing, mention the pricing factors found in knowledge, especially employees/team size, training modules, and analytics requirements when present.
If pilot guidance exists, mention it.
If demo details exist, mention what the demo shows.
For pricing intent, include at least two retrieved pricing factors when available and do not give a fixed price unless an exact price is present in knowledge.
For demo intent, include retrieved demo details such as document/SOP upload, video lessons, quizzes, and analytics/dashboard when available.
Do not invent exact prices.
"""
        if has_knowledge_context
        else "No matching company knowledge was found, so avoid specific product, pricing, pilot, or demo claims that are not in the outreach context."
    ).strip()
    pilot_instruction = (
        f'For pricing replies, include this pilot guidance if it fits naturally: "{pilot_guidance_sentence}"'
        if pilot_guidance_sentence
        else "Only mention pilot guidance if the retrieved knowledge includes pilot, department, or module guidance."
    )
    retry_instruction = clean_value(extra_instruction)

    return f"""
You are an AI sales assistant.
Write a professional reply email draft based on the lead's reply.
Keep it concise, helpful, and non-pushy.
Use the company knowledge below if relevant.
Use AI lead research when it helps personalize the response, but do not overclaim uncertain pain points.
Do not invent details not present in the company knowledge or outreach context.
If pricing is not found in company knowledge, say pricing depends on requirements instead of making up prices.
Do not invent exact pricing if pricing data is not available.
If the lead asks for pricing, explain that pricing depends on requirements and include the exact pricing factors from knowledge when available.
If the lead asks for more info or a demo, briefly explain product value using demo facts from knowledge when available.
If the lead asks for meeting, suggest sharing available slots.
If the lead is not interested or unsubscribes, generate a polite acknowledgement and do not push.
If wrong person, ask politely for the right contact.
If out of office, draft a short acknowledgement and mention follow-up later.
Do not claim attachments or links are included unless available.
Do not send the email. Only draft it for human approval.
Keep the response draft under 160 words.
Return only JSON.

Knowledge grounding rules:
{grounding_instruction}
{pilot_instruction}

Additional instruction:
{retry_instruction or "None"}

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

AI lead research:
{research_section}

Original email:
- subject: {clean_value(email_draft.subject)}
- body: {clean_value(email_draft.body)}

Reply:
- reply_snippet: {clean_value(email_draft.reply_snippet)}
- replied_at: {clean_value(email_draft.replied_at)}

Classification:
- reply_intent: {clean_value(email_draft.reply_intent)}
- reply_sentiment: {clean_value(email_draft.reply_sentiment)}
- reply_priority: {clean_value(email_draft.reply_priority)}
- reply_summary: {clean_value(email_draft.reply_summary)}
- reply_next_action: {clean_value(email_draft.reply_next_action)}
- reply_suggested_response_direction: {clean_value(email_draft.reply_suggested_response_direction)}

Company knowledge:
{knowledge_section}

Expected JSON:
{{
  "subject": "...",
  "body": "..."
}}
""".strip()


def parse_response_draft_output(response_text: str, email_draft: EmailDraft, knowledge_context: str = ""):
    fallback = fallback_response_draft(email_draft, knowledge_context)
    parsed_response = extract_first_json_object(response_text)
    subject = _truncate(parsed_response.get("subject"), 255) or fallback["subject"]
    body = _truncate(parsed_response.get("body")) or fallback["body"]

    return {
        "subject": subject,
        "body": body,
    }


def _response_grounding_issue(email_draft: EmailDraft, generated_response: dict, knowledge_context: str):
    body = clean_value(generated_response.get("body"))

    if not clean_value(knowledge_context) or not body:
        return None

    expected_pricing_facts = _matching_fact_groups(knowledge_context, PRICING_FACT_GROUPS)
    mentioned_pricing_facts = _matching_fact_groups(body, PRICING_FACT_GROUPS)

    pilot_guidance_sentence = _build_pilot_guidance_sentence(knowledge_context)
    expected_pilot_guidance = bool(pilot_guidance_sentence)
    mentioned_pilot_guidance = _pilot_guidance_covered(body, knowledge_context)

    if clean_value(email_draft.reply_intent) == "Asked for Pricing" and (
        (
            expected_pricing_facts
            and len(mentioned_pricing_facts) < min(2, len(expected_pricing_facts))
        )
        or (expected_pilot_guidance and not mentioned_pilot_guidance)
    ):
        pricing_instruction = (
            f"Explicitly mention at least two of these retrieved pricing factors: {_human_join(expected_pricing_facts)}. "
            if expected_pricing_facts
            else ""
        )

        return (
            "Regenerate the response because the lead asked for pricing and the previous draft was too generic. "
            f"{pricing_instruction}"
            f"Include this pilot sentence if it fits naturally: \"{pilot_guidance_sentence}\" "
            "Do not invent exact prices."
        )

    if _lead_asks_for_demo(email_draft):
        expected_demo_facts = _matching_fact_groups(knowledge_context, DEMO_FACT_GROUPS)
        mentioned_demo_facts = _matching_fact_groups(body, DEMO_FACT_GROUPS)

        if expected_demo_facts and len(mentioned_demo_facts) < len(expected_demo_facts):
            return (
                "Regenerate the response because the lead asked for a demo and the previous draft missed retrieved demo facts. "
                f"Explicitly mention demo details from knowledge such as {_human_join(expected_demo_facts)} when relevant. "
                "Do not claim a link or attachment is included."
            )

    return None


def _generate_gemini_response(client, email_draft: EmailDraft, knowledge_context: str, extra_instruction: str = ""):
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=build_response_prompt(email_draft, knowledge_context, extra_instruction=extra_instruction),
    )
    response_text = clean_value(getattr(response, "text", ""))

    if not response_text:
        raise ValueError("Gemini response draft output was empty.")

    return parse_response_draft_output(response_text, email_draft, knowledge_context)


def get_active_response_draft(db: Session, email_draft_id: int):
    return (
        db.query(ReplyResponseDraft)
        .filter(
            ReplyResponseDraft.original_email_draft_id == email_draft_id,
            ReplyResponseDraft.status.in_(ACTIVE_RESPONSE_DRAFT_STATUSES),
        )
        .order_by(ReplyResponseDraft.created_at.desc(), ReplyResponseDraft.id.desc())
        .first()
    )


def _reject_active_response_drafts(db: Session, email_draft_id: int):
    active_drafts = (
        db.query(ReplyResponseDraft)
        .filter(
            ReplyResponseDraft.original_email_draft_id == email_draft_id,
            ReplyResponseDraft.status.in_(ACTIVE_RESPONSE_DRAFT_STATUSES),
        )
        .all()
    )
    now = utc_now()

    for response_draft in active_drafts:
        response_draft.status = "rejected"
        response_draft.rejected_at = now


def _ensure_generation_allowed(email_draft: EmailDraft):
    if email_draft.status != "replied":
        raise ReplyResponseRuleError("Only replied emails can have response drafts.")

    if not clean_value(email_draft.reply_snippet):
        raise ReplyResponseRuleError("No reply text available for response draft generation.")

    if not clean_value(email_draft.reply_intent):
        raise ReplyResponseRuleError("Please classify the reply before generating a response draft.")


def _save_response_draft(db: Session, response_draft: ReplyResponseDraft):
    try:
        db.add(response_draft)
        db.commit()
        db.refresh(response_draft)
    except SQLAlchemyError as exc:
        db.rollback()
        raise ReplyResponseSaveError("Response draft could not be saved.") from exc


def generate_response_draft_for_reply(db: Session, email_draft: EmailDraft, force: bool = False) -> dict:
    _ensure_generation_allowed(email_draft)

    existing_response_draft = get_active_response_draft(db, email_draft.id)

    if existing_response_draft and not force:
        return {
            "created": False,
            "message": "Existing response draft returned",
            "response_draft": existing_response_draft,
        }

    if force and existing_response_draft:
        _reject_active_response_drafts(db, email_draft.id)

    model_used = settings.GEMINI_MODEL
    send_error = None
    knowledge_entries = search_relevant_knowledge(
        db,
        build_response_knowledge_query(email_draft),
        limit=5,
    )
    knowledge_context = build_structured_response_knowledge(knowledge_entries)
    knowledge_used = format_knowledge_used(knowledge_entries)

    if settings.GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            generated_response = _generate_gemini_response(client, email_draft, knowledge_context)
            grounding_issue = _response_grounding_issue(email_draft, generated_response, knowledge_context)

            if grounding_issue:
                try:
                    generated_response = _generate_gemini_response(
                        client,
                        email_draft,
                        knowledge_context,
                        extra_instruction=grounding_issue,
                    )
                except Exception:
                    pass

            generated_response = _ensure_pricing_pilot_guidance(
                generated_response,
                email_draft,
                knowledge_context,
            )
        except Exception:
            generated_response = fallback_response_draft(email_draft, knowledge_context)
            model_used = FALLBACK_RESPONSE_MODEL
            send_error = FALLBACK_RESPONSE_ERROR
    else:
        generated_response = fallback_response_draft(email_draft, knowledge_context)
        model_used = FALLBACK_RESPONSE_MODEL
        send_error = FALLBACK_RESPONSE_ERROR

    now = utc_now()
    response_draft = ReplyResponseDraft(
        original_email_draft_id=email_draft.id,
        campaign_id=email_draft.campaign_id,
        lead_id=email_draft.lead_id,
        subject=generated_response["subject"][:255],
        body=generated_response["body"],
        status="generated",
        intent_used=email_draft.reply_intent,
        next_action_used=email_draft.reply_next_action,
        knowledge_used=knowledge_used,
        model_used=model_used,
        generated_at=now,
        send_error=send_error,
    )

    _save_response_draft(db, response_draft)

    return {
        "created": True,
        "message": "Response draft generated successfully",
        "response_draft": response_draft,
    }
