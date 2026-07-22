from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from echobot.cli.db import run_export
from echobot.cli.main import build_parser
from echobot.models import LLMMessage
from echobot.persistence.export import (
    build_postgres_seed_export,
    validate_postgres_seed_export,
    write_postgres_seed_export,
)
from echobot.runtime.sessions import SessionStore
from echobot.runtime.sqlite_sessions import SQLiteSessionStore


class PostgresSeedExportSourceTests(unittest.TestCase):
    def test_db_export_cli_exposes_explicit_sqlite_source(self) -> None:
        args = build_parser().parse_args(
            [
                "db",
                "export",
                "--session-store-backend",
                "sqlite",
                "--sqlite-source",
                "/tmp/selected-sessions",
            ]
        )
        self.assertEqual("sqlite", args.session_store_backend)
        self.assertEqual("/tmp/selected-sessions", args.sqlite_source)

    def test_db_export_cli_uses_selected_sqlite_backend(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            store = SQLiteSessionStore(workspace / ".echobot" / "sessions.sqlite3")
            store.create_session("sqlite-session")
            output = workspace / "seed.json"
            args = build_parser().parse_args(
                [
                    "db",
                    "export",
                    "--workspace",
                    str(workspace),
                    "--session-store-backend",
                    "sqlite",
                    "--output",
                    str(output),
                ]
            )

            run_export(args)

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("sqlite", payload["session_source"])
            self.assertEqual(
                ["sqlite-session"],
                [item["name"] for item in payload["scopes"][0]["sessions"]],
            )
            store.close()

    def test_jsonl_remains_the_default_when_sqlite_also_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            jsonl_store = SessionStore(workspace / ".echobot" / "sessions")
            jsonl_store.create_session("jsonl-session")
            sqlite_store = SQLiteSessionStore(workspace / ".echobot" / "sessions.sqlite3")
            sqlite_store.create_session("sqlite-session")

            payload = build_postgres_seed_export(workspace)

            self.assertEqual("jsonl", payload["session_source"])
            self.assertEqual(
                ["jsonl-session"],
                [item["name"] for item in payload["scopes"][0]["sessions"]],
            )
            sqlite_store.close()

    def test_explicit_sqlite_source_exports_sqlite_sessions_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            jsonl_store = SessionStore(workspace / ".echobot" / "sessions")
            jsonl_store.create_session("jsonl-session")
            sqlite_store = SQLiteSessionStore(workspace / ".echobot" / "sessions.sqlite3")
            session = sqlite_store.create_session("sqlite-session")
            session.history.append(LLMMessage(role="assistant", content="from sqlite"))
            sqlite_store.save_session(session)

            payload = build_postgres_seed_export(workspace, session_source="sqlite")

            self.assertEqual("sqlite", payload["session_source"])
            self.assertEqual(
                ["sqlite-session"],
                [item["name"] for item in payload["scopes"][0]["sessions"]],
            )
            self.assertEqual(
                "from sqlite",
                payload["scopes"][0]["sessions"][0]["history"][0]["content"],
            )
            self.assertEqual([], validate_postgres_seed_export(payload))
            sqlite_store.close()

    def test_sqlite_source_path_is_explicit_and_does_not_mix_workspace_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            external_root = Path(temp_dir) / "selected-sqlite"
            SessionStore(workspace / ".echobot" / "sessions").create_session(
                "jsonl-session"
            )
            sqlite_store = SQLiteSessionStore(external_root / "sessions.sqlite3")
            sqlite_store.create_session("sqlite-session")

            payload = build_postgres_seed_export(
                workspace,
                sqlite_source=external_root / "sessions.sqlite3",
            )

            self.assertEqual("sqlite", payload["session_source"])
            self.assertEqual(
                ["sqlite-session"],
                [item["name"] for item in payload["scopes"][0]["sessions"]],
            )
            sqlite_store.close()

    def test_sqlite_storage_root_exports_user_scopes_without_jsonl_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            sqlite_root = workspace / ".echobot"
            default_store = SQLiteSessionStore(sqlite_root / "sessions.sqlite3")
            default_store.create_session("default-sqlite")
            alice_store = SQLiteSessionStore(
                sqlite_root / "users" / "alice" / "sessions.sqlite3"
            )
            alice_store.create_session("alice-sqlite")

            payload = build_postgres_seed_export(workspace, session_source="sqlite")

            self.assertEqual(
                ["default", "alice"],
                [scope["owner_user_id"] for scope in payload["scopes"]],
            )
            self.assertEqual(
                ["alice-sqlite"],
                [item["name"] for item in payload["scopes"][1]["sessions"]],
            )
            default_store.close()
            alice_store.close()

    def test_missing_sqlite_source_fails_instead_of_falling_back_to_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            SessionStore(workspace / ".echobot" / "sessions").create_session(
                "jsonl-session"
            )

            with self.assertRaisesRegex(
                FileNotFoundError,
                "Selected SQLite session source",
            ):
                build_postgres_seed_export(workspace, session_source="sqlite")

    def test_sqlite_export_never_initializes_or_reconfigures_source_database(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            db_path = workspace / ".echobot" / "sessions.sqlite3"
            db_path.parent.mkdir(parents=True)
            connection = sqlite3.connect(db_path)
            connection.execute("CREATE TABLE marker(value TEXT)")
            connection.commit()
            before_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            connection.close()

            with self.assertRaisesRegex(ValueError, "SQLite session source"):
                build_postgres_seed_export(workspace, session_source="sqlite")

            connection = sqlite3.connect(db_path)
            after_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            connection.close()
            self.assertEqual(before_mode, after_mode)
            self.assertEqual({"marker"}, tables)

    def test_unknown_or_conflicting_source_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            with self.assertRaisesRegex(ValueError, "session source must be one of"):
                build_postgres_seed_export(workspace, session_source="redis")

            with self.assertRaisesRegex(ValueError, "same backend"):
                build_postgres_seed_export(
                    workspace,
                    session_source="sqlite",
                    session_store_backend="jsonl",
                )

            malformed_db = workspace / ".echobot" / "sessions.sqlite3"
            malformed_db.parent.mkdir(parents=True)
            malformed_db.write_bytes(b"not a sqlite database")
            with self.assertRaisesRegex(ValueError, "Unable to open selected SQLite"):
                build_postgres_seed_export(workspace, session_source="sqlite")

            malformed_payload = {"session_source": []}
            self.assertTrue(
                any(
                    "session_source must be one of" in error
                    for error in validate_postgres_seed_export(malformed_payload)
                )
            )

    def test_write_export_propagates_selected_sqlite_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            sqlite_store = SQLiteSessionStore(workspace / ".echobot" / "sessions.sqlite3")
            sqlite_store.create_session("sqlite-session")
            output = workspace / "seed.json"

            payload = write_postgres_seed_export(
                workspace,
                output,
                session_source="sqlite",
            )

            self.assertEqual("sqlite", payload["session_source"])
            self.assertTrue(output.exists())
            sqlite_store.close()


if __name__ == "__main__":
    unittest.main()
