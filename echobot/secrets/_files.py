from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from .base import SecretPermissionError, SecretStoreError


@dataclass(frozen=True, slots=True)
class Utf8File:
    text: str
    version: str


def read_utf8_file(
    path: Path,
    *,
    max_bytes: int,
    require_restricted_permissions: bool = False,
    allow_symlinks: bool = True,
    missing_ok: bool = False,
) -> Utf8File | None:
    if not allow_symlinks and _is_symlink(path):
        raise SecretPermissionError(
            "Local JSON secret store must not be a symbolic link"
        )

    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    if not allow_symlinks:
        flags |= getattr(os, "O_NOFOLLOW", 0)

    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise SecretStoreError("Secret file could not be opened") from None
    except OSError:
        if not allow_symlinks and _is_symlink(path):
            raise SecretPermissionError(
                "Local JSON secret store must not be a symbolic link"
            ) from None
        raise SecretStoreError("Secret file could not be opened") from None

    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise SecretStoreError("Secret file must be a regular file")
        if require_restricted_permissions and stat.S_IMODE(before.st_mode) & 0o077:
            raise SecretPermissionError(
                "Local JSON secret store permissions are too broad"
            )
        if before.st_size > max_bytes:
            raise SecretStoreError("Secret file exceeds the size limit")

        content = _read_bounded(descriptor, max_bytes=max_bytes)
        after = os.fstat(descriptor)
        if _file_identity(before) != _file_identity(after):
            raise SecretStoreError("Secret file changed while it was being read")
    except OSError:
        raise SecretStoreError("Secret file could not be read") from None
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass

    text = _decode_utf8(content)
    if text is None:
        raise SecretStoreError("Secret file must contain valid UTF-8")

    return Utf8File(text=text, version=_file_version(after))


def descriptor_version(descriptor: int) -> str:
    try:
        file_stat = os.fstat(descriptor)
    except OSError:
        raise SecretStoreError(
            "Local JSON secret store metadata could not be read"
        ) from None
    return _file_version(file_stat)


def _read_bounded(descriptor: int, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    remaining = max_bytes + 1
    while remaining:
        chunk = os.read(descriptor, min(64 * 1024, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)

    content = b"".join(chunks)
    if len(content) > max_bytes:
        raise SecretStoreError("Secret file exceeds the size limit")
    return content


def _file_identity(file_stat: os.stat_result) -> tuple[int, int, int, int]:
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_mtime_ns,
        file_stat.st_size,
    )


def _file_version(file_stat: os.stat_result) -> str:
    identity = (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_mtime_ns,
    )
    return "-".join(f"{part:x}" for part in identity)


def _is_symlink(path: Path) -> bool:
    try:
        return path.is_symlink()
    except OSError:
        return False


def _decode_utf8(content: bytes) -> str | None:
    try:
        return content.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None
