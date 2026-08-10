"""Protocol v1 message envelope and payload models (spec section 7)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field

PROTOCOL_VERSION = 1

MessageType = Literal[
    "permission.request",
    "permission.response",
    "question.request",
    "question.response",
    "prompt.submit",
    "assistant.message",
    "action.result",
    "heartbeat",
]

Decision = Literal["allow", "deny", "cancel", "expired"]
RiskLevel = Literal["low", "medium", "high"]
DeviceType = Literal["watch", "phone", "pc"]


def new_id() -> str:
    return uuid.uuid4().hex


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Envelope(BaseModel):
    protocolVersion: int = PROTOCOL_VERSION
    messageId: str = Field(default_factory=new_id)
    type: MessageType
    timestamp: str = Field(default_factory=now_iso)
    pcId: Optional[str] = None
    sessionId: Optional[str] = None
    requestId: Optional[str] = None
    payload: dict = Field(default_factory=dict)


class PermissionRequestPayload(BaseModel):
    toolName: str
    toolInput: dict = Field(default_factory=dict)
    workingDirectory: str
    summary: str
    riskLevel: RiskLevel
    expiresAt: str
    allowAlwaysAvailable: bool = False


class PermissionResponsePayload(BaseModel):
    decision: Decision
    respondedByDeviceType: DeviceType = "phone"


class QuestionChoice(BaseModel):
    id: str
    label: str


class QuestionRequestPayload(BaseModel):
    title: str
    question: str
    responseType: Literal["single_choice", "yes_no", "text"]
    choices: List[QuestionChoice] = Field(default_factory=list)
    allowVoiceInput: bool = True
    expiresAt: str


class QuestionResponsePayload(BaseModel):
    choiceId: Optional[str] = None
    text: Optional[str] = None


class PromptSubmitPayload(BaseModel):
    text: str
    source: Literal["watch_voice", "watch_quick", "phone", "recent"] = "phone"
    clientRequestId: str = Field(default_factory=new_id)


class AssistantMessagePayload(BaseModel):
    """Claude's reply text, pushed out for display only.

    Unlike permission/question requests this is one-way: there is no
    requestId and nothing for the user to resolve. `text` is already
    truncated for a watch-sized screen; `fullLength` keeps the original
    character count so the UI can say how much was cut.
    """

    text: str
    truncated: bool = False
    fullLength: int = 0
    workingDirectory: str = ""


class ActionResultPayload(BaseModel):
    success: bool
    status: str
    message: str


class HeartbeatPayload(BaseModel):
    timestamp: str = Field(default_factory=now_iso)


def envelope_for(
    type: MessageType,
    payload: BaseModel | dict,
    *,
    pc_id: Optional[str] = None,
    session_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Envelope:
    data = payload.model_dump() if isinstance(payload, BaseModel) else payload
    return Envelope(
        type=type,
        payload=data,
        pcId=pc_id,
        sessionId=session_id,
        requestId=request_id,
    )
