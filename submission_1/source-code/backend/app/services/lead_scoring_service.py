import re
from urllib.parse import urlparse

from google import genai
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Campaign, Lead
from app.services.ai_service import clean_value, extract_json_from_text
from app.services.lead_research_service import build_research_context
from app.utils.time_utils import utc_now

VALID_DECISION_MAKER_KEYWORDS = (
    "hr",
    "human resources",
    "training",
    "learning",
    "l&d",
    "operations",
    "operation",
    "ops",
    "admin",
    "founder",
    "owner",
    "director",
    "head",
    "manager",
    "chief",
    "ceo",
    "coo",
    "people",
    "talent",
)
RELATED_MANAGER_KEYWORDS = ("manager", "head", "lead", "supervisor", "coordinator")
PERSONAL_EMAIL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "icloud.com",
    "protonmail.com",
    "live.com",
    "msn.com",
    "rediffmail.com",
    "aol.com",
}
GENERIC_EMAIL_LOCAL_PARTS = {
    "info",
    "contact",
    "hello",
    "sales",
    "support",
    "hr",
    "admin",
    "careers",
    "enquiry",
    "inquiry",
    "inquiries",
    "marketing",
}
STUDENT_DOMAIN_KEYWORDS = (
    "student",
    "students",
    "edu",
    "ac.in",
    "college",
    "university",
    "school",
    "institute",
    "campus",
)
INDIAN_LOCATION_KEYWORDS = (
    "india",
    "pune",
    "mumbai",
    "delhi",
    "bengaluru",
    "bangalore",
    "chennai",
    "hyderabad",
    "ahmedabad",
    "kolkata",
    "noida",
    "gurgaon",
    "gurugram",
    "jamshedpur",
    "nagpur",
    "surat",
    "vadodara",
    "coimbatore",
    "indore",
    "jaipur",
)
MANUFACTURING_TERMS = (
    "manufacturing",
    "manufacturer",
    "factory",
    "plant",
    "industrial",
    "production",
    "steel",
    "automotive",
    "auto",
    "component",
    "machinery",
    "engineering",
    "bosch",
    "tata steel",
)
TRAINING_TERMS = (
    "training",
    "corporate training",
    "learning",
    "onboarding",
    "employee",
    "hr",
    "sop",
    "l&d",
    "education",
    "edtech",
    "course",
    "academy",
    "simplilearn",
)
COMPANY_STOP_WORDS = {
    "india",
    "pvt",
    "ltd",
    "limited",
    "private",
    "inc",
    "llc",
    "company",
    "corp",
    "corporation",
    "group",
    "the",
}


class LeadScoringError(RuntimeError):
    pass


def clamp_score(score):
    try:
        numeric_score = int(round(float(score)))
    except (TypeError, ValueError):
        return None

    return max(0, min(numeric_score, 100))


def get_priority_for_score(score: int):
    if score >= 80:
        return "High"
    if score >= 50:
        return "Medium"
    return "Low"


def get_qualification_for_score(score: int):
    if score >= 80:
        return "Hot"
    if score >= 60:
        return "Warm"
    if score >= 30:
        return "Cold"
    return "Not Relevant"


def get_final_score(fit_score: int, contact_confidence_score: int):
    return round((fit_score * 0.75) + (contact_confidence_score * 0.25))


def contains_match(left_value, right_value):
    left = clean_value(left_value).lower()
    right = clean_value(right_value).lower()

    return bool(left and right and (left in right or right in left))


def tokenize(value):
    return [
        token
        for token in re.split(r"[^a-z0-9]+", clean_value(value).lower())
        if len(token) >= 3
    ]


def text_contains_any(value, keywords):
    text = clean_value(value).lower()

    return any(keyword in text for keyword in keywords)


def get_combined_lead_text(lead: Lead):
    return " ".join(
        clean_value(value)
        for value in (
            lead.company_name,
            lead.industry,
            lead.contact_role,
            lead.location,
            lead.website,
        )
        if clean_value(value)
    )


def has_direct_role_match(lead_role, campaign_role):
    lead_text = clean_value(lead_role).lower()
    campaign_text = clean_value(campaign_role).lower()

    if contains_match(lead_text, campaign_text):
        return True

    target_roles = [
        role.strip()
        for role in re.split(r"[/,|]+", campaign_text)
        if role.strip()
    ]

    return any(role and (role in lead_text or lead_text in role) for role in target_roles)


def has_valid_decision_maker_role(lead_role):
    role_text = clean_value(lead_role).lower()

    return any(keyword in role_text for keyword in VALID_DECISION_MAKER_KEYWORDS)


def has_related_manager_role(lead_role):
    role_text = clean_value(lead_role).lower()

    return any(keyword in role_text for keyword in RELATED_MANAGER_KEYWORDS)


def get_industry_match_level(campaign: Campaign, lead: Lead):
    campaign_text = f"{clean_value(campaign.industry)} {clean_value(campaign.offer)}".lower()
    lead_text = get_combined_lead_text(lead).lower()

    if contains_match(lead.industry, campaign.industry):
        return "direct"

    campaign_tokens = set(tokenize(campaign.industry))
    lead_tokens = set(tokenize(f"{lead.industry} {lead.company_name}"))
    shared_tokens = campaign_tokens.intersection(lead_tokens)

    if shared_tokens:
        return "direct"

    campaign_has_manufacturing = text_contains_any(campaign_text, MANUFACTURING_TERMS)
    lead_has_manufacturing = text_contains_any(lead_text, MANUFACTURING_TERMS)
    campaign_has_training = text_contains_any(campaign_text, TRAINING_TERMS)
    lead_has_training = text_contains_any(lead_text, TRAINING_TERMS)

    if (
        (campaign_has_manufacturing and lead_has_manufacturing) or
        (campaign_has_training and lead_has_training)
    ):
        return "related"

    if (
        (campaign_has_manufacturing and lead_has_training) or
        (campaign_has_training and lead_has_manufacturing)
    ):
        return "adjacent"

    return "none"


def get_location_score(campaign_location, lead_location):
    campaign_text = clean_value(campaign_location).lower()
    lead_text = clean_value(lead_location).lower()

    if not lead_text:
        return 0

    if contains_match(campaign_text, lead_text):
        return 15

    if "india" in campaign_text and text_contains_any(lead_text, INDIAN_LOCATION_KEYWORDS):
        return 10

    return 5


def has_likely_offer_relevance(campaign: Campaign, lead: Lead):
    offer_text = clean_value(campaign.offer).lower()
    lead_text = " ".join(
        part
        for part in [
            get_combined_lead_text(lead),
            clean_value(getattr(lead, "research_summary", "")),
            clean_value(getattr(lead, "research_business_type", "")),
            clean_value(getattr(lead, "research_products_services", "")),
            clean_value(getattr(lead, "research_use_case_fit", "")),
        ]
        if part
    ).lower()
    offer_tokens = {
        token
        for token in tokenize(offer_text)
        if token not in {"software", "service", "services", "system", "solution", "solutions", "platform", "tool", "tools"}
    }
    lead_tokens = set(tokenize(lead_text))

    return (
        bool(offer_text)
        and (
            bool(offer_tokens.intersection(lead_tokens))
            or has_direct_role_match(lead.contact_role, campaign.target_role)
            or contains_match(lead.industry, campaign.industry)
        )
    )


def is_training_vendor_like(lead: Lead):
    lead_text = get_combined_lead_text(lead).lower()

    return (
        text_contains_any(lead_text, ("edtech", "education", "academy", "course", "online learning", "simplilearn")) or
        ("training" in lead_text and not text_contains_any(lead_text, MANUFACTURING_TERMS))
    )


def get_domain_from_email(email):
    email_value = clean_value(email).lower()

    if "@" not in email_value:
        return ""

    return email_value.rsplit("@", 1)[1].strip()


def get_local_part_from_email(email):
    email_value = clean_value(email).lower()

    if "@" not in email_value:
        return ""

    return email_value.split("@", 1)[0].strip()


def normalize_domain(domain):
    domain_value = clean_value(domain).lower().replace("www.", "")

    return domain_value.strip("/")


def get_domain_from_website(website):
    website_value = clean_value(website)

    if not website_value:
        return ""

    parsed_url = urlparse(website_value if "://" in website_value else f"https://{website_value}")

    return normalize_domain(parsed_url.netloc or parsed_url.path)


def is_example_website(website):
    domain = get_domain_from_website(website)

    return domain in {"example.com", "www.example.com"} or domain.endswith(".example.com")


def is_personal_email_domain(domain):
    return normalize_domain(domain) in PERSONAL_EMAIL_DOMAINS


def is_student_or_institute_domain(domain):
    normalized_domain = normalize_domain(domain)

    return any(keyword in normalized_domain for keyword in STUDENT_DOMAIN_KEYWORDS)


def get_company_tokens(company_name):
    return [
        token
        for token in tokenize(company_name)
        if token not in COMPANY_STOP_WORDS
    ]


def domain_matches_company_or_website(email_domain, website, company_name):
    normalized_email_domain = normalize_domain(email_domain)
    website_domain = get_domain_from_website(website)

    if not normalized_email_domain:
        return False

    if website_domain and (
        normalized_email_domain == website_domain or
        normalized_email_domain.endswith(f".{website_domain}") or
        website_domain.endswith(f".{normalized_email_domain}")
    ):
        return True

    return any(token in normalized_email_domain for token in get_company_tokens(company_name))


def has_specific_contact_name(contact_name):
    contact_text = clean_value(contact_name).lower()

    if not contact_text or contact_text in {"test", "student", "admin", "owner", "na", "n/a"}:
        return False

    return len(tokenize(contact_text)) >= 1


def get_contact_confidence_score(lead: Lead):
    score = 20
    reasons = []
    email = clean_value(lead.email)
    email_domain = get_domain_from_email(email)
    local_part = get_local_part_from_email(email)
    website_is_usable = bool(clean_value(lead.website)) and not is_example_website(lead.website)
    contact_cap = 100

    if email:
        score += 30

        if is_student_or_institute_domain(email_domain):
            score += 10
            contact_cap = 45
            reasons.append("The email appears to be a student or institute address, so contact confidence is limited.")
        elif is_personal_email_domain(email_domain):
            score += 15
            contact_cap = 55
            reasons.append("The email is a personal address, so it is usable for testing but should be replaced with a corporate contact.")
        else:
            if domain_matches_company_or_website(email_domain, lead.website, lead.company_name):
                score += 30
                reasons.append("The email domain appears to match the company or website.")
            else:
                score += 20
                reasons.append("The email is non-personal, but the domain does not clearly match the company.")

            if local_part in GENERIC_EMAIL_LOCAL_PARTS:
                contact_cap = min(contact_cap, 80)
                reasons.append("The email is generic rather than a named business contact.")
    else:
        contact_cap = 25
        reasons.append("No email is available, so outreach readiness is low until a contact is found.")

    if website_is_usable:
        score += 10
    elif clean_value(lead.website):
        reasons.append("The website looks like placeholder data.")

    if has_specific_contact_name(lead.contact_name):
        score += 5

    if clean_value(lead.contact_role):
        score += 5

    if email and is_student_or_institute_domain(email_domain):
        score -= 10

    score = min(clamp_score(score) or 0, contact_cap)

    if not reasons:
        reasons.append("Contact details look usable for outreach.")

    return score, " ".join(reasons)


def get_contact_confidence_cap(lead: Lead):
    email = clean_value(lead.email)

    if not email:
        return 25

    email_domain = get_domain_from_email(email)

    if is_student_or_institute_domain(email_domain):
        return 45

    if is_personal_email_domain(email_domain):
        return 55

    if get_local_part_from_email(email) in GENERIC_EMAIL_LOCAL_PARTS:
        return 80

    return 100


def fallback_score_lead(campaign: Campaign, lead: Lead):
    fit_score = 20
    industry_level = get_industry_match_level(campaign, lead)

    if industry_level == "direct":
        fit_score += 35
    elif industry_level == "related":
        fit_score += 25
    elif industry_level == "adjacent":
        fit_score += 15

    if has_direct_role_match(lead.contact_role, campaign.target_role):
        fit_score += 25
    elif has_valid_decision_maker_role(lead.contact_role):
        fit_score += 20
    elif has_related_manager_role(lead.contact_role):
        fit_score += 10

    fit_score += get_location_score(campaign.location, lead.location)

    if has_likely_offer_relevance(campaign, lead):
        fit_score += 15
    elif clean_value(campaign.offer) and (clean_value(lead.industry) or clean_value(lead.contact_role)):
        fit_score += 8

    research_context = build_research_context(lead)
    research_confidence = clamp_score(getattr(lead, "research_confidence", None))

    if research_context and research_confidence is not None:
        if research_confidence >= 70:
            fit_score += 8
        elif research_confidence >= 45:
            fit_score += 4

        if text_contains_any(getattr(lead, "research_use_case_fit", ""), ("low fit", "not relevant", "unrelated")):
            fit_score -= 10

    fit_score = min(fit_score, 95)

    if is_training_vendor_like(lead) and text_contains_any(campaign.offer, ("employee", "onboarding", "sop", "hr analytics")):
        fit_score = min(fit_score, 75)

    fit_score = clamp_score(fit_score) or 0
    contact_confidence_score, contact_confidence_reason = get_contact_confidence_score(lead)
    score = get_final_score(fit_score, contact_confidence_score)
    priority = get_priority_for_score(score)
    qualification = get_qualification_for_score(fit_score)
    company_name = clean_value(lead.company_name) or "This lead"
    campaign_offer = clean_value(campaign.offer) or "the campaign offer"

    if contact_confidence_score < 60:
        final_priority_reason = (
            f"{company_name} has strong company fit when the fit score is high, but outreach readiness is reduced "
            "because the contact data should be improved before serious outreach."
        )
    else:
        final_priority_reason = (
            f"{company_name} has a final readiness score based mostly on business fit with contact confidence as a secondary factor."
        )

    research_note = (
        f" Research confidence is {research_confidence}/100 and was included in the fit review."
        if research_context and research_confidence is not None
        else ""
    )

    return {
        "score": score,
        "fit_score": fit_score,
        "contact_confidence_score": contact_confidence_score,
        "priority": priority,
        "qualification": qualification,
        "reason": (
            f"{company_name} was scored for business fit using company, industry, role, location, "
            f"offer relevance, and likely pain point signals.{research_note}"
        ),
        "contact_confidence_reason": contact_confidence_reason,
        "outreach_angle": f"Connect the lead's role and company context to {campaign_offer}.",
        "pain_point": "The lead may need a clearer, faster way to evaluate and adopt the offered solution.",
        "recommended_cta": "Ask whether a short call would be useful to explore fit.",
        "final_priority_reason": final_priority_reason,
    }


def build_lead_scoring_prompt(campaign: Campaign, lead: Lead):
    research_context = build_research_context(lead)
    research_section = (
        research_context
        if research_context
        else "No AI lead research is available. Use only campaign and lead fields."
    )

    return f"""
You are a B2B sales lead qualification assistant.
Evaluate how well this lead fits the campaign.
Return only JSON.

Campaign:
- Campaign name: {clean_value(campaign.campaign_name)}
- Industry: {clean_value(campaign.industry)}
- Location: {clean_value(campaign.location)}
- Target role: {clean_value(campaign.target_role)}
- Offer: {clean_value(campaign.offer)}

Lead:
- Company name: {clean_value(lead.company_name)}
- Website: {clean_value(lead.website)}
- Industry: {clean_value(lead.industry)}
- Location: {clean_value(lead.location)}
- Contact name: {clean_value(lead.contact_name)}
- Contact role: {clean_value(lead.contact_role)}
- Email: {clean_value(lead.email)}
- Source: {clean_value(lead.source)}
- Status: {clean_value(lead.status)}

AI lead research:
{research_section}

Rules:
- Score business fit and contact confidence separately from 0 to 100.
- fit_score is only company/campaign fit: company industry, campaign industry, target role, lead role, location match, offer relevance, and likely pain point.
- When AI lead research is available, use it to improve fit reasoning, outreach angle, pain point, and risk assessment.
- If research confidence is low, mention that uncertainty instead of over-weighting the research.
- If research risk flags indicate role mismatch, unrelated industry, generic email, or unclear offering, reflect that in the appropriate score/reason.
- Do not mix contact quality into fit_score.
- A personal, test, Gmail, student, institute, or placeholder email should reduce contact_confidence_score, not fit_score.
- For test/demo data, do not treat Gmail or student email as proof that the company is irrelevant.
- Well-known or large companies should score high only when their industry, role, location, and likely use case align with this campaign's offer.
- Treat roles as relevant only when they plausibly own, influence, or evaluate the current campaign offer.
- HR Manager, Training Manager, Operations Head, Admin Head, Founder, Owner, and Director are valid decision-maker roles depending on context.
- Explain the business fit in 1-3 sentences.
- Explicitly mention when lead research improved or limited confidence.
- Explain contact confidence separately.
- Suggest a practical outreach angle.
- Identify the likely pain point.
- Suggest a recommended CTA.
- Explain final priority/readiness as a combination of fit and contact confidence.
- Do not invent facts about the lead.
- Return valid JSON only with this exact shape:
{{
  "fit_score": 0,
  "contact_confidence_score": 0,
  "reason": "...",
  "contact_confidence_reason": "...",
  "outreach_angle": "...",
  "pain_point": "...",
  "recommended_cta": "...",
  "final_priority_reason": "..."
}}
""".strip()


def parse_ai_scoring_response(response_text: str, campaign: Campaign, lead: Lead):
    fallback_result = fallback_score_lead(campaign, lead)

    try:
        parsed_response = extract_json_from_text(clean_value(response_text))
    except Exception as exc:
        fallback_result["warning"] = "Gemini response was not valid JSON. Fallback scoring was used."
        fallback_result["error"] = str(exc)
        return fallback_result

    fit_score = clamp_score(parsed_response.get("fit_score"))
    contact_confidence_score = clamp_score(parsed_response.get("contact_confidence_score"))

    if fit_score is None or contact_confidence_score is None:
        fallback_result["warning"] = "Gemini response did not include valid fit/contact scores. Fallback scoring was used."
        return fallback_result

    if fallback_result["fit_score"] >= 80 and fit_score < fallback_result["fit_score"] - 10:
        fit_score = fallback_result["fit_score"]

    contact_confidence_score = min(contact_confidence_score, get_contact_confidence_cap(lead))
    score = get_final_score(fit_score, contact_confidence_score)

    return {
        "score": score,
        "fit_score": fit_score,
        "contact_confidence_score": contact_confidence_score,
        "priority": get_priority_for_score(score),
        "qualification": get_qualification_for_score(fit_score),
        "reason": clean_value(parsed_response.get("reason")) or fallback_result["reason"],
        "contact_confidence_reason": (
            clean_value(parsed_response.get("contact_confidence_reason")) or
            fallback_result["contact_confidence_reason"]
        ),
        "outreach_angle": clean_value(parsed_response.get("outreach_angle")) or fallback_result["outreach_angle"],
        "pain_point": clean_value(parsed_response.get("pain_point")) or fallback_result["pain_point"],
        "recommended_cta": clean_value(parsed_response.get("recommended_cta")) or fallback_result["recommended_cta"],
        "final_priority_reason": (
            clean_value(parsed_response.get("final_priority_reason")) or
            fallback_result["final_priority_reason"]
        ),
        "warning": None,
    }


def serialize_lead_score(lead: Lead):
    return {
        "lead_id": lead.id,
        "ai_score": lead.ai_score,
        "ai_fit_score": lead.ai_fit_score,
        "ai_contact_confidence_score": lead.ai_contact_confidence_score,
        "ai_priority": lead.ai_priority,
        "ai_qualification": lead.ai_qualification,
        "ai_score_reason": lead.ai_score_reason,
        "ai_contact_confidence_reason": lead.ai_contact_confidence_reason,
        "ai_outreach_angle": lead.ai_outreach_angle,
        "ai_pain_point": lead.ai_pain_point,
        "ai_recommended_cta": lead.ai_recommended_cta,
        "ai_final_priority_reason": lead.ai_final_priority_reason,
        "ai_scored_at": lead.ai_scored_at,
        "ai_model_used": lead.ai_model_used,
        "ai_score_error": lead.ai_score_error,
    }


def save_lead_score(db: Session, lead: Lead, result: dict, model_used: str | None, error_message: str | None = None):
    lead.ai_score = result["score"]
    lead.ai_fit_score = result["fit_score"]
    lead.ai_contact_confidence_score = result["contact_confidence_score"]
    lead.ai_priority = result["priority"]
    lead.ai_qualification = result["qualification"]
    lead.ai_score_reason = result["reason"]
    lead.ai_contact_confidence_reason = result["contact_confidence_reason"]
    lead.ai_outreach_angle = result["outreach_angle"]
    lead.ai_pain_point = result["pain_point"]
    lead.ai_recommended_cta = result["recommended_cta"]
    lead.ai_final_priority_reason = result["final_priority_reason"]
    lead.ai_scored_at = utc_now()
    lead.ai_model_used = model_used
    lead.ai_score_error = error_message or result.get("warning")

    try:
        db.commit()
        db.refresh(lead)
    except SQLAlchemyError as exc:
        db.rollback()
        raise LeadScoringError("Lead score could not be saved.") from exc


def score_lead_with_ai(db: Session, lead: Lead, campaign: Campaign, force: bool = False) -> dict:
    if lead.ai_score is not None and not force:
        return {
            "created": False,
            "message": "Existing lead score returned",
            "data": serialize_lead_score(lead),
        }

    result = None
    model_used = settings.GEMINI_MODEL
    error_message = None

    if settings.GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=build_lead_scoring_prompt(campaign, lead),
            )
            result = parse_ai_scoring_response(clean_value(getattr(response, "text", "")), campaign, lead)
        except Exception as exc:
            error_message = "Gemini lead scoring failed. Fallback scoring was used."
            result = fallback_score_lead(campaign, lead)
            result["warning"] = error_message
    else:
        error_message = "Gemini API key is not configured. Fallback scoring was used."
        result = fallback_score_lead(campaign, lead)
        result["warning"] = error_message
        model_used = None

    save_lead_score(db, lead, result, model_used=model_used, error_message=error_message)

    return {
        "created": True,
        "message": "Lead scored successfully",
        "data": serialize_lead_score(lead),
    }


def score_lead_safely(db: Session, lead: Lead, campaign: Campaign, force: bool = False) -> dict:
    try:
        return score_lead_with_ai(db, lead, campaign, force=force)
    except Exception as exc:
        lead.ai_score_error = "AI lead scoring failed. Please try again."
        lead.ai_scored_at = utc_now()

        try:
            db.commit()
            db.refresh(lead)
        except SQLAlchemyError:
            db.rollback()

        return {
            "created": False,
            "failed": True,
            "message": str(exc),
            "data": serialize_lead_score(lead),
        }
