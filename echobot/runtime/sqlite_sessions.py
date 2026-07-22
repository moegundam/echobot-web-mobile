from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator
from urllib.parse import quote

from .sessions import (
    ChatSession,
    SessionInfo,
    _read_metadata,
    _now_text,
    message_from_dict,
    message_to_dict,
    normalize_session_name,
)


class SQLiteSessionStore:
    """Transactional SQLite implementation of the synchronous session API."""

    def __init__(
        self,
        db_path: str | Path = ".echobot/sessions.sqlite3",
        *,
        busy_timeout_ms: int = 5_000,
    ) -> None:
        self.db_path = Path(db_path)
        self.base_dir = self.db_path.parent
        self.index_file = self.db_path
        self._lock = threading.RLock()
        self._closed = False
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            isolation_level=None,
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute(
            f"PRAGMA busy_timeout = {max(int(busy_timeout_ms), 1)}"
        )
        self._create_schema()

    @classmethod
    def open_readonly(
        cls,
        db_path: str | Path,
        *,
        busy_timeout_ms: int = 5_000,
    ) -> "SQLiteSessionStore":
        """Open an existing repository without changing schema or journal mode."""
        path = Path(db_path).expanduser().resolve()
        instance = cls.__new__(cls)
        instance.db_path = path
        instance.base_dir = path.parent
        instance.index_file = path
        instance._lock = threading.RLock()
        instance._closed = False
        uri = f"file:{quote(path.as_posix(), safe='/')}?mode=ro"
        instance.connection = sqlite3.connect(
            uri,
            uri=True,
            check_same_thread=False,
            isolation_level=None,
        )
        instance.connection.row_factory = sqlite3.Row
        instance.connection.execute("PRAGMA query_only = ON")
        instance.connection.execute(
            f"PRAGMA busy_timeout = {max(int(busy_timeout_ms), 1)}"
        )
        instance._validate_schema()
        return instance

    def close(self) -> None:
        """Close the SQLite connection; repeated calls are safe."""
        with self._lock:
            if self._closed:
                return
            self.connection.close()
            self._closed = True

    def __enter__(self) -> "SQLiteSessionStore":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def _create_schema(self) -> None:
        with self._lock:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    name TEXT PRIMARY KEY,
                    updated_at TEXT NOT NULL,
                    compressed_summary TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS messages (
                    session_name TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    message_json TEXT NOT NULL,
                    PRIMARY KEY (session_name, position),
                    FOREIGN KEY (session_name) REFERENCES sessions(name)
                        ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS current_pointer (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    current_name TEXT,
                    revision INTEGER NOT NULL
                );
                """
            )

    def _validate_schema(self) -> None:
        required = {"sessions", "messages", "current_pointer"}
        rows = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        available = {str(row["name"]) for row in rows}
        missing = sorted(required - available)
        if missing:
            self.close()
            raise ValueError(
                "SQLite session source is missing required tables: "
                + ", ".join(missing)
            )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run low-level operations in one immediate transaction."""
        with self._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                yield self.connection
            except BaseException:
                self.connection.rollback()
                raise
            else:
                self.connection.commit()

    def load_current_session(self) -> ChatSession:
        with self._lock:
            current_name, current_revision = self._current_pointer_locked()
            if current_name and self._session_exists_locked(current_name):
                return self.load_session(current_name)
            if current_name:
                with self._transaction_locked():
                    pointer_name, pointer_revision = self._current_pointer_locked()
                    if (
                        pointer_name == current_name
                        and pointer_revision == current_revision
                    ):
                        self.connection.execute(
                            "DELETE FROM current_pointer WHERE singleton = 1"
                        )

            remaining = self.list_sessions()
            if remaining:
                replacement = self.load_session(remaining[0].name)
                self.set_current_session(replacement.name)
                return replacement
            default_session = self.load_or_create_session("default")
            self.set_current_session(default_session.name)
            return default_session

    def load_or_create_session(self, name: str) -> ChatSession:
        normalized_name = normalize_session_name(name)
        with self._lock:
            if self._session_exists_locked(normalized_name):
                return self.load_session(normalized_name)
            session = self._new_session(normalized_name)
            with self._transaction_locked():
                self._write_session_locked(session, touch=False)
            return session

    def create_session(self, name: str | None = None) -> ChatSession:
        with self._lock:
            session_name = normalize_session_name(name) if name else self._generate_session_name()
            if self._session_exists_locked(session_name):
                raise ValueError(f"Session already exists: {session_name}")
            session = self._new_session(session_name)
            with self._transaction_locked():
                self._write_session_locked(session, touch=False)
                current_name, revision = self._current_pointer_locked()
                self._set_current_locked(session.name, revision + 1)
            return session

    def load_session(self, name: str) -> ChatSession:
        normalized_name = normalize_session_name(name)
        with self._lock:
            if self.connection.in_transaction:
                return self._load_session_locked(normalized_name)
            with self._read_transaction_locked():
                return self._load_session_locked(normalized_name)

    def save_session(self, session: ChatSession) -> None:
        with self._lock:
            session.name = normalize_session_name(session.name)
            with self._transaction_locked():
                self._write_session_locked(session, touch=True)

    def delete_session(self, name: str) -> None:
        normalized_name = normalize_session_name(name)
        with self._lock:
            with self._transaction_locked():
                self.connection.execute(
                    "DELETE FROM sessions WHERE name = ?",
                    (normalized_name,),
                )

    def rename_session(self, old_name: str, new_name: str) -> ChatSession:
        normalized_old_name = normalize_session_name(old_name)
        normalized_new_name = normalize_session_name(new_name)
        with self._lock:
            session = self.load_session(normalized_old_name)
            if normalized_old_name == normalized_new_name:
                return session
            if self._session_exists_locked(normalized_new_name):
                raise ValueError(f"Session already exists: {normalized_new_name}")
            current_name, revision = self._current_pointer_locked()
            session.name = normalized_new_name
            with self._transaction_locked():
                self.connection.execute(
                    "DELETE FROM sessions WHERE name = ?",
                    (normalized_old_name,),
                )
                self._write_session_locked(session, touch=True)
                if current_name == normalized_old_name:
                    self._set_current_locked(normalized_new_name, revision + 1)
            return session

    def set_current_session(self, name: str) -> None:
        normalized_name = normalize_session_name(name)
        with self._lock:
            _, revision = self._current_pointer_locked()
            with self._transaction_locked():
                self._set_current_locked(normalized_name, revision + 1)

    def compare_and_set_current_session(
        self,
        expected_name: str,
        next_name: str | None,
        *,
        expected_revision: int | None = None,
    ) -> bool:
        expected = normalize_session_name(expected_name)
        with self._lock:
            with self._transaction_locked():
                current_name, current_revision = self._current_pointer_locked()
                if current_name != expected:
                    return False
                if expected_revision is not None and current_revision != expected_revision:
                    return False
                if next_name is None:
                    self.connection.execute("DELETE FROM current_pointer WHERE singleton = 1")
                    return True
                normalized_next = normalize_session_name(next_name)
                if not self._session_exists_locked(normalized_next):
                    raise ValueError(f"Session not found: {normalized_next}")
                self._set_current_locked(normalized_next, current_revision + 1)
                return True

    def repair_current_session_after_deletion(
        self,
        deleted_name: str,
    ) -> ChatSession | None:
        normalized_deleted = normalize_session_name(deleted_name)
        with self._lock:
            if self.get_current_session_name() != normalized_deleted:
                return None
            remaining = self.list_sessions()
            if remaining:
                replacement = self.load_session(remaining[0].name)
            else:
                replacement = self.load_or_create_session("default")
            self.set_current_session(replacement.name)
            return replacement

    def get_current_session_name(self) -> str | None:
        return self.get_current_session_pointer()[0]

    def get_current_session_pointer(self) -> tuple[str | None, int]:
        with self._lock:
            return self._current_pointer_locked()

    def list_sessions(self) -> list[SessionInfo]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT s.name, s.updated_at, s.metadata_json, "
                "(SELECT COUNT(*) FROM messages m WHERE m.session_name = s.name) AS message_count "
                "FROM sessions s ORDER BY s.updated_at DESC"
            ).fetchall()
            result: list[SessionInfo] = []
            for row in rows:
                try:
                    metadata = json.loads(row["metadata_json"])
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise ValueError(f"Invalid session metadata: {row['name']}") from exc
                result.append(
                    SessionInfo(
                        name=str(row["name"]),
                        message_count=int(row["message_count"]),
                        updated_at=str(row["updated_at"]),
                        metadata=_read_metadata(metadata),
                    )
                )
            return result

    def has_session(self, name: str) -> bool:
        normalized_name = normalize_session_name(name)
        with self._lock:
            return self._session_exists_locked(normalized_name)

    def _transaction_locked(self):
        return self._transaction_context()

    @contextmanager
    def _read_transaction_locked(self) -> Iterator[sqlite3.Connection]:
        self.connection.execute("BEGIN")
        try:
            yield self.connection
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()

    @contextmanager
    def _transaction_context(self) -> Iterator[sqlite3.Connection]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield self.connection
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()

    def _write_session_locked(self, session: ChatSession, *, touch: bool) -> None:
        if touch:
            session.updated_at = _now_text()
        metadata_json = json.dumps(session.metadata, ensure_ascii=False)
        self.connection.execute(
            "INSERT OR REPLACE INTO sessions(name, updated_at, compressed_summary, metadata_json) "
            "VALUES (?, ?, ?, ?)",
            (
                session.name,
                session.updated_at,
                session.compressed_summary,
                metadata_json,
            ),
        )
        self.connection.execute(
            "DELETE FROM messages WHERE session_name = ?",
            (session.name,),
        )
        for position, message in enumerate(session.history):
            self.connection.execute(
                "INSERT INTO messages(session_name, position, message_json) VALUES (?, ?, ?)",
                (
                    session.name,
                    position,
                    json.dumps(message_to_dict(message), ensure_ascii=False),
                ),
            )

    def _load_session_locked(self, normalized_name: str) -> ChatSession:
        row = self.connection.execute(
            "SELECT name, updated_at, compressed_summary, metadata_json "
            "FROM sessions WHERE name = ?",
            (normalized_name,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Session not found: {normalized_name}")
        rows = self.connection.execute(
            "SELECT message_json FROM messages WHERE session_name = ? "
            "ORDER BY position ASC",
            (normalized_name,),
        ).fetchall()
        history = [
            message_from_dict(json.loads(item["message_json"])) for item in rows
        ]
        try:
            metadata = json.loads(row["metadata_json"])
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid session metadata: {normalized_name}") from exc
        return ChatSession(
            name=str(row["name"]),
            history=history,
            updated_at=str(row["updated_at"]),
            compressed_summary=str(row["compressed_summary"]),
            metadata=_read_metadata(metadata),
        )

    def _session_exists_locked(self, name: str) -> bool:
        return (
            self.connection.execute(
                "SELECT 1 FROM sessions WHERE name = ?",
                (name,),
            ).fetchone()
            is not None
        )

    def _current_pointer_locked(self) -> tuple[str | None, int]:
        row = self.connection.execute(
            "SELECT current_name, revision FROM current_pointer WHERE singleton = 1"
        ).fetchone()
        if row is None:
            return None, 0
        return (
            str(row["current_name"]) if row["current_name"] else None,
            max(int(row["revision"]), 0),
        )

    def _set_current_locked(self, name: str, revision: int) -> None:
        self.connection.execute(
            "INSERT INTO current_pointer(singleton, current_name, revision) VALUES (1, ?, ?) "
            "ON CONFLICT(singleton) DO UPDATE SET current_name = excluded.current_name, "
            "revision = excluded.revision",
            (normalize_session_name(name), max(int(revision), 0)),
        )

    def _new_session(self, name: str) -> ChatSession:
        return ChatSession(
            name=name,
            history=[],
            updated_at=_now_text(),
            compressed_summary="",
        )

    def _generate_session_name(self) -> str:
        prefix = datetime.now().strftime("session-%Y%m%d-%H%M%S")
        candidate = prefix
        counter = 1
        while self._session_exists_locked(candidate):
            counter += 1
            candidate = f"{prefix}-{counter}"
        return candidate

    def _import_session_locked(self, session: ChatSession) -> None:
        session.name = normalize_session_name(session.name)
        self._write_session_locked(session, touch=False)
