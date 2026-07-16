from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from ._files import read_utf8_file
from .base import (
    DEFAULT_MAX_SECRET_BYTES,
    SecretConfigurationError,
    SecretMetadata,
    SecretValue,
    validate_secret_name,
    validate_secret_value,
    validate_size_limit,
)


class EnvironmentSecretStore:
    """Resolve secrets from one environment variable or its ``_FILE`` peer."""

    def __init__(
        self,
        environment: Mapping[str, str] | None = None,
        *,
        max_secret_bytes: int = DEFAULT_MAX_SECRET_BYTES,
    ) -> None:
        self._environment = os.environ if environment is None else environment
        self._max_secret_bytes = validate_size_limit(
            max_secret_bytes,
            setting_name="max_secret_bytes",
        )

    def get(self, name: str) -> SecretValue | None:
        name = validate_secret_name(name)
        file_name = f"{name}_FILE"
        has_direct_value = name in self._environment
        has_file_value = file_name in self._environment

        if has_direct_value and has_file_value:
            raise SecretConfigurationError(
                "Secret has multiple configured sources"
            )
        if has_direct_value:
            value = validate_secret_value(
                self._environment[name],
                max_bytes=self._max_secret_bytes,
            )
            return SecretValue(
                value=value,
                metadata=SecretMetadata(
                    configured=True,
                    source="environment",
                ),
            )
        if not has_file_value:
            return None

        raw_path = self._environment[file_name]
        if not isinstance(raw_path, str) or not raw_path or "\x00" in raw_path:
            raise SecretConfigurationError("Secret file configuration is invalid")
        secret_file = read_utf8_file(
            Path(raw_path),
            max_bytes=self._max_secret_bytes,
        )
        assert secret_file is not None
        value = validate_secret_value(
            secret_file.text,
            max_bytes=self._max_secret_bytes,
        )
        return SecretValue(
            value=value,
            metadata=SecretMetadata(
                configured=True,
                source="environment_file",
                version=secret_file.version,
            ),
        )

    def metadata(self, name: str) -> SecretMetadata:
        secret = self.get(name)
        if secret is None:
            return SecretMetadata(configured=False)
        return secret.metadata
