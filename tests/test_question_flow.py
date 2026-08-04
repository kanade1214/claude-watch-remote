from tests.conftest import pair_device


def test_question_choice_answer_is_typed_into_terminal(client, fake_terminal):
    device = pair_device(client)
    with client.websocket_connect(f"/ws/mobile?token={device['deviceToken']}") as ws:
        hook_response = client.post(
            "/api/v1/hooks/question",
            json={
                "question": "通信方式を選択",
                "responseType": "single_choice",
                "choices": [{"id": "websocket", "label": "WebSocket"}, {"id": "polling", "label": "HTTPポーリング"}],
            },
        )
        assert hook_response.status_code == 200
        request_id = hook_response.json()["requestId"]

        envelope = ws.receive_json()
        assert envelope["type"] == "question.request"
        assert envelope["requestId"] == request_id

        ws.send_json(
            {
                "type": "question.response",
                "messageId": "q-msg-1",
                "requestId": request_id,
                "payload": {"choiceId": "websocket"},
            }
        )
        ack = ws.receive_json()
        assert ack["payload"]["success"] is True

    assert fake_terminal.sent_texts == ["WebSocket"]

    resolved = client.get(f"/api/v1/requests/{request_id}").json()
    assert resolved["status"] == "answered"


def test_question_free_text_answer(client, fake_terminal):
    device = pair_device(client)
    with client.websocket_connect(f"/ws/mobile?token={device['deviceToken']}") as ws:
        hook_response = client.post(
            "/api/v1/hooks/question",
            json={"question": "続行しますか？", "responseType": "yes_no", "choices": []},
        )
        request_id = hook_response.json()["requestId"]
        ws.receive_json()

        ws.send_json(
            {
                "type": "question.response",
                "messageId": "q-msg-2",
                "requestId": request_id,
                "payload": {"text": "はい、続けてください"},
            }
        )
        ack = ws.receive_json()
        assert ack["payload"]["success"] is True

    assert fake_terminal.sent_texts == ["はい、続けてください"]
