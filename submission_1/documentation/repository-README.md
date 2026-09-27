# AI Lead Generation MVP

For web-team integration notes, screenshot requirements, AI architecture, LLM workflow, and roadmap, see [`docs/team-handover-current-mvp.md`](docs/team-handover-current-mvp.md).

## 1. Project Overview

This is an AI-powered lead generation and cold email outreach MVP. It supports campaign creation, lead upload, public email extraction, AI lead scoring, AI-generated email drafts, Gmail OAuth connection, sending approved drafts, manual reply checks, AI reply classification, AI response drafts, company knowledge retrieval, campaign analytics, and safe follow-up drafts.

## 2. Features

- Campaign management
- Lead CSV upload
- Public email extraction from websites
- AI lead scoring and qualification
- Lead priority, outreach angle, pain point, and CTA recommendations
- AI email generation using Gemini
- Company knowledge base for product, pricing, FAQ, demo, and objection handling notes
- Document upload for the Knowledge Base with PDF, DOCX, TXT, and Markdown extraction
- Hybrid semantic and keyword RAG for company-specific AI context
- AI lead research and enrichment from public company website pages plus campaign/lead fields
- Opportunity/Campaign Generator for turning rough outreach ideas into AI-generated campaign strategies
- Lead Discovery for extracting public contacts from user-reviewed source URLs
- Lead Agent automation that triggers an n8n workflow for Google Maps/Apify lead sourcing
- Gemini-generated Google Maps search queries based on campaign industry, location, role, and offer
- Async campaign email extraction with public website scraping and pattern-based fallback
- Hunter.io enrichment for finding professional emails from lead websites
- Vapi Calling Agent integration for selected-lead AI calls, call logs, outcomes, transcripts, and follow-up draft actions
- Draft approve/reject workflow
- Gmail OAuth connection
- Send approved emails
- Manual Gmail reply checks
- AI reply classification with intent, sentiment, priority, and next action suggestions
- AI response draft generation for classified replies
- Knowledge used in AI response drafts
- Response draft approve/reject/send workflow
- Follow-up draft generation and sending
- Campaign analytics and reply rate
- Dashboard stats

## 3. Tech Stack

Frontend:
- React
- Vite
- Tailwind CSS
- Axios
- Vercel

Backend:
- FastAPI
- SQLAlchemy
- Supabase PostgreSQL
- Render

AI and email:
- Gemini API
- Gmail API OAuth
- Hunter.io API for optional email enrichment
- Vapi API for optional AI calling

Automation:
- n8n for the external Lead Agent workflow
- Apify/Google Maps scraper inside n8n for business place discovery

## 4. Architecture

The frontend is a Vite React app deployed on Vercel. It calls the FastAPI backend through `VITE_API_BASE_URL`.

The backend is deployed on Render and stores application data in Supabase PostgreSQL through SQLAlchemy models. Gmail and Gemini credentials stay on the backend and are loaded from environment variables.

Main data flow:
1. Campaigns are created in the app.
2. Leads can come from CSV upload, manual Lead Discovery, or the automated Lead Agent.
3. Lead Agent uses campaign context to generate Google Maps search queries with Gemini, then triggers n8n through `N8N_WEBHOOK_URL`.
4. n8n runs Apify/Google Maps searches, normalizes places into lead records, and saves them to the selected campaign through `POST /api/leads/create`.
5. Async website extraction searches public lead websites for visible emails and falls back to common business email patterns when useful.
6. Gemini can research leads, score them, and explain priority, fit, outreach angle, pain point, and CTA.
7. Gemini generates cold email drafts with relevant company knowledge when available.
8. Users approve or reject drafts.
9. Gmail OAuth enables sending approved drafts only.
10. Users manually check sent emails for replies and review campaign analytics.
11. Gemini classifies replies by intent, sentiment, priority, summary, and suggested next action.
12. Gemini drafts a safe response for classified replies using relevant company knowledge when available.
13. Users approve, reject, or send approved response drafts manually.
14. If there is no reply, users generate, approve, and send follow-up drafts manually.
15. The Knowledge page stores company-specific facts for the first simple RAG layer. This does not train an LLM.
16. Users can upload PDF, DOCX, TXT, or Markdown knowledge documents. The backend extracts text, splits it into chunks, and stores each chunk as searchable company knowledge.
17. When semantic RAG is enabled, knowledge entries are embedded on the backend and searched through Supabase/PostgreSQL `pgvector`, with keyword fallback if semantic search is unavailable.
18. Users can research leads before scoring or email generation. The backend checks a small number of public website pages, combines that with campaign/lead data, and stores a concise enrichment profile.
19. Users can create an opportunity from a rough idea, generate an AI campaign strategy, and convert the reviewed strategy into a campaign.
20. Opportunities can create lead discovery jobs with suggested target type, department, role, and manual search queries.
21. Users paste public source URLs into discovery jobs. The backend fetches only those reviewed URLs and extracts readable public contact details.
22. Users approve, reject, and import selected discovered contacts into the existing Leads table.
23. Imported discovery leads can be researched, scored, and used for manual email/call outreach preparation.
24. Users can optionally enrich missing lead emails through Hunter.io when a lead has a website.
25. Users can generate call scripts, start a selected Vapi AI call, receive Vapi webhooks/tool calls, and store call outcomes.
26. Interested or details-requested calls can create follow-up email drafts, but nothing is sent automatically.

## 5. Week-wise Progress

Week 1:
- Campaign creation
- Campaign list
- Backend/frontend connection

Week 2:
- Lead CSV upload
- Lead table
- Campaign-wise lead connection
- Invalid CSV validation

Week 3:
- Website/public email extraction
- Single lead email extraction
- Campaign-wise extraction
- Lead statuses: `new`, `email_found`, `email_not_found`, `website_missing`, `extraction_failed`

Week 4:
- Gemini AI email draft generation
- Generate draft for one lead
- Generate drafts for campaign in safe batches
- Email draft model/table
- Approve/reject email drafts

Week 5:
- Gmail OAuth connection
- Gmail token storage
- Send approved drafts only
- Single draft sending
- Campaign approved sending with limits
- Sent status, `sent_at`, and `gmail_message_id`

Week 6:
- Real dashboard stats
- Cleaner Gmail Settings UI
- Status-based email draft actions
- Campaign summary cards
- Better empty states and error messages
- Demo documentation and sample CSVs

Week 7:
- Gmail readonly scope for manual reply checks
- Sent draft reply tracking
- Campaign reply analytics
- Dashboard reply stats

Week 8:
- Follow-up draft generation
- Follow-up approval/rejection
- Follow-up sending through Gmail
- Follow-up safety rules and limits
- Follow-up analytics

Week 9:
- AI lead scoring
- Lead priority and qualification labels
- Explainable score reason
- Suggested outreach angle
- Likely pain point
- Recommended CTA
- Dashboard and campaign analytics for scored leads

Week 10:
- AI reply classification
- Reply intent detection
- Reply sentiment and priority
- Reply summary and next action suggestion
- Suggested response direction without automatic sending
- Manual control and safety-first workflow

Week 11:
- AI response draft generation from classified replies
- Approve/reject response drafts
- Send approved responses through Gmail
- Reply classification to response flow
- Manual safety control before every response is sent

Week 12:
- Company knowledge base
- Simple database-backed RAG
- Knowledge retrieval for AI response drafts
- Relevant company context for cold emails and follow-ups
- Knowledge used visibility on response drafts
- First step toward company-specific AI without training an LLM

Week 12.1:
- Document upload for the Knowledge Base
- Supported document types: PDF, DOCX, TXT, and Markdown
- Uploaded documents are converted into text chunks and stored in `company_knowledge`
- Document chunks remain searchable through the existing keyword RAG flow
- AI cold emails, follow-ups, and response drafts can use uploaded document knowledge when relevant
- Knowledge and response draft UI now show whether knowledge came from a manual entry or an uploaded document

Week 12.2:
- Stronger RAG grounding for response drafts
- Structured retrieved knowledge context for AI replies
- Pricing and demo replies prefer exact retrieved company facts
- Response drafts avoid invented prices and keep manual approval flow

Week 13:
- Semantic RAG with embeddings
- Supabase/PostgreSQL `pgvector` support when available
- Hybrid search that combines semantic retrieval and keyword fallback
- Query expansion for common sales terms such as cost, walkthrough, start small, and track progress
- Search modes: Hybrid, Semantic, and Keyword
- Embedding backfill from the Knowledge page
- Semantic status visibility for active, embedded, missing, and errored knowledge entries

Week 14:
- AI lead research and enrichment
- Lightweight public website research before scoring or email drafting
- Campaign-aware enrichment that uses the current offer, target industry, target location, and target role
- Stored research summary, business type, products/services, likely pain points, use case fit, outreach angle, risk flags, sources, and confidence
- Lead scoring and cold email generation can use enriched research context when available
- Research falls back to CSV/campaign data when website pages are missing or inaccessible

Phase 3:
- Opportunity/Campaign Generator
- Users enter a rough business, research, or outreach goal
- Gemini generates a complete campaign strategy with audience, roles, pain points, value proposition, outreach angle, search keywords, lead source ideas, email script, call script, follow-up sequence, qualification criteria, and risk flags
- Gemini also suggests discovery target type, department/domain, target role, and safe manual search queries
- Strategies can be converted into campaigns after user review
- Strategies can create lead discovery jobs after user review
- Lead Discovery accepts public source URLs, extracts public emails/phones, structures contacts, and keeps them pending for review before import
- Works generically for professors, colleges, SMEs, startups, restaurants, clinics, retail shops, SaaS, manufacturing, and service businesses
- LinkedIn scraping is not automated; use manual search or user-provided URLs only

Lead Agent Automation:
- Campaign Leads page includes a Lead Agent launcher for selected campaigns
- Backend `POST /api/lead-agent/start` generates Gemini search queries and triggers n8n
- Backend `GET /api/lead-agent/status/{campaign_id}` reports current campaign lead/email counts
- n8n workflow runs Google Maps/Apify searches, creates leads, starts async email extraction, then can research and score leads
- Search query count and max results are controlled from the website
- Campaign ids are passed dynamically from the website to n8n so leads save into the selected campaign
- Email extraction can replace Hunter in the automated workflow when free public website/pattern extraction is preferred

Vapi Calling Agent:
- Calls page for configuration status, script generation, selected-lead AI calls, manual call logs, and call history
- Backend-only Vapi API calls through `POST /api/calls/start-vapi`
- Call logs store provider call id, status, outcome, sentiment, transcript, summary, recording URL, and next action
- Vapi webhooks and tool calls update call logs and lead call fields
- Do-not-call leads are blocked before any Vapi request
- Follow-up email drafts can be created from call outcomes without sending

## 6. Local Setup

Backend:
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:
```bash
cd frontend
npm install
npm run dev
```

Default local URLs:
- Backend: `http://127.0.0.1:8000`
- Frontend: `http://localhost:5173`

## 7. Environment Variables

Do not commit real secrets. Use Render, Vercel, or local `.env` files for real values.

Backend:
```env
APP_NAME=
APP_ENV=
FRONTEND_URL=
DATABASE_URL=
DB_POOL_SIZE=
DB_MAX_OVERFLOW=
DB_POOL_TIMEOUT=
DB_POOL_RECYCLE=
BACKEND_HOST=
BACKEND_PORT=
GEMINI_API_KEY=
GEMINI_MODEL=
N8N_WEBHOOK_URL=
EMBEDDING_MODEL=
EMBEDDING_DIMENSION=
ENABLE_SEMANTIC_RAG=
SEMANTIC_RAG_TOP_K=
SEMANTIC_RAG_MIN_SCORE=
GMAIL_CLIENT_ID=
GMAIL_CLIENT_SECRET=
GMAIL_REDIRECT_URI=
GMAIL_SENDER_EMAIL=
GMAIL_DAILY_LIMIT=
HUNTER_API_KEY=
HUNTER_REQUEST_TIMEOUT=
HUNTER_BULK_MAX_LEADS=
HUNTER_BULK_MAX_SECONDS=
HUNTER_BULK_DELAY_SECONDS=
VAPI_ENABLED=
VAPI_API_KEY=
VAPI_ASSISTANT_ID=
VAPI_PHONE_NUMBER_ID=
VAPI_WEBHOOK_SECRET=
VAPI_DEFAULT_TEST_PHONE=
VAPI_BASE_URL=
```

Frontend:
```env
VITE_API_BASE_URL=
```

## 8. Deployment

Frontend:
- Deploy the `frontend` app to Vercel.
- Set `VITE_API_BASE_URL` to the Render backend API URL, including `/api` if the app expects that base path.

Backend:
- Deploy the `backend` app to Render.
- Set all backend environment variables in Render.
- Point `DATABASE_URL` to Supabase PostgreSQL.
- Configure Gmail OAuth redirect URI to match the deployed backend callback.
- Set `N8N_WEBHOOK_URL` to the n8n production webhook URL, for example `https://your-n8n-host/webhook/lead-agent-start`. Do not use the `/webhook-test/...` URL for production website runs.

n8n:
- Keep Apify credentials and workflow-specific API tokens inside n8n, not the frontend.
- The production workflow must be active before the backend can trigger it through `N8N_WEBHOOK_URL`.

## 9. Demo Flow

1. Create an opportunity from a rough outreach idea
2. Generate and review the AI strategy
3. Convert the strategy into a campaign
4. Choose one lead sourcing path:
   - Lead Agent: open the campaign Leads page, choose max results and query count, then click `Find Leads Now`.
   - Lead Discovery: create a discovery job, collect public source URLs, paste them into Lead Discovery, and run discovery.
   - CSV: upload a known lead list.
5. For Lead Agent, confirm n8n creates leads under the selected campaign id and not a hardcoded campaign id.
6. Review discovered/imported/generated leads in the Leads page.
7. Run async Email Extraction for leads that have websites but no email.
8. Research leads when website/lead context is useful.
9. Score leads with AI.
10. Review top priority leads.
11. Use Hunter.io enrichment for website-based leads that still have no email, if Hunter is configured and you want paid enrichment.
12. Add company knowledge such as product details, pricing notes, FAQs, and demo scripts.
13. Upload sample knowledge documents from `sample-data/knowledge-documents/`.
14. Generate missing embeddings from the Knowledge page when semantic RAG is enabled.
15. Generate a call script or save a manual call log when calling is part of the workflow.
16. If Vapi is configured, start an AI test call for one selected lead only.
17. Review call transcript, summary, outcome, next action, and optional follow-up draft.
18. Generate first email.
19. Approve and send first email.
20. Recipient replies.
21. Check replies.
22. Classify reply with AI.
23. Generate response draft using relevant company knowledge.
24. Review intent, priority, next action, suggested response direction, knowledge used, and draft response.
25. Approve response.
26. Send approved response.
27. If no reply, generate follow-up draft.
28. Approve follow-up.
29. Send follow-up.
30. Track follow-up status.

## 10. Lead Agent And n8n Workflow

Lead Agent is the automated sourcing path for creating campaign leads from Google Maps-style searches. The website does not scrape Google Maps itself. The website calls the backend, the backend generates search queries and triggers n8n, and n8n runs the external scraping/automation steps.

Plain-English explanation for demos:

> A user creates a campaign with an industry, location, target role, and offer. When they click `Find Leads Now`, the backend asks Gemini to create targeted Google Maps search phrases for that campaign. The backend sends those searches to n8n. n8n runs Apify/Google Maps searches, cleans the returned places, saves them as leads in the selected campaign, starts email extraction for leads with websites, then optionally researches and scores those leads. Emails and outreach are still manual-control: nothing is sent automatically.

Website flow:
1. User opens a campaign on the Leads page.
2. `LeadAgentLauncher` reads the selected campaign id, industry, location, role, and offer.
3. User selects `max_results` (`25`, `50`, `100`, or `200`) and `queries_per_day` (`1`, `2`, or `3`).
4. Frontend calls `POST /api/lead-agent/start`.
5. Frontend polls `GET /api/lead-agent/status/{campaign_id}` every 10 seconds to show new lead counts.

Backend flow:
1. `/api/lead-agent/start` loads the campaign from the database.
2. Gemini uses `GEMINI_API_KEY` and campaign context to generate exactly the requested number of Google Maps search queries.
3. The prompt asks for realistic business-category plus area/city searches, not web-search syntax. It avoids `site:`, `email`, `contact`, quote operators, and role-title searches.
4. If Gemini fails or returns duplicate/fewer queries, fallback query generation fills the missing queries.
5. Backend sends a payload to `N8N_WEBHOOK_URL` in a background task.

Payload sent to n8n includes:
```json
{
  "campaign_id": 20,
  "campaign_name": "Nagpur Mechanical & Industrial Startup Outreach",
  "industry": "Manufacturing",
  "location": "Nagpur, Hingna MIDC, Butibori MIDC, MIHAN, Kalmeshwar, Wardha Road, Maharashtra",
  "target_role": "Founder / Operations Head / CTO / HR",
  "offer": "AI training and automation upskilling platform...",
  "max_results_per_search": 100,
  "queries_per_day": 3,
  "search_queries": [
    "manufacturing company Nagpur",
    "industrial automation Hingna",
    "fabrication company Butibori"
  ]
}
```

n8n workflow structure:
1. `Webhook`: receives the backend payload. Use the production URL in `N8N_WEBHOOK_URL`.
2. `Code`: converts `search_queries` into one item per search query. It must pass through `campaign_id`, `max_results`, campaign fields, and the search query.
3. `HTTP Request`: calls Apify/Google Maps scraper for each search query.
4. `Wait`: gives the scraper time to finish.
5. `HTTP Request1`: fetches Apify dataset/results.
6. `Code1`: normalizes and filters Apify places into lead objects. It must keep the dynamic `campaign_id` from the webhook or first `Code` node.
7. `HTTP Request2`: creates each lead with `POST /api/leads/create`.
8. `Code2`: collapses many created-lead responses into one campaign-level item.
9. `HTTP Request3`: starts async email extraction once for the campaign.
10. `Wait`: waits 3 to 5 minutes because email extraction runs in the backend background.
11. `HTTP Request4`: researches a small batch of unresearched leads.
12. `HTTP Request5`: scores a small batch of unscored leads.

Node responsibility summary:

| Node | Responsibility | Key input | Key output |
| --- | --- | --- | --- |
| `Webhook` | Entry point from backend | Lead Agent payload | Campaign/search context |
| `Code` | Expands Gemini queries | `search_queries`, `campaign_id`, `max_results` | One item per query |
| `HTTP Request` | Starts Apify/Google Maps search | `search_query`, `max_results` | Apify run or dataset reference |
| `Wait` | Gives scraper time to complete | Apify run context | Same context after delay |
| `HTTP Request1` | Fetches Apify results | Dataset/run reference | Raw place results |
| `Code1` | Cleans, dedupes, filters, maps fields | Raw places plus campaign context | Lead-create payloads |
| `HTTP Request2` | Saves leads in app database | Lead payloads | `lead_id` responses |
| `Code2` | Collapses many leads into one campaign item | Created lead responses | One campaign-level item |
| `HTTP Request3` | Starts async email extraction | `campaign_id`, `limit` | Extraction `job_id` |
| `Wait` after extraction | Lets background email extraction run | Extraction job response | Delayed campaign context |
| `HTTP Request4` | Runs website research | `campaign_id` | Research summary updates |
| `HTTP Request5` | Runs AI scoring | `campaign_id` | Score/priority updates |

Required n8n dynamic rules:
- Never hardcode `campaign_id`; use the id sent by the website/backend.
- Campaign-level endpoints must run once per campaign, not once per lead.
- Use expression mode for URLs that contain `campaign_id`; otherwise n8n may send literal `{{ ... }}` text and FastAPI will reject it as a non-integer.
- `HTTP Request3`, `HTTP Request4`, and `HTTP Request5` should use dynamic URLs and usually have request body disabled.

Recommended `Code2` node after lead creation:
```js
const campaignId = Number($("Code1").first().json.campaign_id);

if (!campaignId) {
  throw new Error("Missing campaign_id for email extraction");
}

return [{
  json: {
    campaign_id: campaignId,
    limit: 100
  }
}];
```

Recommended `HTTP Request3` email extraction node:
- Method: `POST`
- URL expression:
```js
{{ "https://ai-lead-generation-mvp.onrender.com/api/leads/campaign/" + Number($json.campaign_id) + "/extract-emails-async?limit=" + Number($json.limit) }}
```
- Send Body: off

Expected response:
```json
{
  "status": "running",
  "message": "Email extraction started for 28 leads.",
  "job_id": 123,
  "campaign_id": 20
}
```

Email extraction behavior:
- Endpoint: `POST /api/leads/campaign/{campaign_id}/extract-emails-async?limit=100`
- Only leads with a website and no saved email are eligible.
- The job runs in the background to avoid Render request timeouts.
- It first scrapes public website pages for visible emails.
- If no visible email is found, it tries common business patterns such as `info@domain.com`, `contact@domain.com`, `hello@domain.com`, `sales@domain.com`, and `hr@domain.com`.
- The frontend Email Extraction card polls the job every 3 seconds when started from the UI.
- In n8n, add a wait after starting extraction before research/scoring.

Recommended `HTTP Request4` research node:
- Method: `POST`
- URL expression:
```js
{{ "https://ai-lead-generation-mvp.onrender.com/api/campaigns/" + Number($json.campaign_id) + "/research-leads-async?limit=100" }}
```
- Send Body: off
- This starts background AI research and returns immediately with a `job_id`.
- Poll `GET /api/campaigns/research-job/{job_id}` or wait before scoring.
- Keep `limit` around `50-100` for normal runs. The backend allows up to `500`, but larger batches consume more Gemini calls and take longer.

Lead research behavior:
- Endpoint: `POST /api/campaigns/{campaign_id}/research-leads-async?limit=100`
- Poll endpoint: `GET /api/campaigns/research-job/{job_id}`
- Only leads with `research_status` of `not_researched` or `failed` are selected.
- Each lead can fetch public website pages and call Gemini for business summary, pain points, use case fit, outreach angle, confidence, and source notes.
- The worker commits progress after each lead and pauses between leads to reduce API failures.
- The older `POST /api/campaigns/{campaign_id}/research-leads?limit=5` endpoint still exists for small manual tests and is capped to 10 leads.

Recommended `HTTP Request5` scoring node:
- Method: `POST`
- URL expression:
```js
{{ "https://ai-lead-generation-mvp.onrender.com/api/lead-scoring/score-campaign/" + Number($json.campaign_id) + "?limit=10" }}
```
- Send Body: off

Lead Agent quantity rules:
- `queries_per_day` is the number of search phrases generated for one run.
- `max_results` is the target number of Google Maps results per query.
- Estimated leads are `queries_per_day * max_results`.
- Actual saved leads can be lower because Google Maps may return fewer places, Apify can return duplicates, and `Code1` filters empty names, duplicate websites/names, missing website/phone, and wrong-location results.

Common n8n errors:
- `Input should be a valid integer`: the URL probably sent literal `{{ $json.campaign_id }}` text. Switch the URL field to expression mode and concatenate the URL.
- `Hunter bulk enrichment is already running`: a campaign-level Hunter node ran once per lead. Collapse items to one campaign item first, or use the async Email Extraction endpoint instead.
- `Campaign with id ... was not found`: n8n sent the wrong/hardcoded campaign id.
- No emails found after extraction: leads may be missing websites, websites may hide emails, or guessed patterns could not be verified.
- Leads appear in the wrong campaign: a Code node or HTTP body still has a hardcoded campaign id.

Manual Lead Agent test:
1. Create or open a campaign.
2. Select `max_results=25` and `queries_per_day=1` for a small test.
3. Click `Find Leads Now`.
4. Confirm n8n `Webhook` receives the selected `campaign_id`.
5. Confirm `Code1` outputs lead objects with the same `campaign_id`.
6. Confirm `HTTP Request2` creates leads successfully.
7. Confirm `Code2` outputs exactly one item with `campaign_id` and `limit`.
8. Confirm `HTTP Request3` returns `status="running"` and a `job_id`.
9. Wait for email extraction, then run research and scoring.
10. Refresh the Leads page and confirm leads, emails, research status, and scores are attached to the selected campaign.

Current limitations:
- Lead Agent depends on the external n8n workflow and Apify availability.
- Google Maps/Apify output quality varies by query and region.
- Email extraction finds public or pattern-based business emails; it does not guarantee personal emails.
- Research and scoring are intentionally batched to avoid long requests and excessive AI usage.

## 11. Knowledge Document Upload

The Knowledge page supports uploading PDF, DOCX, TXT, and Markdown files up to 5 MB. The backend extracts readable text with `pypdf` for PDF files and `python-docx` for DOCX files. Plain text and Markdown files are read directly with UTF-8 fallback handling.

Uploaded text is sanitized, split into manageable chunks of roughly 2,000 to 2,500 characters with small overlap, and stored as active `company_knowledge` rows with `source_type="document"`. Each chunk keeps its `document_id` and `chunk_index`, while manual knowledge entries continue to use `source_type="manual"`.

AI email generation, follow-up generation, and response draft generation all use the same RAG search path. When uploaded document chunks match the outreach or reply context, they are included in the AI prompt with source information such as document filename and chunk number.

## 12. Semantic RAG

Week 13 adds embeddings for company knowledge. The backend uses Gemini embeddings through `EMBEDDING_MODEL` and stores vectors in Supabase/PostgreSQL with `pgvector` when the extension and permissions are available.

Startup migration tries to run `CREATE EXTENSION IF NOT EXISTS vector`, add an embedding column using the configured embedding dimension, and create an ivfflat cosine index. If any pgvector setup step fails, the app logs a warning and continues with keyword search.

Knowledge entries are embedded when manual entries are created or edited, and document chunks are embedded after upload. If embedding generation fails, the knowledge entry remains usable and stores an `embedding_error`; document upload and AI generation continue.

The Knowledge page includes a Semantic RAG status card and a `Generate Missing Embeddings` button. Search supports Hybrid, Semantic, and Keyword modes. Hybrid search tries semantic retrieval first, expands common sales/product phrases into related terms, merges keyword matches, deduplicates results, and falls back to keyword search when semantic retrieval is unavailable.

Suggested sample knowledge entry:
- Title: Training Analytics and Progress Tracking
- Category: Product Details
- Tags: analytics, progress, completion, quiz scores, HR dashboard
- Content: Managers can track lesson completion, quiz scores, engagement, and employee training status.

Current limitation: semantic quality depends on the embedding model, chunk quality, and how specific the company knowledge is. Keyword fallback remains available for all environments.

## 13. Lead Research

Week 14 adds AI lead research and enrichment. Research uses only the lead's website, existing lead CSV/manual fields, and the selected campaign details. It does not use paid third-party enrichment APIs.

The backend fetches at most 3 public pages per lead from a small fixed list: homepage, `/about`, `/about-us`, `/services`, and `/products`. Requests use an 8 second timeout, a 1 MB response limit, robots.txt checks, and private/local address blocking. Raw HTML is not stored; only extracted research insights are saved.

Research is campaign-aware. The AI must use the current campaign offer, target industry, target location, and target role to decide lead relevance, possible pain points, use case fit, outreach angle, and risk flags. It should not assume every lead needs onboarding, SOPs, training, HR analytics, or any other product-specific need unless the campaign offer supports that.

Stored enrichment fields include summary, business type, target customers, products/services, pain points, use case fit, outreach angle, risk flags, confidence, sources, error, and researched timestamp.

AI lead scoring includes research context when available and should mention whether research improved or limited confidence. Cold email, follow-up, and response draft generation can also use the research summary and outreach angle without overclaiming unsupported facts.

Manual test flow:
1. Add or upload leads for a campaign.
2. On the Leads page, click `Research Lead` for one lead or `Research Unresearched Leads` for a small batch.
3. Confirm research status, confidence, summary, outreach angle, and risk flags appear.
4. Rescore the lead and confirm scoring references research where relevant.
5. Generate a cold email and confirm personalization uses the campaign-aware outreach angle without inventing facts.

Current limitation: research is lightweight website research only. It does not crawl recursively and does not use external paid enrichment APIs.

## 14. Opportunity And Lead Discovery

Phase 3 adds an Opportunities page. A user enters a rough goal such as professor outreach, restaurant marketing, clinic software, cybersecurity audit outreach, college project assistance, SME outreach, or startup sales. Gemini turns that rough idea into a practical campaign strategy.

Generated strategies include target audience, ideal roles, industries, locations, pain points, value proposition, outreach angle, search keywords, lead source ideas, email script, call script, follow-up sequence, qualification criteria, risk flags, suggested campaign fields, and suggested discovery fields.

The user can review the strategy and then create a campaign from the suggested campaign name, industry, location, target role, and offer. The system returns the existing converted campaign if the opportunity was already converted, preventing accidental duplicates.

The user can also create a Lead Discovery job from a generated strategy. Discovery jobs can be tied to a campaign, an opportunity, or both. They store a target type, department/domain, target role, goal, source URLs, generated search queries, status, attempted page count, contact count, and friendly errors.

Lead Discovery supports two practical sourcing paths:
- CSV upload remains available for lead lists the user already has.
- Discovery accepts public source URLs, extracts readable emails and phone numbers, structures contacts with Gemini when available, and keeps every contact pending until the user reviews it.

Generated query mode is guidance only. The app can create safe manual queries such as `site:.ac.in "faculty" "computer science" "email" "India"`, but it does not scrape Google results or automate LinkedIn. Users copy queries, find public official pages, and paste those URLs into the discovery job.

Imported discovery contacts are mapped into the existing Leads table with `source="discovery"`. Duplicate imports are skipped for the same campaign/email. Contacts without an email are skipped by default. After import, users can research imported leads, score them, generate emails, and use the opportunity call script for manual outreach.

The generator is generic and campaign-aware. It should not assume a specific product. It can adapt to professor outreach, colleges, SMEs, restaurants, clinics, startups, retail shops, SaaS, manufacturing, service businesses, and other segments based on the user's goal and offer.

Safety limits:
- Emails are not sent automatically.
- LinkedIn scraping is not automated.
- LinkedIn may be suggested only for manual search or user-provided URLs.
- Paid enrichment APIs are not used.
- AI strategy output is reviewable before campaign creation.
- Discovery fetches only user-provided public URLs.
- Discovery does not bypass login pages, CAPTCHA, private systems, or rate limits.
- Discovery uses short timeouts, a small response-size cap, private/local URL blocking, and friendly errors.
- Raw page HTML is not stored; only extracted contact context and structured review fields are saved.
- Discovered contacts must be reviewed before import.

Manual test examples:
- Professor outreach for research/project implementation assistance across engineering colleges in India.
- Restaurant marketing for Google reviews, Instagram visibility, local discovery, and footfall.
- Clinic software for appointments, patient records, billing, and staff coordination.
- Cybersecurity audit outreach for startups or SaaS companies.
- Manual URL discovery for public faculty, department, company, restaurant, clinic, or startup pages.
- Fake/unavailable URLs should fail cleanly with a friendly warning and zero imported leads.

## 15. Vapi Calling Agent

The Calls module adds optional AI calling through Vapi. The frontend never calls Vapi directly. It calls the FastAPI backend, and the backend uses `VAPI_API_KEY` server-side.

Environment variables:

```env
VAPI_ENABLED=false
VAPI_API_KEY=
VAPI_ASSISTANT_ID=
VAPI_PHONE_NUMBER_ID=
VAPI_WEBHOOK_SECRET=
VAPI_DEFAULT_TEST_PHONE=
VAPI_BASE_URL=https://api.vapi.ai
```

Backend endpoints:
- `GET /api/calls/config/status`
- `GET /api/calls`
- `GET /api/calls/{call_log_id}`
- `POST /api/calls/generate-script`
- `POST /api/calls/start-vapi`
- `POST /api/calls/manual-log`
- `PATCH /api/calls/{call_log_id}/outcome`
- `POST /api/calls/{call_log_id}/create-followup-email`
- `POST /api/calls/vapi/webhook`
- `POST /api/calls/vapi/tool`

The Vapi assistant setup guide is in `backend/docs/vapi_assistant_setup.md`. It includes the assistant system prompt, required tools, webhook URLs, and dashboard setup steps.

The call script generator uses the current campaign offer, lead fields, lead research, AI score context, and relevant company knowledge when available. It is generic and campaign-aware. Professor/research campaigns get a respectful academic tone only when the campaign context supports that.

Vapi webhook handling supports status updates, transcript updates, end-of-call reports, hang events, unknown payloads, and tool/function calls. Tool calls can fetch lead context, update outcomes, save summaries, create follow-up email drafts, mark do-not-call, and store callback notes.

Testing flow:
1. Open Calls page with Vapi env missing. It should show `Vapi not configured` without crashing.
2. Generate a call script for one lead.
3. Save a manual call log with outcome `asked_details`.
4. Create a follow-up email draft from that call log.
5. Configure Vapi envs and test only with your own number first.
6. Start one selected test call.
7. Confirm Vapi webhooks update status, transcript, summary, and outcome.
8. Mark a lead do-not-call and confirm AI calling is blocked.

Current limitations:
- No bulk calling.
- No automatic calling.
- Real calls require Vapi phone setup and credits.
- Use a test number first.
- Follow-up emails are drafts only and require manual approval before sending.

## 16. Safety Notes

- Emails are not sent automatically.
- AI scoring is a recommendation and should be reviewed before outreach.
- Hunter.io enrichment is optional and requires explicit user action.
- Hunter.io bulk enrichment is capped per request to reduce accidental credit usage.
- Calls are not started automatically.
- Bulk calling is not implemented.
- Vapi calls require explicit user action on a selected lead.
- Vapi API keys stay backend-only.
- Do-not-call leads cannot be called from the app.
- Vapi raw payloads are stored for debugging but not shown by default in the UI.
- Only approved drafts can be sent.
- Follow-ups are never sent automatically.
- Discovered contacts are not imported automatically.
- Discovery uses public URLs selected by the user; it does not scrape search result pages or LinkedIn automatically.
- Lead Agent uses an external n8n/Apify workflow and should be run with conservative query/result limits.
- n8n workflow credentials and Apify tokens stay outside the frontend and should not be committed.
- Only approved follow-ups can be sent.
- Follow-ups are limited to 2 per original email.
- Gmail sending is limited.
- Reply checks use Gmail readonly access and do not send emails.
- AI reply classification only suggests next actions. It does not send replies automatically.
- AI response drafts are not sent automatically.
- Response drafts must be approved before sending.
- AI can use saved company knowledge when relevant, but users must review before sending.
- Do not include pricing unless it has been verified.
- Credentials stay backend-only.
- Sample CSV files use placeholder data only.
- Sample knowledge documents use placeholder data only.

## 17. Future Improvements

- Google Search lead discovery
- Authentication
- CRM integration
- Better semantic reranking for larger knowledge bases
- Richer embedding health monitoring and retry controls
- Callback/task calendar for call-later outcomes
- Bulk call queue with explicit opt-in safeguards
