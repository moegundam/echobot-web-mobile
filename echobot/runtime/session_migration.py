from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .sessions import (
    ChatSession,
    _read_metadata,
    message_from_dict,
    normalize_session_name,
)
from .sqlite_sessions import SQLiteSessionStore


@dataclass(slots=True)
class MigrationReport:
    migrated: int = 0
    skipped: int = 0
    conflicts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    pointer_migrated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "migrated": self.migrated,
            "skipped": self.skipped,
            "conflicts": list(self.conflicts),
            "errors": list(self.errors),
            "pointer_migrated": self.pointer_migrated,
        }


def migrate_jsonl_to_sqlite(
    source_dir: str | Path,
    target_db: str | Path,
) -> MigrationReport:
    """Migrate valid JSONL snapshots without replacing existing SQLite rows."""
    source = Path(source_dir)
    report = MigrationReport()
    sessions, source_pointer = _read_source(source, report)
    if report.errors:
        return report

    target = SQLiteSessionStore(target_db)
    try:
        with target.transaction():
            for session in sessions:
                if not target._session_exists_locked(session.name):
                    target._import_session_locked(session)
                    report.migrated += 1
                    continue
                existing = target.load_session(session.name)
                if _session_fingerprint(existing) == _session_fingerprint(session):
                    report.skipped += 1
                else:
                    report.conflicts.append(session.name)

            if source_pointer is not None:
                source_name, source_revision = source_pointer
                target_name, target_revision = target._current_pointer_locked()
                if target_name is None:
                    if (
                        source_name not in report.conflicts
                        and target._session_exists_locked(source_name)
                    ):
                        target._set_current_locked(source_name, source_revision)
                        report.pointer_migrated = True
                elif target_name == source_name and target_revision == source_revision:
                    pass
                else:
                    report.conflicts.append("__current_pointer__")
    except Exception as exc:
        report.migrated = 0
        report.skipped = 0
        report.pointer_migrated = False
        report.errors.append(f"SQLite migration rolled back: {exc}")
    finally:
        target.close()
    return report


def _read_source(
    source_dir: Path,
    report: MigrationReport,
) -> tuple[list[ChatSession], tuple[str, int] | None]:
    if not source_dir.exists() or not source_dir.is_dir():
        report.errors.append(f"Source directory not found: {source_dir}")
        return [], None

    sessions: list[ChatSession] = []
    seen_names: set[str] = set()
    for path in sorted(source_dir.glob("*.jsonl")):
        if path.name == "index.jsonl":
            continue
        try:
            records = _read_jsonl_records(path)
            if not records:
                raise ValueError("file is empty")
            metadata = records[0]
            if metadata.get("type") != "session":
                raise ValueError("first record is not session metadata")
            name = normalize_session_name(str(metadata.get("name", path.stem)))
            if name in seen_names:
                raise ValueError(f"duplicate session name: {name}")
            history = []
            for record in records[1:]:
                if record.get("type") != "message":
                    continue
                data = dict(record)
                data.pop("type", None)
                history.append(message_from_dict(data))
            sessions.append(
                ChatSession(
                    name=name,
                    history=history,
                    updated_at=str(metadata.get("updated_at", "")),
                    compressed_summary=str(metadata.get("compressed_summary", "")),
                    metadata=_read_metadata(metadata.get("metadata")),
                )
            )
            seen_names.add(name)
        except Exception as exc:
            report.errors.append(f"{path}: {exc}")

    pointer: tuple[str, int] | None = None
    index_path = source_dir / "index.jsonl"
    if index_path.exists():
        try:
            records = _read_jsonl_records(index_path)
            if records:
                raw_name = str(records[0].get("current_session", "")).strip()
                if raw_name:
                    name = normalize_session_name(raw_name)
                    try:
                        revision = max(int(records[0].get("revision", 0)), 0)
                    except (TypeError, ValueError):
                        revision = 0
                    pointer = (name, revision)
        except Exception as exc:
            report.errors.append(f"{index_path}: {exc}")
    return sessions, pointer


def _read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("record is not an object")
        records.append(value)
    return records


def _session_fingerprint(session: ChatSession) -> str:
    payload = {
        "name": session.name,
        "updated_at": session.updated_at,
        "compressed_summary": session.compressed_summary,
        "metadata": session.metadata,
        "history": [
            {
                "role": message.role,
                "content": message.content,
                "name": message.name,
                "tool_call_id": message.tool_call_id,
                "tool_calls": [
                    {
                        "id": call.id,
                        "name": call.name,
                        "arguments": call.arguments,
                    }
                    for call in message.tool_calls
                ],
                "reasoning_content": message.reasoning_content,
                "reasoning_field": message.reasoning_field,
            }
            for message in session.history
        ],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate EchoBot JSONL sessions to SQLite")
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("target_db", type=Path)
    args = parser.parse_args(argv)
    report = migrate_jsonl_to_sqlite(args.source_dir, args.target_db)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
