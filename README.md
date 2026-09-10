# Incisight

Incisight is an incident-command application for cybersecurity incidents and service outages. It converts live operator conversation into a structured incident timeline, validates selected claims against controlled evidence sources, highlights contradictions, tracks ownership, and requires explicit approval before stakeholder updates are published.

## Capabilities

- React, TypeScript, and Vite dashboard for incident command workflows
- FastAPI backend with SQLAlchemy models, Alembic migrations, and SQLite/PostgreSQL support
- AssemblyAI Voice Agent integration using browser-safe, server-minted temporary tokens
- Authenticated incident tool endpoints for timeline events, service checks, advisory lookup, contradiction review, update drafting, and approval-gated publishing
- Server-Sent Events for live dashboard updates
- Human approval nonce flow for stakeholder update publishing
- Test coverage for API behavior, validation, authentication, idempotency, contradiction handling, and approval controls
- Render blueprint for API, dashboard, and PostgreSQL deployment

## Project Layout

```text
Incisight/
  backend/              FastAPI application, database models, migrations, and tests
  docs/                 Production-facing architecture and API documentation
  frontend/             React dashboard and browser voice integration
  scripts/              Operational checks and agent configuration helper
  render.yaml           Render blueprint for deployed services
  .env                  Local environment configuration
```

Generated local runtime folders such as `backend/.venv`, `frontend/node_modules`, and `backend/incisight.db` are useful for local development but are not committed or required by Render. Render rebuilds dependencies and provisions the deployment database from the source and blueprint.

## Configuration

The local environment file is `.env` in the project root.

Required for local voice testing:

```env
ASSEMBLYAI_API_KEY=your_real_assemblyai_key
```

Required for backend protection:

```env
TOOL_API_SECRET=your_long_random_tool_secret
ADMIN_API_SECRET=your_long_random_admin_secret
```

Default local values:

```env
DATABASE_URL=sqlite:///./incisight.db
APP_BASE_URL=http://localhost:8000
FRONTEND_ORIGIN=http://localhost:5173
```

Optional values:

```env
ASSEMBLYAI_AGENT_ID=
LLM_API_KEY=
LLM_MODEL=
```

`ASSEMBLYAI_AGENT_ID`, `LLM_API_KEY`, and `LLM_MODEL` are reserved for future integrations and can stay blank in the current application.

## Local Development

Requires Python 3.12 and Node 20 or newer.

Backend:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Quality Checks

Backend:

```powershell
cd backend
pytest -q
python ..\scripts\verify_no_secrets.py
python ..\scripts\publish_agent_config.py
```

Frontend:

```powershell
cd frontend
npm run typecheck
npm run build
```

## Deployment

Incisight is deployment-ready for Render through `render.yaml`.

1. Push the project to a Git repository.
2. Create a Render Blueprint from `render.yaml`.
3. Set `ASSEMBLYAI_API_KEY` on the API service.
4. Set `FRONTEND_ORIGIN` to the deployed dashboard origin.
5. Set `VITE_API_URL` on the dashboard service to the deployed API origin.
6. Deploy the API and dashboard.
7. Confirm `/health`, `/ready`, dashboard loading, Server-Sent Events, HTTPS microphone permission, and voice connection.

Render generates `TOOL_API_SECRET` and `ADMIN_API_SECRET` for the deployed API. The blueprint also provisions PostgreSQL and applies Alembic migrations during the API build.

## Security Posture

- The AssemblyAI API key stays on the backend and is exchanged for short-lived browser tokens.
- Tool routes require either the server tool secret or a signed, incident-scoped grant.
- Voice transcript payloads are treated as untrusted input and validated through Pydantic schemas.
- Stakeholder publishing requires an approval nonce tied to the draft, approver, and expiration time.
- The backend does not execute shell commands, scan networks, remediate systems, or publish to external channels.
- Generated evidence used by the local service-check path is labeled as simulated data.

## Operational Notes

- Use PostgreSQL in deployed environments.
- Keep `.env` private and do not commit real secrets.
- Rotate `TOOL_API_SECRET` and `ADMIN_API_SECRET` if exposed.
- Take a database backup before future destructive migrations.
- Confirm reverse-proxy settings do not buffer Server-Sent Events.

## Current Limitations

- Stakeholder publishing is represented inside Incisight rather than sent to an external email, Slack, or ticketing system.
- Service-health and advisory evidence are controlled application sources, not live internet fetches.
- Authentication is designed for a single trusted operator environment.
- The semantic contradiction stage is deterministic; optional LLM-backed review can be added later.
