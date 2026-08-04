"""HTTP request/response bodies for the PC relay server's REST API."""
from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PairStartRequest(BaseModel):
    displayName: str


class PairStartResponse(BaseModel):
    pcId: str
    token: str
    websocketUrl: str
    displayName: str
    expiresAt: str


class PairCompleteRequest(BaseModel):
    token: str
    deviceName: str
    publicKey: str = ""


class PairCompleteResponse(BaseModel):
    deviceId: str
    deviceToken: str


class SessionInfo(BaseModel):
    id: str
    tmuxTarget: str
    workingDirectory: str
    status: str
    updatedAt: str


class RequestInfo(BaseModel):
    id: str
    sessionId: Optional[str]
    type: str
    status: str
    riskLevel: Optional[str]
    createdAt: str
    expiresAt: str


class StatusResponse(BaseModel):
    pcState: str
    pairedDeviceCount: int
    activeConnections: int
    sessions: List[SessionInfo] = Field(default_factory=list)


class PermissionHookEvent(BaseModel):
    """Raw event forwarded by the Claude Code PermissionRequest hook script.

    Unknown fields are preserved (not validated away) so the official hook
    schema can evolve without breaking this endpoint; see spec section 8.1.
    """

    model_config = ConfigDict(extra="allow")

    sessionId: Optional[str] = None
    toolName: str
    toolInput: dict[str, Any] = Field(default_factory=dict)
    workingDirectory: str = ""


class HookDecisionResponse(BaseModel):
    decision: str
    requestId: str
    message: str = ""


class QuestionHookEvent(BaseModel):
    """Raw event forwarded by a Claude Code hook that detects an input-wait
    state (e.g. Notification). Unknown fields are preserved (spec 8.1)."""

    model_config = ConfigDict(extra="allow")

    sessionId: Optional[str] = None
    title: str = "Claudeからの質問"
    question: str
    responseType: str = "text"
    choices: List[dict[str, str]] = Field(default_factory=list)


class PromptSubmitRequest(BaseModel):
    text: str
    source: str = "phone"
    clientRequestId: Optional[str] = None
    sessionId: Optional[str] = None


class SimpleResponse(BaseModel):
    status: str
    message: str
