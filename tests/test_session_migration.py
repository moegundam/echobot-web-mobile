from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from echobot.models import LLMMessage, ToolCall
from echobot.runtime.session_migration import migrate_jsonl_to_sqlite
from echobot.runtime.sessions import ChatSession, SessionStore
from echobot.runtime.sqlite_sessions import SQLiteSessionStore


class SessionMigrationTests(unittest.TestCase):
    def _seed_source(self, root: Path) -> SessionStore:
        source = SessionStore(root / "sessions")
        source.save_session(
            ChatSession(
                name="alpha",
                history=[
                    LLMMessage(
                        role="assistant",
                        content="hello",
                        tool_calls=[ToolCall("call-1", "clock", "{}")],
                    )
                ],
                updated_at="2026-01-01T00:00:00+08:00",
                compressed_summary="summary",
                metadata={"source": "jsonl"},
            )
        )
        source.save_session(
            ChatSession(
                name="beta",
                history=[],
                updated_at="2026-01-02T00:00:00+08:00",
                metadata={"priority": 2},
            )
        )
        source.set_current_session("alpha")
        return source

    def test_migration_preserves_sessions_messages_metadata_and_current_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = self._seed_source(root)
            db_path = root / "migrated.sqlite3"

            report = migrate_jsonl_to_sqlite(source.base_dir, db_path)
            self.assertEqual(2, report.migrated)
            self.assertEqual([], report.conflicts)
            self.assertEqual([], report.errors)

            target = SQLiteSessionStore(db_path)
            source_pointer = source.get_current_session_pointer()
            self.assertEqual(source_pointer, target.get_current_session_pointer())
            self.assertEqual("alpha", target.get_current_session_name())
            self.assertEqual("hello", target.load_session("alpha").history[0].content)
            self.assertEqual("call-1", target.load_session("alpha").history[0].tool_calls[0].id)
            self.assertEqual({"source": "jsonl"}, target.load_session("alpha").metadata)

    def test_migration_is_idempotent_and_does_not_overwrite_existing_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = self._seed_source(root)
            db_path = root / "migrated.sqlite3"

            first = migrate_jsonl_to_sqlite(source.base_dir, db_path)
            second = migrate_jsonl_to_sqlite(source.base_dir, db_path)
            self.assertEqual(2, first.migrated)
            self.assertEqual(2, second.skipped)
            self.assertEqual([], second.conflicts)

            target = SQLiteSessionStore(db_path)
            target_session = target.load_session("alpha")
            target_session.metadata["local_only"] = True
            target.save_session(target_session)
            source.save_session(
                ChatSession(
                    name="alpha",
                    history=[LLMMessage(role="user", content="changed")],
                    updated_at="2026-01-03T00:00:00+08:00",
                )
            )
            conflict = migrate_jsonl_to_sqlite(source.base_dir, db_path)
            self.assertIn("alpha", conflict.conflicts)
            self.assertEqual("hello", target.load_session("alpha").history[0].content)
            self.assertTrue(target.load_session("alpha").metadata["local_only"])

    def test_parse_error_rolls_back_new_sessions_and_preserves_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = self._seed_source(root)
            broken = source.base_dir / "broken.jsonl"
            broken.write_text("not-json\n", encoding="utf-8")
            original = broken.read_bytes()
            db_path = root / "migrated.sqlite3"

            report = migrate_jsonl_to_sqlite(source.base_dir, db_path)
            self.assertEqual(0, report.migrated)
            self.assertTrue(report.errors)
            self.assertEqual(original, broken.read_bytes())
            self.assertEqual([], SQLiteSessionStore(db_path).list_sessions())

    def test_write_error_rolls_back_all_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = self._seed_source(root)
            db_path = root / "migrated.sqlite3"
            original = SQLiteSessionStore._import_session_locked
            calls = 0

            def flaky_import(store, session):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("injected write failure")
                return original(store, session)

            with patch.object(SQLiteSessionStore, "_import_session_locked", flaky_import):
                report = migrate_jsonl_to_sqlite(source.base_dir, db_path)

            self.assertEqual(0, report.migrated)
            self.assertTrue(any("rolled back" in error for error in report.errors))
            self.assertEqual([], SQLiteSessionStore(db_path).list_sessions())

    def test_invalid_legacy_pointer_revision_falls_back_to_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = self._seed_source(root)
            (source.base_dir / "index.jsonl").write_text(
                '{"current_session":"alpha","revision":"legacy"}\n',
                encoding="utf-8",
            )
            report = migrate_jsonl_to_sqlite(
                source.base_dir,
                root / "migrated.sqlite3",
            )
            self.assertEqual([], report.errors)
            self.assertEqual(
                ("alpha", 0),
                SQLiteSessionStore(root / "migrated.sqlite3").get_current_session_pointer(),
            )

    def test_cli_report_is_json_serializable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._seed_source(root)
            report = migrate_jsonl_to_sqlite(root / "sessions", root / "db.sqlite3")
            encoded = json.dumps(report.to_dict(), ensure_ascii=False)
            self.assertIn('"migrated": 2', encoded)


if __name__ == "__main__":
    unittest.main()
