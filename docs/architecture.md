# Incisight Architecture

Incisight is split into a browser dashboard, a FastAPI application, and a relational database. The browser owns interaction and microphone capture. The backend owns incident state, validation, security boundaries, evidence records, approval rules, and persistence.

## System Components

- `frontend/` contains the React dashboard and AssemblyAI browser WebSocket client.
- `backend/app/main.py` exposes health checks, incident routes, Server-Sent Events, voice token minting, and authenticated tool routes.
- `backend/app/models.py` defines persisted incidents, timeline events, evidence records, contradictions, and stakeholder updates.
- `backend/app/schemas.py` defines request and response validation boundaries.
- `backend/app/services.py` contains incident workflow behavior, controlled evidence generation, contradiction review, update drafting, and event broadcasting.
- `backend/app/security.py` handles tool authentication, signed incident-scoped grants, and approval nonces.
- `backend/alembic/` contains database migration configuration.
- `render.yaml` defines the API service, static dashboard service, and PostgreSQL database for Render.

## Runtime Flow

1. The operator opens the dashboard directly.
2. The dashboard creates or loads an incident from the backend.
3. The dashboard requests a voice token from the backend.
4. The backend exchanges the private AssemblyAI API key for a short-lived browser token and returns a signed Incisight tool grant.
5. The browser connects to AssemblyAI and sends the session prompt, key terms, voice settings, and flat tool schemas.
6. Voice tool calls read current incident data or prepare unsaved proposals in the browser.
7. The operator reviews a proposal and confirms a dashboard write; the backend validates it and emits Server-Sent Events.
8. The dashboard updates live as timeline items, evidence, contradictions, and stakeholder updates change.

## Data Model

Incisight stores:

- Incidents with severity, status, title, and timestamps
- Incident events for claims, tool observations, assignments, and decisions
- Evidence records linked to service checks and advisory lookups
- Contradiction records that preserve both conflicting statements
- Stakeholder updates with draft, approved, or published state

SQLite is the local default. PostgreSQL is used in deployment through Render.

## Security Model

The browser never receives the permanent AssemblyAI API key or permanent tool secret. Browser voice sessions receive:

- a short-lived AssemblyAI connection token
- a signed Incisight tool grant scoped to one incident

The current demo has no sign-in step. Incident reads, dashboard writes, and voice token requests are available to anyone who can reach the app. Production deployment requires an access boundary and controls on voice token issuance.

Server-to-server tool calls can use `X-Tool-Secret` with `TOOL_API_SECRET`. Administrative operations use `X-Admin-Secret` with `ADMIN_API_SECRET`.

Stakeholder publishing requires an approval nonce that expires after two minutes and is bound to the update ID and approver. The UI presents a separate confirmation step before requesting the nonce.

## Evidence and Contradictions

The current service-health and advisory sources are controlled application sources. This keeps local and deployed behavior repeatable while preserving the same interfaces that a live evidence fetcher would use.

Contradiction detection combines normalized subject matching with deterministic health-state judgment. This makes the workflow predictable and testable. `LLM_API_KEY` and `LLM_MODEL` are reserved for a future LLM-backed review stage.

## Deployment Model

Render runs the backend and frontend as separate services:

- `incisight-api` installs Python dependencies, runs Alembic migrations, and starts Uvicorn.
- `incisight-dashboard` installs Node dependencies, builds the Vite app, and serves static assets.
- `incisight-db` provides PostgreSQL for deployed incident data.

Required deployed environment values:

- `ASSEMBLYAI_API_KEY`
- `FRONTEND_ORIGIN`
- `VITE_API_URL`

Render generates `TOOL_API_SECRET` and `ADMIN_API_SECRET` for the API service.

## Operational Boundaries

Incisight does not execute shell commands, scan networks, exploit systems, remediate infrastructure, or publish to external stakeholder systems. It records, structures, validates, and approval-gates incident communication inside the application boundary.
