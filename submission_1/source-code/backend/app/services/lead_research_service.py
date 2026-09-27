import ipaddress
import json
import logging
import re
import socket
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from google import genai
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.models import Campaign, Lead
from app.utils.time_utils import utc_now

REQUEST_TIMEOUT_SECONDS = 8
MAX_RESPONSE_BYTES = 1 * 1024 * 1024
MAX_PAGE_TEXT_CHARS = 8000
MAX_PROMPT_WEBSITE_CHARS = 12000
MAX_PAGES_PER_LEAD = 3
USER_AGENT = "AI Lead Generation MVP Lead Research Bot/1.0"
RESEARCH_MODEL_FALLBACK = "fallback-research"
ROBOTS_CACHE = {}
WEBSITE_FALLBACK_MESSAGE = "Website text unavailable. AI used CSV and campaign data only."

logger = logging.getLogger(__name__)


class LeadResearchError(RuntimeError):
    pass


def clean_value(value):
    if value is None:
        return ""

    return str(value).strip()


def _truncate(value, max_length: int):
    text = clean_value(value)

    if len(text) <= max_length:
        return text

    return text[:max_length].rstrip()


def _clamp_confidence(value):
    try:
        numeric_value = int(round(float(value)))
    except (TypeError, ValueError):
        return 0

    return max(0, min(numeric_value, 100))


def _split_lines(value):
    if isinstance(value, list):
        return [
            clean_value(item)
            for item in value
            if clean_value(item)
        ]

    text = clean_value(value)

    if not text:
        return []

    return [
        item.strip(" -\t")
        for item in re.split(r"[\n;]+", text)
        if item.strip(" -\t")
    ]


def _join_lines(value):
    lines = _split_lines(value)
    return "\n".join(lines)


def _extract_json_from_text(text):
    cleaned_text = clean_value(text)

    if cleaned_text.startswith("```"):
        cleaned_text = re.sub(r"^```(?:json)?", "", cleaned_text, flags=re.IGNORECASE).strip()
        cleaned_text = re.sub(r"```$", "", cleaned_text).strip()

    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned_text, flags=re.DOTALL)

    if not match:
        raise LeadResearchError("Gemini research response was not valid JSON.")

    return json.loads(match.group(0))


def _safe_error_message(exc):
    text = " ".join(clean_value(exc).split())

    if settings.GEMINI_API_KEY:
        text = text.replace(settings.GEMINI_API_KEY, "[redacted]")

    text = re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[redacted]", text)
    text = re.sub(r"Bearer\s+[0-9A-Za-z._-]+", "Bearer [redacted]", text, flags=re.IGNORECASE)

    return text[:500] or "Lead research failed. Please try again."


def _friendly_website_error(exc_or_message, status_code: int | None = None):
    if status_code == 404:
        return "Page not found"

    if status_code in {401, 403, 406, 410, 429}:
        return "Website blocked or unreadable"

    if status_code and status_code >= 400:
        return "Website blocked or unreadable"

    if isinstance(exc_or_message, requests.exceptions.SSLError):
        return "SSL certificate verification failed"

    if isinstance(exc_or_message, requests.exceptions.Timeout):
        return "Website timeout"

    if isinstance(exc_or_message, requests.exceptions.TooManyRedirects):
        return "Website blocked or unreadable"

    if isinstance(exc_or_message, requests.exceptions.HTTPError):
        response = getattr(exc_or_message, "response", None)
        return _friendly_website_error(str(exc_or_message), getattr(response, "status_code", None))

    message = clean_value(exc_or_message).lower()

    if "certificate_verify_failed" in message or "ssl" in message:
        return "SSL certificate verification failed"

    if "timed out" in message or "timeout" in message:
        return "Website timeout"

    if "404" in message or "not found" in message:
        return "Page not found"

    if "robots.txt" in message or "blocked" in message or "forbidden" in message:
        return "Website blocked or unreadable"

    if "no readable" in message:
        return "No readable website text found"

    if "too many redirects" in message or "redirect" in message:
        return "Website blocked or unreadable"

    if "missing" in message:
        return "No readable website text found"

    return "Website blocked or unreadable"


def _dedupe_errors(errors):
    unique_errors = []
    seen = set()

    for error in errors:
        friendly_error = _friendly_website_error(error)

        if friendly_error not in seen:
            unique_errors.append(friendly_error)
            seen.add(friendly_error)

    return unique_errors


def _host_is_private(hostname: str):
    host = clean_value(hostname).lower()

    if not host:
        return True

    if host in {"localhost", "0.0.0.0"} or host.endswith(".localhost"):
        return True

    try:
        ip_address = ipaddress.ip_address(host)
        return (
            ip_address.is_private
            or ip_address.is_loopback
            or ip_address.is_link_local
            or ip_address.is_reserved
            or ip_address.is_multicast
        )
    except ValueError:
        pass

    try:
        address_infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False

    for address_info in address_infos:
        address = address_info[4][0]

        try:
            ip_address = ipaddress.ip_address(address)
        except ValueError:
            return True

        if (
            ip_address.is_private
            or ip_address.is_loopback
            or ip_address.is_link_local
            or ip_address.is_reserved
            or ip_address.is_multicast
        ):
            return True

    return False


def normalize_url(url: str) -> str:
    cleaned_url = clean_value(url)

    if not cleaned_url:
        raise LeadResearchError("Website is missing.")

    if cleaned_url.startswith("//"):
        cleaned_url = f"https:{cleaned_url}"

    parsed_url = urlparse(cleaned_url)

    if not parsed_url.scheme:
        cleaned_url = f"https://{cleaned_url}"
        parsed_url = urlparse(cleaned_url)

    if parsed_url.scheme not in {"http", "https"}:
        raise LeadResearchError("Website URL must use HTTP or HTTPS.")

    if not parsed_url.netloc:
        raise LeadResearchError("Website URL is invalid.")

    if _host_is_private(parsed_url.hostname or ""):
        raise LeadResearchError("Website URL is not allowed for research.")

    return cleaned_url.rstrip("/")


def _is_allowed_by_robots(url: str):
    parsed_url = urlparse(url)
    robots_url = f"{parsed_url.scheme}://{parsed_url.netloc}/robots.txt"

    if robots_url not in ROBOTS_CACHE:
        parser = RobotFileParser()
        parser.set_url(robots_url)

        try:
            response = requests.get(
                robots_url,
                timeout=REQUEST_TIMEOUT_SECONDS,
                headers={"User-Agent": USER_AGENT},
            )

            if response.status_code >= 400:
                ROBOTS_CACHE[robots_url] = None
            else:
                parser.parse(response.text.splitlines())
                ROBOTS_CACHE[robots_url] = parser
        except requests.RequestException:
            ROBOTS_CACHE[robots_url] = None

    parser = ROBOTS_CACHE[robots_url]

    if parser is None:
        return True, None

    if not parser.can_fetch(USER_AGENT, url):
        return False, "Robots.txt disallows research for this page."

    return True, None


def fetch_public_page(url: str) -> dict:
    try:
        normalized_url = normalize_url(url)
    except LeadResearchError as exc:
        return {
            "status": "error",
            "url": clean_value(url),
            "html": "",
            "error": _friendly_website_error(exc),
        }

    try:
        current_url = normalized_url
        response = None

        for _ in range(4):
            allowed, robots_error = _is_allowed_by_robots(current_url)

            if not allowed:
                return {
                    "status": "error",
                    "url": current_url,
                    "html": "",
                    "error": _friendly_website_error(robots_error),
                }

            response = requests.get(
                current_url,
                timeout=REQUEST_TIMEOUT_SECONDS,
                headers={"User-Agent": USER_AGENT},
                stream=True,
                allow_redirects=False,
            )

            if response.is_redirect or response.is_permanent_redirect:
                redirect_location = response.headers.get("Location")

                if not redirect_location:
                    break

                current_url = normalize_url(urljoin(current_url, redirect_location))
                continue

            break

        if response is None:
            raise requests.RequestException("No response was returned.")

        if response.is_redirect or response.is_permanent_redirect:
            return {
                "status": "error",
                "url": current_url,
                "html": "",
                "error": "Website blocked or unreadable",
            }

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            logger.debug("Website research HTTP error for %s: %s", current_url, exc, exc_info=True)
            return {
                "status": "error",
                "url": current_url,
                "html": "",
                "error": _friendly_website_error(exc),
            }

        content = bytearray()
        for chunk in response.iter_content(chunk_size=16384):
            if not chunk:
                continue

            content.extend(chunk)

            if len(content) > MAX_RESPONSE_BYTES:
                return {
                    "status": "error",
                    "url": response.url,
                    "html": "",
                    "error": "Website blocked or unreadable",
                }

        encoding = response.encoding or "utf-8"

        return {
            "status": "success",
            "url": response.url,
            "html": bytes(content).decode(encoding, errors="replace"),
            "error": None,
        }
    except requests.RequestException as exc:
        logger.debug("Website research request failed for %s: %s", normalized_url, exc, exc_info=True)
        return {
            "status": "error",
            "url": normalized_url,
            "html": "",
            "error": _friendly_website_error(exc),
        }


def extract_clean_text(html: str) -> str:
    if not clean_value(html):
        return ""

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "nav", "footer", "form", "svg"]):
        tag.decompose()

    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    return _truncate(text, MAX_PAGE_TEXT_CHARS)


def discover_basic_pages(base_url: str) -> list[str]:
    normalized_url = normalize_url(base_url)
    parsed_url = urlparse(normalized_url)
    root_url = f"{parsed_url.scheme}://{parsed_url.netloc}/"
    host = clean_value(parsed_url.netloc)
    host_without_www = host[4:] if host.startswith("www.") else host
    variant_urls = [
        normalized_url,
        root_url,
    ]

    if host_without_www and host_without_www != host:
        variant_urls.append(f"{parsed_url.scheme}://{host_without_www}/")

    if parsed_url.scheme == "https":
        variant_urls.append(f"http://{host}/")
        if host_without_www and host_without_www != host:
            variant_urls.append(f"http://{host_without_www}/")

    variant_urls.extend([
        urljoin(root_url, "about"),
        urljoin(root_url, "about-us"),
        urljoin(root_url, "services"),
        urljoin(root_url, "products"),
    ])

    urls = []
    seen = set()

    for url in variant_urls:
        try:
            safe_url = normalize_url(url)
        except LeadResearchError:
            continue

        if safe_url not in seen:
            urls.append(safe_url)
            seen.add(safe_url)

    return urls


def _lead_email_risk(lead: Lead):
    email = clean_value(lead.email).lower()

    if not email or "@" not in email:
        return "Missing email reduces outreach readiness."

    domain = email.rsplit("@", 1)[1]

    if domain in {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"}:
        return "Personal email address should be verified before serious outreach."

    local_part = email.split("@", 1)[0]

    if local_part in {"info", "contact", "hello", "sales", "support", "admin"}:
        return "Generic email address may not reach the exact decision-maker."

    return ""


def _role_mismatch_risk(lead: Lead, campaign: Campaign):
    lead_role = clean_value(lead.contact_role).lower()
    target_role = clean_value(campaign.target_role).lower()

    if not lead_role or not target_role:
        return ""

    generic_role_tokens = {
        "admin",
        "chief",
        "contact",
        "coordinator",
        "director",
        "head",
        "lead",
        "leader",
        "manager",
        "officer",
        "owner",
        "person",
        "team",
    }
    target_tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", target_role)
        if len(token) >= 3 and token not in generic_role_tokens
    }
    lead_tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", lead_role)
        if len(token) >= 3 and token not in generic_role_tokens
    }

    if target_tokens and lead_tokens and not target_tokens.intersection(lead_tokens):
        return f"Contact role may not match target role: lead role is {lead.contact_role}, target role is {campaign.target_role}."

    return ""


def _build_research_prompt(campaign: Campaign, lead: Lead, website_text: str, sources: list[str], fallback_only: bool = False):
    source_label = "CSV/campaign fields only" if fallback_only else ", ".join(sources)

    return f"""
You are a B2B lead research assistant.
Research this lead only from the data provided below.
Return strict JSON only.

Campaign:
- Campaign name: {clean_value(campaign.campaign_name)}
- Target industry: {clean_value(campaign.industry)}
- Target location: {clean_value(campaign.location)}
- Target role: {clean_value(campaign.target_role)}
- Offer: {clean_value(campaign.offer)}

Lead fields:
- Company name: {clean_value(lead.company_name)}
- Website: {clean_value(lead.website)}
- Industry: {clean_value(lead.industry)}
- Location: {clean_value(lead.location)}
- Contact name: {clean_value(lead.contact_name)}
- Contact role: {clean_value(lead.contact_role)}
- Email: {clean_value(lead.email)}
- Source: {clean_value(lead.source)}

Website/source text:
{_truncate(website_text, MAX_PROMPT_WEBSITE_CHARS) or "No readable website text was available."}

Sources checked:
{source_label}

Rules:
- Be campaign-aware. Use the current campaign offer, target industry, target location, and target role.
- Do not assume the offer is employee training, onboarding, SOPs, or HR unless the campaign offer says so.
- Use only provided lead fields, campaign fields, and website text.
- Do not invent company facts, customer segments, technologies, locations, claims, awards, or problems.
- If data is thin or website text is unavailable, keep confidence low and say what is uncertain.
- Possible pain points must be relevant to the campaign offer.
- Outreach angle must connect the campaign offer to the lead context without overclaiming.
- Risk flags should include personal/generic email, role mismatch, unrelated industry, missing website, inaccessible website, generic website, or unclear offering when relevant.
- Confidence must be an integer from 0 to 100.

Return JSON with this exact shape:
{{
  "summary": "...",
  "business_type": "...",
  "target_customers": "...",
  "products_services": "...",
  "pain_points": "...",
  "use_case_fit": "...",
  "outreach_angle": "...",
  "risk_flags": "...",
  "confidence": 0,
  "sources": ["..."]
}}
""".strip()


def _fallback_research_payload(campaign: Campaign, lead: Lead, error_message: str | None = None):
    website_unavailable = bool(clean_value(error_message))
    risks = [
        risk
        for risk in [
            _lead_email_risk(lead),
            _role_mismatch_risk(lead, campaign),
            WEBSITE_FALLBACK_MESSAGE if website_unavailable else "",
        ]
        if risk
    ]
    company_name = clean_value(lead.company_name) or "This lead"
    lead_context = ", ".join(
        part
        for part in [clean_value(lead.industry), clean_value(lead.location), clean_value(lead.contact_role)]
        if part
    )
    offer = clean_value(campaign.offer) or "the campaign offer"

    return {
        "summary": f"{company_name} has limited available research data. Known context: {lead_context or 'basic lead fields only'}.",
        "business_type": clean_value(lead.industry) or "Unknown",
        "target_customers": "Unknown from available data.",
        "products_services": "Unknown from available data.",
        "pain_points": f"Possible needs should be validated against {offer}; available data is not enough to assert a specific problem.",
        "use_case_fit": f"Potential fit depends on whether {company_name} has a current need for {offer}.",
        "outreach_angle": f"Use a light, exploratory angle around {offer} and ask whether it is relevant.",
        "risk_flags": "\n".join(risks) or "Low data confidence.",
        "confidence": 30 if website_unavailable else 40,
        "sources": ["CSV/campaign fields only"] if website_unavailable else ["lead CSV fields", "campaign data"],
        "used_fallback": website_unavailable,
    }


def _parse_research_response(response_text: str, campaign: Campaign, lead: Lead, fallback_payload: dict):
    try:
        parsed = _extract_json_from_text(response_text)
    except Exception:
        return {
            **fallback_payload,
            "confidence": min(fallback_payload["confidence"], 25),
            "risk_flags": _join_lines([fallback_payload.get("risk_flags"), "AI response was not valid JSON."]),
        }

    sources = _split_lines(parsed.get("sources"))

    if not sources:
        sources = fallback_payload["sources"]

    if fallback_payload.get("used_fallback"):
        sources = ["CSV/campaign fields only"]

    confidence = _clamp_confidence(parsed.get("confidence") if parsed.get("confidence") is not None else fallback_payload["confidence"])

    if fallback_payload.get("used_fallback"):
        confidence = min(confidence, 50)

    risk_flags = _truncate(parsed.get("risk_flags") or fallback_payload["risk_flags"], 1200)

    if fallback_payload.get("used_fallback") and WEBSITE_FALLBACK_MESSAGE not in risk_flags:
        risk_flags = _join_lines([risk_flags, WEBSITE_FALLBACK_MESSAGE])

    return {
        "summary": _truncate(parsed.get("summary") or fallback_payload["summary"], 1200),
        "business_type": _truncate(parsed.get("business_type") or fallback_payload["business_type"], 255),
        "target_customers": _truncate(parsed.get("target_customers") or fallback_payload["target_customers"], 1200),
        "products_services": _truncate(parsed.get("products_services") or fallback_payload["products_services"], 1200),
        "pain_points": _truncate(parsed.get("pain_points") or fallback_payload["pain_points"], 1200),
        "use_case_fit": _truncate(parsed.get("use_case_fit") or fallback_payload["use_case_fit"], 1200),
        "outreach_angle": _truncate(parsed.get("outreach_angle") or fallback_payload["outreach_angle"], 1200),
        "risk_flags": _truncate(risk_flags, 1200),
        "confidence": confidence,
        "sources": sources,
        "used_fallback": bool(fallback_payload.get("used_fallback")),
    }


def _apply_research_to_lead(
    lead: Lead,
    payload: dict,
    status: str = "researched",
    error_message: str | None = None,
    model_used: str | None = None,
):
    lead.research_status = status
    lead.research_summary = clean_value(payload.get("summary")) or None
    lead.research_business_type = clean_value(payload.get("business_type")) or None
    lead.research_target_customers = clean_value(payload.get("target_customers")) or None
    lead.research_products_services = clean_value(payload.get("products_services")) or None
    lead.research_pain_points = clean_value(payload.get("pain_points")) or None
    lead.research_use_case_fit = clean_value(payload.get("use_case_fit")) or None
    lead.research_outreach_angle = clean_value(payload.get("outreach_angle")) or None
    lead.research_risk_flags = clean_value(payload.get("risk_flags")) or None
    lead.research_confidence = _clamp_confidence(payload.get("confidence"))
    lead.research_sources = "\n".join(_split_lines(payload.get("sources"))) or None
    lead.research_used_fallback = bool(payload.get("used_fallback"))
    if clean_value(error_message):
        lead.research_error = (
            _friendly_website_error(error_message)
            if lead.research_used_fallback
            else _safe_error_message(error_message)
        )
    else:
        lead.research_error = None
    lead.researched_at = utc_now()

    if model_used:
        source_note = f"model: {model_used}"
        lead.research_sources = "\n".join(_split_lines([lead.research_sources, source_note]))


def build_research_context(lead: Lead | None, max_chars: int = 1600):
    if not lead or clean_value(getattr(lead, "research_status", "")) != "researched":
        return ""

    parts = [
        ("Summary", lead.research_summary),
        ("Business type", lead.research_business_type),
        ("Target customers", lead.research_target_customers),
        ("Products/services", lead.research_products_services),
        ("Possible pain points", lead.research_pain_points),
        ("Use case fit", lead.research_use_case_fit),
        ("Outreach angle", lead.research_outreach_angle),
        ("Risk flags", lead.research_risk_flags),
        ("Confidence", lead.research_confidence),
    ]
    lines = [
        f"- {label}: {clean_value(value)}"
        for label, value in parts
        if clean_value(value)
    ]

    if not lines:
        return ""

    return _truncate("\n".join(lines), max_chars)


def _fetch_research_pages(website: str):
    pages = []
    sources = []
    errors = []

    try:
        urls = discover_basic_pages(website)
    except LeadResearchError as exc:
        return "", [], [str(exc)]

    for url in urls[:MAX_PAGES_PER_LEAD]:
        result = fetch_public_page(url)

        if result.get("status") != "success":
            if result.get("error"):
                errors.append(result["error"])
            continue

        text = extract_clean_text(result.get("html", ""))

        if not text:
            errors.append("No readable website text found")
            continue

        sources.append(result.get("url") or url)
        pages.append(f"Source: {result.get('url') or url}\n{text}")

    return _truncate("\n\n".join(pages), MAX_PROMPT_WEBSITE_CHARS), sources, errors


def fallback_research_from_csv(db: Session, lead_id: int, error_message: str | None = None):
    lead = (
        db.query(Lead)
        .options(joinedload(Lead.campaign))
        .filter(Lead.id == lead_id)
        .first()
    )

    if not lead:
        raise LeadResearchError("Lead was not found.")

    campaign = lead.campaign

    if not campaign:
        raise LeadResearchError("Campaign was not found.")

    fallback_payload = _fallback_research_payload(campaign, lead, error_message)

    if settings.GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=_build_research_prompt(
                    campaign,
                    lead,
                    "",
                    fallback_payload["sources"],
                    fallback_only=True,
                ),
            )
            fallback_payload = _parse_research_response(
                clean_value(getattr(response, "text", "")),
                campaign,
                lead,
                fallback_payload,
            )
            model_used = settings.GEMINI_MODEL
        except Exception as exc:
            error_message = error_message or _safe_error_message(exc)
            model_used = RESEARCH_MODEL_FALLBACK
    else:
        error_message = error_message or "Gemini API key is not configured. Fallback research used CSV and campaign data."
        model_used = RESEARCH_MODEL_FALLBACK

    _apply_research_to_lead(
        lead,
        fallback_payload,
        status="researched",
        error_message=error_message,
        model_used=model_used,
    )

    try:
        db.commit()
        db.refresh(lead)
    except SQLAlchemyError as exc:
        db.rollback()
        raise LeadResearchError("Lead research could not be saved.") from exc

    return serialize_research_result(lead)


def serialize_research_result(lead: Lead):
    return {
        "lead_id": lead.id,
        "research_status": lead.research_status,
        "research_summary": lead.research_summary,
        "research_business_type": lead.research_business_type,
        "research_target_customers": lead.research_target_customers,
        "research_products_services": lead.research_products_services,
        "research_pain_points": lead.research_pain_points,
        "research_use_case_fit": lead.research_use_case_fit,
        "research_outreach_angle": lead.research_outreach_angle,
        "research_risk_flags": lead.research_risk_flags,
        "research_confidence": lead.research_confidence,
        "research_sources": lead.research_sources,
        "research_error": lead.research_error,
        "research_used_fallback": lead.research_used_fallback,
        "researched_at": lead.researched_at,
    }


def research_lead(db: Session, lead_id: int) -> dict:
    lead = (
        db.query(Lead)
        .options(joinedload(Lead.campaign))
        .filter(Lead.id == lead_id)
        .first()
    )

    if not lead:
        raise LeadResearchError("Lead was not found.")

    campaign = lead.campaign

    if not campaign:
        raise LeadResearchError("Campaign was not found.")

    lead.research_status = "researching"
    lead.research_error = None

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()

    website_error = None
    website_text = ""
    sources = []

    if clean_value(lead.website):
        website_text, sources, fetch_errors = _fetch_research_pages(lead.website)
        if fetch_errors and not website_text:
            website_error = "; ".join(_dedupe_errors(fetch_errors)[:3])
    else:
        website_error = "Website is missing."

    if not website_text:
        return fallback_research_from_csv(db, lead_id, website_error or "No readable website text found")

    fallback_payload = _fallback_research_payload(campaign, lead, website_error)
    model_used = settings.GEMINI_MODEL

    if settings.GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=_build_research_prompt(campaign, lead, website_text, sources),
            )
            payload = _parse_research_response(
                clean_value(getattr(response, "text", "")),
                campaign,
                lead,
                fallback_payload,
            )
        except Exception as exc:
            return fallback_research_from_csv(db, lead_id, website_error or _safe_error_message(exc))
    else:
        payload = fallback_payload
        model_used = RESEARCH_MODEL_FALLBACK
        website_error = website_error or "Gemini API key is not configured. Fallback research used website text and lead fields."

    _apply_research_to_lead(
        lead,
        payload,
        status="researched",
        error_message=website_error,
        model_used=model_used,
    )

    try:
        db.commit()
        db.refresh(lead)
    except SQLAlchemyError as exc:
        db.rollback()
        lead.research_status = "failed"
        lead.research_error = "Lead research could not be saved."
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
        raise LeadResearchError("Lead research could not be saved.") from exc

    return serialize_research_result(lead)
