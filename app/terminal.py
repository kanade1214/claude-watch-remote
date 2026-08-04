"""Terminal adapter abstraction for sending input to Claude Code (spec section 8.3)."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Protocol

from app.errors import RelayError

MAX_PROMPT_LENGTH = 4000


class TerminalAdapter(Protocol):
    async def is_alive(self) -> bool:
        ...

    async def send_text(self, text: str) -> None:
        ...

    async def send_key(self, key: str) -> None:
        ...

    async def capture_recent_output(self, lines: int) -> str:
        ...


def validate_prompt_text(text: str) -> None:
    if len(text) > MAX_PROMPT_LENGTH:
        raise RelayError("PROMPT_TOO_LONG", f"length={len(text)}")
    if "\x00" in text:
        raise RelayError("INVALID_MESSAGE", "NUL byte in prompt text")


class TmuxTerminalAdapter:
    """MVP TerminalAdapter backed by a tmux session/pane.

    Input is written to a temp file and pasted via tmux's buffer mechanism so
    the text is never interpolated into a shell command line.
    """

    def __init__(self, session_name: str, target_pane: str | None = None):
        self.session_name = session_name
        self.target_pane = target_pane or session_name
        self._lock = asyncio.Lock()

    async def is_alive(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "tmux",
                "has-session",
                "-t",
                self.session_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError:
            return False
        returncode = await proc.wait()
        return returncode == 0

    async def send_text(self, text: str) -> None:
        validate_prompt_text(text)

        async with self._lock:
            if not await self.is_alive():
                raise RelayError("CLAUDE_NOT_RUNNING", self.session_name)

            tmp_dir = Path(tempfile.gettempdir())
            tmp_file = tmp_dir / f"claude_remote_input_{self.session_name}.txt"
            tmp_file.write_text(text, encoding="utf-8")

            try:
                await self._run_tmux(
                    "load-buffer", "-b", "claude-remote-input", str(tmp_file)
                )
                await self._run_tmux(
                    "paste-buffer",
                    "-b",
                    "claude-remote-input",
                    "-t",
                    self.target_pane,
                )
                await self._run_tmux("send-keys", "-t", self.target_pane, "Enter")
            finally:
                tmp_file.unlink(missing_ok=True)

    async def send_key(self, key: str) -> None:
        async with self._lock:
            await self._run_tmux("send-keys", "-t", self.target_pane, key)

    async def capture_recent_output(self, lines: int) -> str:
        proc = await asyncio.create_subprocess_exec(
            "tmux",
            "capture-pane",
            "-t",
            self.target_pane,
            "-p",
            "-S",
            f"-{lines}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RelayError("DELIVERY_FAILED", stderr.decode("utf-8", "ignore"))
        return stdout.decode("utf-8", "ignore")

    async def _run_tmux(self, *args: str) -> None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "tmux",
                *args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise RelayError(
                "INTERNAL_ERROR", "tmux command not found; ensure tmux is on PATH"
            ) from exc

        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RelayError("DELIVERY_FAILED", stderr.decode("utf-8", "ignore"))
