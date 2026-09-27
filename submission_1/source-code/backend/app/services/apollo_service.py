"""
Apollo.io API service for email enrichment.
Docs: https://www.apollo.io/developers/api
Base URL: https://api.apollo.io/v1
Auth: X-Api-Key header
"""

import httpx
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

APOLLO_BASE = "https://api.apollo.io/v1"


def is_configured() -> bool:
    """Check if Apollo API key is configured."""
    return bool(settings.APOLLO_API_KEY)


async def find_email_by_domain(domain: str, limit: int = 5) -> dict:
    """
    Search Apollo for people at a given company domain.
    Returns list of contacts with emails.
    
    Free plan: 50 credits/day
    """
    if not domain:
        return {"contacts": [], "error": "No domain provided"}

    # Clean domain
    domain = domain.replace("https://", "").replace("http://", "")
    domain = domain.replace("www.", "").split("/")[0].strip()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{APOLLO_BASE}/mixed_people/search",
                headers={
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                    "X-Api-Key": settings.APOLLO_API_KEY,
                },
                json={
                    "organization_domains": [domain],
                    "page": 1,
                    "per_page": limit,
                    "contact_email_status": ["verified"],
                }
            )
            resp.raise_for_status()
            data = resp.json()
            people = data.get("people", [])

            contacts = []
            for person in people:
                email = person.get("email")
                if not email:
                    continue
                contacts.append({
                    "email": email,
                    "first_name": person.get("first_name", ""),
                    "last_name": person.get("last_name", ""),
                    "title": person.get("title", ""),
                    "linkedin": person.get("linkedin_url", ""),
                    "confidence": "verified"
                })

            return {
                "domain": domain,
                "contacts": contacts,
                "total": len(contacts),
                "error": None
            }

    except Exception as e:
        logger.error(f"Apollo search failed for {domain}: {e}")
        return {"contacts": [], "error": str(e)}


async def enrich_lead_email(domain: str) -> dict:
    """
    Get the best email for a lead domain.
    Prioritizes: Founder > CEO > CTO > HR > any verified
    """
    result = await find_email_by_domain(domain, limit=10)
    contacts = result.get("contacts", [])

    if not contacts:
        return {"email": None, "error": result.get("error", "No contacts found")}

    # Priority roles
    priority_titles = [
        "founder", "co-founder", "ceo", "cto", 
        "director", "vp", "head", "hr", "manager"
    ]

    # Find best contact
    for title_keyword in priority_titles:
        for contact in contacts:
            title = contact.get("title", "").lower()
            if title_keyword in title:
                return {
                    "email": contact["email"],
                    "name": f"{contact['first_name']} {contact['last_name']}".strip(),
                    "title": contact["title"],
                    "source": "apollo"
                }

    # Return first verified email if no priority match
    return {
        "email": contacts[0]["email"],
        "name": f"{contacts[0]['first_name']} {contacts[0]['last_name']}".strip(),
        "title": contacts[0].get("title", ""),
        "source": "apollo"
    }
