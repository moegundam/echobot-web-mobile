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

    def clear_profile_references(
        self,
        profile_id: str,
        field_names: tuple[str, ...],
    ) -> int:
        """Remove deleted profile IDs from every ephemeral Session override."""
        normalized_profile_id = str(profile_id or "").strip()
        normalized_fields = tuple(
            field_name
            for field_name in field_names
            if field_name in {
                "model_profile_id",
                "llm_model_id",
                "voice_profile_id",
                "live2d_model_id",
            }
        )
        if not normalized_profile_id or not normalized_fields:
            return 0

        cleared = 0
        with self._lock:
            for session_name in list(self._overrides):
                override = self._overrides[session_name]
                changed = False
                for field_name in normalized_fields:
                    if str(override.get(field_name) or "") == normalized_profile_id:
                        override.pop(field_name, None)
                        changed = True
                if not changed:
                    continue
                cleared += 1
                if set(override).issubset({"updated_at"}):
                    self._overrides.pop(session_name, None)
                    continue
                override["updated_at"] = datetime.now().astimezone().isoformat(
                    timespec="microseconds",
                )
        return cleared


def _clean_override(override: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    role_name = _clean_text(override.get("role_name"), max_length=128)
    if role_name:
        cleaned["role_name"] = role_name
    route_mode = _clean_text(override.get("route_mode"), max_length=32)
    if route_mode:
        cleaned["route_mode"] = route_mode
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
    stage = _clean_stage_override(override.get("stage"))
    if stage:
        cleaned["stage"] = stage
    return cleaned


def _clean_text(value: object, *, max_length: int = MAX_RUNTIME_OVERRIDE_VALUE_LENGTH) -> str:
    text = str(value or "").strip()
    if len(text) > max_length:
        raise ValueError("Session runtime override value is too large")
    return text


def _clean_stage_override(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    background = _clean_stage_background(value.get("background"))
    if not background:
        return {}
    return {"background": background}


def _clean_stage_background(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    background = {
        "key": _clean_text(value.get("key"), max_length=128) or "default",
        "label": _clean_text(value.get("label"), max_length=256),
        "url": _clean_text(value.get("url")),
        "kind": _clean_text(value.get("kind"), max_length=64) or "none",
        "transform": _clean_stage_background_transform(value.get("transform")),
    }
    return background


def _clean_stage_background_transform(value: object) -> dict[str, float]:
    transform = value if isinstance(value, dict) else {}
    return {
        "positionX": _clean_float(transform.get("positionX"), default=50, minimum=0, maximum=100),
        "positionY": _clean_float(transform.get("positionY"), default=50, minimum=0, maximum=100),
        "scale": _clean_float(transform.get("scale"), default=100, minimum=60, maximum=200),
    }


def _clean_float(
    value: object,
    *,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if number < minimum:
        number = minimum
    if number > maximum:
        number = maximum
    return round(number, 2)
