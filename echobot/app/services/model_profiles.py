from __future__ import annotations

import json
import os
import re
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...orchestration import normalize_role_name


DEFAULT_PROFILE_IDS = ("a", "b", "c", "d", "e")
DEFAULT_ACTIVE_PROFILE_ID = "a"
MAX_PROFILE_COUNT = 100
MAX_PROFILE_ID_LENGTH = 64
MAX_LABEL_LENGTH = 80
MAX_VALUE_LENGTH = 2048
MAX_SECRET_LENGTH = 4096
PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SECRET_SECTIONS = ("chat", "tts", "asr")
SECRET_ENV_NAMES = {
    "chat": "LLM_API_KEY",
    "tts": "ECHOBOT_TTS_OPENAI_API_KEY",
    "asr": "ECHOBOT_ASR_OPENAI_API_KEY",
}


class ModelProfileService:
    def __init__(self, storage_root: Path) -> None:
        self._path = storage_root / "model_profiles.json"
        self._secret_path = storage_root / "model_profile_secrets.json"
        self._lock = threading.Lock()

    @property
    def storage_root(self) -> Path:
        return self._path.parent

    def list_profiles(self) -> dict[str, Any]:
        with self._lock:
            state = self._load_state_unlocked()
            secrets = self._load_secrets_unlocked()
            return self._response_from_state(state, secrets)

    def get_profile(self, profile_id: str) -> dict[str, Any]:
        normalized_id = _normalize_profile_id(profile_id)
        with self._lock:
            state = self._load_state_unlocked()
            _require_existing_profile(state, normalized_id)
            secrets = self._load_secrets_unlocked()
            return self._profile_response(
                state["profiles"][normalized_id],
                secrets,
                normalized_id,
            )

    def create_profile(
        self,
        *,
        label: str,
        source_profile_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_label = _clean_label(label)
        with self._lock:
            state = self._load_state_unlocked()
            if len(state["profiles"]) >= MAX_PROFILE_COUNT:
                raise ValueError(f"Model profile limit reached: {MAX_PROFILE_COUNT}")

            if source_profile_id:
                source_id = _normalize_profile_id(source_profile_id)
                _require_existing_profile(state, source_id)
                profile = deepcopy(state["profiles"][source_id])
            else:
                profile = _default_profile("")

            profile_id = _next_profile_id(normalized_label, state["profiles"])
            profile["profile_id"] = profile_id
            profile["label"] = normalized_label
            profile["updated_at"] = _now_iso()
            state["profiles"][profile_id] = profile
            secrets = self._load_secrets_unlocked()
            self._save_state_unlocked(state)
            return self._profile_response(profile, secrets, profile_id)

    def update_profile(self, profile_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        normalized_id = _normalize_profile_id(profile_id)
        normalized_updates = _normalize_profile_updates(updates)
        secret_updates = _normalize_secret_updates(updates)
        with self._lock:
            state = self._load_state_unlocked()
            _require_existing_profile(state, normalized_id)
            secrets = self._load_secrets_unlocked()
            profile = state["profiles"][normalized_id]
            if "label" in normalized_updates:
                profile["label"] = normalized_updates["label"]
            for section in ("chat", "tts", "asr", "live2d"):
                if section in normalized_updates:
                    profile[section].update(normalized_updates[section])
            _apply_secret_updates(secrets, normalized_id, secret_updates)
            profile["updated_at"] = _now_iso()
            self._save_state_unlocked(state)
            self._save_secrets_unlocked(secrets)
            return self._profile_response(profile, secrets, normalized_id)

    def activate_profile(self, profile_id: str) -> dict[str, Any]:
        normalized_id = _normalize_profile_id(profile_id)
        with self._lock:
            state = self._load_state_unlocked()
            _require_existing_profile(state, normalized_id)
            secrets = self._load_secrets_unlocked()
            state["active_profile_id"] = normalized_id
            state["profiles"][normalized_id]["updated_at"] = _now_iso()
            self._save_state_unlocked(state)
            return self._response_from_state(state, secrets)

    def delete_profile(self, profile_id: str) -> dict[str, Any]:
        normalized_id = _normalize_profile_id(profile_id)
        with self._lock:
            state = self._load_state_unlocked()
            _require_existing_profile(state, normalized_id)
            if normalized_id == state["active_profile_id"]:
                raise ValueError("Active model profile cannot be deleted")
            if len(state["profiles"]) <= 1:
                raise ValueError("Last model profile cannot be deleted")

            secrets = self._load_secrets_unlocked()
            state["profiles"].pop(normalized_id, None)
            state["role_bindings"] = {
                role_name: bound_profile_id
                for role_name, bound_profile_id in state["role_bindings"].items()
                if bound_profile_id != normalized_id
            }
            secrets.setdefault("profiles", {}).pop(normalized_id, None)
            self._save_state_unlocked(state)
            self._save_secrets_unlocked(secrets)
            return self._response_from_state(state, secrets)

    def set_role_binding(self, role_name: str, profile_id: str) -> dict[str, Any]:
        normalized_role_name = _normalize_role_binding_name(role_name)
        normalized_profile_id = _normalize_profile_id(profile_id)
        with self._lock:
            state = self._load_state_unlocked()
            _require_existing_profile(state, normalized_profile_id)
            secrets = self._load_secrets_unlocked()
            state["role_bindings"][normalized_role_name] = normalized_profile_id
            self._save_state_unlocked(state)
            return self._response_from_state(state, secrets)

    def clear_role_binding(self, role_name: str) -> dict[str, Any]:
        normalized_role_name = _normalize_role_binding_name(role_name)
        with self._lock:
            state = self._load_state_unlocked()
            secrets = self._load_secrets_unlocked()
            state["role_bindings"].pop(normalized_role_name, None)
            self._save_state_unlocked(state)
            return self._response_from_state(state, secrets)

    def profile_id_for_role(self, role_name: str) -> str:
        normalized_role_name = _normalize_role_binding_name(role_name)
        with self._lock:
            state = self._load_state_unlocked()
            return str(state["role_bindings"].get(normalized_role_name, ""))

    def active_profile(self) -> dict[str, Any]:
        with self._lock:
            state = self._load_state_unlocked()
            secrets = self._load_secrets_unlocked()
            active_profile_id = state["active_profile_id"]
            return self._profile_response(
                state["profiles"][active_profile_id],
                secrets,
                active_profile_id,
            )

    def active_profile_for_runtime(self) -> dict[str, Any]:
        with self._lock:
            state = self._load_state_unlocked()
            secrets = self._load_secrets_unlocked()
            active_profile_id = state["active_profile_id"]
            return _profile_for_runtime(
                state["profiles"][active_profile_id],
                secrets,
                active_profile_id,
            )

    def get_profile_for_runtime(self, profile_id: str) -> dict[str, Any]:
        normalized_id = _normalize_profile_id(profile_id)
        with self._lock:
            state = self._load_state_unlocked()
            _require_existing_profile(state, normalized_id)
            secrets = self._load_secrets_unlocked()
            return _profile_for_runtime(
                state["profiles"][normalized_id],
                secrets,
                normalized_id,
            )

    def seed_from(self, source: "ModelProfileService") -> bool:
        """Initialize this profile store from another store if it is still empty."""
        if source is self:
            return False

        with source._lock:
            source_state = deepcopy(source._load_state_unlocked())
            source_secrets = deepcopy(source._load_secrets_unlocked())

        with self._lock:
            if self._path.exists():
                return False
            self._save_state_unlocked(source_state)
            self._save_secrets_unlocked(source_secrets)
            return True

    def _load_state_unlocked(self) -> dict[str, Any]:
        if not self._path.exists():
            return _default_state()

        state = _empty_state()
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Model profile store must contain a JSON object")
        raw_profiles = payload.get("profiles", {})
        if isinstance(raw_profiles, dict):
            for raw_profile_id, raw_profile in raw_profiles.items():
                if isinstance(raw_profile, dict):
                    try:
                        profile_id = _normalize_profile_id(raw_profile_id)
                    except ValueError:
                        continue
                    state["profiles"][profile_id] = _merge_profile(
                        _default_profile(profile_id),
                        raw_profile,
                    )
        if not state["profiles"]:
            state = _default_state()
        state["active_profile_id"] = _coerce_active_profile_id(
            payload.get("active_profile_id"),
            state["profiles"],
        )
        state["role_bindings"] = _coerce_role_bindings(
            payload.get("role_bindings"),
            state["profiles"],
        )
        return state

    def _save_state_unlocked(self, state: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _load_secrets_unlocked(self) -> dict[str, Any]:
        if not self._secret_path.exists():
            return {"profiles": {}}
        payload = json.loads(self._secret_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Model profile secret store must contain a JSON object")
        raw_profiles = payload.get("profiles", {})
        if not isinstance(raw_profiles, dict):
            return {"profiles": {}}

        secrets: dict[str, Any] = {"profiles": {}}
        for raw_profile_id, raw_profile in raw_profiles.items():
            if not isinstance(raw_profile, dict):
                continue
            try:
                profile_id = _normalize_profile_id(raw_profile_id)
            except ValueError:
                continue
            profile_secrets: dict[str, Any] = {}
            for section in SECRET_SECTIONS:
                raw_section = raw_profile.get(section)
                if not isinstance(raw_section, dict):
                    continue
                api_key = _clean_secret(raw_section.get("api_key", ""))
                if api_key:
                    profile_secrets[section] = {"api_key": api_key}
            if profile_secrets:
                secrets["profiles"][profile_id] = profile_secrets
        return secrets

    def _save_secrets_unlocked(self, secrets: dict[str, Any]) -> None:
        self._secret_path.parent.mkdir(parents=True, exist_ok=True)
        self._secret_path.write_text(
            json.dumps(secrets, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        try:
            self._secret_path.chmod(0o600)
        except OSError:
            pass

    def _response_from_state(
        self,
        state: dict[str, Any],
        secrets: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "active_profile_id": state["active_profile_id"],
            "role_bindings": dict(state["role_bindings"]),
            "profiles": [
                self._profile_response(
                    state["profiles"][profile_id],
                    secrets,
                    profile_id,
                )
                for profile_id in state["profiles"]
            ],
        }

    @staticmethod
    def _profile_response(
        profile: dict[str, Any],
        secrets: dict[str, Any],
        profile_id: str,
    ) -> dict[str, Any]:
        response = deepcopy(profile)
        for section in SECRET_SECTIONS:
            response.setdefault(section, {}).pop("api_key", None)
            configured, source = _secret_status(secrets, profile_id, section)
            response[section]["api_key_configured"] = configured
            response[section]["api_key_source"] = source
        return response


def _default_state() -> dict[str, Any]:
    profiles = {
        profile_id: _default_profile(profile_id)
        for profile_id in DEFAULT_PROFILE_IDS
    }
    return {
        "active_profile_id": DEFAULT_ACTIVE_PROFILE_ID,
        "role_bindings": {},
        "profiles": profiles,
    }


def _empty_state() -> dict[str, Any]:
    return {
        "active_profile_id": DEFAULT_ACTIVE_PROFILE_ID,
        "role_bindings": {},
        "profiles": {},
    }


def _default_profile(profile_id: str, *, label: str | None = None) -> dict[str, Any]:
    profile_label = label or (
        f"Profile {profile_id.upper()}" if profile_id else "New Profile"
    )
    return {
        "profile_id": profile_id,
        "label": profile_label,
        "chat": {
            "provider": "openai-compatible",
            "model": _env_text("LLM_MODEL"),
            "base_url": _env_text("LLM_BASE_URL"),
            "temperature": None,
            "max_tokens": None,
        },
        "tts": {
            "provider": _env_text("ECHOBOT_TTS_PROVIDER"),
            "model": _env_text("ECHOBOT_TTS_OPENAI_MODEL"),
            "base_url": _env_text("ECHOBOT_TTS_OPENAI_BASE_URL"),
            "voice": _env_text("ECHOBOT_TTS_OPENAI_DEFAULT_VOICE"),
        },
        "asr": {
            "provider": _env_text("ECHOBOT_ASR_PROVIDER"),
            "model": _env_text("ECHOBOT_ASR_OPENAI_MODEL"),
            "base_url": _env_text("ECHOBOT_ASR_OPENAI_BASE_URL"),
            "language": _env_text("ECHOBOT_ASR_OPENAI_LANGUAGE"),
        },
        "live2d": {
            "selection_key": _env_text("ECHOBOT_WEB_LIVE2D_MODEL"),
        },
        "updated_at": "",
    }


def _merge_profile(default_profile: dict[str, Any], raw_profile: dict[str, Any]) -> dict[str, Any]:
    profile = deepcopy(default_profile)
    updates = _normalize_profile_updates(raw_profile)
    if "label" in updates:
        profile["label"] = updates["label"]
    for section in ("chat", "tts", "asr", "live2d"):
        if section in updates:
            profile[section].update(updates[section])
    profile["profile_id"] = default_profile["profile_id"]
    profile["updated_at"] = _clean_text(raw_profile.get("updated_at", ""), MAX_VALUE_LENGTH)
    return profile


def _normalize_profile_updates(updates: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    if "label" in updates and updates["label"] is not None:
        normalized["label"] = _clean_label(updates["label"])

    for section, allowed_keys in {
        "chat": ("provider", "model", "base_url", "temperature", "max_tokens"),
        "tts": ("provider", "model", "base_url", "voice"),
        "asr": ("provider", "model", "base_url", "language"),
        "live2d": ("selection_key",),
    }.items():
        raw_section = updates.get(section)
        if raw_section is None:
            continue
        if not isinstance(raw_section, dict):
            raise ValueError(f"Model profile {section} settings must be an object")
        normalized[section] = {}
        for key in allowed_keys:
            if key not in raw_section:
                continue
            value = raw_section[key]
            if key == "temperature":
                normalized[section][key] = None if value is None else float(value)
            elif key == "max_tokens":
                normalized[section][key] = None if value is None else int(value)
            else:
                normalized[section][key] = _clean_text(value, MAX_VALUE_LENGTH)
    return normalized


def _normalize_secret_updates(updates: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for section in SECRET_SECTIONS:
        raw_section = updates.get(section)
        if raw_section is None:
            continue
        if not isinstance(raw_section, dict):
            raise ValueError(f"Model profile {section} settings must be an object")
        section_updates: dict[str, Any] = {}
        if bool(raw_section.get("clear_api_key", False)):
            section_updates["clear_api_key"] = True
        if "api_key" in raw_section:
            api_key = _clean_secret(raw_section.get("api_key", ""))
            if api_key:
                section_updates["api_key"] = api_key
        if section_updates:
            normalized[section] = section_updates
    return normalized


def _apply_secret_updates(
    secrets: dict[str, Any],
    profile_id: str,
    updates: dict[str, Any],
) -> None:
    profiles = secrets.setdefault("profiles", {})
    profile_secrets = profiles.setdefault(profile_id, {})
    for section, section_updates in updates.items():
        if section_updates.get("clear_api_key"):
            raw_section = profile_secrets.get(section)
            if isinstance(raw_section, dict):
                raw_section.pop("api_key", None)
            if not raw_section:
                profile_secrets.pop(section, None)
        api_key = section_updates.get("api_key")
        if api_key:
            profile_secrets.setdefault(section, {})["api_key"] = api_key
    if not profile_secrets:
        profiles.pop(profile_id, None)


def _profile_for_runtime(
    profile: dict[str, Any],
    secrets: dict[str, Any],
    profile_id: str,
) -> dict[str, Any]:
    runtime_profile = deepcopy(profile)
    for section in SECRET_SECTIONS:
        api_key = _effective_secret(secrets, profile_id, section)
        if api_key:
            runtime_profile.setdefault(section, {})["api_key"] = api_key
    return runtime_profile


def _effective_secret(
    secrets: dict[str, Any],
    profile_id: str,
    section: str,
) -> str:
    profile_secret = _profile_secret(secrets, profile_id, section)
    if profile_secret:
        return profile_secret
    return os.environ.get(SECRET_ENV_NAMES.get(section, ""), "").strip()


def _secret_status(
    secrets: dict[str, Any],
    profile_id: str,
    section: str,
) -> tuple[bool, str]:
    if _profile_secret(secrets, profile_id, section):
        return True, "profile"
    env_secret = os.environ.get(SECRET_ENV_NAMES.get(section, ""), "").strip()
    if _is_configured_secret(env_secret):
        return True, "environment"
    return False, ""


def _profile_secret(
    secrets: dict[str, Any],
    profile_id: str,
    section: str,
) -> str:
    raw_profile = secrets.get("profiles", {}).get(profile_id, {})
    if not isinstance(raw_profile, dict):
        return ""
    raw_section = raw_profile.get(section, {})
    if not isinstance(raw_section, dict):
        return ""
    return _clean_secret(raw_section.get("api_key", ""))


def _normalize_profile_id(profile_id: str) -> str:
    normalized_id = str(profile_id or "").strip().lower()
    if not PROFILE_ID_PATTERN.fullmatch(normalized_id):
        raise ValueError(f"Invalid model profile id: {profile_id}")
    return normalized_id


def _coerce_active_profile_id(value: Any, profiles: dict[str, Any]) -> str:
    try:
        normalized_id = _normalize_profile_id(str(value))
    except ValueError:
        normalized_id = DEFAULT_ACTIVE_PROFILE_ID
    if normalized_id in profiles:
        return normalized_id
    if DEFAULT_ACTIVE_PROFILE_ID in profiles:
        return DEFAULT_ACTIVE_PROFILE_ID
    return next(iter(profiles), DEFAULT_ACTIVE_PROFILE_ID)


def _coerce_role_bindings(value: Any, profiles: dict[str, Any]) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    bindings: dict[str, str] = {}
    for raw_role_name, raw_profile_id in value.items():
        try:
            role_name = _normalize_role_binding_name(raw_role_name)
            profile_id = _normalize_profile_id(raw_profile_id)
        except ValueError:
            continue
        if profile_id in profiles:
            bindings[role_name] = profile_id
    return bindings


def _normalize_role_binding_name(role_name: Any) -> str:
    raw_name = str(role_name or "").strip()
    if not raw_name:
        raise ValueError("Role name cannot be empty")
    normalized_name = normalize_role_name(raw_name)
    if not normalized_name:
        raise ValueError("Role name cannot be empty")
    return normalized_name


def _require_existing_profile(state: dict[str, Any], profile_id: str) -> None:
    if profile_id not in state["profiles"]:
        raise ValueError(f"Unknown model profile: {profile_id}")


def _clean_label(value: Any) -> str:
    label = _clean_text(value, MAX_LABEL_LENGTH)
    if not label:
        raise ValueError("Model profile label cannot be empty")
    return label


def _next_profile_id(label: str, profiles: dict[str, Any]) -> str:
    base = _slug_from_label(label) or "profile"
    candidate = base
    suffix = 2
    while candidate in profiles:
        suffix_text = f"-{suffix}"
        candidate = f"{base[:MAX_PROFILE_ID_LENGTH - len(suffix_text)]}{suffix_text}"
        suffix += 1
    return candidate


def _slug_from_label(label: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", label.strip().lower())
    normalized = normalized.strip("-")
    if not normalized:
        return "profile"
    return normalized[:MAX_PROFILE_ID_LENGTH].rstrip("-") or "profile"


def _clean_text(value: Any, max_length: int) -> str:
    cleaned = str(value or "").strip()
    if len(cleaned) > max_length:
        raise ValueError("Model profile value is too long")
    return cleaned


def _clean_secret(value: Any) -> str:
    cleaned = str(value or "").strip()
    if len(cleaned) > MAX_SECRET_LENGTH:
        raise ValueError("Model profile secret is too long")
    return cleaned


def _is_configured_secret(value: str) -> bool:
    cleaned = value.strip()
    return bool(cleaned and cleaned.upper() != "EMPTY")


def _env_text(name: str) -> str:
    return os.environ.get(name, "").strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
