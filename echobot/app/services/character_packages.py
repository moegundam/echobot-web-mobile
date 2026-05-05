from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from .character_profiles import normalize_emotion_maps


CHARACTER_PACKAGE_VERSION = 1
MAX_CHARACTER_PACKAGE_BYTES = 128 * 1024
MAX_CHARACTER_PACKAGE_PROMPT_LENGTH = 60000


def normalize_character_package_import(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Character package must be a JSON object")
    _ensure_package_size(payload)

    try:
        package_version = int(payload.get("package_version"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Unsupported character package version") from exc
    if package_version != CHARACTER_PACKAGE_VERSION:
        raise ValueError("Unsupported character package version")

    character = payload.get("character")
    if not isinstance(character, dict):
        raise ValueError("Character package character must be an object")

    import_name = _clean_text(payload.get("import_name", ""), 80)
    name = import_name or _clean_text(character.get("name", ""), 80)
    if not name:
        raise ValueError("Character package name cannot be empty")

    prompt = _clean_text(
        character.get("prompt", ""),
        MAX_CHARACTER_PACKAGE_PROMPT_LENGTH,
    )
    if not prompt:
        raise ValueError("Character package prompt cannot be empty")

    return {
        "name": name,
        "prompt": prompt,
        "model_profile_id": _clean_text(character.get("model_profile_id", ""), 64),
        "llm_model_id": _clean_text(character.get("llm_model_id", ""), 64),
        "voice_profile_id": _clean_text(character.get("voice_profile_id", ""), 64),
        "live2d_model_id": _clean_text(character.get("live2d_model_id", ""), 64),
        "default_channel_type": _clean_text(character.get("default_channel_type", ""), 64),
        "default_channel_integration_id": _clean_text(
            character.get("default_channel_integration_id", ""),
            64,
        ),
        "emotion_maps": normalize_emotion_maps(character.get("emotion_maps", [])),
        "overwrite": payload.get("overwrite") is True,
    }


def safe_model_profile_snapshot(profile: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(profile, dict):
        return {}
    snapshot = deepcopy(profile)
    _drop_secret_fields(snapshot)
    return snapshot


def _ensure_package_size(payload: dict[str, Any]) -> None:
    try:
        package_size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Character package must be JSON serializable") from exc
    if package_size > MAX_CHARACTER_PACKAGE_BYTES:
        raise ValueError(f"Character package is too large: {MAX_CHARACTER_PACKAGE_BYTES} bytes")


def _clean_text(value: Any, max_length: int) -> str:
    cleaned = str(value or "").strip()
    if len(cleaned) > max_length:
        raise ValueError("Character package value is too long")
    return cleaned


def _drop_secret_fields(value: Any) -> None:
    if isinstance(value, dict):
        value.pop("api_key", None)
        for child in value.values():
            _drop_secret_fields(child)
    elif isinstance(value, list):
        for child in value:
            _drop_secret_fields(child)
