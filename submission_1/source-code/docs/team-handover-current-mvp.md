# AI Lead Generation MVP Handover

This document is for the web development team that needs current MVP details, screenshots, AI documentation, integration context, and roadmap material.

## 1. Current MVP Summary

The current project is an AI-powered B2B lead generation and outreach MVP. It is not a full LMS by itself. It can be integrated into the main Rusborn website as a sales/admin lead agent module.

Core purpose:
- Create outreach campaigns.
- Find leads from Google Maps/Apify through n8n automation.
- Extract public emails from lead websites.
- Research leads using public website pages and campaign context.
- Score and prioritize leads with Gemini.
- Generate cold emails, follow-ups, reply classifications, and response drafts.
- Keep sending under manual approval through Gmail OAuth.
- Support optional Hunter.io, Apollo, and Vapi integrations.

Current frontend pages:
- Dashboard
- Campaigns
- Opportunities
- Lead Discovery
- Leads
- Calls
- Emails
- Knowledge
- Settings

Current backend API areas:
- Health and dashboard stats
- Campaigns
- Leads, CSV upload, export, email extraction, lead research
- Lead Agent n8n trigger
- AI lead scoring
- Opportunity and discovery workflows
- Knowledge base and document ingestion
- AI email drafts, follow-ups, replies, response drafts
- Gmail OAuth and send flow
- Hunter.io and Apollo enrichment
- Vapi call workflows

## 2. Screenshot Package Needed

Use these screenshots for the project presentation or integration handoff.

### MVP Screenshots From This Project

Capture these from the deployed frontend:

1. Dashboard
   - URL: `/`
   - Show top stats, recent leads/emails, AI score summary, and reply/research metrics.

2. Campaigns
   - URL: `/campaigns`
   - Show create campaign form and campaign list.

3. Leads page with selected campaign
   - URL example: `/leads?campaign_id=20`
   - Show lead table, filters, AI score columns, research status, email status.

4. Lead Agent card
   - On Leads page
   - Show `Find Leads Now`, max results, queries per day, estimated leads, generated search queries after trigger.

5. Email Extraction card
   - On Leads page
   - Show total leads, with email, needs extraction, coverage, and extraction button.

6. AI Lead Research card
   - On Leads page
   - Show `Research Unresearched Leads` and research status fields in lead rows.

7. Hunter Email Enrichment section
   - On Leads page
   - Show optional Hunter.io enrichment area.

8. Emails page
   - URL: `/emails`
   - Show generated drafts, approve/reject/send controls, reply status.

9. Calls page
   - URL: `/calls`
   - Show Vapi calling controls, call logs, call outcomes, follow-up draft action.

10. Knowledge page
   - URL: `/knowledge`
   - Show company knowledge entries, document upload, RAG/embedding status.

11. Settings page
   - URL: `/settings`
   - Show Gmail connection and integration status.

12. Swagger/OpenAPI
   - Backend URL: `/docs`
   - Show available API endpoints.

### LMS UI Screenshots

This MVP repo does not contain a full LMS UI. If the team asks for LMS screenshots, they should provide screenshots from the main Rusborn LMS/product repo, such as:
- Course dashboard
- Course/lesson player
- Quiz or assessment page
- Student progress page
- Certificate or completion page
- Trainer/admin content upload page

If those screens are not built yet, mark them as:
`Pending from main website/LMS team. This MVP integrates as a sales lead generation module, not as the LMS interface.`

### AI Module Screenshots

Capture these:
- Lead Agent query generation result
- AI Lead Research output on a lead
- AI scoring result with priority and qualification
- Generated email draft
- Reply classification result
- Knowledge page/RAG source usage
- Vapi call script generation if enabled

### Admin Panel Screenshots

This MVP has admin-like operational pages, but no role-based admin dashboard yet. Capture:
- Dashboard
- Campaigns
- Leads
- Emails
- Knowledge
- Settings

For the main website admin panel, ask the main web team for:
- Admin login/dashboard
- User management
- Sales team dashboard
- Lead assignment view
- Role/permission management
- LMS/content admin screens

## 3. AI Architecture

High-level architecture:

```text
React/Vite Frontend
        |
        | Axios API calls
        v
FastAPI Backend on Render/Railway
        |
        | SQLAlchemy
        v
Supabase/PostgreSQL Database
        |
        +-- Gemini API for AI generation, scoring, research, reply classification
        +-- Gmail API for approved email sending and reply checks
        +-- n8n webhook for automated lead sourcing workflow
        +-- Apify/Google Maps scraper inside n8n
        +-- Hunter.io/Apollo optional enrichment
        +-- Vapi optional AI calling
```

Main AI components:
- Gemini query generation for Lead Agent searches.
- Gemini lead research from public website content plus campaign context.
- Gemini lead scoring and qualification.
- Gemini cold email draft generation.
- Gemini follow-up and reply response generation.
- Gemini reply classification.
- Gemini opportunity/campaign strategy generation.
- Gemini embeddings for semantic RAG when enabled.

Knowledge/RAG design:
- Company knowledge is stored in the database.
- Uploaded PDF/DOCX/TXT/Markdown documents are extracted into chunks.
- Chunks can be embedded with Gemini embeddings.
- AI prompts retrieve relevant knowledge by hybrid semantic plus keyword search.
- The system uses retrieved knowledge as context. It does not train a custom LLM.

Safety model:
- Emails are drafts first.
- User must approve before sending.
- Follow-ups and reply responses also require approval.
- Gmail sending uses backend OAuth tokens, not frontend API keys.
- n8n lead generation creates leads, but does not send emails automatically.

## 4. LLM Integration Workflow

### Lead Agent Workflow

1. User creates/selects a campaign.
2. User chooses `max_results` and `queries_per_day`.
3. Frontend calls `POST /api/lead-agent/start`.
4. Backend loads campaign details.
5. Backend sends campaign context to Gemini:
   - campaign name
   - industry
   - location
   - target role
   - offer
   - requested query count
6. Gemini returns Google Maps style search queries.
7. Backend triggers `N8N_WEBHOOK_URL` in the background.
8. n8n runs Apify/Google Maps searches.
9. n8n cleans and deduplicates results.
10. n8n saves leads through `POST /api/leads/create`.
11. n8n starts async email extraction.
12. n8n can start async research and scoring.
13. Frontend polls `GET /api/lead-agent/status/{campaign_id}` for updated lead counts.

### Email Extraction Workflow

1. Lead must have a website and no saved email.
2. Backend starts `POST /api/leads/campaign/{campaign_id}/extract-emails-async?limit=100`.
3. Background job visits public website pages.
4. It extracts visible public email addresses.
5. If needed, it tries common business patterns such as `info@`, `contact@`, `hello@`, `sales@`, and `hr@`.
6. Job status can be checked through `GET /api/leads/extraction-job/{job_id}`.

### Lead Research Workflow

1. Lead must be `not_researched` or `failed`.
2. Backend starts `POST /api/campaigns/{campaign_id}/research-leads-async?limit=100`.
3. Background job selects leads in batches.
4. Backend fetches limited public website pages.
5. Gemini creates structured research:
   - summary
   - business type
   - target customers
   - products/services
   - likely pain points
   - campaign use-case fit
   - outreach angle
   - risk flags
   - confidence
6. Job status can be checked through `GET /api/campaigns/research-job/{job_id}`.

### Lead Scoring Workflow

1. User or n8n calls campaign scoring.
2. Backend sends lead, campaign, and research context to Gemini.
3. Gemini returns:
   - final score
   - fit score
   - contact confidence score
   - priority
   - qualification
   - score reason
   - pain point
   - outreach angle
   - recommended CTA
4. Scores are stored on the lead and shown in the Leads/Dashboard UI.

### Email/Reply Workflow

1. Cold emails are generated with lead, campaign, research, score, and company knowledge context.
2. User approves or rejects drafts.
3. Approved drafts can be sent through Gmail.
4. Replies can be checked manually.
5. Gemini classifies replies.
6. Gemini drafts a response.
7. User approves before sending the response.

## 5. Main Integration Notes

For integration into the Rusborn main website:

Recommended approach:
- Keep this FastAPI backend as an internal lead-agent service.
- Add authentication and role-based access before exposing it to real sales/admin users.
- The main website can embed or route to the React pages, or reuse the backend APIs in the existing UI.
- Sales department users should access campaigns, leads, emails, calls, and analytics.
- Admin users should access settings, integrations, knowledge base, and user/team management.

Important environment variables:
- `DATABASE_URL`
- `FRONTEND_URL`
- `FRONTEND_URLS`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `N8N_WEBHOOK_URL`
- `GMAIL_CLIENT_ID`
- `GMAIL_CLIENT_SECRET`
- `GMAIL_REDIRECT_URI`
- `GMAIL_SENDER_EMAIL`
- `HUNTER_API_KEY`
- `APOLLO_API_KEY`
- `VAPI_ENABLED`
- `VAPI_API_KEY`
- `VAPI_ASSISTANT_ID`
- `VAPI_PHONE_NUMBER_ID`
- `VAPI_WEBHOOK_SECRET`
- `VITE_API_BASE_URL`

Do not put backend secrets in frontend `.env`.

## 6. Feature Roadmap

Short term:
- Add authentication and role-based access.
- Add team/user ownership for campaigns and leads.
- Add lead assignment to sales users.
- Add export to Excel/CSV with selected fields.
- Add job progress UI for async research and scoring.
- Add better n8n execution status visibility in the frontend.

Medium term:
- Add admin dashboard for integrations and usage limits.
- Add campaign-level budgets and API usage counters.
- Add duplicate detection across campaigns.
- Add lead quality rules such as employee count, location radius, industry fit, and budget signals.
- Add scheduled daily lead generation runs.
- Add CRM sync or webhook export to the main Rusborn system.

Long term:
- Add multi-tenant company support.
- Add full sales pipeline stages.
- Add advanced reporting for conversion, reply quality, and call outcomes.
- Add stronger compliance controls for outreach consent, unsubscribe, and do-not-contact lists.
- Add native LMS/product data sync so outreach can use real course/training offerings.

## 7. What To Ask Other Teams For

Ask the main web/LMS team for:
- Main website architecture diagram.
- Auth method used by Rusborn.
- Admin and sales dashboard roles.
- Existing user/team schema.
- Existing deployment method on Railway.
- LMS screenshots and route list.
- Admin panel screenshots and route list.
- Whether the lead agent should be embedded as pages, linked as a sub-app, or integrated API-first.
- Domain/subdomain plan.
- Production environment variable owner.
- Gmail account policy for sending.
- n8n production webhook ownership.

Ask the sales/business team for:
- Target industries.
- Target locations.
- Buyer roles.
- Daily lead target.
- Approved outreach offer.
- Email sender identity.
- Do-not-contact rules.
- Lead quality definition.
- Required export columns.

## 8. Suggested Presentation Flow

Use this order in the meeting:

1. Problem statement: Sales team needs daily targeted leads and AI-assisted outreach.
2. Current MVP demo: Campaigns -> Lead Agent -> Leads -> Email Extraction -> Research -> Scoring -> Draft -> Approval.
3. AI architecture: Gemini, RAG, n8n, Apify, Gmail, optional Hunter/Vapi.
4. Safety: manual approval before sending, backend-only API keys, controlled batch limits.
5. Integration plan: add auth/RBAC, connect to main Rusborn admin/sales dashboards, deploy backend/frontend with proper env vars.
6. Missing dependencies: LMS screenshots, main admin screenshots, auth details, production env owners.
7. Roadmap: role-based access, daily schedules, Excel export, CRM sync, analytics.

