from __future__ import annotations

import threading
from copy import deepcopy
from datetime import datetime
from typing import Any

from ...runtime.sessions import normalize_session_name


MAX_RUNTIME_OVERRIDE_VALUE_LENGTH = 2048


class SessionRuntimeOverrideService:
    """In-memory session-scoped overrides for live Console operation.

    These overrides intentionally do not write to model profile or character
    stores. They exist so Console can apply temporary operational choices to
    Stage without changing Admin configuration.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._overrides: dict[str, dict[str, Any]] = {}

    def set_override(self, session_name: str, override: dict[str, Any]) -> dict[str, Any]:
        normalized_session_name = normalize_session_name(session_name)
        cleaned = _clean_override(override)
        cleaned["updated_at"] = datetime.now().astimezone().isoformat(timespec="microseconds")
        with self._lock:
            self._overrides[normalized_session_name] = deepcopy(cleaned)
        return deepcopy(cleaned)

    def get_override(self, session_name: str) -> dict[str, Any]:
        normalized_session_name = normalize_session_name(session_name)
        with self._lock:
            return deepcopy(self._overrides.get(normalized_session_name, {}))

    def clear_override(self, session_name: str) -> None:
        normalized_session_name = normalize_session_name(session_name)
        with self._lock:
            self._overrides.pop(normalized_session_name, None)


def _clean_override(override: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for field_name in (
        "model_profile_id",
        "llm_model_id",
        "voice_profile_id",
        "live2d_model_id",
    ):
        value = _clean_text(override.get(field_name), max_length=128)
        if value:
            cleaned[field_name] = value

    for section_name in ("tts", "asr", "live2d"):
        section = override.get(section_name)
        if not isinstance(section, dict):
            continue
        cleaned_section = {
            key: _clean_text(value)
            for key, value in section.items()
            if _clean_text(value)
        }
        if cleaned_section:
            cleaned[section_name] = cleaned_section
    return cleaned


def _clean_text(value: object, *, max_length: int = MAX_RUNTIME_OVERRIDE_VALUE_LENGTH) -> str:
    text = str(value or "").strip()
    if len(text) > max_length:
        raise ValueError("Session runtime override value is too large")
    return text
