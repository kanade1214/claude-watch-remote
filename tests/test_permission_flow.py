from datetime import datetime, timedelta, timezone

from app import main
from tests.conftest import pair_device


def test_low_risk_permission_round_trip(client):
    device = pair_device(client)
    with client.websocket_connect(f"/ws/mobile?token={device['deviceToken']}") as ws:
        hook_response = client.post(
            "/api/v1/hooks/permission",
            json={"toolName": "Read", "toolInput": {}, "workingDirectory": "/tmp"},
        )
        request_id = hook_response.json()["requestId"]
        request_envelope = ws.receive_json()
        assert request_envelope["payload"]["riskLevel"] == "low"

        ws.send_json(
            {
                "type": "permission.response",
                "messageId": "msg-1",
                "requestId": request_id,
                "payload": {"decision": "allow", "respondedByDeviceType": "phone"},
            }
        )
        ack = ws.receive_json()
        assert ack["type"] == "action.result"
        assert ack["payload"]["success"] is True

    resolved = client.get(f"/api/v1/requests/{request_id}").json()
    assert resolved["status"] == "allowed"


def test_high_risk_request_rejects_watch_one_tap_allow(client):
    device = pair_device(client)
    with client.websocket_connect(f"/ws/mobile?token={device['deviceToken']}") as ws:
        hook_response = client.post(
            "/api/v1/hooks/permission",
            json={"toolName": "Bash", "toolInput": {"command": "git push --force"}, "workingDirectory": "/tmp"},
        )
        request_id = hook_response.json()["requestId"]
        request_envelope = ws.receive_json()
        assert request_envelope["payload"]["riskLevel"] == "high"

        ws.send_json(
            {
                "type": "permission.response",
                "messageId": "msg-watch",
                "requestId": request_id,
                "payload": {"decision": "allow", "respondedByDeviceType": "watch"},
            }
        )
        rejection = ws.receive_json()
        assert rejection["payload"]["success"] is False
        assert rejection["payload"]["status"] == "INVALID_MESSAGE"

        ws.send_json(
            {
                "type": "permission.response",
                "messageId": "msg-phone",
                "requestId": request_id,
                "payload": {"decision": "allow", "respondedByDeviceType": "phone"},
            }
        )
        ack = ws.receive_json()
        assert ack["payload"]["success"] is True

    resolved = client.get(f"/api/v1/requests/{request_id}").json()
    assert resolved["status"] == "allowed"


def test_duplicate_message_id_is_idempotent(client):
    device = pair_device(client)
    with client.websocket_connect(f"/ws/mobile?token={device['deviceToken']}") as ws:
        hook_response = client.post(
            "/api/v1/hooks/permission",
            json={"toolName": "Read", "toolInput": {}, "workingDirectory": "/tmp"},
        )
        request_id = hook_response.json()["requestId"]
        ws.receive_json()

        message = {
            "type": "permission.response",
            "messageId": "dup-1",
            "requestId": request_id,
            "payload": {"decision": "allow", "respondedByDeviceType": "phone"},
        }
        ws.send_json(message)
        first_ack = ws.receive_json()
        assert first_ack["payload"]["status"] == "accepted"

        ws.send_json(message)
        second_ack = ws.receive_json()
        assert second_ack["payload"] == first_ack["payload"]


def test_expired_request_cannot_be_approved(client):
    device = pair_device(client)
    with client.websocket_connect(f"/ws/mobile?token={device['deviceToken']}") as ws:
        hook_response = client.post(
            "/api/v1/hooks/permission",
            json={"toolName": "Read", "toolInput": {}, "workingDirectory": "/tmp"},
        )
        request_id = hook_response.json()["requestId"]
        ws.receive_json()

        # Force the request into the past without waiting out the real timeout.
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        with main.storage._connect() as conn:
            conn.execute("UPDATE requests SET expires_at = ? WHERE id = ?", (past, request_id))

        ws.send_json(
            {
                "type": "permission.response",
                "messageId": "late-1",
                "requestId": request_id,
                "payload": {"decision": "allow", "respondedByDeviceType": "phone"},
            }
        )
        ack = ws.receive_json()
        assert ack["payload"]["success"] is False
        assert ack["payload"]["status"] == "REQUEST_EXPIRED"

    resolved = client.get(f"/api/v1/requests/{request_id}").json()
    assert resolved["status"] == "expired"


def test_ws_connect_requires_valid_token(client):
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/mobile?token=not-real") as ws:
            ws.receive_json()
