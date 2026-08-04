"""Risk classification for permission requests (spec section 12)."""
from __future__ import annotations

from app.protocol import RiskLevel

HIGH_RISK_COMMAND_MARKERS = (
    "git push",
    "--force",
    "-f ",
    "sudo",
    "rm -rf",
    "rm -r",
    "drop table",
    "drop database",
    "curl ",
    "wget ",
    "| sh",
    "| bash",
    "deploy",
    "kubectl delete",
    "terraform destroy",
)

HIGH_RISK_TOOLS = {"DeployTool", "ProductionShell"}

MEDIUM_RISK_COMMAND_MARKERS = (
    "git commit",
    "npm install",
    "pip install",
    "apt install",
    "apt-get install",
)

MEDIUM_RISK_TOOLS = {"Write", "Edit", "NotebookEdit"}

LOW_RISK_TOOLS = {"Read", "Grep", "Glob", "TodoWrite"}

LOW_RISK_COMMAND_MARKERS = (
    "git status",
    "git log",
    "git diff",
    "ls",
    "dir",
    "pytest",
    "npm test",
)


def classify_risk(tool_name: str, command: str = "") -> RiskLevel:
    lowered_command = command.lower()

    if any(marker in lowered_command for marker in HIGH_RISK_COMMAND_MARKERS):
        return "high"
    if tool_name in HIGH_RISK_TOOLS:
        return "high"

    if any(marker in lowered_command for marker in MEDIUM_RISK_COMMAND_MARKERS):
        return "medium"
    if tool_name in MEDIUM_RISK_TOOLS:
        return "medium"

    if tool_name in LOW_RISK_TOOLS:
        return "low"
    if any(marker in lowered_command for marker in LOW_RISK_COMMAND_MARKERS):
        return "low"

    # Unrecognized Bash command, or unknown tool entirely: fail safe toward
    # the middle, never assume "low".
    return "medium"


def allows_one_tap_watch_approval(risk_level: RiskLevel) -> bool:
    return risk_level == "low"
