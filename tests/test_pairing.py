from tests.conftest import pair_device


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_status_unpaired(client):
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    body = response.json()
    assert body["pairedDeviceCount"] == 0
    assert body["activeConnections"] == 0


def test_pair_start_returns_one_time_token(client):
    response = client.post("/api/v1/pair/start", json={"displayName": "My Phone"})
    assert response.status_code == 200
    body = response.json()
    assert body["displayName"] == "My Phone"
    assert body["token"]
    assert body["websocketUrl"].endswith("/ws/mobile")


def test_pair_complete_registers_device_and_updates_status(client):
    device = pair_device(client, "My Phone")
    assert device["deviceId"].startswith("device-")
    assert device["deviceToken"]

    status = client.get("/api/v1/status").json()
    assert status["pairedDeviceCount"] == 1


def test_pair_complete_rejects_unknown_token(client):
    response = client.post(
        "/api/v1/pair/complete",
        json={"token": "not-a-real-token", "deviceName": "x", "publicKey": ""},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "AUTH_FAILED"


def test_pair_complete_token_is_single_use(client):
    start = client.post("/api/v1/pair/start", json={"displayName": "My Phone"}).json()
    token = start["token"]

    first = client.post(
        "/api/v1/pair/complete",
        json={"token": token, "deviceName": "My Phone", "publicKey": ""},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/pair/complete",
        json={"token": token, "deviceName": "My Phone", "publicKey": ""},
    )
    assert second.status_code == 400
    assert second.json()["code"] == "AUTH_FAILED"
