import hmac
from typing import Annotated

from fastapi import Header, HTTPException
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import get_settings


def _serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().tool_api_secret, salt=salt)


def issue_tool_grant(incident_id: str) -> str:
    return _serializer("tool-grant").dumps({"incident_id": incident_id})


def require_tool_auth(
    authorization: Annotated[str | None, Header()] = None,
    x_tool_secret: Annotated[str | None, Header()] = None,
) -> dict:
    settings = get_settings()
    if x_tool_secret and hmac.compare_digest(x_tool_secret, settings.tool_api_secret):
        return {"kind": "service"}
    if authorization and authorization.startswith("Bearer "):
        try:
            payload = _serializer("tool-grant").loads(authorization[7:], max_age=10800)
            return {"kind": "session", **payload}
        except (BadSignature, SignatureExpired):
            pass
    raise HTTPException(status_code=401, detail={"code": "tool_auth_required", "recovery": "Use a valid tool secret or session grant."})


def assert_grant_incident(auth: dict, incident_id: str) -> None:
    if auth.get("kind") == "session" and auth.get("incident_id") != incident_id:
        raise HTTPException(status_code=403, detail={"code": "incident_scope_mismatch"})


def issue_approval_nonce(update_id: str, approver: str) -> str:
    return _serializer("approval").dumps({"update_id": update_id, "approver": approver})


def verify_approval_nonce(token: str, update_id: str, approver: str) -> None:
    try:
        data = _serializer("approval").loads(token, max_age=120)
    except SignatureExpired as exc:
        raise HTTPException(status_code=403, detail={"code": "approval_nonce_expired"}) from exc
    except BadSignature as exc:
        raise HTTPException(status_code=403, detail={"code": "approval_nonce_invalid"}) from exc
    if data != {"update_id": update_id, "approver": approver}:
        raise HTTPException(status_code=403, detail={"code": "approval_nonce_mismatch"})

