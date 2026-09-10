from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


IncidentId = Annotated[str, Field(pattern=r"^[0-9a-fA-F-]{36}$")]
ShortText = Annotated[str, Field(min_length=2, max_length=500)]


class IncidentCreate(BaseModel):
    title: Annotated[str, Field(min_length=3, max_length=160)]
    affected_service: Annotated[str, Field(min_length=2, max_length=120)]
    severity: Literal["SEV-1", "SEV-2", "SEV-3"]
    keyterms: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(default_factory=list, max_length=30)


class RecordEventRequest(BaseModel):
    incident_id: IncidentId
    event_type: Literal["observation", "hypothesis", "decision", "action_item", "status_update"]
    summary: ShortText
    subject: Annotated[str | None, Field(max_length=120)] = None
    claim_value: Annotated[str | None, Field(max_length=120)] = None
    source_type: Literal["user", "tool", "agent"] = "user"
    confidence: float = Field(ge=0, le=1)
    owner: Annotated[str | None, Field(max_length=80)] = None
    evidence_id: IncidentId | None = None
    idempotency_key: Annotated[str | None, Field(pattern=r"^[A-Za-z0-9_-]{8,80}$")] = None


class FindContradictionsRequest(BaseModel):
    incident_id: IncidentId
    claim_event_id: IncidentId


class DraftUpdateRequest(BaseModel):
    incident_id: IncidentId


class ApprovalNonceRequest(BaseModel):
    update_id: IncidentId
    approver: Annotated[str, Field(min_length=2, max_length=80)]


class ApproveUpdateRequest(BaseModel):
    incident_id: IncidentId
    update_id: IncidentId
    approver: Annotated[str, Field(min_length=2, max_length=80)]
    approval_nonce: Annotated[str, Field(min_length=20, max_length=1000)]
    confirmed: Literal[True]


class ResolveContradictionRequest(BaseModel):
    status: Literal["resolved", "dismissed"]
    resolution_note: Annotated[str, Field(min_length=3, max_length=500)]


class VoiceTokenRequest(BaseModel):
    incident_id: IncidentId


class TranscriptRequest(BaseModel):
    incident_id: IncidentId
    speaker: Literal["user", "agent"]
    text: Annotated[str, Field(min_length=1, max_length=2000)]
    final: bool = True


class DemoAdvanceRequest(BaseModel):
    incident_id: IncidentId
    action: Literal["health_check", "assign_action"]

