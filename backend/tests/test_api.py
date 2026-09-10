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
