"""Common error codes (spec section 15)."""
from __future__ import annotations

from typing import Literal

ErrorCode = Literal[
    "AUTH_FAILED",
    "DEVICE_REVOKED",
    "PC_OFFLINE",
    "PHONE_OFFLINE",
    "WATCH_OFFLINE",
    "CLAUDE_NOT_RUNNING",
    "SESSION_NOT_FOUND",
    "REQUEST_NOT_FOUND",
    "REQUEST_EXPIRED",
    "REQUEST_ALREADY_RESOLVED",
    "INVALID_MESSAGE",
    "UNSUPPORTED_PROTOCOL",
    "TERMINAL_BUSY",
    "PROMPT_TOO_LONG",
    "DELIVERY_FAILED",
    "INTERNAL_ERROR",
]

_USER_MESSAGES: dict[str, str] = {
    "AUTH_FAILED": "認証に失敗しました。",
    "DEVICE_REVOKED": "この端末は利用できません。",
    "PC_OFFLINE": "PCが接続されていません。",
    "PHONE_OFFLINE": "スマートフォンが接続されていません。",
    "WATCH_OFFLINE": "Watchが接続されていません。",
    "CLAUDE_NOT_RUNNING": "Claude Codeが起動していません。",
    "SESSION_NOT_FOUND": "セッションが見つかりません。",
    "REQUEST_NOT_FOUND": "要求が見つかりません。",
    "REQUEST_EXPIRED": "この要求は期限切れです。",
    "REQUEST_ALREADY_RESOLVED": "この要求は既に処理済みです。",
    "INVALID_MESSAGE": "不正なメッセージです。",
    "UNSUPPORTED_PROTOCOL": "対応していないプロトコルバージョンです。",
    "TERMINAL_BUSY": "他の操作が実行中です。",
    "PROMPT_TOO_LONG": "入力が長すぎます。",
    "DELIVERY_FAILED": "送信に失敗しました。",
    "INTERNAL_ERROR": "サーバー内部でエラーが発生しました。",
}


class RelayError(Exception):
    def __init__(self, code: ErrorCode, detail: str | None = None):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail or _USER_MESSAGES.get(code, '')}")

    def user_message(self) -> str:
        return _USER_MESSAGES.get(self.code, "エラーが発生しました。")

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.user_message()}
