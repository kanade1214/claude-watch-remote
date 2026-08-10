import json
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from app.errors import RelayError
from app.protocol import (
    AssistantMessagePayload,
    Envelope,
    HeartbeatPayload,
    PermissionRequestPayload,
    QuestionChoice,
    QuestionRequestPayload,
    envelope_for,
    new_id,
)
from app.risk import classify_risk
from app.schemas import (
    AssistantMessageHookEvent,
    BroadcastResponse,
    HookDecisionResponse,
    PairCompleteRequest,
    PairCompleteResponse,
    PairStartRequest,
    PairStartResponse,
    PermissionHookEvent,
    PromptSubmitRequest,
    QuestionHookEvent,
    RequestInfo,
    SessionInfo,
    SimpleResponse,
    StatusResponse,
)
from app.state import ClaudeStateTracker
from app.storage import RelayStorage
from app.terminal import TmuxTerminalAdapter, validate_prompt_text

DEFAULT_SESSION_ID = "default"
DEFAULT_TMUX_SESSION = os.environ.get("CLAUDE_WATCH_TMUX_SESSION", "claude-remote")
PERMISSION_TIMEOUT_SECONDS = int(os.environ.get("CLAUDE_WATCH_PERMISSION_TIMEOUT", "120"))
ASSISTANT_MESSAGE_MAX_CHARS = int(os.environ.get("CLAUDE_WATCH_MESSAGE_MAX_CHARS", "500"))
PC_ID = os.environ.get("CLAUDE_WATCH_PC_ID") or f"pc-{uuid.uuid4().hex[:8]}"


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[str, WebSocket] = {}
        self.last_seen: dict[str, datetime] = {}

    async def connect(self, device_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections[device_id] = websocket
        self.last_seen[device_id] = datetime.now(timezone.utc)

    def disconnect(self, device_id: str) -> None:
        self.connections.pop(device_id, None)
        self.last_seen.pop(device_id, None)

    def touch(self, device_id: str) -> None:
        self.last_seen[device_id] = datetime.now(timezone.utc)

    async def broadcast(self, envelope: Envelope) -> None:
        for websocket in list(self.connections.values()):
            await websocket.send_json(envelope.model_dump())

    async def send_to(self, device_id: str, envelope: Envelope) -> None:
        websocket = self.connections.get(device_id)
        if websocket is not None:
            await websocket.send_json(envelope.model_dump())

    def count(self) -> int:
        return len(self.connections)


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.ensure_schema()
    storage.upsert_session(
        DEFAULT_SESSION_ID, DEFAULT_TMUX_SESSION, os.getcwd(), status="offline"
    )
    yield


app = FastAPI(
    title="Claude Code Remote Relay",
    description="PC中継サーバー。スマホ／WatchとWebSocketで接続し、Claude Codeへの入力転送を扱います。",
    version="0.2.0",
    lifespan=lifespan,
)

storage = RelayStorage(db_path="data/pairings.db")
manager = ConnectionManager()
terminal = TmuxTerminalAdapter(session_name=DEFAULT_TMUX_SESSION)
state_tracker = ClaudeStateTracker()


def _load_pending_pairing_websocket_base() -> str:
    return os.environ.get("CLAUDE_WATCH_WS_BASE_URL", "ws://127.0.0.1:8000")


async def require_device_token(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail=RelayError("AUTH_FAILED").to_dict())
    token = authorization.split(" ", 1)[1].strip()
    device = storage.authenticate_device(token)
    if device is None:
        raise HTTPException(status_code=401, detail=RelayError("AUTH_FAILED").to_dict())
    return device


@app.exception_handler(RelayError)
async def relay_error_handler(_request: Any, exc: RelayError) -> JSONResponse:
    status_code = 409 if exc.code in ("REQUEST_ALREADY_RESOLVED", "REQUEST_EXPIRED") else 400
    return JSONResponse(status_code=status_code, content=exc.to_dict())


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/v1/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    sessions = [
        SessionInfo(
            id=row["id"],
            tmuxTarget=row["tmux_target"],
            workingDirectory=row["working_directory"],
            status=row["status"],
            updatedAt=row["updated_at"],
        )
        for row in storage.list_sessions()
    ]
    return StatusResponse(
        pcState=state_tracker.state,
        pairedDeviceCount=sum(1 for d in storage.list_devices() if d["revoked_at"] is None),
        activeConnections=manager.count(),
        sessions=sessions,
    )


@app.post("/api/v1/pair/start", response_model=PairStartResponse)
async def pair_start(body: PairStartRequest) -> PairStartResponse:
    token = secrets.token_urlsafe(24)
    expires_at = storage.create_pending_pairing(PC_ID, body.displayName, token)
    return PairStartResponse(
        pcId=PC_ID,
        token=token,
        websocketUrl=f"{_load_pending_pairing_websocket_base()}/ws/mobile",
        displayName=body.displayName,
        expiresAt=expires_at,
    )


@app.post("/api/v1/pair/complete", response_model=PairCompleteResponse)
async def pair_complete(body: PairCompleteRequest) -> PairCompleteResponse:
    device_id = f"device-{uuid.uuid4().hex[:12]}"
    device_token = secrets.token_urlsafe(32)
    storage.complete_pairing(
        pairing_token=body.token,
        device_id=device_id,
        device_name=body.deviceName,
        public_key=body.publicKey,
        device_auth_token=device_token,
    )
    return PairCompleteResponse(deviceId=device_id, deviceToken=device_token)


@app.get("/api/v1/sessions")
async def list_sessions() -> list[SessionInfo]:
    return [
        SessionInfo(
            id=row["id"],
            tmuxTarget=row["tmux_target"],
            workingDirectory=row["working_directory"],
            status=row["status"],
            updatedAt=row["updated_at"],
        )
        for row in storage.list_sessions()
    ]


@app.get("/api/v1/requests")
async def list_requests(status: Optional[str] = None) -> list[RequestInfo]:
    return [
        RequestInfo(
            id=row["id"],
            sessionId=row["session_id"],
            type=row["type"],
            status=row["status"],
            riskLevel=row["risk_level"],
            createdAt=row["created_at"],
            expiresAt=row["expires_at"],
        )
        for row in storage.list_requests(status=status)
    ]


@app.get("/api/v1/requests/{request_id}")
async def get_request(request_id: str) -> RequestInfo:
    row = _get_request_with_lazy_expiry(request_id)
    return RequestInfo(
        id=row["id"],
        sessionId=row["session_id"],
        type=row["type"],
        status=row["status"],
        riskLevel=row["risk_level"],
        createdAt=row["created_at"],
        expiresAt=row["expires_at"],
    )


def _get_request_with_lazy_expiry(request_id: str):
    row = storage.get_request(request_id)
    if row is None:
        raise RelayError("REQUEST_NOT_FOUND", request_id)
    if row["status"] == "pending" and row["expires_at"] < datetime.now(timezone.utc).isoformat():
        storage.resolve_request(request_id, "expired")
        row = storage.get_request(request_id)
    return row


@app.post("/api/v1/hooks/permission", response_model=HookDecisionResponse)
async def hook_permission_request(event: PermissionHookEvent) -> HookDecisionResponse:
    """Called by the local PermissionRequest hook script (spec 8.1).

    Creates the request and notifies connected devices, then returns
    immediately with status "pending" — the hook script polls
    GET /api/v1/requests/{id} until it resolves or its own timeout elapses.
    """
    command = str(event.toolInput.get("command", ""))
    risk_level = classify_risk(event.toolName, command)
    request_id = f"request-{uuid.uuid4().hex[:12]}"
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=PERMISSION_TIMEOUT_SECONDS)).isoformat()

    payload = PermissionRequestPayload(
        toolName=event.toolName,
        toolInput=event.toolInput,
        workingDirectory=event.workingDirectory,
        summary=f"{event.toolName} の実行を要求しています",
        riskLevel=risk_level,
        expiresAt=expires_at,
        allowAlwaysAvailable=False,
    )
    storage.create_request(
        request_id,
        event.sessionId or DEFAULT_SESSION_ID,
        "permission.request",
        payload.model_dump_json(),
        risk_level,
        expires_at,
    )
    state_tracker.set_state("WAITING_PERMISSION")

    envelope = envelope_for(
        "permission.request",
        payload,
        pc_id=PC_ID,
        session_id=event.sessionId or DEFAULT_SESSION_ID,
        request_id=request_id,
    )
    await manager.broadcast(envelope)

    return HookDecisionResponse(decision="pending", requestId=request_id, message="polling required")


@app.post("/api/v1/hooks/question", response_model=HookDecisionResponse)
async def hook_question_request(event: QuestionHookEvent) -> HookDecisionResponse:
    """Called by a hook (or output-wait detector) that finds Claude Code
    waiting on an answer (spec 5.3 / 8.1). Same pending+poll shape as
    /api/v1/hooks/permission."""
    request_id = f"request-{uuid.uuid4().hex[:12]}"
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=PERMISSION_TIMEOUT_SECONDS)).isoformat()

    payload = QuestionRequestPayload(
        title=event.title,
        question=event.question,
        responseType=event.responseType,
        choices=[QuestionChoice(**c) for c in event.choices],
        expiresAt=expires_at,
    )
    storage.create_request(
        request_id,
        event.sessionId or DEFAULT_SESSION_ID,
        "question.request",
        payload.model_dump_json(),
        risk_level=None,
        expires_at=expires_at,
    )
    state_tracker.set_state("WAITING_QUESTION")

    envelope = envelope_for(
        "question.request",
        payload,
        pc_id=PC_ID,
        session_id=event.sessionId or DEFAULT_SESSION_ID,
        request_id=request_id,
    )
    await manager.broadcast(envelope)

    return HookDecisionResponse(decision="pending", requestId=request_id, message="polling required")


@app.post("/api/v1/hooks/assistant-message", response_model=BroadcastResponse)
async def hook_assistant_message(event: AssistantMessageHookEvent) -> BroadcastResponse:
    """Called by the local Stop hook script once Claude finishes replying.

    Display-only, so this is the one hook endpoint that creates no row in
    `requests`: there is no decision to wait for and nothing to expire, and
    the hook script does not poll afterwards. Claude has stopped talking by
    definition here, hence the IDLE state transition.
    """
    text = event.text.strip()
    if not text:
        raise RelayError("INVALID_MESSAGE", "text is empty")

    payload = AssistantMessagePayload(
        text=text[:ASSISTANT_MESSAGE_MAX_CHARS],
        truncated=len(text) > ASSISTANT_MESSAGE_MAX_CHARS,
        fullLength=len(text),
        workingDirectory=event.workingDirectory,
    )
    state_tracker.set_state("IDLE")

    await manager.broadcast(
        envelope_for(
            "assistant.message",
            payload,
            pc_id=PC_ID,
            session_id=event.sessionId or DEFAULT_SESSION_ID,
        )
    )
    return BroadcastResponse(status="broadcast", delivered=manager.count())


@app.post("/api/v1/prompts", response_model=SimpleResponse)
async def submit_prompt(body: PromptSubmitRequest, device=Depends(require_device_token)) -> SimpleResponse:
    return await _handle_prompt_submit(body, device_id=device["id"])


async def _handle_prompt_submit(body: PromptSubmitRequest, device_id: Optional[str]) -> SimpleResponse:
    validate_prompt_text(body.text)
    entry_id = f"prompt-{uuid.uuid4().hex[:12]}"
    is_new = storage.add_prompt_history(
        entry_id,
        body.sessionId or DEFAULT_SESSION_ID,
        body.source,
        body.text,
        status="sent",
        client_request_id=body.clientRequestId,
    )
    if not is_new:
        return SimpleResponse(status="duplicate", message="この入力は既に処理済みです。")

    await terminal.send_text(body.text)
    state_tracker.set_state("RUNNING")
    return SimpleResponse(status="sent", message="Claude Codeへ送信しました。")


@app.websocket("/ws/mobile")
async def websocket_mobile(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token") or ""
    device = storage.authenticate_device(token) if token else None
    if device is None:
        await websocket.close(code=4401)
        return

    device_id = device["id"]
    await manager.connect(device_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await _handle_ws_message(device_id, data)
    except WebSocketDisconnect:
        manager.disconnect(device_id)


async def _handle_ws_message(device_id: str, data: dict) -> None:
    msg_type = data.get("type")
    message_id = data.get("messageId") or new_id()
    payload = data.get("payload", {})
    request_id = data.get("requestId")

    if msg_type == "heartbeat":
        manager.touch(device_id)
        await manager.send_to(device_id, envelope_for("heartbeat", HeartbeatPayload(), pc_id=PC_ID))
        return

    if msg_type == "permission.response":
        await _handle_permission_response(device_id, message_id, request_id, payload)
        return

    if msg_type == "question.response":
        await _handle_question_response(device_id, message_id, request_id, payload)
        return

    if msg_type == "prompt.submit":
        try:
            result = await _handle_prompt_submit(
                PromptSubmitRequest(
                    text=payload.get("text", ""),
                    source=payload.get("source", "watch_voice"),
                    clientRequestId=payload.get("clientRequestId"),
                    sessionId=data.get("sessionId"),
                ),
                device_id=device_id,
            )
            await manager.send_to(
                device_id,
                envelope_for(
                    "action.result",
                    {"success": result.status != "error", "status": result.status, "message": result.message},
                    pc_id=PC_ID,
                    request_id=request_id,
                ),
            )
        except RelayError as exc:
            await manager.send_to(
                device_id,
                envelope_for(
                    "action.result",
                    {"success": False, "status": exc.code, "message": exc.user_message()},
                    pc_id=PC_ID,
                    request_id=request_id,
                ),
            )
        return

    await manager.send_to(
        device_id,
        envelope_for(
            "action.result",
            {"success": False, "status": "INVALID_MESSAGE", "message": f"unsupported type: {msg_type}"},
            pc_id=PC_ID,
            request_id=request_id,
        ),
    )


async def _handle_permission_response(device_id: str, message_id: str, request_id: Optional[str], payload: dict) -> None:
    if not request_id:
        await _reply_action_result(device_id, request_id, False, "INVALID_MESSAGE", "requestId is required")
        return

    cached = _replay_cached_action(request_id, message_id)
    if cached is not None:
        await _reply_action_result(device_id, request_id, **cached)
        return

    row = _get_request_with_lazy_expiry(request_id)
    if row["status"] != "pending":
        code = "REQUEST_EXPIRED" if row["status"] == "expired" else "REQUEST_ALREADY_RESOLVED"
        await _finish_action(
            device_id, request_id, message_id, success=False, status=code, message=RelayError(code).user_message()
        )
        return

    decision = payload.get("decision")
    responded_by = payload.get("respondedByDeviceType", "phone")

    if decision == "allow" and row["risk_level"] == "high" and responded_by == "watch":
        await _finish_action(
            device_id,
            request_id,
            message_id,
            success=False,
            status="INVALID_MESSAGE",
            message="高危険度の要求はスマートフォンまたはPCで承認してください。",
        )
        return

    new_status = {"allow": "allowed", "deny": "denied", "cancel": "cancelled"}.get(decision, "denied")
    resolved = storage.resolve_request(request_id, new_status)
    if not resolved:
        await _finish_action(
            device_id,
            request_id,
            message_id,
            success=False,
            status="REQUEST_ALREADY_RESOLVED",
            message="既に処理済みの要求です。",
        )
        return

    state_tracker.set_state("RUNNING" if decision == "allow" else "IDLE")
    await _finish_action(
        device_id, request_id, message_id, success=True, status="accepted", message="Claude Codeへ回答を送信しました。"
    )


def _resolve_answer_text(row, payload: dict) -> str:
    """A question.response carries either free text or a choiceId; unlike a
    permission decision, the answer has to actually reach Claude's stdin, so
    resolve a choiceId back to its label using the original request payload."""
    text = payload.get("text")
    if text:
        return text

    choice_id = payload.get("choiceId")
    if choice_id:
        stored_payload = json.loads(row["payload_json"])
        for choice in stored_payload.get("choices", []):
            if choice.get("id") == choice_id:
                return choice.get("label", choice_id)
        return choice_id

    return ""


async def _handle_question_response(device_id: str, message_id: str, request_id: Optional[str], payload: dict) -> None:
    if not request_id:
        await _reply_action_result(device_id, request_id, False, "INVALID_MESSAGE", "requestId is required")
        return

    cached = _replay_cached_action(request_id, message_id)
    if cached is not None:
        await _reply_action_result(device_id, request_id, **cached)
        return

    row = _get_request_with_lazy_expiry(request_id)
    if row["status"] != "pending":
        code = "REQUEST_EXPIRED" if row["status"] == "expired" else "REQUEST_ALREADY_RESOLVED"
        await _finish_action(
            device_id, request_id, message_id, success=False, status=code, message=RelayError(code).user_message()
        )
        return

    answer_text = _resolve_answer_text(row, payload)
    if not answer_text:
        await _finish_action(
            device_id,
            request_id,
            message_id,
            success=False,
            status="INVALID_MESSAGE",
            message="text or choiceId is required",
        )
        return

    resolved = storage.resolve_request(request_id, "answered")
    if not resolved:
        await _finish_action(
            device_id,
            request_id,
            message_id,
            success=False,
            status="REQUEST_ALREADY_RESOLVED",
            message="既に処理済みの要求です。",
        )
        return

    try:
        await terminal.send_text(answer_text)
    except RelayError as exc:
        await _finish_action(device_id, request_id, message_id, success=False, status=exc.code, message=exc.user_message())
        return

    state_tracker.set_state("RUNNING")
    await _finish_action(
        device_id, request_id, message_id, success=True, status="accepted", message="Claude Codeへ回答を送信しました。"
    )


def _replay_cached_action(request_id: str, message_id: str) -> Optional[dict]:
    """If this exact messageId was already processed, return its original
    ack payload so retransmits get byte-for-byte the same response (spec 14.3)."""
    cached = storage.get_action_by_message_id(message_id)
    if cached is None:
        return None
    return json.loads(cached)


async def _finish_action(
    device_id: str, request_id: Optional[str], message_id: str, *, success: bool, status: str, message: str
) -> None:
    action_id = f"action-{uuid.uuid4().hex[:12]}"
    result_json = json.dumps({"success": success, "status": status, "message": message})
    is_new, cached_result = storage.record_action_if_new(
        action_id, request_id, message_id, device_id, status, result_json
    )
    final = json.loads(cached_result) if not is_new else {"success": success, "status": status, "message": message}
    await _reply_action_result(device_id, request_id, **final)


async def _reply_action_result(device_id: str, request_id: Optional[str], success: bool, status: str, message: str) -> None:
    await manager.send_to(
        device_id,
        envelope_for(
            "action.result",
            {"success": success, "status": status, "message": message},
            pc_id=PC_ID,
            request_id=request_id,
        ),
    )
