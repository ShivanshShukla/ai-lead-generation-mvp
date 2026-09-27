# Contributing to Lead Agent

Thanks for helping improve **Lead Agent (AI Lead Generation MVP)**! Every contribution counts, from fixing a typo to building a feature.

## Before you start

1. Browse the [open issues](https://github.com/FasterThanAi/ai-lead-generation-mvp/issues). Issues labelled `good first issue` are a great place to begin.
2. **Comment on the issue** ("I'd like to work on this") so two people don't do the same work.
3. Wait for a maintainer to assign it to you, then start.

## Quick contributions from the browser

Small changes don't need a local setup:

1. Open the file on GitHub and click the pencil icon (**Edit this file**).
2. Make your change.
3. Click **Commit changes...** then **Propose changes**. GitHub forks the repo for you.
4. On the next page click **Create pull request**, and write `Fixes #<issue-number>` in the description.

## Local setup

Backend (FastAPI):

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # fill in only the keys you need
uvicorn app.main:app --reload
```

Frontend (React + Vite):

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

- Backend: http://127.0.0.1:8000 (API docs at `/docs`)
- Frontend: http://localhost:5173

## Before opening a pull request

- [ ] One issue per pull request. Keep changes small and focused.
- [ ] Link the issue in the description with `Fixes #<number>`.
- [ ] For frontend changes, `npm run build` passes in `frontend/`.
- [ ] Add a screenshot for any visible UI change.
- [ ] **Never commit** `.env` files, API keys, OAuth tokens or real lead data.

## Commit messages

Use a short prefix describing the change:

| Prefix | Use for |
|---|---|
| `feat:` | a new feature |
| `fix:` | a bug fix |
| `docs:` | documentation only |
| `style:` | formatting or visual tweaks with no logic change |
| `refactor:` | code changes that neither fix a bug nor add a feature |
| `chore:` | tooling, config and cleanup |

Example: `fix(frontend): show Gmail daily limit message`

## Code style

- **Frontend:** React function components with Tailwind utility classes. Reuse the shared components in `frontend/src/components/ui/` (Button, Card, Badge, Toast...) instead of writing new ones.
- **Backend:** routes live in `backend/app/api/routes/`, business logic in `backend/app/services/`, request and response models in `backend/app/schemas/`.
- Match the style of the file you are editing.

## Code of Conduct

By taking part you agree to follow our [Code of Conduct](CODE_OF_CONDUCT.md).
