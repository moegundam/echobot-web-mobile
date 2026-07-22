from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from ..runtime.sessions import SessionStore, message_to_dict
from ..runtime.sqlite_sessions import SQLiteSessionStore


EXPORT_FORMAT = "echobot-postgres-seed-v2"
_STORE_PATHS = {
    "character_profiles": Path("character_profiles.json"),
    "conversation_jobs": Path("jobs/jobs.json"),
    "cron_jobs": Path("cron/jobs.json"),
    "delivery": Path("delivery.json"),
    "live2d_models": Path("live2d_models.json"),
    "llm_models": Path("llm_models.json"),
    "model_profiles": Path("model_profiles.json"),
    "route_sessions": Path("route_sessions.json"),
    "runtime_settings": Path("runtime_settings.json"),
    "voice_profiles": Path("voice_profiles.json"),
}
_SECRET_KEY_EXACT_NAMES = {
    "api_key",
    "authorization",
    "bot_token",
    "client_secret",
    "cookie",
    "credentials",
    "password",
    "private_key",
    "secret",
    "secret_access_key",
    "secret_key",
    "secret_ref",
    "secret_refs",
    "token",
    "token_value",
    "webhook_url",
}
_SECRET_KEY_SUFFIXES = (
    "_api_key",
    "bot_token",
    "_client_secret",
    "_credential",
    "_credentials",
    "_password",
    "_private_key",
    "_secret",
    "_secret_access_key",
    "_secret_key",
    "_secret_ref",
    "_secret_refs",
    "_token",
    "_token_value",
    "_webhook_url",
)
_NON_SECRET_KEY_EXACT_NAMES = {
    "max_token",
    "max_tokens",
}
_MAX_JSON_STRING_DECODE_DEPTH = 4
_CAMEL_WORD_BOUNDARY = re.compile(r"(.)([A-Z][a-z]+)")
_CAMEL_CASE_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")


def build_postgres_seed_export(
    workspace: str | Path,
    *,
    session_source: str = "jsonl",
    sqlite_source: str | Path | None = None,
    session_store_backend: str | None = None,
) -> dict[str, Any]:
    """Build a PostgreSQL seed from one explicitly selected session source.

    JSONL remains the compatibility default.  SQLite selection never falls
    back to JSONL: ``sqlite_source`` may point at a SQLite storage root using
    the runtime layout, or at one default ``sessions.sqlite3`` database.
    Canonical non-session JSON stores continue to be read from ``workspace``;
    the session source is recorded in the payload so an export cannot be
    mistaken for a mixed-backend snapshot.

    ``session_store_backend`` is accepted as a compatibility alias for callers
    that already use the runtime selector.  Supplying both selectors with
    different values is rejected.
    """
    workspace_path = Path(workspace).expanduser().resolve()
    storage_root = workspace_path / ".echobot"
    selected_source = _resolve_session_source(
        session_source,
        session_store_backend=session_store_backend,
        sqlite_source=sqlite_source,
    )
    scope_sources = _session_scope_sources(
        storage_root,
        session_source=selected_source,
        sqlite_source=sqlite_source,
    )
    invalid_records: list[str] = []
    scopes = [
        _export_scope(
            workspace_path,
            owner_user_id=owner_user_id,
            storage_root=canonical_scope_root,
            session_source=selected_source,
            session_storage_root=session_scope_root,
            invalid_records=invalid_records,
        )
        for owner_user_id, canonical_scope_root, session_scope_root in scope_sources
    ]
    payload: dict[str, Any] = {
        "format": EXPORT_FORMAT,
        "schema_version": 2,
        "session_source": selected_source,
        "scopes": scopes,
        "global": {
            "channels": _read_json_object(
                storage_root / "channels.json",
                workspace=workspace_path,
                invalid_records=invalid_records,
            )
        },
        "notes": [
            "Secret-bearing fields and dedicated secret files are not exported.",
            "Attachment bytes are not embedded; the manifest records relative paths, sizes, and SHA-256 digests.",
            "Conversation history can contain sensitive user content and the resulting seed must be handled as private data.",
            "This is a validated migration seed, not a PostgreSQL runtime switch or import-completion claim.",
            f"Session records were read exclusively from the selected {selected_source} source; no backend fallback or merge was performed.",
        ],
        "manifest": {
            "counts": {},
            "invalid_records": sorted(set(invalid_records)),
            "sha256": "",
        },
    }
    payload["manifest"]["counts"] = _compute_counts(payload)
    payload["manifest"]["sha256"] = _payload_digest(payload)
    return payload


def validate_postgres_seed_export(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("format") != EXPORT_FORMAT:
        errors.append(f"unsupported export format: {payload.get('format')!r}")
    if payload.get("schema_version") != 2:
        errors.append("schema_version must be 2")
    session_source = payload.get("session_source", "jsonl")
    if not isinstance(session_source, str) or session_source not in {"jsonl", "sqlite"}:
        errors.append("session_source must be one of: jsonl, sqlite")

    scopes = payload.get("scopes")
    if not isinstance(scopes, list):
        errors.append("scopes must be a list")
    else:
        owner_ids = [
            str(scope.get("owner_user_id", ""))
            for scope in scopes
            if isinstance(scope, dict)
        ]
        if len(owner_ids) != len(scopes) or any(not owner_id for owner_id in owner_ids):
            errors.append("every scope must contain owner_user_id")
        if len(set(owner_ids)) != len(owner_ids):
            errors.append("scope owner_user_id values must be unique")

    manifest = payload.get("manifest")
    if not isinstance(manifest, dict):
        errors.append("manifest must be an object")
        return errors

    invalid_records = manifest.get("invalid_records", [])
    if not isinstance(invalid_records, list):
        errors.append("manifest.invalid_records must be a list")
    else:
        errors.extend(f"invalid source record: {item}" for item in invalid_records)

    counts = manifest.get("counts")
    expected_counts = _compute_counts(payload)
    if counts != expected_counts:
        errors.append("manifest counts do not match the exported payload")

    digest = str(manifest.get("sha256", ""))
    if len(digest) != 64 or digest != _payload_digest(payload):
        errors.append("manifest digest does not match the exported payload")
    return errors


def write_postgres_seed_export(
    workspace: str | Path,
    output_path: str | Path,
    *,
    session_source: str = "jsonl",
    sqlite_source: str | Path | None = None,
    session_store_backend: str | None = None,
) -> dict[str, Any]:
    payload = build_postgres_seed_export(
        workspace,
        session_source=session_source,
        sqlite_source=sqlite_source,
        session_store_backend=session_store_backend,
    )
    errors = validate_postgres_seed_export(payload)
    if errors:
        raise ValueError("PostgreSQL seed validation failed: " + "; ".join(errors))

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_private_atomic_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return payload


def _owner_scopes(storage_root: Path) -> list[tuple[str, Path]]:
    scopes: list[tuple[str, Path]] = [("default", storage_root)]
    users_root = storage_root / "users"
    if users_root.is_dir():
        scopes.extend(
            (path.name, path)
            for path in sorted(users_root.iterdir(), key=lambda item: item.name)
            if path.is_dir() and not path.name.startswith(".")
        )
    return scopes


def _resolve_session_source(
    session_source: str,
    *,
    session_store_backend: str | None,
    sqlite_source: str | Path | None,
) -> str:
    selected = str(session_source or "jsonl").strip().lower()
    if session_store_backend is not None:
        backend = str(session_store_backend or "").strip().lower()
        if selected != "jsonl" and selected != backend:
            raise ValueError(
                "session_source and session_store_backend must select the same backend"
            )
        selected = backend
    if sqlite_source is not None and selected == "jsonl":
        selected = "sqlite"
    if selected not in {"jsonl", "sqlite"}:
        raise ValueError(
            "PostgreSQL seed session source must be one of: jsonl, sqlite"
        )
    if selected == "jsonl" and sqlite_source is not None:
        raise ValueError("sqlite_source requires the sqlite session source")
    return selected


def _session_scope_sources(
    storage_root: Path,
    *,
    session_source: str,
    sqlite_source: str | Path | None,
) -> list[tuple[str, Path, Path]]:
    if session_source == "jsonl":
        return [
            (owner_user_id, scope_root, scope_root)
            for owner_user_id, scope_root in _owner_scopes(storage_root)
        ]

    sqlite_path = (
        Path(sqlite_source).expanduser().resolve()
        if sqlite_source is not None
        else storage_root
    )
    if sqlite_path.is_file() or (
        sqlite_source is not None and sqlite_path.suffix.lower() in {".sqlite", ".sqlite3"}
    ):
        if sqlite_path.name != "sessions.sqlite3":
            raise ValueError(
                "SQLite seed source file must be named sessions.sqlite3; "
                "use its storage root to export user scopes"
            )
        if not sqlite_path.exists():
            raise FileNotFoundError(
                f"Selected SQLite session source was not found: {sqlite_path}"
            )
        _reject_uncovered_user_scopes(storage_root)
        return [("default", storage_root, sqlite_path.parent)]

    if not sqlite_path.exists() or not sqlite_path.is_dir():
        raise FileNotFoundError(
            f"Selected SQLite session source root was not found: {sqlite_path}"
        )
    default_db = sqlite_path / "sessions.sqlite3"
    if not default_db.is_file():
        raise FileNotFoundError(
            f"Selected SQLite session source is missing: {default_db}"
        )

    scopes: list[tuple[str, Path, Path]] = [("default", storage_root, sqlite_path)]
    users_root = sqlite_path / "users"
    if users_root.is_dir():
        for source_scope in sorted(users_root.iterdir(), key=lambda item: item.name):
            if not source_scope.is_dir() or source_scope.name.startswith("."):
                continue
            if not (source_scope / "sessions.sqlite3").is_file():
                raise FileNotFoundError(
                    "Selected SQLite session source is missing: "
                    f"{source_scope / 'sessions.sqlite3'}"
                )
            scopes.append(
                (
                    source_scope.name,
                    storage_root / "users" / source_scope.name,
                    source_scope,
                )
            )
    return scopes


def _reject_uncovered_user_scopes(storage_root: Path) -> None:
    users_root = storage_root / "users"
    if not users_root.is_dir():
        return
    for scope_root in users_root.iterdir():
        if not scope_root.is_dir() or scope_root.name.startswith("."):
            continue
        has_jsonl_sessions = any(scope_root.glob("sessions/*.jsonl"))
        has_sqlite_sessions = (scope_root / "sessions.sqlite3").is_file()
        if has_jsonl_sessions or has_sqlite_sessions:
            raise ValueError(
                "A single SQLite sessions database cannot cover user scopes; "
                "select the SQLite storage root instead"
            )


def _export_scope(
    workspace: Path,
    *,
    owner_user_id: str,
    storage_root: Path,
    session_source: str,
    session_storage_root: Path,
    invalid_records: list[str],
) -> dict[str, Any]:
    if session_source == "jsonl":
        sessions, current_session = _export_sessions(
            session_storage_root / "sessions",
            workspace=workspace,
            invalid_records=invalid_records,
        )
        agent_sessions, current_agent_session = _export_sessions(
            session_storage_root / "agent_sessions",
            workspace=workspace,
            invalid_records=invalid_records,
        )
    else:
        sessions, current_session = _export_sqlite_sessions(
            session_storage_root / "sessions.sqlite3",
            workspace=workspace,
            invalid_records=invalid_records,
        )
        agent_sessions, current_agent_session = _export_sqlite_sessions(
            session_storage_root / "agent_sessions.sqlite3",
            workspace=workspace,
            invalid_records=invalid_records,
        )
    stores: dict[str, Any] = {}
    for name, relative_path in _STORE_PATHS.items():
        path = storage_root / relative_path
        if not path.exists():
            continue
        stores[name] = _read_json_object(
            path,
            workspace=workspace,
            invalid_records=invalid_records,
        )

    return {
        "owner_user_id": owner_user_id,
        "storage_path": _relative_path(storage_root, workspace),
        "current_session": current_session,
        "current_agent_session": current_agent_session,
        "sessions": sessions,
        "agent_sessions": agent_sessions,
        "stores": stores,
        "agent_traces": _export_jsonl_tree(
            storage_root / "agent_traces",
            workspace=workspace,
            invalid_records=invalid_records,
        ),
        "attachments": _export_attachments(
            storage_root / "attachments",
            workspace=workspace,
            invalid_records=invalid_records,
        ),
    }


def _export_sqlite_sessions(
    database_path: Path,
    *,
    workspace: Path,
    invalid_records: list[str],
) -> tuple[list[dict[str, Any]], str | None]:
    if not database_path.is_file():
        return [], None

    try:
        store = SQLiteSessionStore.open_readonly(database_path)
    except (OSError, ValueError, sqlite3.Error) as exc:
        raise ValueError(
            f"Unable to open selected SQLite session source {database_path}: "
            f"{type(exc).__name__}"
        ) from exc

    sessions: list[dict[str, Any]] = []
    try:
        for info in store.list_sessions():
            try:
                session = store.load_session(info.name)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                invalid_records.append(_record_error(database_path, workspace, exc))
                continue
            sessions.append(
                _sanitize_secrets(
                    {
                        "name": session.name,
                        "updated_at": session.updated_at,
                        "compressed_summary": session.compressed_summary,
                        "metadata": dict(session.metadata),
                        "history": [
                            message_to_dict(message) for message in session.history
                        ],
                    }
                )
            )
        sessions.sort(key=lambda item: str(item.get("name", "")))
        try:
            current_session = store.get_current_session_name()
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            invalid_records.append(_record_error(database_path, workspace, exc))
            current_session = None
        return sessions, current_session
    except Exception as exc:
        if isinstance(
            exc,
            (OSError, UnicodeError, ValueError, json.JSONDecodeError, sqlite3.Error),
        ):
            raise ValueError(
                f"Unable to read selected SQLite session source {database_path}: "
                f"{type(exc).__name__}"
            ) from exc
        raise
    finally:
        store.close()


def _export_sessions(
    session_dir: Path,
    *,
    workspace: Path,
    invalid_records: list[str],
) -> tuple[list[dict[str, Any]], str | None]:
    if not session_dir.is_dir():
        return [], None

    store = SessionStore(session_dir)
    sessions: list[dict[str, Any]] = []
    for path in sorted(session_dir.glob("*.jsonl"), key=lambda item: item.name):
        if path.name == "index.jsonl":
            continue
        try:
            session = store.load_session(path.stem)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            invalid_records.append(_record_error(path, workspace, exc))
            continue
        sessions.append(
            _sanitize_secrets(
                {
                    "name": session.name,
                    "updated_at": session.updated_at,
                    "compressed_summary": session.compressed_summary,
                    "metadata": dict(session.metadata),
                    "history": [message_to_dict(message) for message in session.history],
                }
            )
        )
    sessions.sort(key=lambda item: str(item.get("name", "")))

    current_session: str | None = None
    if store.index_file.exists():
        try:
            current_session = store.get_current_session_name()
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            invalid_records.append(_record_error(store.index_file, workspace, exc))
    return sessions, current_session


def _read_json_object(
    path: Path,
    *,
    workspace: Path,
    invalid_records: list[str],
) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        invalid_records.append(_record_error(path, workspace, exc))
        return {}
    if not isinstance(payload, dict):
        invalid_records.append(
            f"{_relative_path(path, workspace)}: expected a JSON object"
        )
        return {}
    return _sanitize_secrets(payload)


def _export_jsonl_tree(
    base_dir: Path,
    *,
    workspace: Path,
    invalid_records: list[str],
) -> list[dict[str, Any]]:
    if not base_dir.is_dir():
        return []
    exported: list[dict[str, Any]] = []
    for path in sorted(base_dir.rglob("*.jsonl"), key=lambda item: item.as_posix()):
        events: list[dict[str, Any]] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            invalid_records.append(_record_error(path, workspace, exc))
            continue
        for line_number, line in enumerate(lines, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                record = json.loads(text)
            except json.JSONDecodeError as exc:
                invalid_records.append(
                    f"{_relative_path(path, workspace)}:{line_number}: {type(exc).__name__}"
                )
                continue
            if not isinstance(record, dict):
                invalid_records.append(
                    f"{_relative_path(path, workspace)}:{line_number}: expected a JSON object"
                )
                continue
            events.append(_sanitize_secrets(record))
        exported.append(
            {
                "path": _relative_path(path, base_dir),
                "events": events,
            }
        )
    return exported


def _export_attachments(
    base_dir: Path,
    *,
    workspace: Path,
    invalid_records: list[str],
) -> list[dict[str, Any]]:
    metadata_dir = base_dir / "meta"
    if not metadata_dir.is_dir():
        return []
    exported: list[dict[str, Any]] = []
    resolved_base = base_dir.resolve()
    for metadata_path in sorted(metadata_dir.glob("*.json"), key=lambda item: item.name):
        metadata = _read_json_object(
            metadata_path,
            workspace=workspace,
            invalid_records=invalid_records,
        )
        if not metadata:
            continue
        relative_path = str(metadata.get("relative_path", "")).strip()
        if not relative_path:
            invalid_records.append(
                f"{_relative_path(metadata_path, workspace)}: missing relative_path"
            )
            continue
        content_path = (base_dir / relative_path).resolve()
        try:
            content_path.relative_to(resolved_base)
        except ValueError:
            invalid_records.append(
                f"{_relative_path(metadata_path, workspace)}: attachment path escapes storage root"
            )
            continue
        try:
            size_bytes, digest = _file_size_and_digest(content_path)
        except OSError as exc:
            invalid_records.append(_record_error(content_path, workspace, exc))
            continue
        record = dict(metadata)
        record["relative_path"] = relative_path
        record["size_bytes"] = size_bytes
        record["sha256"] = digest
        exported.append(_sanitize_secrets(record))
    exported.sort(key=lambda item: str(item.get("attachment_id", "")))
    return exported


def _file_size_and_digest(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size_bytes = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            size_bytes += len(chunk)
            digest.update(chunk)
    return size_bytes, digest.hexdigest()


def _sanitize_secrets(value: Any, *, json_decode_depth: int = 0) -> Any:
    if isinstance(value, list):
        return [
            _sanitize_secrets(item, json_decode_depth=json_decode_depth)
            for item in value
        ]
    if isinstance(value, str):
        return _sanitize_json_string(value, json_decode_depth=json_decode_depth)
    if not isinstance(value, dict):
        return value

    sanitized: dict[str, Any] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key)
        normalized_key = _normalize_secret_key(key)
        if normalized_key.endswith("_configured"):
            sanitized[key] = bool(raw_value)
            continue
        if _is_secret_key(normalized_key):
            sanitized[key] = ""
            configured_key = f"{key}_configured"
            sanitized[configured_key] = _secret_value_is_configured(raw_value)
            continue
        sanitized[key] = _sanitize_secrets(
            raw_value,
            json_decode_depth=json_decode_depth,
        )
    return sanitized


def _sanitize_json_string(value: str, *, json_decode_depth: int) -> str:
    candidate = value.strip()
    if not _looks_like_json_container_or_string(candidate):
        return value
    if json_decode_depth >= _MAX_JSON_STRING_DECODE_DEPTH:
        return ""
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return value
    except RecursionError:
        return ""
    if not isinstance(decoded, (dict, list, str)):
        return value

    sanitized = _sanitize_secrets(
        decoded,
        json_decode_depth=json_decode_depth + 1,
    )
    if isinstance(decoded, str) and sanitized == decoded:
        return value
    return json.dumps(
        sanitized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _looks_like_json_container_or_string(value: str) -> bool:
    if len(value) < 2:
        return False
    return (value[0], value[-1]) in {
        ("[", "]"),
        ("{", "}"),
        ('"', '"'),
    }


def _normalize_secret_key(key: str) -> str:
    normalized = _CAMEL_WORD_BOUNDARY.sub(r"\1_\2", key.strip())
    normalized = _CAMEL_CASE_BOUNDARY.sub(r"\1_\2", normalized)
    return normalized.lower().replace("-", "_").replace(".", "_")


def _is_secret_key(normalized_key: str) -> bool:
    if normalized_key in _NON_SECRET_KEY_EXACT_NAMES:
        return False
    return normalized_key in _SECRET_KEY_EXACT_NAMES or normalized_key.endswith(
        _SECRET_KEY_SUFFIXES,
    )


def _secret_value_is_configured(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return value is not None and bool(value)


def _write_private_atomic_text(path: Path, text: str) -> None:
    descriptor: int | None = None
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        os.fchmod(descriptor, 0o600)
        handle = os.fdopen(descriptor, "w", encoding="utf-8", newline="\n")
        descriptor = None
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
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


def _compute_counts(payload: dict[str, Any]) -> dict[str, int]:
    scopes = payload.get("scopes")
    if not isinstance(scopes, list):
        return {
            "agent_sessions": 0,
            "agent_trace_events": 0,
            "agent_trace_files": 0,
            "attachments": 0,
            "scopes": 0,
            "sessions": 0,
            "store_files": 0,
        }
    return {
        "agent_sessions": sum(
            len(scope.get("agent_sessions", []))
            for scope in scopes
            if isinstance(scope, dict) and isinstance(scope.get("agent_sessions"), list)
        ),
        "agent_trace_events": sum(
            len(trace.get("events", []))
            for scope in scopes
            if isinstance(scope, dict) and isinstance(scope.get("agent_traces"), list)
            for trace in scope["agent_traces"]
            if isinstance(trace, dict) and isinstance(trace.get("events"), list)
        ),
        "agent_trace_files": sum(
            len(scope.get("agent_traces", []))
            for scope in scopes
            if isinstance(scope, dict) and isinstance(scope.get("agent_traces"), list)
        ),
        "attachments": sum(
            len(scope.get("attachments", []))
            for scope in scopes
            if isinstance(scope, dict) and isinstance(scope.get("attachments"), list)
        ),
        "scopes": len(scopes),
        "sessions": sum(
            len(scope.get("sessions", []))
            for scope in scopes
            if isinstance(scope, dict) and isinstance(scope.get("sessions"), list)
        ),
        "store_files": sum(
            len(scope.get("stores", {}))
            for scope in scopes
            if isinstance(scope, dict) and isinstance(scope.get("stores"), dict)
        ),
    }


def _payload_digest(payload: dict[str, Any]) -> str:
    canonical_payload = dict(payload)
    manifest = dict(canonical_payload.get("manifest") or {})
    manifest["sha256"] = ""
    canonical_payload["manifest"] = manifest
    encoded = json.dumps(
        canonical_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _record_error(path: Path, workspace: Path, exc: BaseException) -> str:
    return f"{_relative_path(path, workspace)}: {type(exc).__name__}"


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name
