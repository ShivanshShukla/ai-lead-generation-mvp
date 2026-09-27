LeadGenAI - Prasunethon 2.0 Final Project Submission
Team Avengers: Raj Gautam (Team Leader), Priyanshu Kumar, Sampath Kumar Midde

===========================================================
LINKS
===========================================================

Live application (deployed, working demo):
    https://ai-lead-generation-mvp.vercel.app/

Source repository (public):
    https://github.com/FasterThanAi/ai-lead-generation-mvp

Demo video:
    https://youtu.be/E8rn1ELSbzM

===========================================================
CONTENTS
===========================================================

README.txt
    This file - all submission links.

Prasunethon_2.0_Team_Avengers_Final_Presentation.pptx
    17-slide project presentation.

documentation/
    LeadGenAI_Final_Report.pdf
        35-page technical report: architecture, module design,
        the lead scoring model, data model and API surface,
        security and governance, testing, deployment, roadmap.
        All interface figures are screenshots of the running system.
    LeadGenAI_Demo_Video_Script.md
        Script and shot list used for the demo video.
    repository-README.md
        Setup and run instructions from the repository.

source-code/
    Full application source at the submitted commit.
    backend/   FastAPI + SQLAlchemy - 20 API route modules, 17 services,
               17-table schema, ~20,000 lines of Python.
    frontend/  React 19 + Vite + Tailwind CSS 4 - 9 pages.
    docs/      Additional project documentation.

    No credentials are included. Copy backend/.env.example to
    backend/.env and supply your own keys to run locally.

===========================================================
QUICK START
===========================================================

Backend:
    cd backend
    python -m venv venv && source venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env        # then add your own API keys
    uvicorn app.main:app --reload

Frontend:
    cd frontend
    npm install
    npm run dev

Requires a Gemini API key. Gmail OAuth, Vapi and n8n are optional
integrations; the application runs without them.
