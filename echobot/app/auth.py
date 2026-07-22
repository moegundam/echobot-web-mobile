from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from starlette.datastructures import Headers

from ..naming import normalize_name_token


DEFAULT_TRUSTED_USER_HEADER = "Cf-Access-Authenticated-User-Email"
DEFAULT_TRUSTED_ASSERTION_HEADER = "Cf-Access-Jwt-Assertion"
TRUSTED_USER_STATE_KEY = "echobot_user_id"
MAX_TRUSTED_USER_ID_LENGTH = 320
MAX_TRUSTED_ASSERTION_LENGTH = 16 * 1024
ADMIN_ALLOWLIST_ENV = "ECHOBOT_ADMIN_ALLOWLIST"
ADMIN_USERS_ENV = "ECHOBOT_ADMIN_USERS"
ADMIN_REQUIRED_ENV = "ECHOBOT_ADMIN_REQUIRED"
OPERATOR_ALLOWLIST_ENV = "ECHOBOT_OPERATOR_ALLOWLIST"
OPERATOR_USERS_ENV = "ECHOBOT_OPERATOR_USERS"
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


class AccessRole(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    USER = "user"


@dataclass(slots=True, frozen=True)
class TrustedUserConfig:
    enabled: bool = False
    required: bool = False
    header_name: str = DEFAULT_TRUSTED_USER_HEADER
    assertion_required: bool = False
    assertion_header_name: str = DEFAULT_TRUSTED_ASSERTION_HEADER

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "TrustedUserConfig":
        source = os.environ if env is None else env
        enabled = _env_bool(source, "ECHOBOT_TRUSTED_USER_HEADER_ENABLED", False)
        required = _env_bool(source, "ECHOBOT_TRUSTED_USER_REQUIRED", enabled)
        header_name = (
            source.get("ECHOBOT_TRUSTED_USER_HEADER", DEFAULT_TRUSTED_USER_HEADER).strip()
            or DEFAULT_TRUSTED_USER_HEADER
        )
        assertion_required = _env_bool(
            source,
            "ECHOBOT_TRUSTED_USER_ASSERTION_REQUIRED",
            False,
        )
        assertion_header_name = (
            source.get(
                "ECHOBOT_TRUSTED_USER_ASSERTION_HEADER",
                DEFAULT_TRUSTED_ASSERTION_HEADER,
            ).strip()
            or DEFAULT_TRUSTED_ASSERTION_HEADER
        )
        return cls(
            enabled=enabled,
            required=required,
            header_name=header_name,
            assertion_required=assertion_required,
            assertion_header_name=assertion_header_name,
        )


@dataclass(slots=True, frozen=True)
class AdminAccessConfig:
    allowlist: frozenset[str] = frozenset()
    required: bool = False

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "AdminAccessConfig":
        source = os.environ if env is None else env
        allowlist = frozenset(
            _normalize_access_user_id(item)
            for item in _csv_values(source.get(ADMIN_ALLOWLIST_ENV, ""))
            + _csv_values(source.get(ADMIN_USERS_ENV, ""))
            if _normalize_access_user_id(item)
        )
        required = _env_bool(source, ADMIN_REQUIRED_ENV, bool(allowlist))
        return cls(allowlist=allowlist, required=required)

    def is_admin(self, user_id: str) -> bool:
        if "*" in self.allowlist:
            return True
        normalized_user_id = _normalize_access_user_id(user_id)
        if not self.required and not self.allowlist:
            return True
        return normalized_user_id in self.allowlist


@dataclass(slots=True, frozen=True)
class OperatorAccessConfig:
    allowlist: frozenset[str] = frozenset()

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "OperatorAccessConfig":
        source = os.environ if env is None else env
        allowlist = frozenset(
            _normalize_access_user_id(item)
            for item in _csv_values(source.get(OPERATOR_ALLOWLIST_ENV, ""))
            + _csv_values(source.get(OPERATOR_USERS_ENV, ""))
            if _normalize_access_user_id(item)
        )
        return cls(allowlist=allowlist)

    def is_operator(self, user_id: str) -> bool:
        if "*" in self.allowlist:
            return True
        return _normalize_access_user_id(user_id) in self.allowlist


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
    operator_access: OperatorAccessConfig | None = None,
) -> None:
    if deployment.profile not in EXPOSED_DEPLOYMENT_PROFILES:
        return

    if not trusted_user.enabled or not trusted_user.required:
        raise ValueError(
            f"Deployment profile '{deployment.profile}' requires trusted-user "
            "authentication with ECHOBOT_TRUSTED_USER_HEADER_ENABLED=true and "
            "ECHOBOT_TRUSTED_USER_REQUIRED=true"
        )
    if not trusted_user.assertion_required:
        raise ValueError(
            f"Deployment profile '{deployment.profile}' requires a proxy-validated "
            "Cloudflare Access JWT assertion with "
            "ECHOBOT_TRUSTED_USER_ASSERTION_REQUIRED=true"
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
    if operator_access is not None and "*" in operator_access.allowlist:
        raise ValueError(
            f"Deployment profile '{deployment.profile}' requires an explicit operator "
            "allowlist; wildcard operator access is not allowed"
        )


def resolve_access_role(
    user_id: str,
    trusted_user: TrustedUserConfig,
    admin_access: AdminAccessConfig,
    operator_access: OperatorAccessConfig,
) -> AccessRole:
    if trusted_user.enabled:
        if not user_id:
            return AccessRole.USER
        if admin_access.allowlist and admin_access.is_admin(user_id):
            return AccessRole.ADMIN
        if operator_access.is_operator(user_id):
            return AccessRole.OPERATOR
        return AccessRole.USER

    if admin_access.is_admin(user_id):
        return AccessRole.ADMIN
    if operator_access.is_operator(user_id):
        return AccessRole.OPERATOR
    return AccessRole.USER


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
        or path == "/guide"
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
    if config.assertion_required:
        assertion = str(headers.get(config.assertion_header_name, "")).strip()
        assertion_user_id = _access_assertion_user_id(assertion)
        if assertion_user_id.casefold() != value.casefold():
            raise ValueError("Trusted user assertion does not match user header")
    return value


def is_cross_site_mutation(
    method: str,
    headers: Headers | Mapping[str, str],
) -> bool:
    if str(method or "").upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
        return False

    fetch_site = str(headers.get("Sec-Fetch-Site", "")).strip().lower()
    if fetch_site == "cross-site":
        return True

    origin = str(headers.get("Origin", "")).strip()
    if not origin:
        return False
    if origin.lower() == "null":
        return True

    host = str(headers.get("Host", "")).strip().lower()
    try:
        parsed_origin = urlsplit(origin)
        origin_authority = parsed_origin.netloc.lower()
        valid_origin = (
            parsed_origin.scheme.lower() in {"http", "https"}
            and bool(origin_authority)
            and not parsed_origin.username
            and not parsed_origin.password
            and parsed_origin.path in {"", "/"}
            and not parsed_origin.query
            and not parsed_origin.fragment
        )
    except ValueError:
        return True
    return not valid_origin or not host or origin_authority != host


def is_valid_trusted_user_id(user_id: str) -> bool:
    if not user_id or len(user_id) > MAX_TRUSTED_USER_ID_LENGTH:
        return False
    if any(ord(character) < 32 or ord(character) == 127 for character in user_id):
        return False
    return "/" not in user_id and "\\" not in user_id


def _access_assertion_user_id(assertion: str) -> str:
    # Cryptographic validation belongs to cloudflared's originRequest.access gate.
    # This local check only binds the validated assertion identity to the header.
    if not assertion or len(assertion) > MAX_TRUSTED_ASSERTION_LENGTH:
        raise ValueError("Trusted user assertion is invalid")

    parts = assertion.split(".")
    if len(parts) != 3 or not parts[1]:
        raise ValueError("Trusted user assertion is invalid")
    payload_segment = parts[1]
    padding = "=" * (-len(payload_segment) % 4)
    try:
        payload_bytes = base64.b64decode(
            (payload_segment + padding).encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (binascii.Error, UnicodeError, ValueError, TypeError) as exc:
        raise ValueError("Trusted user assertion is invalid") from exc

    user_id = str(payload.get("email") or "").strip() if isinstance(payload, dict) else ""
    if not is_valid_trusted_user_id(user_id):
        raise ValueError("Trusted user assertion is invalid")
    return user_id


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


def _normalize_access_user_id(user_id: str) -> str:
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
