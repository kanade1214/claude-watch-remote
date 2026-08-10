from app import main
from tests.conftest import pair_device


def test_assistant_message_is_broadcast_to_connected_device(client):
    device = pair_device(client)
    with client.websocket_connect(f"/ws/mobile?token={device['deviceToken']}") as ws:
        response = client.post(
            "/api/v1/hooks/assistant-message",
            json={"text": "テストは通りました。", "workingDirectory": "/home/kanade/claude-watch-remote"},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "broadcast", "delivered": 1}

        envelope = ws.receive_json()

    assert envelope["type"] == "assistant.message"
    assert envelope["payload"]["text"] == "テストは通りました。"
    assert envelope["payload"]["truncated"] is False
    assert envelope["payload"]["fullLength"] == len("テストは通りました。")
    assert envelope["payload"]["workingDirectory"] == "/home/kanade/claude-watch-remote"


def test_long_assistant_message_is_truncated_for_the_watch(client, monkeypatch):
    monkeypatch.setattr(main, "ASSISTANT_MESSAGE_MAX_CHARS", 10)
    device = pair_device(client)
    with client.websocket_connect(f"/ws/mobile?token={device['deviceToken']}") as ws:
        client.post("/api/v1/hooks/assistant-message", json={"text": "あ" * 42})
        envelope = ws.receive_json()

    assert envelope["payload"]["text"] == "あ" * 10
    assert envelope["payload"]["truncated"] is True
    assert envelope["payload"]["fullLength"] == 42


def test_blank_assistant_message_is_rejected(client):
    response = client.post("/api/v1/hooks/assistant-message", json={"text": "   \n  "})
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_MESSAGE"


def test_assistant_message_creates_no_request_to_resolve(client):
    """It is display-only, so it must not show up as something pending."""
    response = client.post("/api/v1/hooks/assistant-message", json={"text": "完了しました。"})
    assert response.status_code == 200
    assert client.get("/api/v1/requests").json() == []


def test_assistant_message_without_a_paired_device_still_succeeds(client):
    """The hook is fire-and-forget: no watch connected is not an error."""
    response = client.post("/api/v1/hooks/assistant-message", json={"text": "誰も見ていません。"})
    assert response.status_code == 200
    assert response.json()["delivered"] == 0
