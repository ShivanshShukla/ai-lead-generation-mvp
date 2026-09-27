"""
Hunter.io API v2 service.

Docs: https://hunter.io/api-documentation
Base URL: https://api.hunter.io/v2/
Auth: api_key query parameter
"""

import logging
from urllib.parse import urlparse

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

HUNTER_BASE_URL = "https://api.hunter.io/v2"


def normalize_domain(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    if "://" not in text:
        text = f"https://{text}"

    parsed = urlparse(text)
    domain = parsed.netloc or parsed.path.split("/", 1)[0]
    domain = domain.lower().strip()

    if domain.startswith("www."):
        domain = domain[4:]

    return domain


def get_hunter_status() -> dict:
    api_key = settings.HUNTER_API_KEY

    return {
        "configured": bool(api_key),
        "is_test_key": api_key == "test-api-key",
        "message": (
            "Hunter.io configured with the test key. Dummy responses only."
            if api_key == "test-api-key"
            else "Hunter.io configured."
            if api_key
            else "Hunter.io not configured. Set HUNTER_API_KEY in the backend environment."
        ),
    }


def _api_key() -> str:
    return settings.HUNTER_API_KEY


def _missing_key_response(default_payload: dict) -> dict:
    return {
        **default_payload,
        "error": "Hunter.io is not configured. Set HUNTER_API_KEY in the backend environment.",
    }


def _hunter_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"Hunter API error: {response.status_code}"

    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        details = errors[0].get("details") or errors[0].get("id")
        if details:
            return f"Hunter API error: {details}"

    if isinstance(errors, dict):
        details = errors.get("details") or errors.get("id")
        if details:
            return f"Hunter API error: {details}"

    return f"Hunter API error: {response.status_code}"


async def _hunter_get(endpoint: str, params: dict, client: httpx.AsyncClient | None = None):
    timeout = max(1.0, float(settings.HUNTER_REQUEST_TIMEOUT or 8.0))
    url = f"{HUNTER_BASE_URL}/{endpoint}"

    if client is not None:
        return await client.get(url, params=params, timeout=timeout)

    async with httpx.AsyncClient(timeout=timeout) as temporary_client:
        return await temporary_client.get(url, params=params)


async def domain_search(domain: str, limit: int = 10, client: httpx.AsyncClient | None = None) -> dict:
    normalized_domain = normalize_domain(domain)
    if not normalized_domain:
        return {"domain": "", "organization": "", "pattern": "", "emails": [], "total": 0, "error": "No domain provided"}

    if not _api_key():
        return _missing_key_response({
            "domain": normalized_domain,
            "organization": "",
            "pattern": "",
            "emails": [],
            "total": 0,
        })

    params = {
        "domain": normalized_domain,
        "api_key": _api_key(),
        "limit": max(1, min(int(limit or 10), 100)),
    }

    try:
        response = await _hunter_get("domain-search", params, client=client)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        message = _hunter_error_message(exc.response)
        logger.warning("Hunter domain search HTTP error for %s: %s", normalized_domain, message)
        return {"domain": normalized_domain, "organization": "", "pattern": "", "emails": [], "total": 0, "error": message}
    except httpx.HTTPError as exc:
        logger.warning("Hunter domain search failed for %s: %s", normalized_domain, exc)
        return {"domain": normalized_domain, "organization": "", "pattern": "", "emails": [], "total": 0, "error": str(exc)}

    data = response.json().get("data", {})
    emails = data.get("emails") or []

    return {
        "domain": normalized_domain,
        "organization": data.get("organization") or "",
        "pattern": data.get("pattern") or "",
        "emails": emails,
        "total": len(emails),
        "error": None,
    }


async def email_finder(domain: str, first_name: str, last_name: str, client: httpx.AsyncClient | None = None) -> dict:
    normalized_domain = normalize_domain(domain)
    first_name = str(first_name or "").strip()
    last_name = str(last_name or "").strip()

    if not normalized_domain or not first_name or not last_name:
        return {"email": None, "score": 0, "type": "", "sources": [], "error": "Missing domain, first name, or last name"}

    if not _api_key():
        return _missing_key_response({"email": None, "score": 0, "type": "", "sources": []})

    params = {
        "domain": normalized_domain,
        "first_name": first_name,
        "last_name": last_name,
        "api_key": _api_key(),
    }

    try:
        response = await _hunter_get("email-finder", params, client=client)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        message = _hunter_error_message(exc.response)
        logger.warning("Hunter email finder HTTP error for %s: %s", normalized_domain, message)
        return {"email": None, "score": 0, "type": "", "sources": [], "error": message}
    except httpx.HTTPError as exc:
        logger.warning("Hunter email finder failed for %s: %s", normalized_domain, exc)
        return {"email": None, "score": 0, "type": "", "sources": [], "error": str(exc)}

    data = response.json().get("data", {})

    return {
        "email": data.get("email"),
        "score": data.get("score") or 0,
        "type": data.get("type") or "",
        "sources": data.get("sources") or [],
        "error": None,
    }


async def email_verifier(email: str, client: httpx.AsyncClient | None = None) -> dict:
    email = str(email or "").strip()
    if not email:
        return {"result": "unknown", "score": 0, "deliverable": False, "error": "No email provided"}

    if not _api_key():
        return _missing_key_response({"result": "unknown", "score": 0, "deliverable": False})

    params = {
        "email": email,
        "api_key": _api_key(),
    }

    try:
        response = await _hunter_get("email-verifier", params, client=client)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        message = _hunter_error_message(exc.response)
        logger.warning("Hunter email verifier HTTP error for %s: %s", email, message)
        return {"result": "unknown", "score": 0, "deliverable": False, "error": message}
    except httpx.HTTPError as exc:
        logger.warning("Hunter email verifier failed for %s: %s", email, exc)
        return {"result": "unknown", "score": 0, "deliverable": False, "error": str(exc)}

    data = response.json().get("data", {})
    result = data.get("result") or "unknown"

    return {
        "result": result,
        "score": data.get("score") or 0,
        "deliverable": result == "deliverable",
        "error": None,
    }
