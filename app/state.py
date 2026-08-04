"""Claude Code state tracking (spec section 8.4).

Detection priority: Hook events > tmux process liveness > terminal output
monitoring > silence duration. Terminal-output monitoring is inherently
fragile against Claude Code UI changes, so it is expressed as a pluggable
`OutputWaitDetector` interface rather than baked-in string matching; the MVP
ships a null implementation that never claims to detect anything from raw
output, leaving hook events and tmux liveness as the only trusted signals.
"""
from __future__ import annotations

from typing import Literal, Protocol

ClaudeState = Literal[
    "OFFLINE",
    "STARTING",
    "IDLE",
    "RUNNING",
    "WAITING_PERMISSION",
    "WAITING_QUESTION",
    "ERROR",
]


class OutputWaitDetector(Protocol):
    """Adapter for detecting an input-wait state from raw terminal output.

    Only consulted when Hook events cannot answer the question (spec 5.3).
    """

    async def looks_like_waiting_for_input(self, recent_output: str) -> bool:
        ...


class NullOutputWaitDetector:
    async def looks_like_waiting_for_input(self, recent_output: str) -> bool:
        return False


class ClaudeStateTracker:
    def __init__(self) -> None:
        self._state: ClaudeState = "OFFLINE"

    @property
    def state(self) -> ClaudeState:
        return self._state

    def set_state(self, state: ClaudeState) -> None:
        self._state = state
