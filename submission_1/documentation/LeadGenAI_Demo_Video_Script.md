# LeadGenAI — Demo Video Script

**Prasunethon 2.0 · Final Project Submission · Team Avengers**
Raj Gautam (lead) · Priyanshu Kumar · Sampath Kumar Midde

**Target length:** 4:00 (a 3:00 cut is marked at the end)
**Format:** screen recording with voice-over — record narration separately if you can
**UI:** light mode, to match the deck and the report

---

## ⚠️ Pre-flight — do these before you hit record

**1. Wake the backend 20 minutes early.** Render's free tier sleeps after ~15 minutes idle, and the next request takes 50+ seconds to cold-start. That is 50 seconds of dead air on camera.

Open this in a tab and refresh it every 5 minutes right up to the take, and keep the tab open while recording:

```
https://ai-lead-generation-mvp.onrender.com/api/health
```

**2. Pre-run everything slow.** Gemini calls take 3–15 seconds each. Before recording, run the AI research and scoring on the leads you plan to show so the results are already on screen. Demonstrate the *result*, not the spinner. The only thing worth showing live is a click that responds instantly.

**3. Set the stage.** Have these tabs open and ready in this order: Dashboard → Campaigns → Lead Discovery → Leads (with the Kanpur campaign filtered) → Emails → Calls → the n8n canvas.

**4. Re-check your numbers.** The script quotes the dashboard figures as of the last check — 37 campaigns, 2,033 leads, 170 scored. **Open your dashboard and read the current numbers**, then say those. Never quote a figure you haven't just looked at.

**5. Do not click:** bulk Hunter enrichment (subscription lapsed), or "Start Actual Lead Call" (your Vapi plan only dials the registered test number — the script handles this honestly instead).

**6. Screen setup:** 1920×1080, browser zoom at 100%, bookmarks bar hidden, no notifications. Record at 1080p.

---

## The script

Timings are cumulative. Bracketed text is what you do on screen; plain text is what you say.

---

### 0:00 – 0:22 · The problem — **Raj**

> *[Dashboard on screen, still]*
>
> "Finding a B2B lead is the easy part. What actually costs a sales team its week is everything between finding the lead and sending a message that's worth reading — research, qualification, writing, follow-up. Each of those lives in a different tool, so context gets lost at every handoff, and two identical leads end up with different priorities depending on who looked at them.
>
> LeadGenAI puts that whole chain in one place."

---

### 0:22 – 0:40 · What it is — **Raj**

> *[Slowly scroll the dashboard so the stat tiles are visible]*
>
> "This is the deployed product, running on real data — **[read your current numbers]** campaigns, **[N]** leads, **[N]** of them AI-scored, with replies coming back in.
>
> Here's one lead moving through the whole system."

---

### 0:40 – 1:05 · Campaign + discovery — **Priyanshu**

> *[Campaigns → open the Kanpur Mechanical & Industrial Outreach campaign]*
>
> "Everything starts from a campaign: industry, location, target role, and the offer. Every AI stage downstream reads these fields, so how specific you are here decides how good the output is.
>
> *[Lead Discovery page]*
>
> "Leads come in three ways — CSV upload, public URLs you've reviewed yourself, or the automated Lead Agent. For this campaign the agent sourced **118 leads, and recovered a public email address for all 118** — no paid data subscription involved. The cost estimate is shown before you trigger the run, so you know what a discovery job will spend."

---

### 1:05 – 1:30 · Research — **Priyanshu**

> *[Leads → open a researched lead → expand "View AI Research"]*
>
> "Gemini reads the company's public pages and produces a structured profile — business type, likely pain points, use-case fit, outreach angle, risk flags.
>
> And look at this one specifically. This company's website couldn't be read, so the model says so: the summary records that research data was limited, and the risk flag states plainly that it only had CSV and campaign data to work with. It doesn't invent a business problem to fill the field. That matters, because a research layer that always sounds confident is one you can't trust."

---

### 1:30 – 2:05 · Scoring — the key moment — **Priyanshu**

> *[Open the New Sindh Biscuit lead so the AI Scores panel is visible: Fit 95, Contact 25, Final 78]*
>
> "This is the part I'd most want you to see. We don't produce one blended number — we score two things separately.
>
> **Fit** is how well the business matches the campaign: this one scores 95, it's a strong match. **Contact confidence** is how likely our stored address is to reach a decision-maker — and that scores 25, because the only email we recovered is a generic address whose domain doesn't match the company at all.
>
> The final score is a fixed formula: **0.75 times fit, plus 0.25 times contact confidence** — which gives 78.
>
> A single blended score would have said 'seventy-something' and left you guessing. Splitting them tells you the diagnosis immediately: right company, wrong contact route. Don't drop the lead — go find a better address. And the interface offers exactly those actions."

---

### 2:05 – 2:30 · Draft and the approval gate — **Priyanshu**

> *[Emails page → open a generated draft]*
>
> "Drafting pulls in the lead, the campaign, the research, the score, and any relevant company knowledge. Here's a real generated email with the score breakdown attached.
>
> *[Hover over Send / Reject / Edit without clicking Send]*
>
> "And this is the boundary the whole product is built around. The AI writes it. **A human sends it.** That's enforced in the backend, not just in the interface — an unapproved draft is rejected by the send endpoint no matter how you call it. Same for replies, follow-ups, and calls."

---

### 2:30 – 2:50 · Replies and calling — **Priyanshu**

> *[Show the classified replies list]*
>
> "Replies that come back are classified by intent, sentiment and priority, each with a specific recommended next action — not just a status label.
>
> *[Calls page, Vapi status row visible]*
>
> "Calling is a stage of the same workflow, not a separate tool. Vapi is enabled and configured. On our current provider plan outbound calls go to a registered test number — that's a billing limit, not a missing integration; the call path, script generation and outcome capture all run end to end."

---

### 2:50 – 3:20 · Under the hood — **Sampath**

> *[n8n canvas on screen]*
>
> "One architectural decision worth calling out. Automated sourcing doesn't run inside our backend — it runs in this n8n workflow. Our API triggers it by webhook, n8n calls the Google Maps scraper, normalises the results, and posts leads back through our public lead endpoint.
>
> We did that deliberately: scraping is slow, metered and unreliable, so we kept it out of the request path and behind a replaceable interface. Swap the provider and no backend deploy is needed."

> *[Knowledge page]*
>
> "Grounding is retrieval, not fine-tuning. Company documents are chunked and embedded at 3,072 dimensions in Postgres with pgvector, and retrieval is hybrid — semantic plus keyword, with keyword as the fallback. Relevant facts go into the prompt; we never train a model on your documents."

---

### 3:20 – 3:45 · What's real — **Sampath**

> *[Back to the dashboard]*
>
> "To be precise about what's built: twenty API route modules, seventeen services, a seventeen-table schema, and a nine-page interface — deployed on Vercel, Render and Supabase.
>
> The reply and conversion numbers you see are pilot-scale, and we've said so in the report rather than dressing them up. Our full write-up also documents what isn't done yet — authentication is the next thing we're building, and it's the one blocker before this goes multi-user."

---

### 3:45 – 4:00 · Close — **Raj**

> *[Title slide or the live URL]*
>
> "LeadGenAI turns fragmented prospecting into one traceable workflow — where every priority carries its reasoning, and every outbound message carries a human decision.
>
> It's live, the repository is public, and both links are on screen. Thank you."

> *[Hold on screen for 4 seconds:]*
> `ai-lead-generation-mvp.vercel.app`
> `github.com/FasterThanAi/ai-lead-generation-mvp`

---

## If you need a 3:00 cut

Drop these, in this order — they lose the least:

1. **Replies** (2:30–2:38) — the approval-gate point already covers the principle. *Saves ~10s*
2. **The knowledge/RAG paragraph** (3:05–3:20) — keep the n8n boundary, drop pgvector. *Saves ~15s*
3. **Discovery detail** (0:50–1:05) — compress to "the agent sourced 118 leads and found an email for every one." *Saves ~15s*
4. **Trim the problem opener** to two sentences. *Saves ~8s*
5. **Shorten "what's real"** to one sentence on scale. *Saves ~12s*

Never cut the scoring section. It's the strongest 35 seconds you have and it's the part that separates this from a wrapper around a language model.

---

## Delivery notes

**Slow down on the scoring segment.** It's the one place a judge has to follow a number. Everywhere else you can move quickly; there, pause after "0.75 times fit plus 0.25 times contact confidence" and let it land.

**Don't narrate your clicks.** "Now I'll click on Leads" is dead air. Click, and talk about what appears.

**Say what's not finished, once.** The single line about authentication buys you more credibility than it costs. Judges assume a hackathon MVP has gaps; a team that names its own gap sounds like it knows its codebase.

**Record narration separately if you can.** Screen-record the clicks first, then voice over. You'll get a cleaner take and you can fix a fumbled sentence without redoing the whole capture.

**If something errors on camera, keep going.** Don't apologise on the recording — cut it in the edit.
