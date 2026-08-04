#!/usr/bin/env python3
"""Claude Code Notification hook entry point (spec section 5.3 / 8.1).

Unlike PermissionRequest, a Notification/input-wait event does not gate
Claude Code's execution through the hook's return value — Claude is already
blocked on its own stdin by the time this fires. So this hook is
fire-and-forget: it registers a question.request with the PC agent (which
broadcasts it to the Watch/phone) and exits immediately. The eventual answer
reaches Claude Code through the normal terminal-input path (the PC agent
types it into the tmux pane), not through this hook's output.
"""
from __future__ import annotations

from _common import load_config, log_event, post_json, read_event


def main() -> None:
    event = read_event()
    config = load_config()

    message = event.get("message") or event.get("notification") or ""
    session_id = event.get("session_id") or event.get("sessionId")

    if not message:
        log_event("notification_hook_no_message", event_keys=list(event.keys()))
        return

    body = {
        "sessionId": session_id,
        "title": "Claudeからの通知",
        "question": message,
        "responseType": "text",
        "choices": [],
    }
    response = post_json(f"{config['base_url']}/api/v1/hooks/question", body, timeout=5)
    if response is None:
        log_event("notification_hook_agent_unreachable")
        return

    log_event("notification_hook_registered", request_id=response.get("requestId"))


if __name__ == "__main__":
    main()
