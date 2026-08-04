#!/usr/bin/env python3
"""Claude Code PermissionRequest hook entry point (spec section 8.1/8.2).

Reads the hook event JSON from stdin, forwards it to the PC relay agent,
waits for a remote decision (Pixel Watch / phone), and prints the Claude
Code hookSpecificOutput JSON to stdout.

NOTE: field names below (tool_name/tool_input/cwd/session_id) are a best
guess at the official PermissionRequest hook schema as of spec-writing time.
Verify against the current Claude Code hooks documentation before relying
on this in production — unknown fields are preserved and forwarded as-is
rather than dropped, so a schema change should degrade gracefully rather
than crash.
"""
from __future__ import annotations

import time

from _common import load_config, log_event, poll_until_resolved, post_json, read_event

FALLBACK_MESSAGE = {
    "local_prompt": "リモート承認が利用できないため、Claude Code側のローカル確認に委ねます。",
    "deny": "リモート承認が利用できないため拒否しました。",
}


def _deny(message: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "deny", "message": message},
        }
    }


def _allow(message: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "allow", "message": message},
        }
    }


def _local_prompt_fallback() -> dict:
    # Emitting no decision lets Claude Code fall through to its own local
    # confirmation UI instead of the remote flow.
    return {}


def _apply_fallback(mode: str) -> dict:
    if mode == "deny":
        return _deny(FALLBACK_MESSAGE["deny"])
    return _local_prompt_fallback()


def main() -> dict:
    event = read_event()
    config = load_config()

    tool_name = event.get("tool_name") or event.get("toolName") or "unknown"
    tool_input = event.get("tool_input") or event.get("toolInput") or {}
    working_directory = event.get("cwd") or event.get("workingDirectory") or ""
    session_id = event.get("session_id") or event.get("sessionId")

    body = {
        "toolName": tool_name,
        "toolInput": tool_input,
        "workingDirectory": working_directory,
        "sessionId": session_id,
        **{k: v for k, v in event.items() if k not in {"tool_name", "tool_input", "cwd", "session_id"}},
    }

    response = post_json(
        f"{config['base_url']}/api/v1/hooks/permission", body, timeout=5
    )
    if response is None:
        log_event("permission_hook_agent_unreachable", tool_name=tool_name)
        return _apply_fallback(config["on_remote_unavailable"])

    request_id = response.get("requestId")
    if not request_id:
        log_event("permission_hook_no_request_id", response=response)
        return _apply_fallback(config["on_remote_unavailable"])

    deadline = time.monotonic() + config["remote_timeout_seconds"]
    resolved = poll_until_resolved(
        config["base_url"], request_id, deadline, config["poll_interval_seconds"]
    )

    if resolved is None:
        log_event("permission_hook_timeout", request_id=request_id)
        return _apply_fallback(config["on_timeout"])

    status = resolved.get("status")
    log_event("permission_hook_resolved", request_id=request_id, status=status)

    if status == "allowed":
        return _allow("Pixel Watch / スマートフォンから承認されました。")
    return _deny(f"リモートで拒否またはタイムアウトしました（status={status}）。")


if __name__ == "__main__":
    import json

    print(json.dumps(main(), ensure_ascii=False))
