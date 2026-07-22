from __future__ import annotations

from typing import Protocol, runtime_checkable

from .sessions import ChatSession, SessionInfo


@runtime_checkable
class SessionRepository(Protocol):
    """Synchronous persistence contract shared by JSONL and SQLite sessions."""

    def load_current_session(self) -> ChatSession: ...

    def load_or_create_session(self, name: str) -> ChatSession: ...

    def create_session(self, name: str | None = None) -> ChatSession: ...

    def load_session(self, name: str) -> ChatSession: ...

    def save_session(self, session: ChatSession) -> None: ...

    def delete_session(self, name: str) -> None: ...

    def rename_session(self, old_name: str, new_name: str) -> ChatSession: ...

    def set_current_session(self, name: str) -> None: ...

    def compare_and_set_current_session(
        self,
        expected_name: str,
        next_name: str | None,
        *,
        expected_revision: int | None = None,
    ) -> bool: ...

    def repair_current_session_after_deletion(
        self,
        deleted_name: str,
    ) -> ChatSession | None: ...

    def get_current_session_name(self) -> str | None: ...

    def get_current_session_pointer(self) -> tuple[str | None, int]: ...

    def list_sessions(self) -> list[SessionInfo]: ...

    def has_session(self, name: str) -> bool: ...
