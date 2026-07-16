from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

DEFAULT_MAX_SECRET_BYTES = 64 * 1024
DEFAULT_MAX_STORE_BYTES = 1024 * 1024
MAX_SECRET_NAME_LENGTH = 255


class SecretStoreError(RuntimeError):
    """Base error for secret-store failures with sanitized messages."""


class SecretConfigurationError(SecretStoreError):
    """Raised when secret-store configuration is unsafe or invalid."""


class SecretPermissionError(SecretStoreError):
    """Raised when a local secret store has unsafe permissions."""


@dataclass(frozen=True, slots=True)
class SecretMetadata:
    """Non-sensitive information about a secret lookup."""

    configured: bool
    source: str | None = None
    version: str | None = None


@dataclass(frozen=True, slots=True)
class SecretValue:
    """A resolved secret whose representation never includes plaintext."""

    value: str = field(repr=False)
    metadata: SecretMetadata

    def __post_init__(self) -> None:
        if not self.metadata.configured:
            raise ValueError("Resolved secret metadata must be configured")


@runtime_checkable
class SecretStore(Protocol):
    """Provider-neutral read contract for secret stores."""

    def get(self, name: str) -> SecretValue | None:
        """Resolve a secret, returning ``None`` when it is not configured."""

    def metadata(self, name: str) -> SecretMetadata:
        """Return non-sensitive configuration and version metadata."""


def validate_secret_name(name: str) -> str:
    if not isinstance(name, str):
        raise SecretConfigurationError("Secret name must be text")
    if not name or len(name) > MAX_SECRET_NAME_LENGTH:
        raise SecretConfigurationError("Secret name is invalid")
    if "\x00" in name or "=" in name:
        raise SecretConfigurationError("Secret name is invalid")
    return name


def validate_secret_value(value: str, *, max_bytes: int) -> str:
    if not isinstance(value, str):
        raise SecretConfigurationError("Configured secret must be UTF-8 text")
    if not value:
        raise SecretConfigurationError("Configured secret must not be empty")
    encoded_length = _utf8_length(value)
    if encoded_length is None:
        raise SecretConfigurationError("Configured secret must be UTF-8 text")
    if encoded_length > max_bytes:
        raise SecretConfigurationError("Configured secret exceeds the size limit")
    return value


def validate_size_limit(value: int, *, setting_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{setting_name} must be a positive integer")
    return value


def _utf8_length(value: str) -> int | None:
    try:
        return len(value.encode("utf-8", errors="strict"))
    except UnicodeEncodeError:
        return None
