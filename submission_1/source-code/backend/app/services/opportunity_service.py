import json
import re

from google import genai
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Campaign, DiscoveryJob, Opportunity
from app.services.ai_service import clean_value, extract_json_from_text
from app.services.knowledge_service import build_knowledge_context, search_relevant_knowledge
from app.utils.time_utils import utc_now

FALLBACK_OPPORTUNITY_MODEL = "fallback-opportunity-template"
MAX_STRATEGY_CONTEXT_CHARS = 2200
VALID_OPPORTUNITY_STATUSES = {"draft", "generated", "converted", "archived"}


class OpportunityServiceError(RuntimeError):
    pass


def _truncate(value, max_length: int | None = None):
    text = clean_value(value)

    if max_length and len(text) > max_length:
        return text[:max_length].rstrip()

    return text


def _as_list(value):
    if value is None:
        return []

    if isinstance(value, list):
        return [
            clean_value(item)
            for item in value
            if clean_value(item)
        ]

    if isinstance(value, dict):
        return [
            clean_value(value)
        ]

    text = clean_value(value)

    if not text:
        return []

    return [
        item.strip(" -\t")
        for item in re.split(r"[\n;]+", text)
        if item.strip(" -\t")
    ]


def _join_list(value):
    return "\n".join(_as_list(value)) or None


def _format_follow_up_sequence(value):
    if isinstance(value, list):
        normalized_steps = []

        for index, item in enumerate(value, start=1):
            if isinstance(item, dict):
                normalized_steps.append({
                    "step": item.get("step") or index,
                    "purpose": _truncate(item.get("purpose"), 500),
                    "message": _truncate(item.get("message"), 1200),
                })
            elif clean_value(item):
                normalized_steps.append({
                    "step": index,
                    "purpose": "Follow up",
                    "message": clean_value(item),
                })

        return json.dumps(normalized_steps, ensure_ascii=True, indent=2) if normalized_steps else None

    text = clean_value(value)
    return text or None


def _fallback_strategy(opportunity: Opportunity):
    target_domain = clean_value(opportunity.target_domain) or "the target market"
    target_location = clean_value(opportunity.target_location) or "the selected region"
    offer = clean_value(opportunity.offer) or clean_value(opportunity.raw_goal) or "the offer"
    title = clean_value(opportunity.title) or "New opportunity"
    goal_text = f"{title} {target_domain} {target_location} {offer} {clean_value(opportunity.raw_goal)}".lower()
    ideal_roles = ["Founder", "Owner", "Manager", "Operations Head", "Relevant department lead"]
    pain_points = [
        "Current process may be manual or inconsistent.",
        "Decision-makers may need a clearer way to evaluate the offer.",
        "Relevance should be confirmed before making strong claims.",
    ]
    discovery = {
        "target_type": "general",
        "department": target_domain,
        "role": "Relevant decision-maker",
        "queries": [
            f"{target_domain} {target_location} contact email",
            f"{target_domain} {target_location} team decision maker",
            f"{target_domain} {target_location} official website",
        ],
    }

    if any(keyword in goal_text for keyword in ("professor", "faculty", "hod", "college", "department", "research")):
        ideal_roles = ["Professor", "HOD", "Faculty coordinator", "Research coordinator", "Project coordinator"]
        pain_points = [
            "Students may need project implementation support, prototypes, mentorship, or documentation.",
            "Departments may need practical project and research execution support.",
            "Faculty relevance should be verified before outreach.",
        ]
        discovery = {
            "target_type": "professor",
            "department": target_domain,
            "role": "Professor / HOD / Faculty coordinator",
            "queries": [
                f'site:.ac.in "faculty" "{target_domain}" "email" "{target_location}"',
                f'site:.edu.in "engineering college" "HOD" "email" "{target_location}"',
                f'site:.ac.in "{target_domain}" "research" "faculty" "email"',
            ],
        }
    elif "restaurant" in goal_text:
        ideal_roles = ["Owner", "Restaurant manager", "Marketing manager"]
        pain_points = ["Weak local discovery", "Few Google reviews", "Low Instagram visibility", "Inconsistent footfall"]
        discovery = {
            "target_type": "company",
            "department": "Restaurants",
            "role": "Owner / Manager",
            "queries": [
                f'"restaurant" "{target_location}" "contact" "email"',
                f'"restaurant owner" "{target_location}" "official website"',
                f'"restaurant" "{target_location}" "contact us"',
            ],
        }

    return {
        "ai_summary": f"Build an outreach campaign for {target_domain} in {target_location} around {offer}.",
        "target_audience": f"Organizations, decision-makers, and coordinators connected to {target_domain}.",
        "ideal_roles": ideal_roles,
        "industries": [target_domain],
        "locations": [target_location],
        "pain_points": pain_points,
        "value_proposition": f"A practical way to explore whether {offer} can help the target audience.",
        "outreach_angle": "Lead with a short, exploratory message focused on relevance and a low-pressure conversation.",
        "search_keywords": [target_domain, target_location, "decision maker", "contact"],
        "lead_source_ideas": [
            "Company websites and public directories",
            "Manual Google search",
            "User-provided LinkedIn URLs or manual LinkedIn search",
            "Industry association directories",
        ],
        "email_script": (
            "Hi {name},\n\n"
            f"I am reaching out because {title} may be relevant for teams in {target_domain}. "
            f"We are exploring whether {offer} could be useful for your organization.\n\n"
            "Would you be open to a short conversation to see if this is relevant?\n\n"
            "Regards,\nTeam"
        ),
        "call_script": (
            f"Hi, I am calling to check whether {offer} is relevant for your team. "
            "Who would be the right person to briefly discuss this with?"
        ),
        "follow_up_sequence": [
            {
                "step": 1,
                "purpose": "Gentle reminder",
                "message": "Just following up to see if this is relevant. Happy to share a short overview.",
            },
            {
                "step": 2,
                "purpose": "Close the loop",
                "message": "Should I reconnect later, or is there someone else better suited for this conversation?",
            },
        ],
        "qualification_criteria": [
            "Matches the campaign domain",
            "Has a relevant decision-maker or influencer",
            "Located in the target region if location matters",
            "Shows a plausible need for the offer",
        ],
        "risk_flags": [
            "Avoid automated LinkedIn scraping",
            "Validate role and relevance before outreach",
            "Do not claim facts that are not confirmed",
        ],
        "suggested_campaign": {
            "campaign_name": title,
            "industry": target_domain,
            "location": target_location,
            "target_role": "Founder / Owner / Manager / Relevant decision-maker",
            "offer": offer,
        },
        "suggested_discovery": discovery,
    }


def _build_opportunity_query(opportunity: Opportunity):
    return " ".join(
        part
        for part in [
            clean_value(opportunity.raw_goal),
            clean_value(opportunity.offer),
            clean_value(opportunity.target_domain),
            clean_value(opportunity.target_location),
        ]
        if part
    )


def _get_knowledge_context(db: Session, opportunity: Opportunity):
    try:
        knowledge_entries = search_relevant_knowledge(
            db,
            _build_opportunity_query(opportunity),
            limit=3,
        )
        return _truncate(build_knowledge_context(knowledge_entries), MAX_STRATEGY_CONTEXT_CHARS)
    except Exception:
        return ""


def _build_prompt(opportunity: Opportunity, knowledge_context: str):
    knowledge_section = knowledge_context or "No matching company knowledge was found."

    return f"""
You are an AI campaign strategist for a generic B2B/outreach MVP.
Generate a complete, practical campaign strategy from the rough opportunity below.
Return strict JSON only.

Opportunity:
- Title: {clean_value(opportunity.title)}
- Raw goal: {clean_value(opportunity.raw_goal)}
- Target domain: {clean_value(opportunity.target_domain)}
- Target location: {clean_value(opportunity.target_location)}
- Offer: {clean_value(opportunity.offer)}

Optional company knowledge:
{knowledge_section}

Rules:
- Do not hardcode any specific product or industry.
- Use the user's raw goal, offer, target domain, and target location.
- If the goal is professor/college outreach, include professor, HOD, faculty coordinator, and research coordinator as possible roles.
- If the goal is SME/startup outreach, include owner, founder, operations, and manager roles.
- If the goal is restaurant marketing, focus on reviews, local visibility, Instagram, local discovery, and footfall.
- If the goal is clinic software, focus on appointments, patient records, billing, and admin coordination.
- If the goal is cybersecurity, focus on vulnerabilities, data protection, compliance, and security risk.
- If the goal is research/project assistance, focus on SIP, final-year projects, prototype support, technical mentorship, and documentation.
- Search keywords must be realistic and safe.
- Suggested discovery should describe what public source URLs the user should collect manually.
- For professor/college/research goals, suggested discovery target_type should usually be professor, college, or department.
- For company/SME/startup/service-business goals, suggested discovery target_type should usually be company, startup, or general.
- Do not recommend scraping LinkedIn directly.
- For LinkedIn, suggest manual search or user-provided URLs only.
- Do not claim exact market facts, pricing, partnerships, or credentials unless provided.
- Keep outputs practical and actionable.

Return JSON with this exact shape:
{{
  "ai_summary": "...",
  "target_audience": "...",
  "ideal_roles": ["..."],
  "industries": ["..."],
  "locations": ["..."],
  "pain_points": ["..."],
  "value_proposition": "...",
  "outreach_angle": "...",
  "search_keywords": ["..."],
  "lead_source_ideas": ["..."],
  "email_script": "...",
  "call_script": "...",
  "follow_up_sequence": [
    {{
      "step": 1,
      "purpose": "...",
      "message": "..."
    }}
  ],
  "qualification_criteria": ["..."],
  "risk_flags": ["..."],
  "suggested_campaign": {{
    "campaign_name": "...",
    "industry": "...",
    "location": "...",
    "target_role": "...",
    "offer": "..."
  }},
  "suggested_discovery": {{
    "target_type": "...",
    "department": "...",
    "role": "...",
    "queries": ["..."]
  }}
}}
""".strip()


def _parse_strategy(response_text: str, opportunity: Opportunity):
    fallback = _fallback_strategy(opportunity)

    try:
        parsed = extract_json_from_text(clean_value(response_text))
    except Exception:
        return fallback, True

    if not isinstance(parsed, dict):
        return fallback, True

    suggested_campaign = parsed.get("suggested_campaign")
    suggested_discovery = parsed.get("suggested_discovery")

    if not isinstance(suggested_campaign, dict):
        suggested_campaign = fallback["suggested_campaign"]
    if not isinstance(suggested_discovery, dict):
        suggested_discovery = fallback["suggested_discovery"]

    strategy = {
        "ai_summary": parsed.get("ai_summary") or fallback["ai_summary"],
        "target_audience": parsed.get("target_audience") or fallback["target_audience"],
        "ideal_roles": parsed.get("ideal_roles") or fallback["ideal_roles"],
        "industries": parsed.get("industries") or fallback["industries"],
        "locations": parsed.get("locations") or fallback["locations"],
        "pain_points": parsed.get("pain_points") or fallback["pain_points"],
        "value_proposition": parsed.get("value_proposition") or fallback["value_proposition"],
        "outreach_angle": parsed.get("outreach_angle") or fallback["outreach_angle"],
        "search_keywords": parsed.get("search_keywords") or fallback["search_keywords"],
        "lead_source_ideas": parsed.get("lead_source_ideas") or fallback["lead_source_ideas"],
        "email_script": parsed.get("email_script") or fallback["email_script"],
        "call_script": parsed.get("call_script") or fallback["call_script"],
        "follow_up_sequence": parsed.get("follow_up_sequence") or fallback["follow_up_sequence"],
        "qualification_criteria": parsed.get("qualification_criteria") or fallback["qualification_criteria"],
        "risk_flags": parsed.get("risk_flags") or fallback["risk_flags"],
        "suggested_campaign": {
            "campaign_name": suggested_campaign.get("campaign_name") or fallback["suggested_campaign"]["campaign_name"],
            "industry": suggested_campaign.get("industry") or fallback["suggested_campaign"]["industry"],
            "location": suggested_campaign.get("location") or fallback["suggested_campaign"]["location"],
            "target_role": suggested_campaign.get("target_role") or fallback["suggested_campaign"]["target_role"],
            "offer": suggested_campaign.get("offer") or fallback["suggested_campaign"]["offer"],
        },
        "suggested_discovery": {
            "target_type": suggested_discovery.get("target_type") or fallback["suggested_discovery"]["target_type"],
            "department": suggested_discovery.get("department") or fallback["suggested_discovery"]["department"],
            "role": suggested_discovery.get("role") or fallback["suggested_discovery"]["role"],
            "queries": suggested_discovery.get("queries") or fallback["suggested_discovery"]["queries"],
        },
    }

    return strategy, False


def _apply_strategy(opportunity: Opportunity, strategy: dict, model_used: str):
    suggested_campaign = strategy.get("suggested_campaign") or {}
    suggested_discovery = strategy.get("suggested_discovery") or {}

    opportunity.ai_summary = _truncate(strategy.get("ai_summary"), 3000)
    opportunity.target_audience = _truncate(strategy.get("target_audience"), 3000)
    opportunity.ideal_roles = _join_list(strategy.get("ideal_roles"))
    opportunity.industries = _join_list(strategy.get("industries"))
    opportunity.locations = _join_list(strategy.get("locations"))
    opportunity.pain_points = _join_list(strategy.get("pain_points"))
    opportunity.value_proposition = _truncate(strategy.get("value_proposition"), 3000)
    opportunity.outreach_angle = _truncate(strategy.get("outreach_angle"), 3000)
    opportunity.search_keywords = _join_list(strategy.get("search_keywords"))
    opportunity.lead_source_ideas = _join_list(strategy.get("lead_source_ideas"))
    opportunity.email_script = _truncate(strategy.get("email_script"), 5000)
    opportunity.call_script = _truncate(strategy.get("call_script"), 5000)
    opportunity.follow_up_sequence = _format_follow_up_sequence(strategy.get("follow_up_sequence"))
    opportunity.qualification_criteria = _join_list(strategy.get("qualification_criteria"))
    opportunity.risk_flags = _join_list(strategy.get("risk_flags"))
    opportunity.suggested_campaign_name = _truncate(suggested_campaign.get("campaign_name"), 255)
    opportunity.suggested_campaign_industry = _truncate(suggested_campaign.get("industry"), 255)
    opportunity.suggested_campaign_location = _truncate(suggested_campaign.get("location"), 255)
    opportunity.suggested_campaign_target_role = _truncate(suggested_campaign.get("target_role"), 255)
    opportunity.suggested_campaign_offer = _truncate(suggested_campaign.get("offer"), 5000)
    opportunity.suggested_discovery_target_type = _truncate(suggested_discovery.get("target_type"), 100)
    opportunity.suggested_discovery_department = _truncate(suggested_discovery.get("department"), 255)
    opportunity.suggested_discovery_role = _truncate(suggested_discovery.get("role"), 255)
    opportunity.suggested_discovery_queries = _join_list(suggested_discovery.get("queries"))
    opportunity.status = "generated"
    opportunity.ai_model = model_used
    opportunity.updated_at = utc_now()


def generate_opportunity_strategy(db: Session, opportunity_id: int) -> Opportunity:
    opportunity = db.get(Opportunity, opportunity_id)

    if not opportunity:
        raise OpportunityServiceError("Opportunity was not found.")

    model_used = settings.GEMINI_MODEL
    strategy = None

    if settings.GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=_build_prompt(opportunity, _get_knowledge_context(db, opportunity)),
            )
            strategy, used_fallback = _parse_strategy(clean_value(getattr(response, "text", "")), opportunity)
            if used_fallback:
                model_used = FALLBACK_OPPORTUNITY_MODEL
        except Exception:
            strategy = _fallback_strategy(opportunity)
            model_used = FALLBACK_OPPORTUNITY_MODEL
    else:
        strategy = _fallback_strategy(opportunity)
        model_used = FALLBACK_OPPORTUNITY_MODEL

    _apply_strategy(opportunity, strategy, model_used)

    try:
        db.commit()
        db.refresh(opportunity)
    except SQLAlchemyError as exc:
        db.rollback()
        raise OpportunityServiceError("Opportunity strategy could not be saved.") from exc

    return opportunity


def convert_opportunity_to_campaign(db: Session, opportunity: Opportunity, force_new: bool = False):
    if opportunity.converted_campaign_id and not force_new:
        existing_campaign = db.get(Campaign, opportunity.converted_campaign_id)

        if existing_campaign:
            return existing_campaign, True

    campaign_name = (
        clean_value(opportunity.suggested_campaign_name)
        or clean_value(opportunity.title)
        or "AI Generated Campaign"
    )
    industry = (
        clean_value(opportunity.suggested_campaign_industry)
        or clean_value(opportunity.target_domain)
        or "General"
    )
    location = (
        clean_value(opportunity.suggested_campaign_location)
        or clean_value(opportunity.target_location)
        or "Any"
    )
    ideal_role_fallback = clean_value(opportunity.ideal_roles).splitlines()[0] if clean_value(opportunity.ideal_roles) else ""
    target_role = (
        clean_value(opportunity.suggested_campaign_target_role)
        or ideal_role_fallback
        or "Decision Maker"
    )
    offer = (
        clean_value(opportunity.suggested_campaign_offer)
        or clean_value(opportunity.offer)
        or clean_value(opportunity.raw_goal)
    )

    campaign = Campaign(
        campaign_name=campaign_name[:255],
        industry=industry[:255],
        location=location[:255],
        target_role=target_role[:255],
        offer=offer,
    )
    db.add(campaign)

    try:
        db.flush()
        opportunity.converted_campaign_id = campaign.id
        opportunity.status = "converted"
        opportunity.updated_at = utc_now()
        db.commit()
        db.refresh(campaign)
        db.refresh(opportunity)
    except SQLAlchemyError as exc:
        db.rollback()
        raise OpportunityServiceError("Campaign could not be created from opportunity.") from exc

    return campaign, False


def create_discovery_job_from_opportunity(
    db: Session,
    opportunity: Opportunity,
    campaign_id: int | None = None,
):
    selected_campaign_id = campaign_id or opportunity.converted_campaign_id

    if selected_campaign_id:
        campaign = db.get(Campaign, selected_campaign_id)
        if not campaign:
            raise OpportunityServiceError("Selected campaign was not found.")

    generated_queries = (
        clean_value(opportunity.suggested_discovery_queries)
        or clean_value(opportunity.search_keywords)
        or clean_value(opportunity.lead_source_ideas)
    )
    title = f"{clean_value(opportunity.title) or 'Opportunity'} Discovery"
    query_goal = clean_value(opportunity.raw_goal) or clean_value(opportunity.ai_summary)

    job = DiscoveryJob(
        opportunity_id=opportunity.id,
        campaign_id=selected_campaign_id,
        title=title[:255],
        target_type=clean_value(opportunity.suggested_discovery_target_type) or "general",
        department=clean_value(opportunity.suggested_discovery_department) or clean_value(opportunity.target_domain),
        location=clean_value(opportunity.suggested_campaign_location) or clean_value(opportunity.target_location),
        target_role=clean_value(opportunity.suggested_discovery_role) or clean_value(opportunity.suggested_campaign_target_role),
        query_goal=query_goal,
        source_mode="generated_queries",
        generated_queries=generated_queries or None,
        limit=20,
        status="draft",
    )
    db.add(job)

    try:
        db.commit()
        db.refresh(job)
    except SQLAlchemyError as exc:
        db.rollback()
        raise OpportunityServiceError("Discovery job could not be created from opportunity.") from exc

    return job
