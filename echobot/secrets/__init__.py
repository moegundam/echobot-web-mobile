"""Provider-neutral secret-store contracts and local adapters."""

from .base import (
    DEFAULT_MAX_SECRET_BYTES,
    DEFAULT_MAX_STORE_BYTES,
    SecretConfigurationError,
    SecretMetadata,
    SecretPermissionError,
    SecretStore,
    SecretStoreError,
    SecretValue,
)
from .environment import EnvironmentSecretStore
from .local_json import LocalJsonSecretStore

__all__ = [
    "DEFAULT_MAX_SECRET_BYTES",
    "DEFAULT_MAX_STORE_BYTES",
    "EnvironmentSecretStore",
    "LocalJsonSecretStore",
    "SecretConfigurationError",
    "SecretMetadata",
    "SecretPermissionError",
    "SecretStore",
    "SecretStoreError",
    "SecretValue",
]
