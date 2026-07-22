from __future__ import annotations

import json
import os
import shutil
import sys
import tarfile
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from .network.http import open_http_url, validate_http_url


CancelledErrorFactory = Callable[[], Exception] | None
_DOWNLOAD_PROGRESS_UPDATE_INTERVAL_SECONDS = 1.0
_DOWNLOAD_PROGRESS_PERCENT_STEP = 10.0
_PROGRESS_OUTPUT_LOCK = threading.Lock()


def relative_to_root(path: Path, root_dir: Path) -> str:
    try:
        return path.relative_to(root_dir).as_posix()
    except ValueError:
        return path.name


def file_name_from_url(url: str, *, allow_private: bool = False) -> str:
    parsed = urlparse(
        validate_http_url(
            url,
            field_name="download URL",
            allow_private=allow_private,
        ),
    )
    file_name = Path(parsed.path).name
    if not file_name:
        raise ValueError(f"Unable to determine file name from URL: {url}")
    return file_name


def safe_extract_tar(archive: tarfile.TarFile, destination: Path) -> None:
    destination_root = destination.resolve()
    for member in archive.getmembers():
        member_path = (destination / member.name).resolve()
        if not _is_within_directory(member_path, destination_root):
            raise ValueError(f"Archive member escapes extraction directory: {member.name}")
        if member.issym() or member.islnk():
            link_path = (member_path.parent / member.linkname).resolve()
            if not _is_within_directory(link_path, destination_root):
                raise ValueError(f"Archive link escapes extraction directory: {member.name}")
    archive.extractall(destination)  # nosec B202


def _is_within_directory(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def write_download_metadata(path: Path, *, name: str, source_url: str) -> None:
    payload = {
        "name": name,
        "source_url": source_url,
        "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def replace_directory(source_dir: Path, target_dir: Path) -> None:
    backup_dir = target_dir.with_name(f"{target_dir.name}.backup")
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    if target_dir.exists():
        target_dir.replace(backup_dir)
    source_dir.replace(target_dir)
    if backup_dir.exists():
        shutil.rmtree(backup_dir)


def download_file(
    url: str,
    destination: Path,
    *,
    timeout_seconds: float,
    allow_private: bool = False,
    stop_event: threading.Event | None = None,
    cancelled_error_factory: CancelledErrorFactory = None,
    chunk_size: int = 64 * 1024,
    progress_label: str | None = None,
) -> None:
    url = validate_http_url(
        url,
        field_name="download URL",
        allow_private=allow_private,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with open_http_url(
        url,
        timeout_seconds=timeout_seconds,
        allow_private=allow_private,
    ) as response:
        reporter = _DownloadProgressReporter(
            progress_label or file_name_from_url(url),
            total_bytes=_content_length_from_response(response),
        )
        reporter.start()
        with destination.open("wb") as handle:
            while True:
                raise_if_cancelled(
                    stop_event,
                    cancelled_error_factory=cancelled_error_factory,
                )
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                handle.write(chunk)
                reporter.advance(len(chunk))
        reporter.complete()


@contextmanager
def acquire_download_lock(
    lock_path: Path,
    *,
    timeout_seconds: float,
    timeout_message: str,
    stop_event: threading.Event | None = None,
    cancelled_error_factory: CancelledErrorFactory = None,
) -> Iterator[None]:
    deadline = time.monotonic() + timeout_seconds
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    while True:
        raise_if_cancelled(
            stop_event,
            cancelled_error_factory=cancelled_error_factory,
        )
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if remove_stale_lock(lock_path):
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(timeout_message)
            time.sleep(0.25)
            continue

        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"pid": os.getpid()}, ensure_ascii=False))
        break

    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def remove_stale_lock(lock_path: Path, *, max_age_seconds: float = 3600) -> bool:
    try:
        modified_at = lock_path.stat().st_mtime
    except FileNotFoundError:
        return False

    if time.time() - modified_at < max_age_seconds:
        return False

    try:
        lock_path.unlink()
    except FileNotFoundError:
        return False
    return True


def raise_if_cancelled(
    stop_event: threading.Event | None,
    *,
    cancelled_error_factory: CancelledErrorFactory = None,
) -> None:
    if stop_event is None or not stop_event.is_set():
        return
    if cancelled_error_factory is not None:
        raise cancelled_error_factory()
    raise RuntimeError("Speech model preparation was cancelled")


class _DownloadProgressReporter:
    def __init__(self, label: str, *, total_bytes: int | None) -> None:
        self._label = label
        self._total_bytes = total_bytes if total_bytes and total_bytes > 0 else None
        self._downloaded_bytes = 0
        self._started_at = 0.0
        self._last_report_at = 0.0
        self._next_percent_threshold = _DOWNLOAD_PROGRESS_PERCENT_STEP

    def start(self) -> None:
        self._started_at = time.monotonic()
        self._last_report_at = self._started_at
        if self._total_bytes is None:
            _emit_progress_line(
                f"[download] {self._label}: starting (size unknown)"
            )
            return

        _emit_progress_line(
            f"[download] {self._label}: starting ({_format_bytes(self._total_bytes)})"
        )

    def advance(self, chunk_size: int) -> None:
        self._downloaded_bytes += max(0, chunk_size)
        now = time.monotonic()
        if not self._should_report(now):
            return

        self._last_report_at = now
        _emit_progress_line(self._build_progress_message(now))

    def complete(self) -> None:
        now = time.monotonic()
        duration_seconds = max(0.001, now - self._started_at)
        if self._total_bytes is None:
            _emit_progress_line(
                (
                    f"[download] {self._label}: completed "
                    f"({_format_bytes(self._downloaded_bytes)} in "
                    f"{duration_seconds:.1f}s, {_format_rate(self._downloaded_bytes, duration_seconds)})"
                )
            )
            return

        _emit_progress_line(
            (
                f"[download] {self._label}: completed "
                f"(100.0%, {_format_bytes(self._downloaded_bytes)} / "
                f"{_format_bytes(self._total_bytes)}, "
                f"{_format_rate(self._downloaded_bytes, duration_seconds)})"
            )
        )

    def _should_report(self, now: float) -> bool:
        if self._downloaded_bytes <= 0:
            return False

        if self._total_bytes is not None:
            progress_percent = (self._downloaded_bytes / self._total_bytes) * 100
            if progress_percent >= self._next_percent_threshold:
                while progress_percent >= self._next_percent_threshold:
                    self._next_percent_threshold += _DOWNLOAD_PROGRESS_PERCENT_STEP
                return True

        return now - self._last_report_at >= _DOWNLOAD_PROGRESS_UPDATE_INTERVAL_SECONDS

    def _build_progress_message(self, now: float) -> str:
        duration_seconds = max(0.001, now - self._started_at)
        rate_text = _format_rate(self._downloaded_bytes, duration_seconds)
        if self._total_bytes is None:
            return (
                f"[download] {self._label}: "
                f"{_format_bytes(self._downloaded_bytes)} downloaded ({rate_text})"
            )

        progress_percent = min(100.0, (self._downloaded_bytes / self._total_bytes) * 100)
        return (
            f"[download] {self._label}: {progress_percent:.1f}% "
            f"({_format_bytes(self._downloaded_bytes)} / {_format_bytes(self._total_bytes)}, "
            f"{rate_text})"
        )


def _content_length_from_response(response: object) -> int | None:
    headers = getattr(response, "headers", None)
    if headers is None:
        return None

    content_length = headers.get("Content-Length")
    if not content_length:
        return None

    try:
        parsed_length = int(content_length)
    except (TypeError, ValueError):
        return None
    return parsed_length if parsed_length > 0 else None


def _format_bytes(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"

    units = ["KiB", "MiB", "GiB", "TiB"]
    size = float(size_bytes)
    for unit in units:
        size /= 1024.0
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.1f} {unit}"
    return f"{size_bytes} B"


def _format_rate(size_bytes: int, duration_seconds: float) -> str:
    if duration_seconds <= 0:
        return "0 B/s"
    return f"{_format_bytes(round(size_bytes / duration_seconds))}/s"


def _emit_progress_line(message: str) -> None:
    with _PROGRESS_OUTPUT_LOCK:
        print(message, file=sys.stderr, flush=True)
