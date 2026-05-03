from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from starlette.datastructures import Headers

from ..naming import normalize_name_token


DEFAULT_TRUSTED_USER_HEADER = "Cf-Access-Authenticated-User-Email"
TRUSTED_USER_STATE_KEY = "echobot_user_id"
MAX_TRUSTED_USER_ID_LENGTH = 320
OPENWEBUI_BRIDGE_PATHS = {
    "/api/openwebui/tools/openapi.json",
    "/api/openwebui/stage/events",
    "/api/openwebui/chat",
    "/api/openwebui/sessions",
}


@dataclass(slots=True, frozen=True)
class TrustedUserConfig:
    enabled: bool = False
    required: bool = False
    header_name: str = DEFAULT_TRUSTED_USER_HEADER

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "TrustedUserConfig":
        source = os.environ if env is None else env
        enabled = _env_bool(source, "ECHOBOT_TRUSTED_USER_HEADER_ENABLED", False)
        required = _env_bool(source, "ECHOBOT_TRUSTED_USER_REQUIRED", enabled)
        header_name = (
            source.get("ECHOBOT_TRUSTED_USER_HEADER", DEFAULT_TRUSTED_USER_HEADER).strip()
            or DEFAULT_TRUSTED_USER_HEADER
        )
        return cls(enabled=enabled, required=required, header_name=header_name)


def is_protected_path(path: str) -> bool:
    if path in OPENWEBUI_BRIDGE_PATHS:
        return False
    return (
        path == "/web"
        or path.startswith("/web/")
        or path == "/stage"
        or path.startswith("/stage/")
        or path == "/console"
        or path.startswith("/console/")
        or path == "/messenger"
        or path.startswith("/messenger/")
        or path == "/admin"
        or path.startswith("/admin/")
        or path in {"/docs", "/redoc", "/openapi.json"}
        or path.startswith("/api/")
    )


def resolve_trusted_user_id(
    headers: Headers | Mapping[str, str],
    config: TrustedUserConfig,
) -> str:
    if not config.enabled:
        return ""

    value = str(headers.get(config.header_name, "")).strip()
    if not value:
        return ""
    if not is_valid_trusted_user_id(value):
        raise ValueError("Trusted user header is invalid")
    return value


def is_valid_trusted_user_id(user_id: str) -> bool:
    if not user_id or len(user_id) > MAX_TRUSTED_USER_ID_LENGTH:
        return False
    if any(ord(character) < 32 or ord(character) == 127 for character in user_id):
        return False
    return "/" not in user_id and "\\" not in user_id


def user_storage_key(user_id: str) -> str:
    normalized_user_id = str(user_id or "").strip().lower()
    if not normalized_user_id:
        raise ValueError("Trusted user id cannot be empty")

    label = normalize_name_token(
        normalized_user_id.replace("@", " at ").replace(".", " "),
    )
    digest = hashlib.sha256(normalized_user_id.encode("utf-8")).hexdigest()[:12]
    if not label:
        return digest
    return f"{label[:80]}-{digest}"


def user_storage_root(workspace: Path, user_id: str) -> Path:
    return workspace / ".echobot" / "users" / user_storage_key(user_id)


def _env_bool(source: Mapping[str, str], name: str, default: bool) -> bool:
    raw_value = source.get(name)
    if raw_value is None:
        return default

    cleaned = raw_value.strip().lower()
    if not cleaned:
        return default
    return cleaned not in {"0", "false", "no", "off"}
