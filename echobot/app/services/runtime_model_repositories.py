from __future__ import annotations

import json
import os
import re
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .model_profiles import (
    DEFAULT_ACTIVE_PROFILE_ID,
    DEFAULT_PROFILE_IDS,
    MAX_LABEL_LENGTH,
    MAX_PROFILE_COUNT,
    MAX_PROFILE_ID_LENGTH,
    MAX_SECRET_LENGTH,
    MAX_VALUE_LENGTH,
    ModelProfileService,
    PROFILE_ID_PATTERN,
)


class LLMModelRepository:
    """LLM model repository with a local store and compatibility mirror."""

    def __init__(self, model_profiles: ModelProfileService) -> None:
        self._model_profiles = model_profiles
        self._store = _DomainStore(
            path=model_profiles.storage_root / "llm_models.json",
            secret_path=model_profiles.storage_root / "llm_model_secrets.json",
            active_key="active_model_id",
            collection_key="models",
            default_item=_default_llm_item,
            project_legacy=_llm_item_to_legacy_profile,
            seed_state=lambda: _seed_llm_state(model_profiles),
            seed_secrets=lambda: _seed_llm_secrets(model_profiles),
            secret_sections=("chat",),
            secret_env_names={"chat": "LLM_API_KEY"},
        )
        self._mirror = _CompatibilityMirror(model_profiles)

    def list_payload(self) -> dict[str, Any]:
        return self._store.list_legacy_payload()

    def create(
        self,
        *,
        name: str,
        source_model_id: str | None = None,
    ) -> dict[str, Any]:
        item = self._store.create(name=name, source_id=source_model_id)
        self._mirror.upsert(item["id"], item["name"], {"chat": _llm_item_to_chat(item)})
        return self._store.legacy_profile(item["id"])

    def update(self, model_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        item_updates: dict[str, Any] = {}
        if "name" in updates and updates["name"] is not None:
            item_updates["name"] = updates["name"]
        for key in (
            "provider",
            "model",
            "base_url",
            "temperature",
            "max_tokens",
            "api_key",
            "clear_api_key",
        ):
            if key in updates:
                item_updates[key] = updates[key]

        item = self._store.update(model_id, item_updates)
        self._mirror.upsert(item["id"], item["name"], {"chat": _llm_item_to_chat(item)})
        return self._store.legacy_profile(item["id"])

    def activate(self, model_id: str) -> dict[str, Any]:
        item = self._store.activate(model_id)
        self._mirror.upsert(item["id"], item["name"], {"chat": _llm_item_to_chat(item)})
        self._mirror.activate_if_present(item["id"])
        return self.list_payload()

    def delete(self, model_id: str) -> dict[str, Any]:
        self._store.delete(model_id)
        return self.list_payload()

    def get_runtime_profile(self, model_id: str) -> dict[str, Any]:
        return self._store.legacy_profile(model_id, include_secrets=True)

    def active_runtime_profile(self) -> dict[str, Any]:
        return self._store.active_legacy_profile(include_secrets=True)


class VoiceModelRepository:
    """Voice profile repository with independent STT/TTS storage."""

    def __init__(self, model_profiles: ModelProfileService) -> None:
        self._model_profiles = model_profiles
        self._store = _DomainStore(
            path=model_profiles.storage_root / "voice_profiles.json",
            secret_path=model_profiles.storage_root / "voice_profile_secrets.json",
            active_key="active_voice_profile_id",
            collection_key="profiles",
            default_item=_default_voice_item,
            project_legacy=_voice_item_to_legacy_profile,
            seed_state=lambda: _seed_voice_state(model_profiles),
            seed_secrets=lambda: _seed_voice_secrets(model_profiles),
            secret_sections=("tts", "asr"),
            secret_env_names={
                "tts": "ECHOBOT_TTS_OPENAI_API_KEY",
                "asr": "ECHOBOT_ASR_OPENAI_API_KEY",
            },
        )
        self._mirror = _CompatibilityMirror(model_profiles)

    def list_payload(self) -> dict[str, Any]:
        return self._store.list_legacy_payload()

    def create(
        self,
        *,
        name: str,
        source_profile_id: str | None = None,
    ) -> dict[str, Any]:
        item = self._store.create(name=name, source_id=source_profile_id)
        self._mirror.upsert(item["id"], item["name"], _voice_item_to_sections(item))
        return self._store.legacy_profile(item["id"])

    def update(self, profile_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        item_updates: dict[str, Any] = {}
        if "name" in updates and updates["name"] is not None:
            item_updates["name"] = updates["name"]
        if "tts" in updates and updates["tts"] is not None:
            item_updates["tts"] = dict(updates["tts"] or {})
        if "stt" in updates and updates["stt"] is not None:
            item_updates["asr"] = dict(updates["stt"] or {})

        item = self._store.update(profile_id, item_updates)
        self._mirror.upsert(item["id"], item["name"], _voice_item_to_sections(item))
        return self._store.legacy_profile(item["id"])

    def activate(self, profile_id: str) -> dict[str, Any]:
        item = self._store.activate(profile_id)
        self._mirror.upsert(item["id"], item["name"], _voice_item_to_sections(item))
        self._mirror.activate_if_present(item["id"])
        return self.list_payload()

    def delete(self, profile_id: str) -> dict[str, Any]:
        self._store.delete(profile_id)
        return self.list_payload()

    def get_runtime_profile(self, profile_id: str) -> dict[str, Any]:
        return self._store.legacy_profile(profile_id, include_secrets=True)

    def active_runtime_profile(self) -> dict[str, Any]:
        return self._store.active_legacy_profile(include_secrets=True)


class Live2DModelRepository:
    """Live2D model repository with independent visual-profile storage."""

    def __init__(self, model_profiles: ModelProfileService) -> None:
        self._model_profiles = model_profiles
        self._store = _DomainStore(
            path=model_profiles.storage_root / "live2d_models.json",
            secret_path=None,
            active_key="active_live2d_model_id",
            collection_key="models",
            default_item=_default_live2d_item,
            project_legacy=_live2d_item_to_legacy_profile,
            seed_state=lambda: _seed_live2d_state(model_profiles),
            seed_secrets=lambda: {"profiles": {}},
            secret_sections=(),
            secret_env_names={},
        )
        self._mirror = _CompatibilityMirror(model_profiles)

    def list_payload(self) -> dict[str, Any]:
        return self._store.list_legacy_payload()

    def create(
        self,
        *,
        name: str,
        source_model_id: str | None = None,
    ) -> dict[str, Any]:
        item = self._store.create(name=name, source_id=source_model_id)
        self._mirror.upsert(item["id"], item["name"], {"live2d": _live2d_item_to_section(item)})
        return self._store.legacy_profile(item["id"])

    def update(self, model_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        item_updates: dict[str, Any] = {}
        if "name" in updates and updates["name"] is not None:
            item_updates["name"] = updates["name"]
        if "selection_key" in updates:
            item_updates["selection_key"] = updates["selection_key"]

        item = self._store.update(model_id, item_updates)
        self._mirror.upsert(item["id"], item["name"], {"live2d": _live2d_item_to_section(item)})
        return self._store.legacy_profile(item["id"])

    def activate(self, model_id: str) -> dict[str, Any]:
        item = self._store.activate(model_id)
        self._mirror.upsert(item["id"], item["name"], {"live2d": _live2d_item_to_section(item)})
        self._mirror.activate_if_present(item["id"])
        return self.list_payload()

    def delete(self, model_id: str) -> dict[str, Any]:
        self._store.delete(model_id)
        return self.list_payload()

    def get_runtime_profile(self, model_id: str) -> dict[str, Any]:
        return self._store.legacy_profile(model_id, include_secrets=True)

    def active_runtime_profile(self) -> dict[str, Any]:
        return self._store.active_legacy_profile(include_secrets=True)


class _DomainStore:
    def __init__(
        self,
        *,
        path: Path,
        secret_path: Path | None,
        active_key: str,
        collection_key: str,
        default_item,
        project_legacy,
        seed_state,
        seed_secrets,
        secret_sections: tuple[str, ...],
        secret_env_names: dict[str, str],
    ) -> None:
        self._path = path
        self._secret_path = secret_path
        self._active_key = active_key
        self._collection_key = collection_key
        self._default_item = default_item
        self._project_legacy = project_legacy
        self._seed_state = seed_state
        self._seed_secrets = seed_secrets
        self._secret_sections = secret_sections
        self._secret_env_names = secret_env_names
        self._lock = threading.Lock()

    def list_legacy_payload(self) -> dict[str, Any]:
        with self._lock:
            state = self._load_state_unlocked()
            secrets = self._load_secrets_unlocked()
            return self._legacy_payload_from_state(state, secrets)

    def legacy_profile(self, item_id: str, *, include_secrets: bool = False) -> dict[str, Any]:
        normalized_id = _normalize_id(item_id)
        with self._lock:
            state = self._load_state_unlocked()
            item = self._require_item(state, normalized_id)
            secrets = self._load_secrets_unlocked()
            return self._legacy_profile_from_item(
                item,
                secrets,
                include_secrets=include_secrets,
            )

    def active_legacy_profile(self, *, include_secrets: bool = False) -> dict[str, Any]:
        with self._lock:
            state = self._load_state_unlocked()
            secrets = self._load_secrets_unlocked()
            item = self._require_item(state, state[self._active_key])
            return self._legacy_profile_from_item(
                item,
                secrets,
                include_secrets=include_secrets,
            )

    def create(self, *, name: str, source_id: str | None = None) -> dict[str, Any]:
        normalized_name = _clean_label(name)
        with self._lock:
            state = self._load_state_unlocked()
            if len(state[self._collection_key]) >= MAX_PROFILE_COUNT:
                raise ValueError(f"Model profile limit reached: {MAX_PROFILE_COUNT}")
            if source_id:
                source_item = deepcopy(self._require_item(state, _normalize_id(source_id)))
                item = source_item
            else:
                item = self._default_item("")
            item_id = _next_id(normalized_name, state[self._collection_key])
            item["id"] = item_id
            item["name"] = normalized_name
            item["updated_at"] = _now_iso()
            state[self._collection_key][item_id] = item
            self._save_state_unlocked(state)
            return self._public_item(item, self._load_secrets_unlocked())

    def update(self, item_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        normalized_id = _normalize_id(item_id)
        with self._lock:
            state = self._load_state_unlocked()
            item = self._require_item(state, normalized_id)
            secrets = self._load_secrets_unlocked()
            normalized_updates = _normalize_item_updates(updates, self._secret_sections)
            if "name" in normalized_updates:
                item["name"] = normalized_updates["name"]
            for key, value in normalized_updates.items():
                if key in {"name", "secrets"}:
                    continue
                if isinstance(value, dict) and isinstance(item.get(key), dict):
                    item[key].update(value)
                else:
                    item[key] = value
            _apply_secret_updates(secrets, normalized_id, normalized_updates.get("secrets", {}))
            item["updated_at"] = _now_iso()
            self._save_state_unlocked(state)
            self._save_secrets_unlocked(secrets)
            return self._public_item(item, secrets)

    def activate(self, item_id: str) -> dict[str, Any]:
        normalized_id = _normalize_id(item_id)
        with self._lock:
            state = self._load_state_unlocked()
            item = self._require_item(state, normalized_id)
            state[self._active_key] = normalized_id
            item["updated_at"] = _now_iso()
            self._save_state_unlocked(state)
            return self._public_item(item, self._load_secrets_unlocked())

    def delete(self, item_id: str) -> None:
        normalized_id = _normalize_id(item_id)
        with self._lock:
            state = self._load_state_unlocked()
            self._require_item(state, normalized_id)
            if normalized_id == state[self._active_key]:
                raise ValueError("Active model profile cannot be deleted")
            if len(state[self._collection_key]) <= 1:
                raise ValueError("Last model profile cannot be deleted")
            state[self._collection_key].pop(normalized_id, None)
            secrets = self._load_secrets_unlocked()
            secrets.setdefault("profiles", {}).pop(normalized_id, None)
            self._save_state_unlocked(state)
            self._save_secrets_unlocked(secrets)

    def _load_state_unlocked(self) -> dict[str, Any]:
        if not self._path.exists():
            state = self._default_state()
            self._save_state_unlocked(state)
            return state
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Runtime model store must contain a JSON object")
        state = self._empty_state()
        raw_items = payload.get(self._collection_key, {})
        if isinstance(raw_items, dict):
            for raw_id, raw_item in raw_items.items():
                if not isinstance(raw_item, dict):
                    continue
                try:
                    item_id = _normalize_id(raw_id)
                except ValueError:
                    continue
                state[self._collection_key][item_id] = _merge_item(
                    self._default_item(item_id),
                    raw_item,
                )
        if not state[self._collection_key]:
            state = self._default_state()
        state[self._active_key] = _coerce_active_id(
            payload.get(self._active_key),
            state[self._collection_key],
        )
        return state

    def _save_state_unlocked(self, state: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _load_secrets_unlocked(self) -> dict[str, Any]:
        if self._secret_path is None or not self._secret_path.exists():
            secrets = self._seed_secrets()
            return secrets if isinstance(secrets, dict) else {"profiles": {}}
        payload = json.loads(self._secret_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Runtime model secret store must contain a JSON object")
        profiles = payload.get("profiles", {})
        return {"profiles": profiles if isinstance(profiles, dict) else {}}

    def _save_secrets_unlocked(self, secrets: dict[str, Any]) -> None:
        if self._secret_path is None:
            return
        self._secret_path.parent.mkdir(parents=True, exist_ok=True)
        self._secret_path.write_text(
            json.dumps(secrets, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        try:
            self._secret_path.chmod(0o600)
        except OSError:
            pass

    def _default_state(self) -> dict[str, Any]:
        seeded_state = self._seed_state()
        if isinstance(seeded_state, dict) and isinstance(
            seeded_state.get(self._collection_key),
            dict,
        ) and seeded_state[self._collection_key]:
            return {
                self._active_key: _coerce_active_id(
                    seeded_state.get(self._active_key),
                    seeded_state[self._collection_key],
                ),
                self._collection_key: seeded_state[self._collection_key],
            }
        seeded_items = {
            item_id: self._default_item(item_id)
            for item_id in DEFAULT_PROFILE_IDS
        }
        return {
            self._active_key: DEFAULT_ACTIVE_PROFILE_ID,
            self._collection_key: seeded_items,
        }

    def _empty_state(self) -> dict[str, Any]:
        return {
            self._active_key: DEFAULT_ACTIVE_PROFILE_ID,
            self._collection_key: {},
        }

    def _require_item(self, state: dict[str, Any], item_id: str) -> dict[str, Any]:
        item = state[self._collection_key].get(item_id)
        if not isinstance(item, dict):
            raise ValueError(f"Unknown model profile: {item_id}")
        return item

    def _legacy_payload_from_state(
        self,
        state: dict[str, Any],
        secrets: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "active_profile_id": state[self._active_key],
            "role_bindings": {},
            "profiles": [
                self._legacy_profile_from_item(item, secrets, include_secrets=False)
                for item in state[self._collection_key].values()
            ],
        }

    def _legacy_profile_from_item(
        self,
        item: dict[str, Any],
        secrets: dict[str, Any],
        *,
        include_secrets: bool,
    ) -> dict[str, Any]:
        public_item = (
            deepcopy(item)
            if include_secrets
            else self._public_item(item, secrets)
        )
        if include_secrets:
            _inject_effective_secrets(
                public_item,
                secrets,
                item["id"],
                self._secret_sections,
                self._secret_env_names,
            )
        return self._project_legacy(public_item)

    def _public_item(self, item: dict[str, Any], secrets: dict[str, Any]) -> dict[str, Any]:
        public = deepcopy(item)
        for section in self._secret_sections:
            _strip_secret_section(
                public,
                secrets,
                item["id"],
                section,
                self._secret_env_names.get(section, ""),
            )
        return public


class _CompatibilityMirror:
    def __init__(self, model_profiles: ModelProfileService) -> None:
        self._model_profiles = model_profiles

    def upsert(
        self,
        profile_id: str,
        label: str,
        sections: dict[str, dict[str, Any]],
    ) -> None:
        updates: dict[str, Any] = {"label": label}
        updates.update(sections)
        mirror_id = self._ensure_profile(profile_id, label)
        self._model_profiles.update_profile(mirror_id, updates)

    def activate_if_present(self, profile_id: str) -> None:
        try:
            self._model_profiles.activate_profile(profile_id)
        except ValueError:
            pass

    def _ensure_profile(self, profile_id: str, label: str) -> str:
        try:
            self._model_profiles.get_profile(profile_id)
            return profile_id
        except ValueError:
            created = self._model_profiles.create_profile(label=label)
            return str(created.get("profile_id") or profile_id)


def _seed_llm_state(model_profiles: ModelProfileService) -> dict[str, Any]:
    payload = model_profiles.list_profiles()
    items: dict[str, dict[str, Any]] = {}
    for profile in _legacy_profiles(payload):
        profile_id = str(profile.get("profile_id") or "")
        chat = _legacy_section(profile, "chat")
        items[profile_id] = {
            "id": profile_id,
            "name": str(profile.get("label") or profile_id),
            "provider": str(chat.get("provider") or "openai-compatible"),
            "model": str(chat.get("model") or ""),
            "base_url": str(chat.get("base_url") or ""),
            "temperature": chat.get("temperature"),
            "max_tokens": chat.get("max_tokens"),
            "updated_at": str(profile.get("updated_at") or ""),
        }
    return {
        "active_model_id": str(payload.get("active_profile_id") or DEFAULT_ACTIVE_PROFILE_ID),
        "models": items,
    }


def _seed_llm_secrets(model_profiles: ModelProfileService) -> dict[str, Any]:
    payload = model_profiles.list_profiles()
    secrets: dict[str, Any] = {"profiles": {}}
    for profile in _legacy_profiles(payload):
        profile_id = str(profile.get("profile_id") or "")
        chat = _legacy_section(profile, "chat")
        if str(chat.get("api_key_source") or "") != "profile":
            continue
        runtime_profile = model_profiles.get_profile_for_runtime(profile_id)
        api_key = _legacy_section(runtime_profile, "chat").get("api_key")
        if api_key:
            secrets["profiles"].setdefault(profile_id, {})["chat"] = {
                "api_key": _clean_secret(api_key),
            }
    return secrets


def _seed_voice_state(model_profiles: ModelProfileService) -> dict[str, Any]:
    payload = model_profiles.list_profiles()
    items: dict[str, dict[str, Any]] = {}
    for profile in _legacy_profiles(payload):
        profile_id = str(profile.get("profile_id") or "")
        items[profile_id] = {
            "id": profile_id,
            "name": str(profile.get("label") or profile_id),
            "tts": _speech_seed_section(_legacy_section(profile, "tts")),
            "asr": _speech_seed_section(_legacy_section(profile, "asr")),
            "updated_at": str(profile.get("updated_at") or ""),
        }
    return {
        "active_voice_profile_id": str(payload.get("active_profile_id") or DEFAULT_ACTIVE_PROFILE_ID),
        "profiles": items,
    }


def _seed_voice_secrets(model_profiles: ModelProfileService) -> dict[str, Any]:
    payload = model_profiles.list_profiles()
    secrets: dict[str, Any] = {"profiles": {}}
    for profile in _legacy_profiles(payload):
        profile_id = str(profile.get("profile_id") or "")
        runtime_profile = model_profiles.get_profile_for_runtime(profile_id)
        for section in ("tts", "asr"):
            public_section = _legacy_section(profile, section)
            if str(public_section.get("api_key_source") or "") != "profile":
                continue
            api_key = _legacy_section(runtime_profile, section).get("api_key")
            if api_key:
                secrets["profiles"].setdefault(profile_id, {})[section] = {
                    "api_key": _clean_secret(api_key),
                }
    return secrets


def _seed_live2d_state(model_profiles: ModelProfileService) -> dict[str, Any]:
    payload = model_profiles.list_profiles()
    items: dict[str, dict[str, Any]] = {}
    for profile in _legacy_profiles(payload):
        profile_id = str(profile.get("profile_id") or "")
        live2d = _legacy_section(profile, "live2d")
        items[profile_id] = {
            "id": profile_id,
            "name": str(profile.get("label") or profile_id),
            "selection_key": str(live2d.get("selection_key") or ""),
            "updated_at": str(profile.get("updated_at") or ""),
        }
    return {
        "active_live2d_model_id": str(payload.get("active_profile_id") or DEFAULT_ACTIVE_PROFILE_ID),
        "models": items,
    }


def _default_llm_item(item_id: str) -> dict[str, Any]:
    name = f"Profile {item_id.upper()}" if item_id else "New LLM Model"
    return {
        "id": item_id,
        "name": name,
        "provider": _env_text("LLM_PROVIDER", "openai-compatible"),
        "model": _env_text("LLM_MODEL"),
        "base_url": _env_text("LLM_BASE_URL"),
        "temperature": None,
        "max_tokens": None,
        "updated_at": "",
    }


def _default_voice_item(item_id: str) -> dict[str, Any]:
    name = f"Profile {item_id.upper()}" if item_id else "New Voice Profile"
    return {
        "id": item_id,
        "name": name,
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
        "updated_at": "",
    }


def _default_live2d_item(item_id: str) -> dict[str, Any]:
    name = f"Profile {item_id.upper()}" if item_id else "New Live2D Model"
    return {
        "id": item_id,
        "name": name,
        "selection_key": _env_text("ECHOBOT_WEB_LIVE2D_MODEL"),
        "updated_at": "",
    }


def _llm_item_to_legacy_profile(item: dict[str, Any]) -> dict[str, Any]:
    profile_id = str(item.get("id") or "")
    return {
        "profile_id": profile_id,
        "label": str(item.get("name") or profile_id),
        "chat": _llm_item_to_chat(item),
        "tts": {},
        "asr": {},
        "live2d": {},
        "updated_at": str(item.get("updated_at") or ""),
    }


def _voice_item_to_legacy_profile(item: dict[str, Any]) -> dict[str, Any]:
    profile_id = str(item.get("id") or "")
    sections = _voice_item_to_sections(item)
    return {
        "profile_id": profile_id,
        "label": str(item.get("name") or profile_id),
        "chat": {},
        "tts": sections["tts"],
        "asr": sections["asr"],
        "live2d": {},
        "updated_at": str(item.get("updated_at") or ""),
    }


def _live2d_item_to_legacy_profile(item: dict[str, Any]) -> dict[str, Any]:
    profile_id = str(item.get("id") or "")
    return {
        "profile_id": profile_id,
        "label": str(item.get("name") or profile_id),
        "chat": {},
        "tts": {},
        "asr": {},
        "live2d": _live2d_item_to_section(item),
        "updated_at": str(item.get("updated_at") or ""),
    }


def _llm_item_to_chat(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": str(item.get("provider") or "openai-compatible"),
        "model": str(item.get("model") or ""),
        "base_url": str(item.get("base_url") or ""),
        "temperature": item.get("temperature"),
        "max_tokens": item.get("max_tokens"),
        **({"api_key": item["api_key"]} if item.get("api_key") else {}),
        **({"api_key_configured": item["api_key_configured"]} if "api_key_configured" in item else {}),
        **({"api_key_source": item["api_key_source"]} if "api_key_source" in item else {}),
    }


def _voice_item_to_sections(item: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        "tts": _speech_section(item.get("tts")),
        "asr": _speech_section(item.get("asr")),
    }


def _speech_section(value: Any) -> dict[str, Any]:
    section = value if isinstance(value, dict) else {}
    return {
        "provider": str(section.get("provider") or ""),
        "model": str(section.get("model") or ""),
        "base_url": str(section.get("base_url") or ""),
        "voice": str(section.get("voice") or ""),
        "language": str(section.get("language") or ""),
        **({"api_key": section["api_key"]} if section.get("api_key") else {}),
        **({"api_key_configured": section["api_key_configured"]} if "api_key_configured" in section else {}),
        **({"api_key_source": section["api_key_source"]} if "api_key_source" in section else {}),
    }


def _speech_seed_section(section: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": str(section.get("provider") or ""),
        "model": str(section.get("model") or ""),
        "base_url": str(section.get("base_url") or ""),
        "voice": str(section.get("voice") or ""),
        "language": str(section.get("language") or ""),
    }


def _live2d_item_to_section(item: dict[str, Any]) -> dict[str, Any]:
    return {"selection_key": str(item.get("selection_key") or "")}


def _merge_item(default_item: dict[str, Any], raw_item: dict[str, Any]) -> dict[str, Any]:
    item = deepcopy(default_item)
    updates = _normalize_item_updates(raw_item, ())
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(item.get(key), dict):
            item[key].update(value)
        else:
            item[key] = value
    item["id"] = default_item["id"]
    item["updated_at"] = _clean_text(raw_item.get("updated_at", ""), MAX_VALUE_LENGTH)
    return item


def _normalize_item_updates(
    updates: dict[str, Any],
    secret_sections: tuple[str, ...],
) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    secret_updates: dict[str, Any] = {}
    if "name" in updates and updates["name"] is not None:
        normalized["name"] = _clean_label(updates["name"])
    for key in ("provider", "model", "base_url", "selection_key"):
        if key in updates:
            normalized[key] = _clean_text(updates[key], MAX_VALUE_LENGTH)
    if "temperature" in updates:
        value = updates["temperature"]
        normalized["temperature"] = None if value is None else float(value)
    if "max_tokens" in updates:
        value = updates["max_tokens"]
        normalized["max_tokens"] = None if value is None else int(value)
    for section in ("tts", "asr"):
        if section not in updates or updates[section] is None:
            continue
        raw_section = updates[section]
        if not isinstance(raw_section, dict):
            raise ValueError(f"Model profile {section} settings must be an object")
        normalized[section] = {}
        for key in ("provider", "model", "base_url", "voice", "language"):
            if key in raw_section:
                normalized[section][key] = _clean_text(raw_section[key], MAX_VALUE_LENGTH)
        section_secret_updates = _secret_updates_from_section(raw_section)
        if section in secret_sections and section_secret_updates:
            secret_updates[section] = section_secret_updates
    if "api_key" in updates or "clear_api_key" in updates:
        chat_secret_updates = _secret_updates_from_section(updates)
        if "chat" in secret_sections and chat_secret_updates:
            secret_updates["chat"] = chat_secret_updates
    if secret_updates:
        normalized["secrets"] = secret_updates
    return normalized


def _secret_updates_from_section(section: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if bool(section.get("clear_api_key", False)):
        updates["clear_api_key"] = True
    if "api_key" in section:
        api_key = _clean_secret(section.get("api_key", ""))
        if api_key:
            updates["api_key"] = api_key
    return updates


def _apply_secret_updates(
    secrets: dict[str, Any],
    item_id: str,
    updates: dict[str, Any],
) -> None:
    profiles = secrets.setdefault("profiles", {})
    profile_secrets = profiles.setdefault(item_id, {})
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
        profiles.pop(item_id, None)


def _strip_secret_section(
    item: dict[str, Any],
    secrets: dict[str, Any],
    item_id: str,
    section: str,
    env_name: str,
) -> None:
    target = item if section == "chat" else item.get(section, {})
    if not isinstance(target, dict):
        return
    target.pop("api_key", None)
    configured, source = _secret_status(secrets, item_id, section, env_name)
    target["api_key_configured"] = configured
    target["api_key_source"] = source


def _inject_effective_secrets(
    item: dict[str, Any],
    secrets: dict[str, Any],
    item_id: str,
    sections: tuple[str, ...],
    env_names: dict[str, str],
) -> None:
    for section in sections:
        api_key = _effective_secret(secrets, item_id, section, env_names.get(section, ""))
        if not api_key:
            continue
        target = item if section == "chat" else item.setdefault(section, {})
        if isinstance(target, dict):
            target["api_key"] = api_key


def _effective_secret(
    secrets: dict[str, Any],
    item_id: str,
    section: str,
    env_name: str,
) -> str:
    profile_secret = _profile_secret(secrets, item_id, section)
    if profile_secret:
        return profile_secret
    return os.environ.get(env_name, "").strip() if env_name else ""


def _secret_status(
    secrets: dict[str, Any],
    item_id: str,
    section: str,
    env_name: str,
) -> tuple[bool, str]:
    if _profile_secret(secrets, item_id, section):
        return True, "profile"
    env_secret = os.environ.get(env_name, "").strip() if env_name else ""
    if _is_configured_secret(env_secret):
        return True, "environment"
    return False, ""


def _profile_secret(secrets: dict[str, Any], item_id: str, section: str) -> str:
    raw_profile = secrets.get("profiles", {}).get(item_id, {})
    if not isinstance(raw_profile, dict):
        return ""
    raw_section = raw_profile.get(section, {})
    if not isinstance(raw_section, dict):
        return ""
    return _clean_secret(raw_section.get("api_key", ""))


def _coerce_active_id(value: Any, items: dict[str, Any]) -> str:
    try:
        normalized_id = _normalize_id(str(value))
    except ValueError:
        normalized_id = DEFAULT_ACTIVE_PROFILE_ID
    if normalized_id in items:
        return normalized_id
    if DEFAULT_ACTIVE_PROFILE_ID in items:
        return DEFAULT_ACTIVE_PROFILE_ID
    return next(iter(items), DEFAULT_ACTIVE_PROFILE_ID)


def _legacy_profiles(payload: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = payload.get("profiles")
    if not isinstance(profiles, list):
        return []
    return [profile for profile in profiles if isinstance(profile, dict)]


def _legacy_section(profile: dict[str, Any], section_name: str) -> dict[str, Any]:
    section = profile.get(section_name)
    return section if isinstance(section, dict) else {}


def _normalize_id(item_id: str) -> str:
    normalized_id = str(item_id or "").strip().lower()
    if not PROFILE_ID_PATTERN.fullmatch(normalized_id):
        raise ValueError(f"Invalid model profile id: {item_id}")
    return normalized_id


def _next_id(label: str, items: dict[str, Any]) -> str:
    base = _slug_from_label(label) or "profile"
    candidate = base
    suffix = 2
    while candidate in items:
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


def _clean_label(value: Any) -> str:
    label = _clean_text(value, MAX_LABEL_LENGTH)
    if not label:
        raise ValueError("Model profile label cannot be empty")
    return label


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


def _env_text(name: str, default: str = "") -> str:
    return os.environ.get(name, "").strip() or default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
