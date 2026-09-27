import ipaddress
import json
import re
from urllib.parse import urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from google import genai
from requests import exceptions as request_exceptions
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.models import Campaign, DiscoveredLead, DiscoveryJob, Lead
from app.services.ai_service import clean_value, extract_json_from_text
from app.services.lead_research_service import research_lead
from app.utils.time_utils import utc_now

REQUEST_TIMEOUT_SECONDS = 8
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_TEXT_CHARS = 10000
MAX_CONTEXT_CHARS = 900
MAX_DISCOVERY_PAGES = 20
USER_AGENT = "AI Lead Generation MVP Discovery Bot/1.0"
VALID_TARGET_TYPES = {"professor", "college", "department", "company", "startup", "student", "general"}
VALID_SOURCE_MODES = {"manual_urls", "generated_queries", "search_api_later"}
VALID_JOB_STATUSES = {"draft", "running", "completed", "failed"}
VALID_RESULT_STATUSES = {"pending", "approved", "rejected", "imported", "updated_existing"}
IMPORTED_RESULT_STATUSES = {"imported", "updated_existing"}
FAKE_EMAIL_DOMAINS = {"example.com", "example.org", "example.net"}
GENERIC_EMAIL_PREFIXES = {"info", "contact", "admin", "support", "hello", "admissions", "office", "enquiry", "enquiries"}
PERSONAL_EMAIL_DOMAINS = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "rediffmail.com"}
MISSING_TEXT_VALUES = {"", "n/a", "na", "-", "--", "null", "none", "unknown", "not available"}
GENERIC_CONTACT_NAMES = {"faculty", "contact", "team", "staff", "office", "admin", "administrator", "department"}
GENERIC_ROLES = {"faculty", "contact", "team"}
WEAK_COMPANY_NAMES = {"discovered contact", "unknown company", "unknown organization", "organization", "company"}
BETTER_ROLE_KEYWORDS = (
    "assistant professor",
    "associate professor",
    "adjunct faculty",
    "hod",
    "head of department",
    "professor",
)

robots_cache = {}


class LeadDiscoveryError(RuntimeError):
    pass


def _truncate(value, max_length: int | None = None):
    text = clean_value(value)

    if max_length and len(text) > max_length:
        return text[:max_length].rstrip()

    return text


def _clean_upsert_value(value, max_length: int | None = None):
    text = re.sub(r"\s+", " ", clean_value(value)).strip()
    if text.lower() in MISSING_TEXT_VALUES:
        return None
    if max_length and len(text) > max_length:
        return text[:max_length].rstrip()
    return text


def _normalize_text_key(value):
    text = _clean_upsert_value(value)
    if not text:
        return None
    return re.sub(r"\s+", " ", text.lower()).strip()


def _normalize_email(value):
    email = _normalize_text_key(value)
    if not email or "@" not in email:
        return None
    return email


def _normalize_url_key(value):
    text = _clean_upsert_value(value)
    if not text:
        return None
    try:
        normalized = normalize_url(text)
    except LeadDiscoveryError:
        normalized = text
    parsed_url = urlparse(normalized.lower())
    netloc = parsed_url.netloc[4:] if parsed_url.netloc.startswith("www.") else parsed_url.netloc
    path = parsed_url.path.rstrip("/")
    return urlunparse(parsed_url._replace(scheme="", netloc=netloc, path=path, params="", query="", fragment="")).lstrip("//")


def _normalize_phone_digits(value):
    digits = re.sub(r"\D+", "", clean_value(value))
    if len(digits) < 5:
        return None
    return digits


def _is_same_phone_number(first_digits, second_digits):
    if not first_digits or not second_digits:
        return False
    if first_digits == second_digits:
        return True
    shorter, longer = sorted((first_digits, second_digits), key=len)
    return len(shorter) >= 7 and len(longer) - len(shorter) <= 3 and longer.endswith(shorter)


def _is_missing_value(value):
    return _clean_upsert_value(value) is None


def _email_domain(email):
    normalized_email = _normalize_email(email)
    if not normalized_email or "@" not in normalized_email:
        return ""
    return normalized_email.rsplit("@", 1)[-1]


def _email_prefix(email):
    normalized_email = _normalize_email(email)
    if not normalized_email or "@" not in normalized_email:
        return ""
    return normalized_email.split("@", 1)[0]


def _is_fake_email(email):
    return _email_domain(email) in FAKE_EMAIL_DOMAINS


def _is_generic_email(email):
    prefix = re.split(r"[.+_-]", _email_prefix(email) or "", maxsplit=1)[0]
    return prefix in GENERIC_EMAIL_PREFIXES


def _is_generic_contact_name(value):
    text = _normalize_text_key(value)
    return not text or text in GENERIC_CONTACT_NAMES


def _role_quality(value):
    text = _normalize_text_key(value)
    if not text:
        return 0
    if any(keyword in text for keyword in BETTER_ROLE_KEYWORDS):
        if text == "professor":
            return 2
        return 4
    if text in GENERIC_ROLES:
        return 1
    return 3


def _is_domain_like(value):
    text = _normalize_text_key(value)
    if not text or " " in text:
        return False
    return "." in text


def _is_weak_company_name(value):
    text = _normalize_text_key(value)
    return not text or text in WEAK_COMPANY_NAMES or text in MISSING_TEXT_VALUES


def _phone_quality(value):
    text = _clean_upsert_value(value) or ""
    quality = len(text)
    if text.startswith("+"):
        quality += 6
    if re.search(r"[\s()-]", text):
        quality += 2
    return quality


def _url_quality(value):
    text = _clean_upsert_value(value) or ""
    quality = len(text)
    if text.lower().startswith("https://"):
        quality += 5
    if "www." in text.lower():
        quality += 1
    return quality


def _append_discovery_source(source):
    existing_source = _clean_upsert_value(source, 100)
    if not existing_source:
        return "discovery"
    if "discovery" in existing_source.lower():
        return existing_source
    candidate = f"{existing_source}; discovery"
    return candidate[:100].rstrip()


def _set_if_changed(target, field_name, value):
    if getattr(target, field_name) == value:
        return False
    setattr(target, field_name, value)
    return True


def _safe_error_message(exc_or_message):
    text = clean_value(exc_or_message)

    if isinstance(exc_or_message, request_exceptions.SSLError) or "certificate" in text.lower():
        return "SSL certificate verification failed"
    if isinstance(exc_or_message, request_exceptions.Timeout) or "timed out" in text.lower() or "timeout" in text.lower():
        return "Website timeout"
    if isinstance(exc_or_message, request_exceptions.TooManyRedirects):
        return "Website blocked or unreadable"
    if "404" in text:
        return "Page not found"
    if isinstance(exc_or_message, request_exceptions.ConnectionError):
        return "Website unavailable"

    lower_text = text.lower()
    if "forbidden" in lower_text or "403" in lower_text:
        return "Website blocked or unreadable"
    if "not found" in lower_text:
        return "Page not found"

    return text[:160] or "Website blocked or unreadable"


def _is_private_or_local_host(hostname: str):
    host = clean_value(hostname).lower()

    if not host:
        return True

    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
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
        return False


def normalize_url(url: str) -> str:
    cleaned_url = clean_value(url)

    if not cleaned_url:
        raise LeadDiscoveryError("Website URL is missing")

    if cleaned_url.startswith("//"):
        cleaned_url = f"https:{cleaned_url}"

    parsed_url = urlparse(cleaned_url)

    if not parsed_url.scheme:
        cleaned_url = f"https://{cleaned_url}"
        parsed_url = urlparse(cleaned_url)

    if parsed_url.scheme not in {"http", "https"}:
        raise LeadDiscoveryError("Unsupported URL scheme")

    if not parsed_url.netloc or _is_private_or_local_host(parsed_url.hostname or ""):
        raise LeadDiscoveryError("Invalid public website URL")

    return urlunparse(parsed_url._replace(fragment="")).rstrip("/")


def _url_variants(url: str):
    normalized_url = normalize_url(url)
    parsed_url = urlparse(normalized_url)
    variants = []

    def add_variant(candidate):
        try:
            normalized_candidate = normalize_url(candidate)
        except LeadDiscoveryError:
            return
        if normalized_candidate not in variants:
            variants.append(normalized_candidate)

    add_variant(normalized_url)

    host = parsed_url.netloc
    if host.startswith("www."):
        add_variant(urlunparse(parsed_url._replace(netloc=host[4:])))
    else:
        add_variant(urlunparse(parsed_url._replace(netloc=f"www.{host}")))

    if parsed_url.scheme == "https":
        add_variant(urlunparse(parsed_url._replace(scheme="http")))

    root_path = "/" if parsed_url.path and parsed_url.path != "/" else parsed_url.path
    add_variant(urlunparse(parsed_url._replace(path=root_path, params="", query="", fragment="")))

    return variants[:4]


def _allowed_by_robots(url: str):
    parsed_url = urlparse(url)
    robots_url = f"{parsed_url.scheme}://{parsed_url.netloc}/robots.txt"

    if robots_url not in robots_cache:
        parser = RobotFileParser()
        parser.set_url(robots_url)

        try:
            response = requests.get(
                robots_url,
                timeout=REQUEST_TIMEOUT_SECONDS,
                headers={"User-Agent": USER_AGENT},
            )
            if response.status_code >= 400:
                robots_cache[robots_url] = None
            else:
                parser.parse(response.text.splitlines())
                robots_cache[robots_url] = parser
        except requests.RequestException:
            robots_cache[robots_url] = None

    parser = robots_cache[robots_url]

    if parser is None:
        return True, None

    if not parser.can_fetch(USER_AGENT, url):
        return False, "Website blocked or unreadable"

    return True, None


def _fetch_single_url(url: str):
    allowed, robots_error = _allowed_by_robots(url)
    if not allowed:
        return {"status": "error", "url": url, "error": robots_error}

    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
            stream=True,
            allow_redirects=True,
        )

        if response.status_code == 404:
            return {"status": "error", "url": url, "error": "Page not found"}
        if response.status_code >= 400:
            return {"status": "error", "url": url, "error": "Website blocked or unreadable"}

        content_type = response.headers.get("content-type", "").lower()
        if content_type and not any(allowed_type in content_type for allowed_type in ("text/html", "text/plain", "application/xhtml")):
            return {"status": "error", "url": url, "error": "Website blocked or unreadable"}

        chunks = []
        total_bytes = 0
        for chunk in response.iter_content(chunk_size=16384):
            if not chunk:
                continue
            total_bytes += len(chunk)
            if total_bytes > MAX_RESPONSE_BYTES:
                break
            chunks.append(chunk)

        if not chunks:
            return {"status": "error", "url": url, "error": "No readable website text found"}

        response.encoding = response.encoding or response.apparent_encoding or "utf-8"
        html = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")

        return {
            "status": "success",
            "url": response.url or url,
            "html": html,
            "truncated": total_bytes > MAX_RESPONSE_BYTES,
        }
    except requests.RequestException as exc:
        return {"status": "error", "url": url, "error": _safe_error_message(exc)}


def fetch_public_page(url: str) -> dict:
    errors = []

    try:
        variants = _url_variants(url)
    except LeadDiscoveryError as exc:
        return {"status": "error", "url": clean_value(url), "error": str(exc)}

    for variant in variants:
        result = _fetch_single_url(variant)
        if result.get("status") == "success":
            return result
        if result.get("error"):
            errors.append(result["error"])

    return {
        "status": "error",
        "url": variants[0] if variants else clean_value(url),
        "error": _dedupe(errors)[0] if errors else "Website unavailable",
    }


def extract_clean_text(html: str) -> str:
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        tag.decompose()

    text = soup.get_text("\n", strip=True)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text[:MAX_TEXT_CHARS].strip()


def extract_emails_regex(text: str):
    if not text:
        return []

    pattern = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    emails = []
    seen = set()

    for match in re.findall(pattern, text):
        email = match.strip(".,;:()[]{}<>\"'").lower()
        domain = email.split("@")[-1]
        if domain in FAKE_EMAIL_DOMAINS:
            continue
        if email not in seen:
            seen.add(email)
            emails.append(email)

    return emails


def extract_phone_regex(text: str):
    if not text:
        return []

    phones = []
    seen = set()

    def add_phone(candidate, label=""):
        phone = _normalize_extracted_phone(candidate, label=label)
        if not phone:
            return

        key = _phone_key(phone)
        if key and key not in seen:
            seen.add(key)
            phones.append(phone)

    label_pattern = re.compile(
        r"(?i)\b(mobile|mob|phone|ph|telephone|tel|contact|office|cell)\.?"
        r"\s*(?:no\.?|number)?\s*[:\-]?\s*"
        r"(\+?\d[\d\s()./-]{6,}\d(?:\s*\(?\s*(?:ext|extension)\.?\s*[:.-]?\s*-?\d{1,5}\s*\)?)?)"
    )
    general_patterns = [
        r"\+91[\s().-]?[6-9]\d[\d\s().-]{8,12}",
        r"\b0?[6-9]\d{9}\b",
        r"\b0\d{2,4}[\s().-]?\d{6,8}\b",
        r"\+91[\s().-]?[1-9]\d{1,4}[\s().-]?\d{6,8}\b",
    ]

    for label, match in label_pattern.findall(text):
        add_phone(match, label=label)

    for line in clean_value(text).splitlines():
        line_text = clean_value(line)
        if not line_text:
            continue

        has_label = re.search(r"(?i)\b(?:mobile|mob|phone|ph|telephone|tel|contact|office|cell)\b", line_text)
        if not has_label and len(phones) >= 8:
            break

        for pattern in general_patterns:
            for match in re.findall(pattern, line_text):
                add_phone(match)

    return phones[:8]


def _normalize_extracted_phone(candidate: str, label: str = ""):
    phone = re.sub(r"\s+", " ", clean_value(candidate)).strip(".,;:()[]{}<>\"'")

    if not phone:
        return ""

    extension_match = re.search(r"(?i)\b(?:ext|extension)\.?\s*[:.-]?\s*(-?\d{1,5})\b", phone)
    extension = extension_match.group(1).lstrip("-") if extension_match else ""
    main_phone = re.sub(r"(?i)\(?\s*\b(?:ext|extension)\.?\s*[:.-]?\s*-?\d{1,5}\s*\)?", "", phone)
    main_phone = re.sub(r"\s+", " ", main_phone).strip(" -./()")
    digits = re.sub(r"\D", "", main_phone)
    normalized_label = clean_value(label).lower().replace(".", "")
    mobile_label = normalized_label in {"mobile", "mob", "cell"}
    office_like = bool(
        not mobile_label
        and (
            re.match(r"^\+?91[\s().-]+\d{2,5}[\s().-]+\d[\d\s().-]{5,10}$", main_phone)
            or re.match(r"^0\d{2,5}[\s().-]+\d[\d\s().-]{5,10}$", main_phone)
            or (len(digits) == 11 and digits.startswith("0") and re.search(r"[\s().-]", main_phone))
            or (len(digits) == 12 and digits.startswith("91") and re.search(r"[\s().-]", main_phone))
        )
    )

    if len(digits) < 8 or len(digits) > 15:
        return ""

    if len(set(digits)) <= 2:
        return ""

    if not office_like and digits.startswith("91") and len(digits) == 12 and digits[2] in "6789":
        normalized = f"+91{digits[2:]}"
    elif not office_like and len(digits) == 10 and digits[0] in "6789":
        normalized = f"+91{digits}"
    elif not office_like and len(digits) == 11 and digits.startswith("0") and digits[1] in "6789":
        normalized = f"+91{digits[1:]}"
    else:
        normalized = re.sub(r"\s*-\s*", "-", main_phone)
        normalized = re.sub(r"\s+", " ", normalized).strip(" -./()")
        if normalized.startswith("91") and not normalized.startswith("+") and len(digits) > 10:
            normalized = f"+{normalized}"

    if extension:
        normalized = f"{normalized} ext {extension}"

    return normalized[:100]


def _phone_key(value: str):
    return re.sub(r"\D", "", clean_value(value))


def _find_phone_near_text(text: str, marker: str):
    lower_text = clean_value(text).lower()
    marker_index = lower_text.find(clean_value(marker).lower())

    if marker_index == -1:
        return ""

    start = max(0, marker_index - 700)
    end = min(len(text), marker_index + len(marker) + 700)
    nearby_phones = extract_phone_regex(text[start:end])

    return nearby_phones[0] if nearby_phones else ""


def _extract_label_value(block: str, label: str, stop_labels: tuple[str, ...]):
    stop_pattern = "|".join(re.escape(stop_label) for stop_label in stop_labels)
    match = re.search(
        rf"(?is)\b{re.escape(label)}\s*:\s*(.*?)(?=\b(?:{stop_pattern})\s*:|$)",
        block,
    )

    if not match:
        return ""

    value = re.sub(r"\s+", " ", match.group(1)).strip(" -|")
    return value


def _extract_person_contact_blocks(page_text: str, source_url: str, organization: str):
    text = clean_value(page_text)
    if not text:
        return []

    contexts = []
    blocks = [
        block.strip()
        for block in re.split(r"(?=\bName\s*:)", text)
        if block.strip()
    ]

    for block in blocks:
        if "Name:" not in block or ("Email:" not in block and "Phone:" not in block and "Mobile:" not in block):
            continue

        block = _truncate(block, 1600)
        emails = extract_emails_regex(block)
        phones = extract_phone_regex(block)

        if not emails and not phones:
            continue

        name = _truncate(
            _extract_label_value(
                block,
                "Name",
                ("Designation", "Date of Joining", "Email", "Phone", "Mobile", "Contact", "Office", "Area of Interest", "Personal Website"),
            ),
            255,
        )
        designation = _truncate(
            _extract_label_value(
                block,
                "Designation",
                ("Date of Joining", "Email", "Phone", "Mobile", "Contact", "Office", "Area of Interest", "Personal Website"),
            ),
            255,
        )

        if emails:
            for email in emails:
                contexts.append({
                    "email": email,
                    "phone": phones[0] if phones else "",
                    "name": name or "",
                    "designation": designation or "",
                    "source_url": source_url,
                    "organization": organization,
                    "context": block,
                    "page_text": page_text,
                })
        else:
            for phone in phones:
                contexts.append({
                    "email": "",
                    "phone": phone,
                    "name": name or "",
                    "designation": designation or "",
                    "source_url": source_url,
                    "organization": organization,
                    "context": block,
                    "page_text": page_text,
                })

    return contexts


def extract_context_around_email(text: str, email: str):
    lower_text = text.lower()
    index = lower_text.find(email.lower())

    if index == -1:
        return _truncate(text, MAX_CONTEXT_CHARS)

    start = max(0, index - 500)
    end = min(len(text), index + len(email) + 500)

    return _truncate(text[start:end], MAX_CONTEXT_CHARS)


def _dedupe(values):
    result = []
    seen = set()

    for value in values:
        text = clean_value(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)

    return result


def _extract_json_array(text):
    cleaned_text = clean_value(text)

    if cleaned_text.startswith("```"):
        cleaned_text = re.sub(r"^```(?:json)?", "", cleaned_text, flags=re.IGNORECASE).strip()
        cleaned_text = re.sub(r"```$", "", cleaned_text).strip()

    try:
        parsed = json.loads(cleaned_text)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\[.*\]", cleaned_text, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON array found in Gemini response.")

    parsed = json.loads(match.group(0))
    if not isinstance(parsed, list):
        raise ValueError("Gemini response did not contain a JSON array.")

    return parsed


def _split_lines(value):
    return [
        item.strip()
        for item in clean_value(value).splitlines()
        if item.strip()
    ]


def _infer_organization(page_text: str, source_url: str):
    lines = [
        line.strip()
        for line in clean_value(page_text).splitlines()
        if line.strip()
    ]

    for line in lines[:10]:
        if 3 <= len(line) <= 120 and "@" not in line:
            return line

    parsed_url = urlparse(source_url)
    return parsed_url.netloc.replace("www.", "")


def _risk_flags_for_contact(email: str | None, source_error: str | None = None):
    flags = []
    email_value = clean_value(email).lower()

    if email_value:
        local_part, _, domain = email_value.partition("@")
        if local_part in GENERIC_EMAIL_PREFIXES:
            flags.append("Generic email address")
        if domain in PERSONAL_EMAIL_DOMAINS:
            flags.append("Personal email address")

    if source_error:
        flags.append(source_error)

    return "; ".join(flags) or None


def _fallback_contacts(contexts, job: DiscoveryJob):
    contacts = []

    for item in contexts:
        email = clean_value(item.get("email"))
        phone = clean_value(item.get("phone"))
        source_url = clean_value(item.get("source_url"))
        organization = clean_value(item.get("organization")) or _infer_organization(item.get("page_text", ""), source_url)

        confidence = 45 if email.split("@")[0] in GENERIC_EMAIL_PREFIXES else 65
        if not email and phone:
            confidence = 35

        contacts.append({
            "name": _truncate(item.get("name"), 255) or None,
            "organization": organization,
            "department": clean_value(job.department) or None,
            "designation": _truncate(item.get("designation"), 255) or clean_value(job.target_role) or None,
            "email": email or None,
            "phone": phone or None,
            "lead_type": clean_value(job.target_type) or "general",
            "location": clean_value(job.location) or None,
            "confidence": confidence,
            "fit_reason": "Contact detail was found on a public source page and needs user review.",
            "risk_flags": _risk_flags_for_contact(email),
            "source_url": source_url,
            "raw_context": clean_value(item.get("context")),
        })

    return contacts


def _build_contact_prompt(contexts, job: DiscoveryJob, campaign: Campaign | None):
    context_lines = []
    for index, item in enumerate(contexts, start=1):
        context_lines.append(
            "\n".join([
                f"CONTACT_CONTEXT_{index}",
                f"Source URL: {clean_value(item.get('source_url'))}",
                f"Found name: {clean_value(item.get('name'))}",
                f"Found designation: {clean_value(item.get('designation'))}",
                f"Found email: {clean_value(item.get('email'))}",
                f"Found phone: {clean_value(item.get('phone'))}",
                f"Page organization hint: {clean_value(item.get('organization'))}",
                f"Nearby text: {clean_value(item.get('context'))}",
            ])
        )

    campaign_context = "No campaign selected."
    if campaign:
        campaign_context = (
            f"Campaign: {clean_value(campaign.campaign_name)}\n"
            f"Industry: {clean_value(campaign.industry)}\n"
            f"Location: {clean_value(campaign.location)}\n"
            f"Target role: {clean_value(campaign.target_role)}\n"
            f"Offer: {clean_value(campaign.offer)}"
        )

    return f"""
Convert public contact snippets into structured lead JSON.
Use only facts present in the snippets, discovery job, and campaign context.
Do not invent email addresses, phone numbers, names, roles, organizations, or locations.
Return strict JSON array only.

Discovery job:
- Title: {clean_value(job.title)}
- Target type: {clean_value(job.target_type)}
- Department/domain: {clean_value(job.department)}
- Location: {clean_value(job.location)}
- Target role: {clean_value(job.target_role)}
- Goal: {clean_value(job.query_goal)}

{campaign_context}

Rules:
- Only include email if it appears as Found email.
- Only include phone if it appears as Found phone.
- If email is generic like info@, contact@, admissions@, admin@, mark risk_flags.
- If email is Gmail/Yahoo/Hotmail/Outlook/Rediffmail, mark risk_flags.
- If name or designation is unknown, use null.
- If the page is a faculty/department page, classify likely professor/department contacts.
- If the page is a company contact page, classify company/generic contacts.
- Always preserve source_url.

Public snippets:
{chr(10).join(context_lines)}

Return JSON array:
[
  {{
    "name": null,
    "organization": "...",
    "department": "...",
    "designation": "...",
    "email": "...",
    "phone": "...",
    "lead_type": "...",
    "location": "...",
    "confidence": 0,
    "fit_reason": "...",
    "risk_flags": "...",
    "source_url": "..."
  }}
]
""".strip()


def ai_structure_contacts(contexts, job: DiscoveryJob, campaign: Campaign | None = None):
    if not contexts:
        return []

    allowed_emails = {
        clean_value(item.get("email")).lower()
        for item in contexts
        if clean_value(item.get("email"))
    }
    allowed_phone_by_key = {
        _phone_key(item.get("phone")): clean_value(item.get("phone"))
        for item in contexts
        if clean_value(item.get("phone")) and _phone_key(item.get("phone"))
    }

    if not settings.GEMINI_API_KEY:
        return _fallback_contacts(contexts, job)

    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=_build_contact_prompt(contexts, job, campaign),
        )
        parsed = _extract_json_array(clean_value(getattr(response, "text", "")))
    except Exception:
        return _fallback_contacts(contexts, job)

    if not isinstance(parsed, list):
        return _fallback_contacts(contexts, job)

    structured_contacts = []
    fallback_by_email = {
        clean_value(item.get("email")).lower(): item
        for item in _fallback_contacts(contexts, job)
        if clean_value(item.get("email"))
    }
    fallback_by_phone = {
        _phone_key(item.get("phone")): item
        for item in _fallback_contacts(contexts, job)
        if clean_value(item.get("phone")) and _phone_key(item.get("phone"))
    }

    for item in parsed:
        if not isinstance(item, dict):
            continue

        email = clean_value(item.get("email")).lower()
        phone = clean_value(item.get("phone"))
        phone_key = _phone_key(phone)

        if email and email not in allowed_emails:
            email = ""
        if phone and phone_key not in allowed_phone_by_key:
            phone = ""
        elif phone:
            phone = allowed_phone_by_key.get(phone_key) or phone

        fallback = fallback_by_email.get(email) or fallback_by_phone.get(_phone_key(phone)) or {}
        if not phone and fallback.get("phone"):
            phone = clean_value(fallback.get("phone"))
        if not email and fallback.get("email"):
            email = clean_value(fallback.get("email")).lower()
        if not email and not phone:
            continue

        confidence = item.get("confidence")
        try:
            confidence = max(0, min(100, int(confidence)))
        except (TypeError, ValueError):
            confidence = fallback.get("confidence") or 50

        structured_contacts.append({
            "name": _truncate(item.get("name"), 255) or None,
            "organization": _truncate(item.get("organization") or fallback.get("organization"), 255) or None,
            "department": _truncate(item.get("department") or fallback.get("department"), 255) or None,
            "designation": _truncate(item.get("designation") or fallback.get("designation"), 255) or None,
            "email": email or None,
            "phone": _truncate(phone, 100) or None,
            "lead_type": _truncate(item.get("lead_type") or fallback.get("lead_type"), 100) or None,
            "location": _truncate(item.get("location") or fallback.get("location"), 255) or None,
            "confidence": confidence,
            "fit_reason": _truncate(item.get("fit_reason") or fallback.get("fit_reason"), 1200) or None,
            "risk_flags": _truncate(item.get("risk_flags") or fallback.get("risk_flags") or _risk_flags_for_contact(email), 1200) or None,
            "source_url": _truncate(item.get("source_url") or fallback.get("source_url"), 1000),
            "raw_context": _truncate(fallback.get("raw_context"), 1200) or None,
        })

    return structured_contacts or _fallback_contacts(contexts, job)


def _make_contexts_for_page(source_url: str, html: str, page_text: str):
    combined_text = f"{page_text}\n{html}"
    emails = extract_emails_regex(combined_text)
    phones = extract_phone_regex(page_text)
    organization = _infer_organization(page_text, source_url)
    contexts = _extract_person_contact_blocks(page_text, source_url, organization)
    seen_emails = {
        clean_value(item.get("email")).lower()
        for item in contexts
        if clean_value(item.get("email"))
    }
    seen_phone_keys = {
        _phone_key(item.get("phone"))
        for item in contexts
        if clean_value(item.get("phone"))
    }

    for email in emails:
        if email in seen_emails:
            continue

        nearby_phone = _find_phone_near_text(page_text, email)
        contexts.append({
            "email": email,
            "phone": nearby_phone or (phones[0] if phones else ""),
            "source_url": source_url,
            "organization": organization,
            "context": extract_context_around_email(page_text, email),
            "page_text": page_text,
        })
        seen_emails.add(email)

    if not contexts:
        for phone in phones[:2]:
            phone_key = _phone_key(phone)
            if phone_key in seen_phone_keys:
                continue

            contexts.append({
                "email": "",
                "phone": phone,
                "source_url": source_url,
                "organization": organization,
                "context": _truncate(page_text, MAX_CONTEXT_CHARS),
                "page_text": page_text,
            })
            seen_phone_keys.add(phone_key)

    return contexts


def _find_existing_contact(db: Session, job_id: int, email: str | None, phone: str | None, source_url: str):
    query = db.query(DiscoveredLead).filter(DiscoveredLead.discovery_job_id == job_id)

    if email:
        return query.filter(DiscoveredLead.email == email).first()

    if phone:
        return query.filter(
            DiscoveredLead.phone == phone,
            DiscoveredLead.source_url == source_url,
        ).first()

    return None


def run_discovery_job(db: Session, job_id: int):
    job = (
        db.query(DiscoveryJob)
        .options(joinedload(DiscoveryJob.campaign))
        .filter(DiscoveryJob.id == job_id)
        .first()
    )

    if not job:
        raise LeadDiscoveryError("Discovery job was not found.")

    job.status = "running"
    job.errors = None
    job.pages_attempted = 0
    job.updated_at = utc_now()
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()

    source_urls = _split_lines(job.source_urls)
    errors = []
    inserted_count = 0

    if not source_urls:
        if clean_value(job.generated_queries):
            errors.append("Generated search queries are ready. Add public source URLs before running discovery.")
        else:
            errors.append("Add public source URLs before running discovery.")
        job.status = "completed"
        job.errors = "\n".join(errors)
        job.contacts_found = db.query(DiscoveredLead).filter(DiscoveredLead.discovery_job_id == job.id).count()
        job.updated_at = utc_now()
        db.commit()
        db.refresh(job)
        return {
            "job_id": job.id,
            "status": job.status,
            "pages_attempted": job.pages_attempted,
            "contacts_found": job.contacts_found,
            "inserted": 0,
            "errors": errors,
        }

    effective_limit = max(1, min(job.limit or 20, MAX_DISCOVERY_PAGES))
    source_urls = source_urls[:effective_limit]

    try:
        for source_url in source_urls:
            job.pages_attempted += 1
            result = fetch_public_page(source_url)

            if result.get("status") != "success":
                errors.append(f"{source_url}: {result.get('error') or 'Website unavailable'}")
                continue

            page_text = extract_clean_text(result.get("html", ""))
            if not page_text:
                errors.append(f"{source_url}: No readable website text found")
                continue

            contexts = _make_contexts_for_page(result.get("url") or source_url, result.get("html", ""), page_text)
            if not contexts:
                errors.append(f"{source_url}: No public contact details found")
                continue

            structured_contacts = ai_structure_contacts(contexts, job, job.campaign)

            for contact in structured_contacts:
                email = clean_value(contact.get("email")).lower() or None
                phone = clean_value(contact.get("phone")) or None
                contact_source_url = clean_value(contact.get("source_url")) or result.get("url") or source_url

                if not email and not phone:
                    continue
                existing_contact = _find_existing_contact(db, job.id, email, phone, contact_source_url)
                if existing_contact:
                    if phone and not clean_value(existing_contact.phone):
                        existing_contact.phone = _truncate(phone, 100) or None
                        existing_contact.updated_at = utc_now()
                        if existing_contact.imported_lead_id:
                            imported_lead = db.get(Lead, existing_contact.imported_lead_id)
                            if imported_lead and not clean_value(imported_lead.phone):
                                imported_lead.phone = _truncate(phone, 100) or None
                    if contact.get("raw_context") and not clean_value(existing_contact.raw_context):
                        existing_contact.raw_context = _truncate(contact.get("raw_context"), 1200) or None
                    continue

                discovered_lead = DiscoveredLead(
                    discovery_job_id=job.id,
                    campaign_id=job.campaign_id,
                    name=_truncate(contact.get("name"), 255) or None,
                    organization=_truncate(contact.get("organization"), 255) or None,
                    department=_truncate(contact.get("department"), 255) or None,
                    designation=_truncate(contact.get("designation"), 255) or None,
                    email=email,
                    phone=_truncate(phone, 100) or None,
                    website=contact_source_url,
                    profile_url=contact_source_url,
                    source_url=contact_source_url,
                    lead_type=_truncate(contact.get("lead_type"), 100) or clean_value(job.target_type) or None,
                    location=_truncate(contact.get("location"), 255) or clean_value(job.location) or None,
                    confidence=contact.get("confidence"),
                    fit_reason=_truncate(contact.get("fit_reason"), 1200) or None,
                    risk_flags=_truncate(contact.get("risk_flags"), 1200) or _risk_flags_for_contact(email),
                    raw_context=_truncate(contact.get("raw_context"), 1200) or None,
                    status="pending",
                )
                db.add(discovered_lead)
                inserted_count += 1

        db.flush()
        job.contacts_found = db.query(DiscoveredLead).filter(DiscoveredLead.discovery_job_id == job.id).count()
        job.status = "completed"
        job.errors = "\n".join(_dedupe(errors)) or None
        job.updated_at = utc_now()
        db.commit()
        db.refresh(job)
    except SQLAlchemyError as exc:
        db.rollback()
        job.status = "failed"
        job.errors = "Discovery results could not be saved."
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
        raise LeadDiscoveryError("Discovery results could not be saved.") from exc

    return {
        "job_id": job.id,
        "status": job.status,
        "pages_attempted": job.pages_attempted,
        "contacts_found": job.contacts_found,
        "inserted": inserted_count,
        "errors": _dedupe(errors),
    }


def _fallback_search_queries(payload: dict):
    target_type = clean_value(payload.get("target_type")).lower()
    department = clean_value(payload.get("department")) or clean_value(payload.get("query_goal")) or "target audience"
    location = clean_value(payload.get("location")) or "India"
    role = clean_value(payload.get("target_role"))

    if target_type in {"professor", "college", "department", "student"} or any(
        keyword in f"{department} {role}".lower()
        for keyword in ("professor", "faculty", "hod", "college", "department", "research")
    ):
        return [
            f'site:.ac.in "faculty" "{department}" "email" "{location}"',
            f'site:.edu.in "engineering college" "{role or "HOD"}" "email"',
            f'site:.ac.in "{department}" "HOD" "email"',
            f'site:.ac.in "{department}" "research" "faculty" "email"',
        ]

    if "restaurant" in f"{department} {payload.get('query_goal')}".lower():
        return [
            f'"restaurant" "{location}" "contact" "email"',
            f'"restaurant owner" "{location}" "official website"',
            f'"best restaurants" "{location}" "contact us"',
        ]

    return [
        f'"{department}" "{location}" "contact" "email"',
        f'"{department}" "{role or "manager"}" "official website"',
        f'"{department}" "{location}" "team" "contact"',
        f'"{department}" "{location}" "directory"',
    ]


def generate_search_queries(payload: dict):
    fallback_queries = _fallback_search_queries(payload)

    if not settings.GEMINI_API_KEY:
        return fallback_queries

    prompt = f"""
Generate safe manual search queries for finding public source URLs.
Do not suggest scraping LinkedIn or search result pages. LinkedIn may be used only as manual search or user-provided URLs.
Return strict JSON only: {{"queries": ["..."]}}

Context:
- Title: {clean_value(payload.get("title"))}
- Target type: {clean_value(payload.get("target_type"))}
- Department/domain: {clean_value(payload.get("department"))}
- Location: {clean_value(payload.get("location"))}
- Target role: {clean_value(payload.get("target_role"))}
- Goal: {clean_value(payload.get("query_goal"))}
- Offer: {clean_value(payload.get("offer"))}

Examples:
- site:.ac.in "faculty" "computer science" "email" "India"
- site:.edu.in "engineering college" "HOD" "email"
- "restaurant" "Pune" "contact" "email"
- "SaaS startup" "CTO" "security" "contact"
""".strip()

    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
        )
        parsed = extract_json_from_text(clean_value(getattr(response, "text", "")))
        queries = parsed.get("queries") if isinstance(parsed, dict) else None
        if isinstance(queries, list):
            cleaned_queries = _dedupe(_truncate(query, 220) for query in queries)
            return cleaned_queries[:8] or fallback_queries
    except Exception:
        return fallback_queries

    return fallback_queries


def approve_or_reject_results(db: Session, result_ids: list[int], status: str):
    if status not in {"approved", "rejected"}:
        raise LeadDiscoveryError("Invalid result status.")

    if not result_ids:
        return 0

    results = db.query(DiscoveredLead).filter(DiscoveredLead.id.in_(result_ids)).all()

    for result in results:
        if result.status not in IMPORTED_RESULT_STATUSES:
            result.status = status
            result.updated_at = utc_now()

    db.commit()
    return len(results)


def _build_discovered_lead_values(result: DiscoveredLead, job: DiscoveryJob, include_fallbacks: bool = False):
    email = _normalize_email(result.email)
    source_url = _clean_upsert_value(result.source_url)
    profile_url = _clean_upsert_value(result.profile_url)
    website = _clean_upsert_value(result.website) or profile_url or source_url
    organization = _clean_upsert_value(result.organization, 255)

    if include_fallbacks and not organization:
        organization = _email_domain(email) if email else "Discovered contact"

    return {
        "company_name": organization,
        "website": _clean_upsert_value(website, 255),
        "industry": _clean_upsert_value(result.department, 255)
        or _clean_upsert_value(result.lead_type, 255)
        or (_clean_upsert_value(job.campaign.industry, 255) if include_fallbacks and job.campaign else None),
        "location": _clean_upsert_value(result.location, 255)
        or (_clean_upsert_value(job.location, 255) if include_fallbacks else None)
        or (_clean_upsert_value(job.campaign.location, 255) if include_fallbacks and job.campaign else None),
        "contact_name": _clean_upsert_value(result.name, 255),
        "contact_role": _clean_upsert_value(result.designation, 255)
        or (_clean_upsert_value(job.target_role, 255) if include_fallbacks else None),
        "email": email,
        "phone": _clean_upsert_value(result.phone, 100),
        "source_url": _clean_upsert_value(source_url),
        "profile_url": _clean_upsert_value(profile_url),
    }


def _find_duplicate_lead(db: Session, campaign_id: int, values: dict):
    email = values.get("email")
    if email:
        duplicate = (
            db.query(Lead)
            .filter(
                Lead.campaign_id == campaign_id,
                func.lower(func.trim(Lead.email)) == email,
            )
            .first()
        )
        if duplicate:
            return duplicate

    name_key = _normalize_text_key(values.get("contact_name"))
    organization_key = _normalize_text_key(values.get("company_name"))
    if name_key and organization_key:
        candidates = (
            db.query(Lead)
            .filter(
                Lead.campaign_id == campaign_id,
                Lead.contact_name.isnot(None),
                Lead.company_name.isnot(None),
            )
            .all()
        )
        for candidate in candidates:
            if (
                _normalize_text_key(candidate.contact_name) == name_key
                and _normalize_text_key(candidate.company_name) == organization_key
            ):
                return candidate

    if not email:
        discovered_url_keys = {
            key
            for key in (
                _normalize_url_key(values.get("website")),
                _normalize_url_key(values.get("source_url")),
                _normalize_url_key(values.get("profile_url")),
            )
            if key
        }
        if discovered_url_keys:
            candidates = db.query(Lead).filter(Lead.campaign_id == campaign_id).all()
            for candidate in candidates:
                candidate_url_keys = {
                    key
                    for key in (
                        _normalize_url_key(candidate.website),
                        _normalize_url_key(candidate.source_url),
                        _normalize_url_key(candidate.profile_url),
                    )
                    if key
                }
                if discovered_url_keys.intersection(candidate_url_keys):
                    return candidate

    return None


def _apply_discovered_data_to_existing_lead(lead: Lead, values: dict):
    updated_fields = []

    contact_name = values.get("contact_name")
    if contact_name and not _is_generic_contact_name(contact_name):
        if _is_missing_value(lead.contact_name) or _is_generic_contact_name(lead.contact_name):
            if _set_if_changed(lead, "contact_name", contact_name):
                updated_fields.append("contact_name")

    contact_role = values.get("contact_role")
    new_role_quality = _role_quality(contact_role)
    existing_role_quality = _role_quality(lead.contact_role)
    if contact_role and new_role_quality > 0:
        if _is_missing_value(lead.contact_role) or (
            existing_role_quality < new_role_quality and existing_role_quality <= 2
        ):
            if _set_if_changed(lead, "contact_role", contact_role):
                updated_fields.append("contact_role")

    email = values.get("email")
    existing_email = _normalize_email(lead.email)
    if email and not _is_fake_email(email):
        existing_email_is_weak = (
            not existing_email
            or _is_fake_email(existing_email)
            or (_is_generic_email(existing_email) and not _is_generic_email(email))
        )
        if existing_email_is_weak and _set_if_changed(lead, "email", email):
            updated_fields.append("email")

    phone = values.get("phone")
    if phone:
        existing_phone_digits = _normalize_phone_digits(lead.phone)
        new_phone_digits = _normalize_phone_digits(phone)
        if _is_missing_value(lead.phone):
            if _set_if_changed(lead, "phone", phone):
                updated_fields.append("phone")
        elif (
            existing_phone_digits
            and new_phone_digits
            and _is_same_phone_number(existing_phone_digits, new_phone_digits)
            and _phone_quality(phone) > _phone_quality(lead.phone)
        ):
            if _set_if_changed(lead, "phone", phone):
                updated_fields.append("phone")

    website = values.get("website") or values.get("profile_url") or values.get("source_url")
    if website:
        existing_website_key = _normalize_url_key(lead.website)
        website_key = _normalize_url_key(website)
        if _is_missing_value(lead.website):
            if _set_if_changed(lead, "website", website[:255]):
                updated_fields.append("website")
        elif website_key and existing_website_key == website_key and _url_quality(website) > _url_quality(lead.website):
            if _set_if_changed(lead, "website", website[:255]):
                updated_fields.append("website")

    company_name = values.get("company_name")
    if company_name:
        should_update_company = _is_weak_company_name(lead.company_name) or (
            _is_domain_like(lead.company_name) and not _is_domain_like(company_name)
        )
        if should_update_company and _set_if_changed(lead, "company_name", company_name[:255]):
            updated_fields.append("company_name")

    industry = values.get("industry")
    if industry and _is_missing_value(lead.industry):
        if _set_if_changed(lead, "industry", industry[:255]):
            updated_fields.append("industry")

    location = values.get("location")
    if location and _is_missing_value(lead.location):
        if _set_if_changed(lead, "location", location[:255]):
            updated_fields.append("location")

    source_url = values.get("source_url")
    if source_url and _is_missing_value(lead.source_url):
        if _set_if_changed(lead, "source_url", source_url):
            updated_fields.append("source_url")

    profile_url = values.get("profile_url")
    if profile_url and _is_missing_value(lead.profile_url):
        if _set_if_changed(lead, "profile_url", profile_url):
            updated_fields.append("profile_url")

    if updated_fields or _is_missing_value(lead.source):
        source = _append_discovery_source(lead.source)
        if _set_if_changed(lead, "source", source):
            updated_fields.append("source")

    return updated_fields


def import_selected_results(db: Session, job_id: int, result_ids: list[int], allow_no_email: bool = False):
    job = (
        db.query(DiscoveryJob)
        .options(joinedload(DiscoveryJob.campaign))
        .filter(DiscoveryJob.id == job_id)
        .first()
    )

    if not job:
        raise LeadDiscoveryError("Discovery job was not found.")

    if not job.campaign_id or not job.campaign:
        raise LeadDiscoveryError("Select a campaign before importing discovered leads.")

    results = (
        db.query(DiscoveredLead)
        .filter(
            DiscoveredLead.discovery_job_id == job_id,
            DiscoveredLead.id.in_(result_ids),
        )
        .all()
    )
    imported = 0
    updated = 0
    skipped_duplicates = 0
    unchanged = 0
    failed = 0
    skipped_no_email = 0
    skipped_rejected = 0
    imported_lead_ids = []
    details = []

    try:
        for result in results:
            if result.status == "rejected":
                skipped_rejected += 1
                details.append({
                    "discovered_lead_id": result.id,
                    "lead_id": result.imported_lead_id,
                    "action": "skipped",
                    "reason": "rejected",
                    "updated_fields": [],
                })
                continue

            values = _build_discovered_lead_values(result, job)
            duplicate = _find_duplicate_lead(db, job.campaign_id, values)

            if duplicate:
                updated_fields = _apply_discovered_data_to_existing_lead(duplicate, values)
                result.imported_lead_id = duplicate.id
                result.status = (
                    "updated_existing"
                    if updated_fields or result.status == "updated_existing"
                    else "imported"
                )
                result.updated_at = utc_now()

                if updated_fields:
                    updated += 1
                    details.append({
                        "discovered_lead_id": result.id,
                        "lead_id": duplicate.id,
                        "action": "updated",
                        "updated_fields": updated_fields,
                    })
                else:
                    unchanged += 1
                    details.append({
                        "discovered_lead_id": result.id,
                        "lead_id": duplicate.id,
                        "action": "unchanged",
                        "updated_fields": [],
                    })
                continue

            if not values.get("email") and not allow_no_email:
                skipped_no_email += 1
                details.append({
                    "discovered_lead_id": result.id,
                    "lead_id": None,
                    "action": "skipped",
                    "reason": "no_email",
                    "updated_fields": [],
                })
                continue

            create_values = _build_discovered_lead_values(result, job, include_fallbacks=True)
            organization = create_values.get("company_name") or "Discovered contact"
            lead = Lead(
                campaign_id=job.campaign_id,
                company_name=organization[:255],
                website=create_values.get("website"),
                industry=create_values.get("industry"),
                location=create_values.get("location"),
                contact_name=create_values.get("contact_name"),
                contact_role=create_values.get("contact_role"),
                email=create_values.get("email"),
                phone=create_values.get("phone"),
                source_url=create_values.get("source_url"),
                profile_url=create_values.get("profile_url"),
                source="discovery",
                status="new",
            )
            db.add(lead)
            db.flush()
            result.status = "imported"
            result.imported_lead_id = lead.id
            result.updated_at = utc_now()
            imported += 1
            imported_lead_ids.append(lead.id)
            details.append({
                "discovered_lead_id": result.id,
                "lead_id": lead.id,
                "action": "imported",
                "updated_fields": [],
            })

        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise LeadDiscoveryError("Discovered leads could not be imported.") from exc

    return {
        "processed": len(results),
        "imported": imported,
        "updated": updated,
        "skipped_duplicates": skipped_duplicates,
        "unchanged": unchanged,
        "failed": failed,
        "skipped_no_email": skipped_no_email,
        "skipped_rejected": skipped_rejected,
        "imported_lead_ids": imported_lead_ids,
        "details": details,
    }


def research_imported_leads(db: Session, job_id: int, limit: int = 5):
    effective_limit = max(1, min(limit, 10))
    results = (
        db.query(DiscoveredLead)
        .filter(
            DiscoveredLead.discovery_job_id == job_id,
            DiscoveredLead.status.in_(IMPORTED_RESULT_STATUSES),
            DiscoveredLead.imported_lead_id.isnot(None),
        )
        .order_by(DiscoveredLead.updated_at.desc(), DiscoveredLead.id.desc())
        .limit(effective_limit)
        .all()
    )
    researched = 0
    failed = 0
    output = []

    for result in results:
        try:
            research_result = research_lead(db, result.imported_lead_id)
            if research_result.get("research_status") == "researched":
                researched += 1
            else:
                failed += 1
            output.append(research_result)
        except Exception:
            failed += 1
            output.append({
                "lead_id": result.imported_lead_id,
                "research_status": "failed",
                "research_error": "Lead research failed. Please try again.",
            })

    return {
        "processed": len(results),
        "researched": researched,
        "failed": failed,
        "results": output,
    }


def parse_json_list(value):
    text = clean_value(value)
    if not text:
        return []

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    return _split_lines(text)
