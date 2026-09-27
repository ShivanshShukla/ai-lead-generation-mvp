"""
Pattern-based email resolver for Indian businesses.

This keeps the existing website scraper as the first pass, then falls back to
common company aliases and a best-effort SMTP probe when a public email is not
visible on the site.
"""

from __future__ import annotations

import logging
import re
import smtplib
import socket
import unicodedata
from urllib.parse import urlparse

try:
    from dns import resolver as dns_resolver
except ImportError:  # pragma: no cover - optional dependency in local dev shells
    dns_resolver = None

from app.services.scraper_service import find_emails_from_website

logger = logging.getLogger(__name__)

FAKE_EMAIL_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "test.com",
    "domain.com",
    "email.com",
    "yoursite.com",
    "website.com",
}

BUSINESS_PREFIXES = [
    "info",
    "contact",
    "hello",
    "admin",
    "support",
    "sales",
    "founder",
    "ceo",
    "hr",
    "enquiry",
]

SECONDARY_PREFIXES = [
    "enquiries",
    "office",
    "team",
    "business",
    "mail",
    "accounts",
    "billing",
    "operations",
    "care",
    "connect",
    "reach",
]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
DNS_TIMEOUT_SECONDS = 3.0
SMTP_TIMEOUT_SECONDS = 3.0
MAX_CANDIDATES = 14


def _normalize_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def clean_domain(website: str | None) -> str:
    if not website:
        return ""

    text = str(website).strip().lower()
    if not text:
        return ""

    if "://" not in text:
        text = f"https://{text}"

    parsed = urlparse(text)
    domain = parsed.netloc or parsed.path.split("/", 1)[0]
    domain = domain.split("@")[-1].split(":", 1)[0].strip()

    if domain.startswith("www."):
        domain = domain[4:]

    if not domain or domain in FAKE_EMAIL_DOMAINS or "." not in domain:
        return ""

    return domain


def _is_fake_email(email: str) -> bool:
    if "@" not in email:
        return True

    domain = email.split("@", 1)[1].lower()
    return domain in FAKE_EMAIL_DOMAINS


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    deduped = []
    seen = set()

    for item in items:
        normalized = str(item or "").strip().lower()
        if not normalized or normalized in seen:
            continue

        seen.add(normalized)
        deduped.append(normalized)

    return deduped


def _split_contact_name(contact_name: str | None) -> tuple[str, str]:
    parts = [_normalize_text(part) for part in re.split(r"\s+", str(contact_name or "").strip()) if _normalize_text(part)]
    if not parts:
        return "", ""

    first_name = parts[0]
    last_name = parts[-1] if len(parts) > 1 else ""
    return first_name, last_name


def build_candidate_emails(domain: str, contact_name: str | None = None) -> list[str]:
    candidates: list[str] = []

    for prefix in BUSINESS_PREFIXES:
        candidates.append(f"{prefix}@{domain}")

    first_name, last_name = _split_contact_name(contact_name)
    if first_name and last_name:
        candidates.extend(
            [
                f"{first_name}.{last_name}@{domain}",
                f"{first_name}{last_name}@{domain}",
                f"{first_name}@{domain}",
                f"{first_name[0]}.{last_name}@{domain}",
            ]
        )
    elif first_name:
        candidates.append(f"{first_name}@{domain}")

    for prefix in SECONDARY_PREFIXES:
        candidates.append(f"{prefix}@{domain}")

    return _dedupe_preserve_order(candidates)[:MAX_CANDIDATES]


def _email_priority_key(email: str):
    local_part = str(email or "").split("@", 1)[0].lower()

    if local_part in BUSINESS_PREFIXES:
        return (0, BUSINESS_PREFIXES.index(local_part), local_part)

    if local_part in SECONDARY_PREFIXES:
        return (1, SECONDARY_PREFIXES.index(local_part), local_part)

    if "." in local_part:
        return (2, local_part)

    return (3, local_part)


def prioritize_emails(emails: list[str]) -> list[str]:
    normalized = [
        email
        for email in _dedupe_preserve_order(emails)
        if email and not _is_fake_email(email) and EMAIL_RE.fullmatch(email)
    ]
    return sorted(normalized, key=_email_priority_key)


def resolve_mx_hosts(domain: str) -> list[str]:
    if dns_resolver is None:
        return []

    resolver = dns_resolver.Resolver()
    resolver.timeout = DNS_TIMEOUT_SECONDS
    resolver.lifetime = DNS_TIMEOUT_SECONDS

    try:
        answers = resolver.resolve(domain, "MX")
    except Exception:
        return []

    mx_hosts = [
        str(record.exchange).rstrip(".")
        for record in sorted(answers, key=lambda record: record.preference)
    ]

    return mx_hosts


def has_mx_record(domain: str) -> bool:
    return bool(resolve_mx_hosts(domain))


def verify_email_smtp(email: str, mx_hosts: list[str] | None = None, domain: str | None = None) -> bool:
    mx_hosts = mx_hosts or (resolve_mx_hosts(domain) if domain else [])
    if not mx_hosts:
        return False

    mx_host = mx_hosts[0]

    try:
        with smtplib.SMTP(timeout=SMTP_TIMEOUT_SECONDS) as smtp:
            smtp.connect(mx_host, 25)
            smtp.ehlo_or_helo_if_needed()
            smtp.mail("verify@localhost")
            code, _message = smtp.rcpt(email)
            return code in {250, 251}
    except (OSError, smtplib.SMTPException, socket.timeout, ValueError):
        return False


def guess_email_by_pattern(domain: str, contact_name: str | None = None) -> dict:
    candidates = build_candidate_emails(domain, contact_name)
    if not candidates:
        return {
            "domain": domain,
            "email": None,
            "emails": [],
            "candidate_emails": [],
            "method": None,
            "source": "Email Guesser",
            "verified": False,
            "verification": "no_candidates",
            "confidence": 0,
            "error": "No candidate email patterns available.",
        }

    mx_hosts = resolve_mx_hosts(domain)
    if mx_hosts:
        for candidate in candidates:
            if verify_email_smtp(candidate, mx_hosts=mx_hosts):
                return {
                    "domain": domain,
                    "email": candidate,
                    "emails": [candidate],
                    "candidate_emails": candidates,
                    "method": "pattern_verified",
                    "source": "Email Guesser",
                    "verified": True,
                    "verification": "smtp_rcpt",
                    "confidence": 95,
                    "error": None,
                }

        return {
            "domain": domain,
            "email": candidates[0],
            "emails": [candidates[0]],
            "candidate_emails": candidates,
            "method": "pattern_guess",
            "source": "Email Guesser",
            "verified": False,
            "verification": "mx_record_only",
            "confidence": 75,
            "error": None,
        }

    return {
        "domain": domain,
        "email": candidates[0],
        "emails": [candidates[0]],
        "candidate_emails": candidates,
        "method": "pattern_guess",
        "source": "Email Guesser",
        "verified": False,
        "verification": "no_mx_record",
        "confidence": 60,
        "error": None,
    }


def find_email_for_website(website: str, contact_name: str | None = None) -> dict:
    domain = clean_domain(website)
    if not domain:
        return {
            "domain": "",
            "email": None,
            "emails": [],
            "candidate_emails": [],
            "method": None,
            "source": "Email Guesser",
            "verified": False,
            "verification": "invalid_domain",
            "confidence": 0,
            "pages_checked": [],
            "error": "Invalid domain",
        }

    scraped = find_emails_from_website(website)
    scraped_emails = prioritize_emails(scraped.get("emails") or [])

    if scraped_emails:
        return {
            "domain": domain,
            "email": scraped_emails[0],
            "emails": scraped_emails,
            "candidate_emails": scraped_emails,
            "method": "website_scrape",
            "source": "Website Scraper",
            "verified": True,
            "verification": "found_on_website",
            "confidence": 90,
            "pages_checked": scraped.get("pages_checked", []),
            "error": None,
        }

    guessed = guess_email_by_pattern(domain, contact_name)
    guessed["pages_checked"] = scraped.get("pages_checked", [])

    if scraped.get("error") and not guessed.get("email"):
        guessed["error"] = scraped["error"]

    return guessed
