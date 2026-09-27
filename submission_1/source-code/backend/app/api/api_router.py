from fastapi import APIRouter
from app.api.routes import (
    ai,
    analytics,
    apollo,
    campaigns,
    calls,
    dashboard,
    discovery,
    emails,
    followups,
    gmail,
    health,
    hunter,
    knowledge,
    lead_agent,
    lead_scoring,
    leads,
    opportunities,
    replies,
    reply_classification,
    reply_responses,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(dashboard.router)
api_router.include_router(campaigns.router)
api_router.include_router(calls.router)
api_router.include_router(leads.router)
api_router.include_router(lead_agent.router)
api_router.include_router(lead_scoring.router)
api_router.include_router(opportunities.router)
api_router.include_router(discovery.router)
api_router.include_router(knowledge.router)
api_router.include_router(ai.router)
api_router.include_router(emails.router)
api_router.include_router(followups.router)
api_router.include_router(gmail.router)
api_router.include_router(hunter.router)
api_router.include_router(apollo.router)
api_router.include_router(replies.router)
api_router.include_router(reply_classification.router)
api_router.include_router(reply_responses.router)
api_router.include_router(analytics.router)
