from __future__ import annotations

import json
import threading
from collections.abc import Iterable
from copy import deepcopy
from pathlib import Path
from typing import Any

from ...orchestration import normalize_role_name


MAX_CHARACTER_EMOTION_MAPS = 64
MAX_CHARACTER_MAP_VALUE_LENGTH = 256
CHARACTER_RUNTIME_BINDING_FIELDS = (
    "model_profile_id",
    "llm_model_id",
    "voice_profile_id",
    "live2d_model_id",
    "default_channel_type",
    "default_channel_integration_id",
)


class CharacterProfileSettingsService:
    def __init__(self, storage_root: Path) -> None:
        self._path = storage_root / "character_profiles.json"
        self._lock = threading.Lock()

    def emotion_maps_for_role(self, role_name: str) -> list[dict[str, str]]:
        normalized_role_name = _normalize_role_name(role_name)
        with self._lock:
            state = self._load_state_unlocked()
            role_settings = state["roles"].get(normalized_role_name, {})
            return deepcopy(role_settings.get("emotion_maps", []))

    def set_emotion_maps(
        self,
        role_name: str,
        emotion_maps: Iterable[Any],
    ) -> list[dict[str, str]]:
        normalized_role_name = _normalize_role_name(role_name)
        normalized_maps = normalize_emotion_maps(emotion_maps)
        with self._lock:
            state = self._load_state_unlocked()
            roles = state["roles"]
            role_settings = roles.setdefault(normalized_role_name, {})
            role_settings["emotion_maps"] = normalized_maps
            if not normalized_maps:
                role_settings.pop("emotion_maps", None)
            if not role_settings:
                roles.pop(normalized_role_name, None)
            self._save_state_unlocked(state)
        return deepcopy(normalized_maps)

    def runtime_bindings_for_role(self, role_name: str) -> dict[str, str]:
        normalized_role_name = _normalize_role_name(role_name)
        with self._lock:
            state = self._load_state_unlocked()
            role_settings = state["roles"].get(normalized_role_name, {})
            return {
                field_name: str(role_settings.get(field_name) or "")
                for field_name in CHARACTER_RUNTIME_BINDING_FIELDS
            }

    def settings_for_roles(
        self,
        role_names: Iterable[Any],
    ) -> dict[str, dict[str, Any]]:
        """Read all requested character settings from one consistent store snapshot."""
        normalized_role_names = tuple(
            dict.fromkeys(_normalize_role_name(role_name) for role_name in role_names)
        )
        with self._lock:
            state = self._load_state_unlocked()
            return {
                role_name: _role_settings_snapshot(state["roles"].get(role_name, {}))
                for role_name in normalized_role_names
            }

    def model_profile_id_for_role(self, role_name: str) -> str:
        return self.runtime_bindings_for_role(role_name).get("model_profile_id", "")

    def model_profile_bindings(self) -> dict[str, str]:
        with self._lock:
            state = self._load_state_unlocked()
            return {
                role_name: str(role_settings.get("model_profile_id") or "")
                for role_name, role_settings in state["roles"].items()
                if isinstance(role_settings, dict)
                and str(role_settings.get("model_profile_id") or "")
            }

    def set_model_profile_binding(
        self,
        role_name: str,
        profile_id: str,
    ) -> dict[str, str]:
        return self.set_runtime_bindings(
            role_name,
            {"model_profile_id": profile_id},
        )

    def clear_model_profile_binding(self, role_name: str) -> dict[str, str]:
        return self.set_runtime_bindings(role_name, {"model_profile_id": ""})

    def clear_model_profile_bindings_for_profile(self, profile_id: str) -> dict[str, str]:
        normalized_profile_id = _clean_map_value(profile_id)
        if not normalized_profile_id:
            return self.model_profile_bindings()
        with self._lock:
            state = self._load_state_unlocked()
            for role_name in list(state["roles"].keys()):
                role_settings = state["roles"].get(role_name, {})
                if not isinstance(role_settings, dict):
                    continue
                if str(role_settings.get("model_profile_id") or "") != normalized_profile_id:
                    continue
                role_settings.pop("model_profile_id", None)
                if not role_settings:
                    state["roles"].pop(role_name, None)
            self._save_state_unlocked(state)
            return {
                role_name: str(role_settings.get("model_profile_id") or "")
                for role_name, role_settings in state["roles"].items()
                if isinstance(role_settings, dict)
                and str(role_settings.get("model_profile_id") or "")
            }

    def clear_runtime_bindings_for_profile(
        self,
        profile_id: str,
        field_names: Iterable[str],
    ) -> dict[str, dict[str, str]]:
        normalized_profile_id = _clean_map_value(profile_id)
        normalized_fields = tuple(
            field_name
            for field_name in dict.fromkeys(field_names)
            if field_name in CHARACTER_RUNTIME_BINDING_FIELDS
        )
        if not normalized_profile_id or not normalized_fields:
            return {}

        with self._lock:
            state = self._load_state_unlocked()
            for role_name in list(state["roles"]):
                role_settings = state["roles"].get(role_name, {})
                if not isinstance(role_settings, dict):
                    continue
                for field_name in normalized_fields:
                    if (
                        str(role_settings.get(field_name) or "")
                        == normalized_profile_id
                    ):
                        role_settings.pop(field_name, None)
                if not role_settings:
                    state["roles"].pop(role_name, None)
            self._save_state_unlocked(state)
            return {
                role_name: {
                    field_name: str(role_settings.get(field_name) or "")
                    for field_name in CHARACTER_RUNTIME_BINDING_FIELDS
                }
                for role_name, role_settings in state["roles"].items()
                if isinstance(role_settings, dict)
            }

    def set_runtime_bindings(
        self,
        role_name: str,
        updates: dict[str, Any],
    ) -> dict[str, str]:
        normalized_role_name = _normalize_role_name(role_name)
        normalized_updates = _normalize_runtime_binding_updates(updates)
        with self._lock:
            state = self._load_state_unlocked()
            roles = state["roles"]
            role_settings = roles.setdefault(normalized_role_name, {})
            for field_name, value in normalized_updates.items():
                if value:
                    role_settings[field_name] = value
                else:
                    role_settings.pop(field_name, None)
            if not role_settings:
                roles.pop(normalized_role_name, None)
            self._save_state_unlocked(state)
            return {
                field_name: str(role_settings.get(field_name) or "")
                for field_name in CHARACTER_RUNTIME_BINDING_FIELDS
            }

    def clear_role(self, role_name: str) -> None:
        normalized_role_name = _normalize_role_name(role_name)
        with self._lock:
            state = self._load_state_unlocked()
            state["roles"].pop(normalized_role_name, None)
            self._save_state_unlocked(state)

    def resolve_emotion(self, role_name: str, emotion: str) -> dict[str, str]:
        normalized_emotion = _normalize_lookup(emotion)
        if not normalized_emotion:
            return {}
        for item in self.emotion_maps_for_role(role_name):
            if _normalize_lookup(item.get("emotion", "")) == normalized_emotion:
                return {
                    "expression": item.get("expression", ""),
                    "motion": item.get("motion", ""),
                }
        return {}

    def seed_from(self, source: "CharacterProfileSettingsService") -> bool:
        if source is self:
            return False

        with source._lock:
            source_state = deepcopy(source._load_state_unlocked())

        with self._lock:
            if self._path.exists():
                return False
            self._save_state_unlocked(source_state)
            return True

    def _load_state_unlocked(self) -> dict[str, Any]:
        state = _default_state()
        if not self._path.exists():
            return state
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Character profile settings store must contain a JSON object")
        raw_roles = payload.get("roles")
        if not isinstance(raw_roles, dict):
            return state
        for raw_role_name, raw_settings in raw_roles.items():
            if not isinstance(raw_settings, dict):
                continue
            try:
                role_name = _normalize_role_name(raw_role_name)
                emotion_maps = normalize_emotion_maps(raw_settings.get("emotion_maps", []))
            except ValueError:
                continue
            runtime_bindings = _normalize_runtime_binding_updates(raw_settings)
            if emotion_maps:
                state["roles"].setdefault(role_name, {})["emotion_maps"] = emotion_maps
            if runtime_bindings:
                state["roles"].setdefault(role_name, {}).update(runtime_bindings)
        return state

    def _save_state_unlocked(self, state: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def normalize_emotion_maps(emotion_maps: Iterable[Any]) -> list[dict[str, str]]:
    if emotion_maps is None:
        return []
    if not isinstance(emotion_maps, Iterable) or isinstance(emotion_maps, (str, bytes)):
        raise ValueError("Character emotion maps must be a list")

    normalized: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for raw_item in emotion_maps:
        item = _raw_map_item(raw_item)
        if item is None:
            continue
        emotion = _clean_map_value(item.get("emotion", ""))
        expression = _clean_map_value(item.get("expression", ""))
        motion = _clean_map_value(item.get("motion", ""))
        if not emotion and not expression and not motion:
            continue
        if not emotion:
            raise ValueError("Character emotion map emotion is required")
        key = _normalize_lookup(emotion)
        if key not in normalized:
            order.append(key)
        normalized[key] = {
            "emotion": emotion,
            "expression": expression,
            "motion": motion,
        }
    if len(order) > MAX_CHARACTER_EMOTION_MAPS:
        raise ValueError(f"Character emotion map limit reached: {MAX_CHARACTER_EMOTION_MAPS}")
    return [normalized[key] for key in order]


def _raw_map_item(raw_item: Any) -> dict[str, Any] | None:
    if hasattr(raw_item, "model_dump"):
        raw_item = raw_item.model_dump(mode="json")
    if raw_item is None:
        return None
    if not isinstance(raw_item, dict):
        raise ValueError("Character emotion map item must be an object")
    return raw_item


def _clean_map_value(value: Any) -> str:
    cleaned = str(value or "").strip()
    if len(cleaned) > MAX_CHARACTER_MAP_VALUE_LENGTH:
        raise ValueError("Character emotion map value is too long")
    return cleaned


def _normalize_role_name(role_name: Any) -> str:
    normalized = normalize_role_name(str(role_name or ""))
    if not normalized:
        raise ValueError("Role name cannot be empty")
    return normalized


def _normalize_lookup(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_runtime_binding_updates(updates: dict[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    if not isinstance(updates, dict):
        return normalized
    for field_name in CHARACTER_RUNTIME_BINDING_FIELDS:
        if field_name not in updates:
            continue
        normalized[field_name] = _clean_map_value(updates.get(field_name, ""))
    return normalized


def _role_settings_snapshot(role_settings: Any) -> dict[str, Any]:
    if not isinstance(role_settings, dict):
        role_settings = {}
    return {
        "emotion_maps": deepcopy(role_settings.get("emotion_maps", [])),
        "runtime_bindings": {
            field_name: str(role_settings.get(field_name) or "")
            for field_name in CHARACTER_RUNTIME_BINDING_FIELDS
        },
    }


def _default_state() -> dict[str, Any]:
    return {
        "roles": {},
    }
