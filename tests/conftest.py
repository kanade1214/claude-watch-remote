import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import main  # noqa: E402
from app.storage import RelayStorage  # noqa: E402


class FakeTerminalAdapter:
    def __init__(self, alive: bool = True):
        self.alive = alive
        self.sent_texts: list[str] = []
        self.sent_keys: list[str] = []

    async def is_alive(self) -> bool:
        return self.alive

    async def send_text(self, text: str) -> None:
        from app.terminal import validate_prompt_text

        validate_prompt_text(text)
        if not self.alive:
            from app.errors import RelayError

            raise RelayError("CLAUDE_NOT_RUNNING")
        self.sent_texts.append(text)

    async def send_key(self, key: str) -> None:
        self.sent_keys.append(key)

    async def capture_recent_output(self, lines: int) -> str:
        return ""


@pytest.fixture
def fake_terminal(monkeypatch):
    terminal = FakeTerminalAdapter()
    monkeypatch.setattr(main, "terminal", terminal)
    return terminal


@pytest.fixture
def client(tmp_path, monkeypatch, fake_terminal):
    db_path = tmp_path / "relay.db"
    monkeypatch.setattr(main, "storage", RelayStorage(str(db_path)))
    monkeypatch.setattr(main, "manager", main.ConnectionManager())
    return TestClient(main.app)


def pair_device(client, display_name: str = "Test Phone") -> dict:
    start = client.post("/api/v1/pair/start", json={"displayName": display_name})
    assert start.status_code == 200
    token = start.json()["token"]

    complete = client.post(
        "/api/v1/pair/complete",
        json={"token": token, "deviceName": display_name, "publicKey": "pub"},
    )
    assert complete.status_code == 200
    return complete.json()
