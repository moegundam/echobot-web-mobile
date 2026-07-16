from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ._files import descriptor_version, read_utf8_file
from .base import (
    DEFAULT_MAX_SECRET_BYTES,
    DEFAULT_MAX_STORE_BYTES,
    SecretConfigurationError,
    SecretMetadata,
    SecretStoreError,
    SecretValue,
    validate_secret_name,
    validate_secret_value,
    validate_size_limit,
)


class _DuplicateNameError(ValueError):
    pass


class LocalJsonSecretStore:
    """Local flat-JSON compatibility store with restrictive atomic writes."""

    def __init__(
        self,
        path: str | Path,
        *,
        max_file_bytes: int = DEFAULT_MAX_STORE_BYTES,
        max_secret_bytes: int = DEFAULT_MAX_SECRET_BYTES,
    ) -> None:
        self._path = Path(path)
        self._max_file_bytes = validate_size_limit(
            max_file_bytes,
            setting_name="max_file_bytes",
        )
        self._max_secret_bytes = validate_size_limit(
            max_secret_bytes,
            setting_name="max_secret_bytes",
        )
        self._lock = threading.RLock()

    def get(self, name: str) -> SecretValue | None:
        name = validate_secret_name(name)
        with self._lock:
            secrets, version = self._load()
            value = secrets.get(name)
            if value is None:
                return None
            assert version is not None
            return SecretValue(
                value=value,
                metadata=SecretMetadata(
                    configured=True,
                    source="local_json",
                    version=version,
                ),
            )

    def metadata(self, name: str) -> SecretMetadata:
        secret = self.get(name)
        if secret is None:
            return SecretMetadata(configured=False)
        return secret.metadata

    def get_many(self, names: list[str] | tuple[str, ...]) -> dict[str, SecretValue]:
        validated_names = [validate_secret_name(name) for name in names]
        with self._lock:
            secrets, version = self._load()
        if version is None:
            return {}
        metadata = SecretMetadata(
            configured=True,
            source="local_json",
            version=version,
        )
        return {
            name: SecretValue(value=secrets[name], metadata=metadata)
            for name in validated_names
            if name in secrets
        }

    def set(self, name: str, value: str) -> SecretMetadata:
        name = validate_secret_name(name)
        value = validate_secret_value(value, max_bytes=self._max_secret_bytes)
        with self._lock:
            secrets, _ = self._load()
            secrets[name] = value
            version = self._write(secrets)
        return SecretMetadata(
            configured=True,
            source="local_json",
            version=version,
        )

    def delete(self, name: str) -> SecretMetadata:
        name = validate_secret_name(name)
        with self._lock:
            secrets, _ = self._load()
            if name in secrets:
                del secrets[name]
                self._write(secrets)
        return SecretMetadata(configured=False)

    def replace_all(self, values: Mapping[str, str]) -> SecretMetadata:
        """Validate then atomically replace the complete local snapshot."""

        validated: dict[str, str] = {}
        for raw_name, raw_value in values.items():
            name = validate_secret_name(raw_name)
            value = validate_secret_value(
                raw_value,
                max_bytes=self._max_secret_bytes,
            )
            validated[name] = value
        with self._lock:
            version = self._write(validated)
        return SecretMetadata(
            configured=bool(validated),
            source="local_json" if validated else None,
            version=version,
        )

    def _load(self) -> tuple[dict[str, str], str | None]:
        stored_file = read_utf8_file(
            self._path,
            max_bytes=self._max_file_bytes,
            require_restricted_permissions=True,
            allow_symlinks=False,
            missing_ok=True,
        )
        if stored_file is None:
            return {}, None

        valid_json, payload = _load_json(stored_file.text)
        if not valid_json:
            raise SecretStoreError(
                "Local JSON secret store contains invalid JSON"
            )
        if not isinstance(payload, dict):
            raise SecretStoreError("Local JSON secret store must contain an object")

        secrets: dict[str, str] = {}
        for raw_name, raw_value in payload.items():
            valid_entry, name, value = _validate_json_entry(
                raw_name,
                raw_value,
                max_secret_bytes=self._max_secret_bytes,
            )
            if not valid_entry:
                raise SecretStoreError(
                    "Local JSON secret store contains an invalid entry"
                )
            assert name is not None
            assert value is not None
            secrets[name] = value
        return secrets, stored_file.version

    def _write(self, secrets: dict[str, str]) -> str:
        text = json.dumps(
            secrets,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        content = text.encode("utf-8")
        if len(content) > self._max_file_bytes:
            raise SecretStoreError("Local JSON secret store exceeds the size limit")

        parent = self._path.parent
        temporary_path: Path | None = None
        descriptor: int | None = None
        try:
            parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor, temporary_name = tempfile.mkstemp(
                dir=parent,
                prefix=f".{self._path.name}.",
            )
            temporary_path = Path(temporary_name)
            os.fchmod(descriptor, 0o600)
            _write_all(descriptor, content)
            os.fsync(descriptor)
            version = descriptor_version(descriptor)
            os.close(descriptor)
            descriptor = None
            os.replace(temporary_path, self._path)
            temporary_path = None
            _sync_directory(parent)
            return version
        except SecretStoreError:
            raise
        except OSError:
            raise SecretStoreError(
                "Local JSON secret store could not be written"
            ) from None
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except OSError:
                    pass


def _object_without_duplicate_names(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for name, value in pairs:
        if name in payload:
            raise _DuplicateNameError
        payload[name] = value
    return payload


def _load_json(text: str) -> tuple[bool, Any]:
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_names,
        )
    except (json.JSONDecodeError, _DuplicateNameError, RecursionError):
        return False, None
    return True, payload


def _validate_json_entry(
    raw_name: Any,
    raw_value: Any,
    *,
    max_secret_bytes: int,
) -> tuple[bool, str | None, str | None]:
    try:
        name = validate_secret_name(raw_name)
        value = validate_secret_value(
            raw_value,
            max_bytes=max_secret_bytes,
        )
    except SecretConfigurationError:
        return False, None, None
    return True, name, value


def _write_all(descriptor: int, content: bytes) -> None:
    view = memoryview(content)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("short write")
        view = view[written:]


def _sync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
