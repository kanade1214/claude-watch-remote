"""SQLite-backed storage for pairing, sessions, requests and history (spec section 9.2)."""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from app.errors import RelayError

PENDING_PAIRING_TTL_SECONDS = 300


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RelayStorage:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS pending_pairings (
                    token_hash TEXT PRIMARY KEY,
                    pc_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS paired_devices (
                    id TEXT PRIMARY KEY,
                    device_name TEXT NOT NULL,
                    public_key TEXT,
                    token_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT,
                    revoked_at TEXT
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    tmux_target TEXT NOT NULL,
                    working_directory TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    risk_level TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    resolved_at TEXT
                );

                CREATE TABLE IF NOT EXISTS actions (
                    id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    message_id TEXT NOT NULL UNIQUE,
                    device_id TEXT,
                    action TEXT NOT NULL,
                    result TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS prompt_history (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    source TEXT NOT NULL,
                    text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    client_request_id TEXT UNIQUE,
                    created_at TEXT NOT NULL
                );
                """
            )

    # -- Pairing ---------------------------------------------------------

    def create_pending_pairing(self, pc_id: str, display_name: str, token: str) -> str:
        created_at = datetime.now(timezone.utc)
        expires_at = created_at + timedelta(seconds=PENDING_PAIRING_TTL_SECONDS)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO pending_pairings (token_hash, pc_id, display_name, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (hash_token(token), pc_id, display_name, created_at.isoformat(), expires_at.isoformat()),
            )
        return expires_at.isoformat()

    def complete_pairing(
        self,
        pairing_token: str,
        device_id: str,
        device_name: str,
        public_key: str,
        device_auth_token: str,
    ) -> None:
        pairing_token_hash = hash_token(pairing_token)
        with self._connect() as conn:
            pending = conn.execute(
                "SELECT * FROM pending_pairings WHERE token_hash = ?", (pairing_token_hash,)
            ).fetchone()
            if pending is None:
                raise RelayError("AUTH_FAILED", "unknown or already used pairing token")
            if pending["expires_at"] < _now():
                conn.execute("DELETE FROM pending_pairings WHERE token_hash = ?", (pairing_token_hash,))
                raise RelayError("REQUEST_EXPIRED", "pairing token expired")

            conn.execute(
                "INSERT INTO paired_devices (id, device_name, public_key, token_hash, created_at, last_seen_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (device_id, device_name, public_key, hash_token(device_auth_token), _now(), _now()),
            )
            conn.execute("DELETE FROM pending_pairings WHERE token_hash = ?", (pairing_token_hash,))

    def authenticate_device(self, token: str) -> Optional[sqlite3.Row]:
        token_hash = hash_token(token)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM paired_devices WHERE token_hash = ? AND revoked_at IS NULL",
                (token_hash,),
            ).fetchone()
            if row is not None:
                conn.execute(
                    "UPDATE paired_devices SET last_seen_at = ? WHERE id = ?", (_now(), row["id"])
                )
            return row

    def revoke_device(self, device_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE paired_devices SET revoked_at = ? WHERE id = ?", (_now(), device_id)
            )

    def list_devices(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM paired_devices").fetchall()

    def has_paired_device(self) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(1) AS n FROM paired_devices WHERE revoked_at IS NULL"
            ).fetchone()
        return bool(row and row["n"])

    # -- Sessions ---------------------------------------------------------

    def upsert_session(self, session_id: str, tmux_target: str, working_directory: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, tmux_target, working_directory, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at
                """,
                (session_id, tmux_target, working_directory, status, _now(), _now()),
            )

    def update_session_status(self, session_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET status = ?, updated_at = ? WHERE id = ?",
                (status, _now(), session_id),
            )

    def list_sessions(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM sessions ORDER BY updated_at DESC").fetchall()

    # -- Requests ---------------------------------------------------------

    def create_request(
        self,
        request_id: str,
        session_id: Optional[str],
        type_: str,
        payload_json: str,
        risk_level: Optional[str],
        expires_at: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO requests (id, session_id, type, payload_json, status, risk_level, created_at, expires_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
                """,
                (request_id, session_id, type_, payload_json, risk_level, _now(), expires_at),
            )

    def get_request(self, request_id: str) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()

    def list_requests(self, status: Optional[str] = None) -> list[sqlite3.Row]:
        with self._connect() as conn:
            if status:
                return conn.execute(
                    "SELECT * FROM requests WHERE status = ? ORDER BY created_at DESC", (status,)
                ).fetchall()
            return conn.execute("SELECT * FROM requests ORDER BY created_at DESC").fetchall()

    def resolve_request(self, request_id: str, new_status: str) -> bool:
        """Conditionally resolve a pending request. Returns True iff this call won the race."""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE requests SET status = ?, resolved_at = ? WHERE id = ? AND status = 'pending'",
                (new_status, _now(), request_id),
            )
            return cursor.rowcount > 0

    def expire_stale_requests(self) -> list[str]:
        with self._connect() as conn:
            now = _now()
            rows = conn.execute(
                "SELECT id FROM requests WHERE status = 'pending' AND expires_at < ?", (now,)
            ).fetchall()
            if rows:
                conn.execute(
                    "UPDATE requests SET status = 'expired', resolved_at = ? WHERE status = 'pending' AND expires_at < ?",
                    (now, now),
                )
            return [row["id"] for row in rows]

    # -- Actions (idempotency, spec 14.3) ---------------------------------

    def get_action_by_message_id(self, message_id: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT result FROM actions WHERE message_id = ?", (message_id,)
            ).fetchone()
        return row["result"] if row is not None else None

    def record_action_if_new(
        self, action_id: str, request_id: str, message_id: str, device_id: Optional[str], action: str, result: str
    ) -> tuple[bool, str]:
        """Insert an action keyed by message_id. Returns (is_new, result_to_return)."""
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT result FROM actions WHERE message_id = ?", (message_id,)
            ).fetchone()
            if existing is not None:
                return False, existing["result"]

            conn.execute(
                "INSERT INTO actions (id, request_id, message_id, device_id, action, result, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (action_id, request_id, message_id, device_id, action, result, _now()),
            )
            return True, result

    # -- Prompt history -----------------------------------------------------

    def add_prompt_history(
        self,
        entry_id: str,
        session_id: Optional[str],
        source: str,
        text: str,
        status: str,
        client_request_id: Optional[str],
        enabled: bool = True,
    ) -> bool:
        """Returns True if this is a newly recorded prompt (False if a duplicate client_request_id)."""
        if not enabled:
            return True
        with self._connect() as conn:
            if client_request_id:
                existing = conn.execute(
                    "SELECT id FROM prompt_history WHERE client_request_id = ?", (client_request_id,)
                ).fetchone()
                if existing is not None:
                    return False
            conn.execute(
                "INSERT INTO prompt_history (id, session_id, source, text, status, client_request_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (entry_id, session_id, source, text, status, client_request_id, _now()),
            )
            return True

    def list_prompt_history(self, session_id: Optional[str] = None) -> list[sqlite3.Row]:
        with self._connect() as conn:
            if session_id:
                return conn.execute(
                    "SELECT * FROM prompt_history WHERE session_id = ? ORDER BY created_at DESC",
                    (session_id,),
                ).fetchall()
            return conn.execute("SELECT * FROM prompt_history ORDER BY created_at DESC").fetchall()
