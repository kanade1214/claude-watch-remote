from tests.conftest import pair_device


def test_submit_prompt_via_http_requires_auth(client):
    response = client.post("/api/v1/prompts", json={"text": "テスト"})
    assert response.status_code == 401


def test_submit_prompt_via_http(client, fake_terminal):
    device = pair_device(client)
    response = client.post(
        "/api/v1/prompts",
        json={"text": "テストを実行して"},
        headers={"Authorization": f"Bearer {device['deviceToken']}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    assert fake_terminal.sent_texts == ["テストを実行して"]


def test_submit_prompt_via_http_deduplicates_client_request_id(client, fake_terminal):
    device = pair_device(client)
    headers = {"Authorization": f"Bearer {device['deviceToken']}"}
    body = {"text": "テストを実行して", "clientRequestId": "same-id"}

    first = client.post("/api/v1/prompts", json=body, headers=headers)
    second = client.post("/api/v1/prompts", json=body, headers=headers)

    assert first.json()["status"] == "sent"
    assert second.json()["status"] == "duplicate"
    assert fake_terminal.sent_texts == ["テストを実行して"]


def test_submit_prompt_rejects_oversized_text(client):
    device = pair_device(client)
    response = client.post(
        "/api/v1/prompts",
        json={"text": "a" * 4001},
        headers={"Authorization": f"Bearer {device['deviceToken']}"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "PROMPT_TOO_LONG"


def test_prompt_submit_over_websocket(client, fake_terminal):
    device = pair_device(client)
    with client.websocket_connect(f"/ws/mobile?token={device['deviceToken']}") as ws:
        ws.send_json(
            {
                "type": "prompt.submit",
                "messageId": "p-1",
                "payload": {"text": "音声入力のテスト", "source": "watch_voice"},
            }
        )
        ack = ws.receive_json()
        assert ack["type"] == "action.result"
        assert ack["payload"]["success"] is True

    assert fake_terminal.sent_texts == ["音声入力のテスト"]


def test_heartbeat_over_websocket(client):
    device = pair_device(client)
    with client.websocket_connect(f"/ws/mobile?token={device['deviceToken']}") as ws:
        ws.send_json({"type": "heartbeat", "payload": {}})
        response = ws.receive_json()
        assert response["type"] == "heartbeat"
