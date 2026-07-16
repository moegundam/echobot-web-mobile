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
ADMIN_ALLOWLIST_ENV = "ECHOBOT_ADMIN_ALLOWLIST"
ADMIN_USERS_ENV = "ECHOBOT_ADMIN_USERS"
ADMIN_REQUIRED_ENV = "ECHOBOT_ADMIN_REQUIRED"
DEPLOYMENT_PROFILE_ENV = "ECHOBOT_DEPLOYMENT_PROFILE"
LOCAL_DEPLOYMENT_PROFILES = frozenset({"local", "development", "test"})
EXPOSED_DEPLOYMENT_PROFILES = frozenset({"tunnel", "public", "production", "vps"})
VALID_DEPLOYMENT_PROFILES = LOCAL_DEPLOYMENT_PROFILES | EXPOSED_DEPLOYMENT_PROFILES
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


@dataclass(slots=True, frozen=True)
class AdminAccessConfig:
    allowlist: frozenset[str] = frozenset()
    required: bool = False

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "AdminAccessConfig":
        source = os.environ if env is None else env
        allowlist = frozenset(
            _normalize_admin_user_id(item)
            for item in _csv_values(source.get(ADMIN_ALLOWLIST_ENV, ""))
            + _csv_values(source.get(ADMIN_USERS_ENV, ""))
            if _normalize_admin_user_id(item)
        )
        required = _env_bool(source, ADMIN_REQUIRED_ENV, bool(allowlist))
        return cls(allowlist=allowlist, required=required)

    def is_admin(self, user_id: str) -> bool:
        if "*" in self.allowlist:
            return True
        normalized_user_id = _normalize_admin_user_id(user_id)
        if not self.required and not self.allowlist:
            return True
        return normalized_user_id in self.allowlist


@dataclass(slots=True, frozen=True)
class DeploymentSecurityConfig:
    profile: str = "local"

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
    ) -> "DeploymentSecurityConfig":
        source = os.environ if env is None else env
        profile = str(source.get(DEPLOYMENT_PROFILE_ENV, "local")).strip().lower()
        profile = profile or "local"
        if profile not in VALID_DEPLOYMENT_PROFILES:
            valid_profiles = ", ".join(sorted(VALID_DEPLOYMENT_PROFILES))
            raise ValueError(
                f"{DEPLOYMENT_PROFILE_ENV} must be one of: {valid_profiles}"
            )
        return cls(profile=profile)


def validate_deployment_security(
    deployment: DeploymentSecurityConfig,
    trusted_user: TrustedUserConfig,
    admin_access: AdminAccessConfig,
) -> None:
    if deployment.profile not in EXPOSED_DEPLOYMENT_PROFILES:
        return

    if not trusted_user.enabled or not trusted_user.required:
        raise ValueError(
            f"Deployment profile '{deployment.profile}' requires trusted-user "
            "authentication with ECHOBOT_TRUSTED_USER_HEADER_ENABLED=true and "
            "ECHOBOT_TRUSTED_USER_REQUIRED=true"
        )
    if (
        not admin_access.required
        or not admin_access.allowlist
        or "*" in admin_access.allowlist
    ):
        raise ValueError(
            f"Deployment profile '{deployment.profile}' requires an explicit admin "
            "allowlist and ECHOBOT_ADMIN_REQUIRED=true"
        )


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


def _normalize_admin_user_id(user_id: str) -> str:
    return str(user_id or "").strip().lower()


def _csv_values(raw_value: str) -> list[str]:
    return [
        item.strip()
        for item in str(raw_value or "").split(",")
        if item.strip()
    ]


def _env_bool(source: Mapping[str, str], name: str, default: bool) -> bool:
    raw_value = source.get(name)
    if raw_value is None:
        return default

    cleaned = raw_value.strip().lower()
    if not cleaned:
        return default
    return cleaned not in {"0", "false", "no", "off"}
