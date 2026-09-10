import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from . import models, schemas, services
from .config import get_settings
from .database import Base, engine, get_db
from .security import (assert_grant_incident, issue_approval_nonce, issue_tool_grant,
                       require_tool_auth, verify_approval_nonce)

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Incisight API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"status": "ok", "service": "incisight-api"}


@app.get("/ready")
def ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ready"}


@app.post("/api/incidents", status_code=201)
async def create_incident(payload: schemas.IncidentCreate, db: Session = Depends(get_db)):
    row = services.create_incident(db, payload)
    await services.bus.publish(row.id, {"type": "incident.created"})
    return services.incident_dict(row)


@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str, db: Session = Depends(get_db)):
    return services.aggregate(db, incident_id)


@app.get("/api/incidents/{incident_id}/timeline")
def get_timeline(incident_id: str, db: Session = Depends(get_db)):
    return services.aggregate(db, incident_id)["timeline"]


@app.get("/api/incidents/{incident_id}/stream")
async def stream_incident(incident_id: str, request: Request, db: Session = Depends(get_db)):
    if not db.get(models.Incident, incident_id):
        raise HTTPException(404, detail={"code": "incident_not_found"})
    async def events():
        queue = services.bus.subscribe(incident_id)
        try:
            yield "event: connected\ndata: {}\n\n"
            while not await request.is_disconnected():
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: refresh\ndata: {json.dumps(item)}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            services.bus.unsubscribe(incident_id, queue)
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/voice/token")
async def voice_token(payload: schemas.VoiceTokenRequest, db: Session = Depends(get_db)):
    incident = db.get(models.Incident, payload.incident_id)
    if not incident: raise HTTPException(404, detail={"code": "incident_not_found"})
    if not settings.assemblyai_api_key:
        raise HTTPException(503, detail={"code": "assemblyai_not_configured", "recovery": "Set ASSEMBLYAI_API_KEY on the backend."})
    started = time.monotonic()
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.get("https://agents.assemblyai.com/v1/token",
            params={"expires_in_seconds": 120, "max_session_duration_seconds": 1800},
            headers={"Authorization": f"Bearer {settings.assemblyai_api_key}"})
    if response.is_error:
        raise HTTPException(502, detail={"code": "voice_token_failed", "recovery": "Check the AssemblyAI key and try again."})
    return {"token": response.json()["token"], "tool_grant": issue_tool_grant(incident.id),
            "expires_in_seconds": 120, "session_max_seconds": 1800,
            "keyterms": list(dict.fromkeys([incident.affected_service, *incident.keyterms])),
            "telemetry": {"provider": "assemblyai", "duration_ms": round((time.monotonic()-started)*1000)}}


@app.post("/api/transcripts")
async def save_transcript(payload: schemas.TranscriptRequest, auth: dict = Depends(require_tool_auth)):
    assert_grant_incident(auth, payload.incident_id)
    await services.bus.publish(payload.incident_id, {"type": "transcript", **payload.model_dump()})
    return {"ok": True}


@app.post("/api/tools/record-incident-event")
async def record_incident_event(payload: schemas.RecordEventRequest, auth: dict = Depends(require_tool_auth), db: Session = Depends(get_db)):
    assert_grant_incident(auth, payload.incident_id)
    event, duplicate = services.record_event(db, payload)
    contradictions = services.find_for_event(db, event) if not duplicate else []
    await services.bus.publish(payload.incident_id, {"type": "timeline.changed", "event_id": event.id})
    return {"ok": True, "duplicate": duplicate, "event": services.event_dict(event),
            "potential_contradictions": [services.contradiction_dict(x, db) for x in contradictions]}


@app.get("/api/tools/check-service-health")
async def check_service_health(incident_id: str, service: str = Query(min_length=2, max_length=120),
                               auth: dict = Depends(require_tool_auth), db: Session = Depends(get_db)):
    assert_grant_incident(auth, incident_id)
    if not db.get(models.Incident, incident_id): raise HTTPException(404, detail={"code": "incident_not_found"})
    data = services.SIM_STATUS
    evidence = services.add_evidence(db, incident_id, "Incisight Demo Status API", "https://status.incisight.invalid/api/auth", data["message"])
    event, _ = services.record_event(db, schemas.RecordEventRequest(incident_id=incident_id, event_type="observation",
        summary=data["message"], subject="database", claim_value="degraded", source_type="tool", confidence=.99,
        evidence_id=evidence.id, idempotency_key="demo-service-health-v1"))
    contradictions = services.find_for_event(db, event)
    await services.bus.publish(incident_id, {"type": "evidence.changed", "evidence_id": evidence.id})
    return {"ok": True, "simulated": True, "service": service, **data, "evidence_id": evidence.id,
            "potential_contradictions": [services.contradiction_dict(x, db) for x in contradictions]}


@app.get("/api/tools/search-security-advisory")
async def search_security_advisory(incident_id: str, query: str = Query(min_length=2, max_length=160),
                                   auth: dict = Depends(require_tool_auth), db: Session = Depends(get_db)):
    assert_grant_incident(auth, incident_id)
    if not db.get(models.Incident, incident_id): raise HTTPException(404, detail={"code": "incident_not_found"})
    data = services.SIM_ADVISORY
    evidence = services.add_evidence(db, incident_id, "Incisight Advisory Cache", data["source_url"], data["excerpt"])
    await services.bus.publish(incident_id, {"type": "evidence.changed", "evidence_id": evidence.id})
    return {"ok": True, "simulated": True, "query": query, "result": data, "evidence_id": evidence.id}


@app.post("/api/tools/find-contradictions")
async def find_contradictions(payload: schemas.FindContradictionsRequest, auth: dict = Depends(require_tool_auth), db: Session = Depends(get_db)):
    assert_grant_incident(auth, payload.incident_id)
    event = db.get(models.IncidentEvent, payload.claim_event_id)
    if not event or event.incident_id != payload.incident_id: raise HTTPException(404, detail={"code": "event_not_found"})
    rows = services.find_for_event(db, event)
    return {"ok": True, "potential_contradictions": [services.contradiction_dict(x, db) for x in rows]}


@app.patch("/api/contradictions/{contradiction_id}")
async def resolve_contradiction(contradiction_id: str, payload: schemas.ResolveContradictionRequest,
                               db: Session = Depends(get_db)):
    row = db.get(models.Contradiction, contradiction_id)
    if not row: raise HTTPException(404, detail={"code": "contradiction_not_found"})
    row.status = payload.status; row.resolution_note = payload.resolution_note
    db.commit(); await services.bus.publish(row.incident_id, {"type": "contradiction.changed"})
    return services.contradiction_dict(row, db)


@app.post("/api/tools/draft-stakeholder-update")
async def draft_stakeholder_update(payload: schemas.DraftUpdateRequest, auth: dict = Depends(require_tool_auth), db: Session = Depends(get_db)):
    assert_grant_incident(auth, payload.incident_id)
    row = services.draft_update(db, payload.incident_id)
    await services.bus.publish(payload.incident_id, {"type": "update.changed", "update_id": row.id})
    return {"ok": True, "update": services.update_dict(row), "requires_explicit_approval": True}


@app.post("/api/updates/approval-nonce")
def approval_nonce(payload: schemas.ApprovalNonceRequest, db: Session = Depends(get_db)):
    row = db.get(models.StakeholderUpdate, payload.update_id)
    if not row or row.status != "draft": raise HTTPException(409, detail={"code": "draft_not_approvable"})
    return {"approval_nonce": issue_approval_nonce(row.id, payload.approver), "expires_in_seconds": 120}


@app.post("/api/updates/draft")
async def dashboard_draft(payload: schemas.DraftUpdateRequest, db: Session = Depends(get_db)):
    """Dashboard action. Tool-driven drafting uses the authenticated endpoint below."""
    row = services.draft_update(db, payload.incident_id)
    await services.bus.publish(payload.incident_id, {"type": "update.changed", "update_id": row.id})
    return {"ok": True, "update": services.update_dict(row), "requires_explicit_approval": True}


@app.post("/api/updates/publish")
async def dashboard_publish(payload: schemas.ApproveUpdateRequest, db: Session = Depends(get_db)):
    """Human dashboard path: the short-lived nonce is proof of the explicit click."""
    row = db.get(models.StakeholderUpdate, payload.update_id)
    if not row or row.incident_id != payload.incident_id: raise HTTPException(404, detail={"code": "update_not_found"})
    verify_approval_nonce(payload.approval_nonce, row.id, payload.approver)
    row.status = "published"; row.approved_by = payload.approver; row.approved_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(row)
    await services.bus.publish(payload.incident_id, {"type": "update.published", "update_id": row.id})
    return {"ok": True, "simulated_publish": True, "update": services.update_dict(row)}


@app.post("/api/tools/approve-stakeholder-update")
async def approve_stakeholder_update(payload: schemas.ApproveUpdateRequest, auth: dict = Depends(require_tool_auth), db: Session = Depends(get_db)):
    assert_grant_incident(auth, payload.incident_id)
    row = db.get(models.StakeholderUpdate, payload.update_id)
    if not row or row.incident_id != payload.incident_id: raise HTTPException(404, detail={"code": "update_not_found"})
    if row.status == "published": return {"ok": True, "duplicate": True, "update": services.update_dict(row)}
    verify_approval_nonce(payload.approval_nonce, row.id, payload.approver)
    row.status = "published"; row.approved_by = payload.approver; row.approved_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(row)
    await services.bus.publish(payload.incident_id, {"type": "update.published", "update_id": row.id})
    return {"ok": True, "duplicate": False, "simulated_publish": True, "update": services.update_dict(row)}


@app.post("/api/demo/reset")
async def reset_demo(x_admin_secret: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)):
    import hmac
    if not x_admin_secret or not hmac.compare_digest(x_admin_secret, settings.admin_api_secret):
        raise HTTPException(401, detail={"code": "admin_auth_required"})
    row = services.reset_demo(db)
    await services.bus.publish(row.id, {"type": "demo.reset"})
    return services.incident_dict(row)


@app.post("/api/demo/start", status_code=201)
def start_demo(db: Session = Depends(get_db)):
    """Local/demo convenience: create the deterministic scenario without deleting other incidents."""
    incident = services.create_incident(db, schemas.IncidentCreate(title="Customer Login Failure", affected_service="Authentication Service",
        severity="SEV-1", keyterms=["AuthN", "PostgreSQL", "CVE-2026-4107", "connection pool"]))
    services.record_event(db, schemas.RecordEventRequest(incident_id=incident.id, event_type="observation",
        summary="Authentication is failing, but the database appears healthy.", subject="database", claim_value="healthy",
        source_type="user", confidence=.72, idempotency_key="demo-initial-claim"))
    return services.incident_dict(incident)


@app.post("/api/demo/advance")
async def advance_demo(payload: schemas.DemoAdvanceRequest, db: Session = Depends(get_db)):
    """Deterministic demo controls; this endpoint never reaches external systems."""
    if not db.get(models.Incident, payload.incident_id): raise HTTPException(404, detail={"code": "incident_not_found"})
    if payload.action == "assign_action":
        event, duplicate = services.record_event(db, schemas.RecordEventRequest(incident_id=payload.incident_id,
            event_type="action_item", summary="Inspect the authentication database connection pool.", owner="Mia",
            source_type="user", confidence=.98, idempotency_key="demo-mia-connection-pool"))
        await services.bus.publish(payload.incident_id, {"type": "timeline.changed", "event_id": event.id})
        return {"ok": True, "duplicate": duplicate, "event": services.event_dict(event)}
    data = services.SIM_STATUS
    evidence = services.add_evidence(db, payload.incident_id, "Incisight Demo Status API", "https://status.incisight.invalid/api/auth", data["message"])
    event, duplicate = services.record_event(db, schemas.RecordEventRequest(incident_id=payload.incident_id, event_type="observation",
        summary=data["message"], subject="database", claim_value="degraded", source_type="tool", confidence=.99,
        evidence_id=evidence.id, idempotency_key="demo-service-health-v1"))
    contradictions = services.find_for_event(db, event)
    await services.bus.publish(payload.incident_id, {"type": "evidence.changed", "evidence_id": evidence.id})
    return {"ok": True, "duplicate": duplicate, "event": services.event_dict(event),
            "potential_contradictions": [services.contradiction_dict(x, db) for x in contradictions]}
