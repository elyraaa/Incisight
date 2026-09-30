def test_health(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/ready").status_code == 200

def test_create_and_order_events(client,incident,tool_headers):
    base={"incident_id":incident["id"],"event_type":"observation","source_type":"user","confidence":.8}
    a=client.post("/api/tools/record-incident-event",headers=tool_headers,json={**base,"summary":"Database is healthy.","subject":"database","claim_value":"healthy","idempotency_key":"event-alpha-001"})
    b=client.post("/api/tools/record-incident-event",headers=tool_headers,json={**base,"summary":"Connections are failing.","subject":"database","claim_value":"degraded","idempotency_key":"event-beta-0001"})
    assert a.status_code==200 and b.status_code==200
    assert len(b.json()["potential_contradictions"])==1
    timeline=client.get(f"/api/incidents/{incident['id']}/timeline").json()
    assert [e["summary"] for e in timeline][-2:]==["Database is healthy.","Connections are failing."]

def test_tools_reject_missing_auth(client,incident):
    response=client.post("/api/tools/draft-stakeholder-update",json={"incident_id":incident["id"]})
    assert response.status_code==401

def test_duplicate_event_is_idempotent(client,incident,tool_headers):
    body={"incident_id":incident["id"],"event_type":"decision","summary":"Freeze deploys.","source_type":"user","confidence":1,"idempotency_key":"same-event-0001"}
    assert client.post("/api/tools/record-incident-event",headers=tool_headers,json=body).json()["duplicate"] is False
    assert client.post("/api/tools/record-incident-event",headers=tool_headers,json=body).json()["duplicate"] is True

def test_publish_requires_matching_nonce(client,incident,tool_headers):
    draft=client.post("/api/tools/draft-stakeholder-update",headers=tool_headers,json={"incident_id":incident["id"]}).json()["update"]
    body={"incident_id":incident["id"],"update_id":draft["id"],"approver":"Commander","approval_nonce":"invalid-token-which-is-long-enough","confirmed":True}
    assert client.post("/api/tools/approve-stakeholder-update",headers=tool_headers,json=body).status_code==403
    nonce=client.post("/api/updates/approval-nonce",json={"update_id":draft["id"],"approver":"Commander"}).json()["approval_nonce"]
    body["approval_nonce"]=nonce
    published=client.post("/api/tools/approve-stakeholder-update",headers=tool_headers,json=body)
    assert published.status_code==200 and published.json()["update"]["status"]=="published"

def test_invalid_schema(client,incident,tool_headers):
    response=client.post("/api/tools/record-incident-event",headers=tool_headers,json={"incident_id":incident["id"],"event_type":"remediation","summary":"x","source_type":"user","confidence":2})
    assert response.status_code==422

def test_reviewed_conflict_is_visible_in_incident(client,incident,tool_headers):
    base={"incident_id":incident["id"],"event_type":"observation","source_type":"user","confidence":.8,"subject":"database"}
    client.post("/api/tools/record-incident-event",headers=tool_headers,json={**base,"summary":"Database is healthy.","claim_value":"healthy"})
    second=client.post("/api/tools/record-incident-event",headers=tool_headers,json={**base,"summary":"Database is degraded.","claim_value":"degraded"})
    conflict_id=second.json()["potential_contradictions"][0]["id"]
    reviewed=client.patch(f"/api/contradictions/{conflict_id}",json={"status":"resolved","resolution_note":"Status evidence supersedes the initial report."})
    assert reviewed.status_code==200
    assert reviewed.json()["status"]=="resolved"
    snapshot=client.get(f"/api/incidents/{incident['id']}").json()
    assert snapshot["contradictions"][0]["resolution_note"]=="Status evidence supersedes the initial report."


def test_direct_incident_access_and_cors(client, incident):
    assert client.get(f"/api/incidents/{incident['id']}").status_code == 200
    recorded = client.post("/api/events", json={"incident_id":incident["id"],"event_type":"observation","summary":"Operator report","source_type":"user","confidence":0.7})
    assert recorded.status_code == 200
    preflight = client.options("/api/voice/token", headers={"Origin":"http://localhost:5173", "Access-Control-Request-Method":"POST", "Access-Control-Request-Headers":"content-type"})
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_voice_token_without_login(client, incident, monkeypatch):
    from app import main
    monkeypatch.setattr(main.settings, "assemblyai_api_key", "test-key")
    class ProviderResponse:
        is_error = False
        def json(self): return {"token":"temporary-provider-token"}
    class ProviderClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url, **kwargs):
            assert kwargs["headers"]["Authorization"] == "Bearer test-key"
            return ProviderResponse()
    monkeypatch.setattr(main.httpx, "AsyncClient", ProviderClient)
    issued = client.post("/api/voice/token", json={"incident_id":incident["id"]})
    assert issued.status_code == 200
    grant = issued.json()["tool_grant"]
    context = client.get("/api/tools/incident-context", params={"incident_id":incident["id"]}, headers={"Authorization":f"Bearer {grant}"})
    assert context.status_code == 200 and context.json()["incident"]["id"] == incident["id"]
    other = client.post("/api/incidents",json={"title":"Another incident","affected_service":"API","severity":"SEV-2"}).json()
    denied = client.get("/api/tools/incident-context", params={"incident_id":other["id"]}, headers={"Authorization":f"Bearer {grant}"})
    assert denied.status_code == 403


def test_voice_proposals_remain_unsaved_until_dashboard_confirmation(client, incident, tool_headers):
    preview = client.get("/api/tools/preview-stakeholder-update", params={"incident_id":incident["id"]}, headers=tool_headers)
    assert preview.status_code == 200 and preview.json()["saved"] is False
    assert client.get(f"/api/incidents/{incident['id']}").json()["updates"] == []
    saved = client.post("/api/updates/draft-from-proposal", json={"incident_id":incident["id"],"content":preview.json()["content"]})
    assert saved.status_code == 200 and saved.json()["update"]["status"] == "draft"
    assert client.get(f"/api/incidents/{incident['id']}").json()["updates"][0]["content"] == preview.json()["content"]
