from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models import LLMMessage, ToolCall, normalize_message_content
from ..naming import normalize_name_token
from ..session_contracts import MAX_SESSION_NAME_LENGTH


@dataclass(slots=True)
class ChatSession:
    name: str
    history: list[LLMMessage]
    updated_at: str
    compressed_summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SessionInfo:
    name: str
    message_count: int
    updated_at: str
    metadata: dict[str, Any] = field(default_factory=dict)


class SessionStore:
    def __init__(self, base_dir: str | Path = ".echobot/sessions") -> None:
        self.base_dir = Path(base_dir)
        self.index_file = self.base_dir / "index.jsonl"
        self._lock = threading.RLock()

    def load_current_session(self) -> ChatSession:
        with self._lock:
            current_name, current_revision = self.get_current_session_pointer()
            if current_name and self.has_session(current_name):
                return self.load_session(current_name)
            if current_name:
                self.compare_and_set_current_session(
                    current_name,
                    None,
                    expected_revision=current_revision,
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
        with self._lock:
            normalized_name = normalize_session_name(name)
            path = self._session_path(normalized_name)
            if path.exists():
                return self.load_session(normalized_name)

            session = ChatSession(
                name=normalized_name,
                history=[],
                updated_at=_now_text(),
                compressed_summary="",
            )
            self.save_session(session)
            return session

    def create_session(self, name: str | None = None) -> ChatSession:
        with self._lock:
            session_name = (
                normalize_session_name(name) if name else self._generate_session_name()
            )
            path = self._session_path(session_name)
            if path.exists():
                raise ValueError(f"Session already exists: {session_name}")

            session = ChatSession(
                name=session_name,
                history=[],
                updated_at=_now_text(),
                compressed_summary="",
            )
            self.save_session(session)
            self.set_current_session(session.name)
            return session

    def load_session(self, name: str) -> ChatSession:
        with self._lock:
            normalized_name = normalize_session_name(name)
            path = self._session_path(normalized_name)
            if not path.exists():
                raise ValueError(f"Session not found: {normalized_name}")

            records = self._read_jsonl_records(path)
            if not records:
                raise ValueError(f"Session file is empty: {normalized_name}")

            metadata = records[0]
            if metadata.get("type") != "session":
                raise ValueError(f"Invalid session metadata: {normalized_name}")

            history: list[LLMMessage] = []
            for record in records[1:]:
                if record.get("type") != "message":
                    continue

                message_data = dict(record)
                message_data.pop("type", None)
                history.append(message_from_dict(message_data))

            return ChatSession(
                name=str(metadata.get("name", normalized_name)),
                history=history,
                updated_at=str(metadata.get("updated_at", "")),
                compressed_summary=str(metadata.get("compressed_summary", "")),
                metadata=_read_metadata(metadata.get("metadata")),
            )

    def save_session(self, session: ChatSession) -> None:
        with self._lock:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            session.updated_at = _now_text()

            records: list[dict[str, Any]] = [
                {
                    "type": "session",
                    "name": session.name,
                    "updated_at": session.updated_at,
                    "compressed_summary": session.compressed_summary,
                    "metadata": dict(session.metadata),
                }
            ]
            for message in session.history:
                records.append(
                    {
                        "type": "message",
                        **message_to_dict(message),
                    }
                )

            lines = [json.dumps(record, ensure_ascii=False) for record in records]
            self._session_path(session.name).write_text(
                "\n".join(lines) + "\n",
                encoding="utf-8",
            )

    def delete_session(self, name: str) -> None:
        with self._lock:
            path = self._session_path(name)
            if path.exists():
                path.unlink()

    def rename_session(self, old_name: str, new_name: str) -> ChatSession:
        with self._lock:
            normalized_old_name = normalize_session_name(old_name)
            normalized_new_name = normalize_session_name(new_name)

            session = self.load_session(normalized_old_name)
            if normalized_old_name == normalized_new_name:
                return session

            new_path = self._session_path(normalized_new_name)
            if new_path.exists():
                raise ValueError(f"Session already exists: {normalized_new_name}")

            current_name = self.get_current_session_name()
            old_path = self._session_path(normalized_old_name)

            session.name = normalized_new_name
            self.save_session(session)

            if old_path.exists():
                old_path.unlink()

            if current_name == normalized_old_name:
                self.set_current_session(normalized_new_name)

            return session

    def set_current_session(self, name: str) -> None:
        with self._lock:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            _, current_revision = self.get_current_session_pointer()
            record = {
                "current_session": normalize_session_name(name),
                "revision": current_revision + 1,
            }
            self.index_file.write_text(
                json.dumps(record, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    def compare_and_set_current_session(
        self,
        expected_name: str,
        next_name: str | None,
        *,
        expected_revision: int | None = None,
    ) -> bool:
        with self._lock:
            expected = normalize_session_name(expected_name)
            current_name, current_revision = self.get_current_session_pointer()
            if current_name != expected:
                return False
            if (
                expected_revision is not None
                and current_revision != expected_revision
            ):
                return False

            if next_name is None:
                if self.index_file.exists():
                    self.index_file.unlink()
                return True

            normalized_next = normalize_session_name(next_name)
            if not self._session_path(normalized_next).exists():
                raise ValueError(f"Session not found: {normalized_next}")
            self.set_current_session(normalized_next)
            return True

    def repair_current_session_after_deletion(
        self,
        deleted_name: str,
    ) -> ChatSession | None:
        with self._lock:
            normalized_deleted = normalize_session_name(deleted_name)
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
        current_name, _ = self.get_current_session_pointer()
        return current_name

    def get_current_session_pointer(self) -> tuple[str | None, int]:
        with self._lock:
            if not self.index_file.exists():
                return None, 0

            records = self._read_jsonl_records(self.index_file)
            if not records:
                return None, 0

            current_name = str(records[0].get("current_session", "")).strip()
            try:
                revision = max(int(records[0].get("revision", 0)), 0)
            except (TypeError, ValueError):
                revision = 0
            return current_name or None, revision

    def list_sessions(self) -> list[SessionInfo]:
        with self._lock:
            if not self.base_dir.exists():
                return []

            sessions: list[SessionInfo] = []
            for path in sorted(self.base_dir.glob("*.jsonl")):
                if path.name == self.index_file.name:
                    continue

                records = self._read_jsonl_records(path)
                if not records:
                    continue

                metadata = records[0]
                if metadata.get("type") != "session":
                    continue

                message_count = sum(
                    1 for record in records[1:] if record.get("type") == "message"
                )
                sessions.append(
                    SessionInfo(
                        name=str(metadata.get("name", path.stem)),
                        message_count=message_count,
                        updated_at=str(metadata.get("updated_at", "")),
                        metadata=_read_metadata(metadata.get("metadata")),
                    )
                )

            sessions.sort(key=lambda item: item.updated_at, reverse=True)
            return sessions

    def has_session(self, name: str) -> bool:
        with self._lock:
            return self._session_path(name).exists()

    def _session_path(self, name: str) -> Path:
        return self.base_dir / f"{normalize_session_name(name)}.jsonl"

    def _generate_session_name(self) -> str:
        prefix = datetime.now().strftime("session-%Y%m%d-%H%M%S")
        candidate = prefix
        counter = 1

        while self._session_path(candidate).exists():
            counter += 1
            candidate = f"{prefix}-{counter}"

        return candidate

    def _read_jsonl_records(self, path: Path) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            cleaned_line = line.strip()
            if not cleaned_line:
                continue

            data = json.loads(cleaned_line)
            if isinstance(data, dict):
                records.append(data)

        return records


def normalize_session_name(name: str) -> str:
    raw_name = str(name or "").strip()
    if not raw_name:
        raise ValueError("Session name cannot be empty")
    if len(raw_name) > MAX_SESSION_NAME_LENGTH:
        raise ValueError(
            f"Session name must be {MAX_SESSION_NAME_LENGTH} characters or fewer",
        )

    normalized = normalize_name_token(raw_name)
    if not normalized:
        raise ValueError("Session name must contain letters, digits, hyphen, or underscore")
    if len(normalized) > MAX_SESSION_NAME_LENGTH:
        raise ValueError(
            f"Session name must be {MAX_SESSION_NAME_LENGTH} characters or fewer",
        )

    return normalized


def message_to_dict(message: LLMMessage) -> dict[str, Any]:
    data: dict[str, Any] = {
        "role": message.role,
        "content": normalize_message_content(message.content),
        "name": message.name,
        "tool_call_id": message.tool_call_id,
        "tool_calls": [
            {
                "id": tool_call.id,
                "name": tool_call.name,
                "arguments": tool_call.arguments,
            }
            for tool_call in message.tool_calls
        ],
    }
    if message.role == "assistant" and message.reasoning_content:
        data["reasoning_content"] = message.reasoning_content
        data["reasoning_field"] = message.reasoning_field
    return data


def message_from_dict(data: dict[str, Any]) -> LLMMessage:
    return LLMMessage(
        role=str(data.get("role", "user")),  # type: ignore[arg-type]
        content=normalize_message_content(data.get("content", "")),
        name=_read_optional_text(data.get("name")),
        tool_call_id=_read_optional_text(data.get("tool_call_id")),
        tool_calls=[
            ToolCall(
                id=str(item.get("id", "")),
                name=str(item.get("name", "")),
                arguments=str(item.get("arguments", "")),
            )
            for item in data.get("tool_calls", [])
        ],
        reasoning_content=str(
            data.get("reasoning_content") or data.get("reasoning") or ""
        ),
        reasoning_field=_read_reasoning_field(data.get("reasoning_field")),
    )


def _read_optional_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _read_reasoning_field(value: Any) -> str:
    text = str(value or "").strip()
    if text == "reasoning":
        return "reasoning"
    return "reasoning_content"


def _read_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return dict(value)


def _now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
