"""Shared helpers for Claude Code hook scripts.

Deliberately stdlib-only (urllib, json) so the hooks run with whatever
interpreter Claude Code invokes them with, without requiring the PC agent's
virtualenv to be active.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

DEFAULT_CONFIG = {
    "base_url": "http://127.0.0.1:8000",
    "remote_timeout_seconds": 120,
    "on_remote_unavailable": "local_prompt",
    "on_timeout": "deny",
    "poll_interval_seconds": 1.0,
}

VALID_FALLBACKS = {"local_prompt", "deny"}


def load_config() -> dict:
    config = dict(DEFAULT_CONFIG)
    config_path = os.environ.get(
        "CLAUDE_WATCH_HOOK_CONFIG", str(Path(__file__).parent / "config.yaml")
    )
    path = Path(config_path)
    if path.exists():
        try:
            import yaml  # optional dependency; fall back to defaults if missing

            with path.open("r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            permission_cfg = loaded.get("permission", {})
            config.update({k: v for k, v in permission_cfg.items() if k in DEFAULT_CONFIG})
        except ImportError:
            log_event("config_load_skipped_no_yaml", path=str(path))

    if config["on_remote_unavailable"] not in VALID_FALLBACKS:
        config["on_remote_unavailable"] = "local_prompt"
    if config["on_timeout"] not in VALID_FALLBACKS:
        config["on_timeout"] = "deny"
    return config


def read_event() -> dict[str, Any]:
    raw = sys.stdin.read()
    try:
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        log_event("invalid_hook_input_json")
        return {}


def post_json(url: str, body: dict, timeout: float) -> Optional[dict]:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return None


def get_json(url: str, timeout: float) -> Optional[dict]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return None


def poll_until_resolved(base_url: str, request_id: str, deadline: float, poll_interval: float) -> Optional[dict]:
    while time.monotonic() < deadline:
        result = get_json(f"{base_url}/api/v1/requests/{request_id}", timeout=5)
        if result is not None and result.get("status") != "pending":
            return result
        time.sleep(poll_interval)
    return None


def log_event(event: str, **fields: Any) -> None:
    """Emit a structured log line to stderr so Claude Code's own stdout stays clean."""
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), file=sys.stderr)
