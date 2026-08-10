#!/usr/bin/env python3
"""Claude Code Stop hook entry point — push Claude's reply to the Watch.

Fires once Claude has finished responding. Like the Notification hook this is
fire-and-forget: nothing about Claude Code's execution depends on what this
returns, we only want the reply text to land on the user's wrist.

The Stop event does not carry the reply itself, only a `transcript_path`
pointing at the session's JSONL log, so the text is recovered by walking that
log backwards to the newest assistant turn.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

from _common import load_config, log_event, post_json, read_event

# Transcripts grow for the whole session and this hook runs on every reply,
# so only the tail is read — enough to cover the last turn without the cost
# scaling with session length.
TAIL_BYTES = 1024 * 1024


def _tail_lines(path: Path) -> list[str]:
    with path.open("rb") as f:
        f.seek(0, io.SEEK_END)
        start = max(0, f.tell() - TAIL_BYTES)
        f.seek(start)
        chunk = f.read()

    lines = chunk.decode("utf-8", errors="replace").splitlines()
    if start > 0 and lines:
        lines.pop(0)  # the first line was probably cut mid-JSON
    return lines


def _text_of(entry: dict) -> str:
    """Join the text blocks of one transcript entry's message.

    `content` is normally an Anthropic-style block list; tool_use blocks have
    nothing displayable in them and are dropped. Older/simpler entries store
    a plain string instead.
    """
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
    return ""


def extract_last_assistant_text(transcript_path: str) -> str:
    """Return the text of the newest assistant turn, or "" if there is none.

    Keeps walking back past turns with no text — a turn that only issued tool
    calls has nothing to show — and skips sidechain entries, which are
    subagent output covered by the separate SubagentStop event.
    """
    path = Path(transcript_path)
    if not path.exists():
        return ""

    try:
        lines = _tail_lines(path)
    except OSError as exc:
        log_event("stop_hook_transcript_unreadable", path=str(path), error=str(exc))
        return ""

    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "assistant" or entry.get("isSidechain"):
            continue
        text = _text_of(entry)
        if text:
            return text
    return ""


def main() -> None:
    event = read_event()
    config = load_config()

    transcript_path = event.get("transcript_path") or event.get("transcriptPath") or ""
    text = extract_last_assistant_text(transcript_path) if transcript_path else ""
    if not text:
        log_event("stop_hook_no_assistant_text", transcript_path=transcript_path)
        return

    body = {
        "sessionId": event.get("session_id") or event.get("sessionId"),
        "text": text,
        "workingDirectory": event.get("cwd") or "",
    }
    response = post_json(
        f"{config['base_url']}/api/v1/hooks/assistant-message", body, timeout=5
    )
    if response is None:
        log_event("stop_hook_agent_unreachable")
        return

    log_event("stop_hook_broadcast", delivered=response.get("delivered"), chars=len(text))


if __name__ == "__main__":
    main()
