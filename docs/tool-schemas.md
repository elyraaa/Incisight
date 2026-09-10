# Incisight Tool API

Incisight exposes a small set of authenticated HTTP tools for incident workflows. These routes are used by the AssemblyAI voice session and can also be called by trusted server integrations.

All `/api/tools/*` routes require one of the following:

- `X-Tool-Secret: <TOOL_API_SECRET>` for trusted server integrations
- `Authorization: Bearer <scoped-grant>` for browser voice sessions

The browser grant is signed, time-limited, and bound to one incident. Schemas reject unexpected fields, invalid enum values, overlong text, malformed identifiers, and confidence values outside `0` to `1`.

## Tools

| Tool name | Method and route | Required arguments | Result |
| --- | --- | --- | --- |
| `record_incident_event` | `POST /api/tools/record-incident-event` | `incident_id`, `event_type`, `summary`, `source_type`, `confidence` | Adds an idempotent timeline event |
| `check_service_health` | `GET /api/tools/check-service-health` | `incident_id`, `service` | Records controlled service evidence and a tool event |
| `search_security_advisory` | `GET /api/tools/search-security-advisory` | `incident_id`, `query` | Records controlled advisory evidence |
| `find_contradictions` | `POST /api/tools/find-contradictions` | `incident_id`, `claim_event_id` | Persists new open contradiction candidates |
| `draft_stakeholder_update` | `POST /api/tools/draft-stakeholder-update` | `incident_id` | Creates a stakeholder update draft from stored facts |
| `approve_stakeholder_update` | `POST /api/tools/approve-stakeholder-update` | `incident_id`, `update_id`, `approver`, `approval_nonce`, `confirmed: true` | Marks an approved update as published inside Incisight |

The canonical request schemas live in `backend/app/schemas.py`. The flat AssemblyAI Voice Agent function definitions live in `frontend/src/voice.ts`.

## Error Contract

Errors use FastAPI response bodies with stable `detail.code` values. Common codes include:

- `tool_auth_required`
- `incident_not_found`
- `approval_nonce_invalid`
- `draft_not_approvable`
- `assemblyai_not_configured`

When an error can be resolved by user or operator action, the response includes recovery text.

## Evidence Ingestion Requirements

The current application uses controlled evidence sources. A future external fetcher should keep the same safety boundary:

- accept HTTPS only
- reject private, loopback, and link-local IP resolutions
- use a hostname allowlist
- enforce request timeout and response-size limits
- accept known text content types only
- normalize extracted text
- store source URL, retrieval time, and SHA-256 hash
- never accept arbitrary URLs directly from voice-tool arguments