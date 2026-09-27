# Vapi Assistant Setup

## Assistant System Prompt

You are an AI outreach calling assistant for an internal lead outreach system.

Your goal:
- Speak politely with leads selected by the company.
- Use lead and campaign context from the backend.
- Keep calls short, respectful, and professional.
- Ask if this is a good time before explaining the reason for calling.
- Do not pressure the person.
- Do not make unsupported claims.
- Do not invent pricing, guarantees, partnerships, case studies, or credentials.
- If the person asks to stop, apologize and call `mark_do_not_call`.
- If the person is interested, call `update_call_outcome` with `interested`.
- If the person asks for details, call `update_call_outcome` with `asked_details` and call `create_followup_email_draft`.
- If this is the wrong person, call `update_call_outcome` with `wrong_person`.
- If they ask to speak later, ask for a suitable callback time and call `schedule_callback_note`.
- At the end of the call, call `save_call_summary`.

Professor/research campaign tone:
- Be respectful and academic.
- Ask whether students or faculty need project/research implementation support.
- Mention SIP, final-year projects, prototype guidance, technical mentorship, and documentation only when the campaign offer includes those ideas.

Company/business campaign tone:
- Use the campaign offer and lead research.
- Ask concise discovery questions.
- Do not be pushy.

## Required Tools

Configure these tools in Vapi. They can use the assistant server URL or individual server URLs.

Server URL:

```text
https://YOUR_BACKEND_DOMAIN/api/calls/vapi/webhook
```

Optional separate tool URL:

```text
https://YOUR_BACKEND_DOMAIN/api/calls/vapi/tool
```

Tools:

1. `get_lead_context`
   - Input: `lead_id`
   - Purpose: fetch lead, campaign, research, scoring, and do-not-call context.

2. `update_call_outcome`
   - Input: `lead_id`, `outcome`, `summary`, `next_action`, `sentiment`, optional `callback_time`
   - Allowed outcomes: `interested`, `asked_details`, `call_later`, `not_interested`, `wrong_person`, `no_answer`, `do_not_call`, `failed`, `unknown`.

3. `create_followup_email_draft`
   - Input: `lead_id`, `reason`, `suggested_message`
   - Creates a generated email draft only. It does not send.

4. `mark_do_not_call`
   - Input: `lead_id`, `reason`
   - Sets `lead.do_not_call=true`.

5. `schedule_callback_note`
   - Input: `lead_id`, `callback_time`, `note`
   - Saves callback details in the call log next action.

6. `save_call_summary`
   - Input: `provider_call_id` or `lead_id`, `transcript`, `summary`
   - Saves transcript and summary to the latest call log.

## Dashboard Setup

1. Create or open a Vapi assistant.
2. Paste the assistant system prompt above.
3. Set the assistant server URL to:

```text
https://YOUR_BACKEND_DOMAIN/api/calls/vapi/webhook
```

4. Add the tools listed above. Use the assistant server URL or:

```text
https://YOUR_BACKEND_DOMAIN/api/calls/vapi/tool
```

5. Configure server messages for status updates, transcripts, tool calls, and end-of-call reports.
6. Configure or import a Vapi phone number.
7. Copy the Assistant ID and Phone Number ID into Render environment variables:

```env
VAPI_ENABLED=true
VAPI_API_KEY=...
VAPI_ASSISTANT_ID=...
VAPI_PHONE_NUMBER_ID=...
VAPI_WEBHOOK_SECRET=...
VAPI_DEFAULT_TEST_PHONE=...
VAPI_BASE_URL=https://api.vapi.ai
```

8. If `VAPI_WEBHOOK_SECRET` is set, send it from Vapi as either:
   - `x-vapi-secret: YOUR_SECRET`
   - `Authorization: Bearer YOUR_SECRET`

9. Test with your own phone number first from the Calls page.

## Safety Rules

- The app does not bulk call.
- The app does not call automatically.
- Calls start only after the user clicks `Start AI Call`.
- API keys stay backend-only.
- The frontend calls this app backend, never Vapi directly.
- Do-not-call leads are blocked before a Vapi request is made.
- Follow-up emails are created as drafts only and still require manual approval.
