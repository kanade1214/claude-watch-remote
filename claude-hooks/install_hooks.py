#!/usr/bin/env python3
"""Register this repo's hook scripts in a Claude Code settings.json.

WARNING: Claude Code's hooks configuration schema may have changed since
this was written (spec section 11, item 11). Confirm the current schema
against the official Claude Code hooks documentation before trusting this
script in a real setup; it merges rather than overwrites existing hooks so
a wrong guess is at least easy to spot and revert.

Usage:
    python install_hooks.py [--settings-path PATH] [--dry-run]

Defaults to ~/.claude/settings.json.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent

HOOK_ENTRIES = {
    "PermissionRequest": HOOKS_DIR / "permission_request.py",
    "Notification": HOOKS_DIR / "notification.py",
    "Stop": HOOKS_DIR / "stop.py",
}


def _hook_command(script_path: Path) -> str:
    return f"python3 {script_path}"


def merge_hooks(settings: dict) -> dict:
    hooks = settings.setdefault("hooks", {})
    for event_name, script_path in HOOK_ENTRIES.items():
        command = _hook_command(script_path)
        entries = hooks.setdefault(event_name, [])
        already_installed = any(
            command in hook.get("command", "")
            for entry in entries
            for hook in entry.get("hooks", [])
        )
        if already_installed:
            continue
        entries.append({"matcher": "*", "hooks": [{"type": "command", "command": command}]})
    return settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--settings-path", default=str(Path.home() / ".claude" / "settings.json")
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings_path = Path(args.settings_path)
    settings = {}
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))

    updated = merge_hooks(settings)

    output = json.dumps(updated, ensure_ascii=False, indent=2)
    if args.dry_run:
        print(output)
        return

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(output, encoding="utf-8")
    print(f"Updated {settings_path}")


if __name__ == "__main__":
    main()
