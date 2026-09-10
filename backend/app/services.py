import asyncio
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models
from .schemas import IncidentCreate, RecordEventRequest


SIM_STATUS = {
    "service": "Authentication Service",
    "status": "degraded",
    "database_connection_failure_rate": 0.31,
    "threshold": 0.05,
    "message": "Database connection failures exceed the configured threshold.",
}
SIM_ADVISORY = {
    "title": "BW-2026-014: Connection pool exhaustion during token refresh bursts",
    "published_at": "2026-08-29T09:00:00Z",
    "excerpt": "Auth gateways may exhaust database pools when token refresh traffic spikes. Rotate pools and inspect wait time.",
    "source_url": "https://advisories.incisight.invalid/IN-2026-014",
}


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

    async def publish(self, incident_id: str, event: dict) -> None:
        for queue in tuple(self._subscribers[incident_id]):
            await queue.put(event)

    def subscribe(self, incident_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers[incident_id].add(queue)
        return queue

    def unsubscribe(self, incident_id: str, queue: asyncio.Queue) -> None:
        self._subscribers[incident_id].discard(queue)


bus = EventBus()


def iso(value):
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def incident_dict(row: models.Incident) -> dict:
    return {"id": row.id, "title": row.title, "affected_service": row.affected_service, "severity": row.severity,
            "status": row.status, "keyterms": row.keyterms, "started_at": iso(row.started_at), "resolved_at": iso(row.resolved_at)}


def event_dict(row: models.IncidentEvent) -> dict:
    return {"id": row.id, "incident_id": row.incident_id, "event_type": row.event_type, "summary": row.summary,
            "subject": row.subject, "claim_value": row.claim_value, "source_type": row.source_type,
            "confidence": row.confidence, "owner": row.owner, "evidence_id": row.evidence_id, "created_at": iso(row.created_at)}


def evidence_dict(row: models.Evidence) -> dict:
    return {"id": row.id, "source_name": row.source_name, "source_url": row.source_url, "excerpt": row.excerpt,
            "retrieved_at": iso(row.retrieved_at), "is_simulated": row.is_simulated}


def contradiction_dict(row: models.Contradiction, db: Session | None = None) -> dict:
    data = {"id": row.id, "reason": row.reason, "confidence": row.confidence, "status": row.status,
            "resolution_note": row.resolution_note, "earlier_event_id": row.earlier_event_id, "later_event_id": row.later_event_id}
    if db:
        earlier = db.get(models.IncidentEvent, row.earlier_event_id)
        later = db.get(models.IncidentEvent, row.later_event_id)
        data.update({"earlier_statement": earlier.summary if earlier else "", "earlier_at": iso(earlier.created_at) if earlier else None,
                     "later_statement": later.summary if later else "", "later_at": iso(later.created_at) if later else None})
    return data


def update_dict(row: models.StakeholderUpdate) -> dict:
    return {"id": row.id, "content": row.content, "status": row.status, "approved_by": row.approved_by,
            "approved_at": iso(row.approved_at), "created_at": iso(row.created_at)}


def create_incident(db: Session, payload: IncidentCreate) -> models.Incident:
    row = models.Incident(**payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return row


def record_event(db: Session, payload: RecordEventRequest) -> tuple[models.IncidentEvent, bool]:
    if not db.get(models.Incident, payload.incident_id):
        raise HTTPException(404, detail={"code": "incident_not_found"})
    if payload.idempotency_key:
        existing = db.scalar(select(models.IncidentEvent).where(models.IncidentEvent.incident_id == payload.incident_id,
                                                                 models.IncidentEvent.idempotency_key == payload.idempotency_key))
        if existing:
            return existing, True
    row = models.IncidentEvent(**payload.model_dump())
    db.add(row)
    try:
        db.commit(); db.refresh(row)
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(models.IncidentEvent).where(models.IncidentEvent.incident_id == payload.incident_id,
                                                                 models.IncidentEvent.idempotency_key == payload.idempotency_key))
        return existing, True
    return row, False


def normalize_subject(value: str | None) -> str:
    if not value: return ""
    value = re.sub(r"[^a-z0-9 ]", "", value.lower())
    aliases = {"db": "database", "postgres": "database", "auth db": "database"}
    return aliases.get(value.strip(), value.strip())


def values_conflict(a: str | None, b: str | None) -> bool:
    healthy = {"healthy", "unaffected", "normal", "available"}
    unhealthy = {"degraded", "affected", "failing", "unhealthy", "unavailable", "elevated failures"}
    return (str(a).lower() in healthy and str(b).lower() in unhealthy) or (str(b).lower() in healthy and str(a).lower() in unhealthy)


def find_for_event(db: Session, event: models.IncidentEvent) -> list[models.Contradiction]:
    subject = normalize_subject(event.subject)
    if not subject or not event.claim_value:
        return []
    candidates = db.scalars(select(models.IncidentEvent).where(models.IncidentEvent.incident_id == event.incident_id,
        models.IncidentEvent.id != event.id).order_by(models.IncidentEvent.created_at)).all()
    created: list[models.Contradiction] = []
    for earlier in candidates:
        if normalize_subject(earlier.subject) != subject or not values_conflict(earlier.claim_value, event.claim_value):
            continue
        pair = db.scalar(select(models.Contradiction).where(models.Contradiction.earlier_event_id == earlier.id,
                                                             models.Contradiction.later_event_id == event.id))
        if pair: created.append(pair); continue
        row = models.Contradiction(incident_id=event.incident_id, earlier_event_id=earlier.id, later_event_id=event.id,
            reason=f"The statements report incompatible health states for {subject} during the active incident.", confidence=0.93)
        db.add(row); db.commit(); db.refresh(row); created.append(row)
    return created


def add_evidence(db: Session, incident_id: str, name: str, url: str, excerpt: str, simulated: bool = True) -> models.Evidence:
    digest = hashlib.sha256(excerpt.strip().encode()).hexdigest()
    existing = db.scalar(select(models.Evidence).where(models.Evidence.incident_id == incident_id, models.Evidence.content_hash == digest))
    if existing: return existing
    row = models.Evidence(incident_id=incident_id, source_name=name, source_url=url, excerpt=excerpt,
                          content_hash=digest, is_simulated=simulated)
    db.add(row); db.commit(); db.refresh(row); return row


def aggregate(db: Session, incident_id: str) -> dict:
    incident = db.get(models.Incident, incident_id)
    if not incident: raise HTTPException(404, detail={"code": "incident_not_found"})
    events = db.scalars(select(models.IncidentEvent).where(models.IncidentEvent.incident_id == incident_id).order_by(models.IncidentEvent.created_at)).all()
    evidence = db.scalars(select(models.Evidence).where(models.Evidence.incident_id == incident_id).order_by(models.Evidence.retrieved_at.desc())).all()
    contradictions = db.scalars(select(models.Contradiction).where(models.Contradiction.incident_id == incident_id).order_by(models.Contradiction.created_at.desc())).all()
    updates = db.scalars(select(models.StakeholderUpdate).where(models.StakeholderUpdate.incident_id == incident_id).order_by(models.StakeholderUpdate.created_at.desc())).all()
    return {"incident": incident_dict(incident), "timeline": [event_dict(x) for x in events], "evidence": [evidence_dict(x) for x in evidence],
            "contradictions": [contradiction_dict(x, db) for x in contradictions], "updates": [update_dict(x) for x in updates]}


def draft_update(db: Session, incident_id: str) -> models.StakeholderUpdate:
    data = aggregate(db, incident_id); incident = data["incident"]
    events = data["timeline"][-5:]
    verified = [e["summary"] for e in events if e["source_type"] == "tool"]
    actions = [e["summary"] for e in events if e["event_type"] == "action_item"]
    body = (f"{incident['severity']} — {incident['title']}. {incident['affected_service']} remains under investigation. "
            f"Verified: {' '.join(verified) if verified else 'No tool-verified facts yet.'} "
            f"Actions: {' '.join(actions) if actions else 'Incident team is assessing impact.'} "
            "This is a simulated Incisight stakeholder update.")
    row = models.StakeholderUpdate(incident_id=incident_id, content=body)
    db.add(row); db.commit(); db.refresh(row); return row


def reset_demo(db: Session) -> models.Incident:
    for table in (models.Contradiction, models.StakeholderUpdate, models.IncidentEvent, models.Evidence, models.Incident):
        db.query(table).delete()
    db.commit()
    incident = create_incident(db, IncidentCreate(title="Customer Login Failure", affected_service="Authentication Service",
        severity="SEV-1", keyterms=["AuthN", "PostgreSQL", "CVE-2026-4107", "connection pool"]))
    event, _ = record_event(db, RecordEventRequest(incident_id=incident.id, event_type="observation",
        summary="Authentication is failing, but the database appears healthy.", subject="database", claim_value="healthy",
        source_type="user", confidence=.72, idempotency_key="demo-initial-claim"))
    return incident
