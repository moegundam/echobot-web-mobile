from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from echobot.cli.main import build_parser
from echobot.cli.common import runtime_options_from_args
from echobot.models import LLMMessage, ToolCall
from echobot.runtime.bootstrap import (
    RuntimeOptions,
    build_runtime_context,
    close_session_repositories,
)
from echobot.runtime.session_repository import SessionRepository
from echobot.runtime.sessions import ChatSession, SessionStore
from echobot.runtime.sqlite_sessions import SQLiteSessionStore


class SessionRepositoryContractTests(unittest.TestCase):
    def _stores(self, root: Path):
        return (
            SessionStore(root / "jsonl"),
            SQLiteSessionStore(root / "sqlite" / "sessions.sqlite3"),
        )

    def test_jsonl_and_sqlite_implement_the_same_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            for store in self._stores(Path(temp_dir)):
                self.assertIsInstance(store, SessionRepository)

    def test_crud_rename_delete_and_current_pointer_are_backend_parity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            for store in self._stores(Path(temp_dir)):
                created = store.create_session("demo")
                self.assertEqual("demo", created.name)
                self.assertEqual("demo", store.load_session("demo").name)
                self.assertEqual(["demo"], [item.name for item in store.list_sessions()])

                renamed = store.rename_session("demo", "renamed")
                self.assertEqual("renamed", renamed.name)
                self.assertFalse(store.has_session("demo"))
                self.assertTrue(store.has_session("renamed"))
                self.assertEqual("renamed", store.get_current_session_name())

                store.delete_session("renamed")
                self.assertFalse(store.has_session("renamed"))
                self.assertEqual([], store.list_sessions())

    def test_messages_tool_calls_content_and_metadata_round_trip(self) -> None:
        message = LLMMessage(
            role="assistant",
            content=[
                {"type": "text", "text": "answer"},
                {"type": "image_url", "image_url": {"url": "https://example.test/a"}},
            ],
            name="Echo",
            tool_call_id="tool-result-1",
            tool_calls=[
                ToolCall(
                    id="call-1",
                    name="search",
                    arguments='{"query":"session"}',
                )
            ],
            reasoning_content="short reasoning",
            reasoning_field="reasoning",
        )
        session = ChatSession(
            name="rich",
            history=[message],
            updated_at="2026-01-01T00:00:00+08:00",
            compressed_summary="summary",
            metadata={"owner": "operator", "flags": ["a", 2]},
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            for store in self._stores(Path(temp_dir)):
                store.save_session(session)
                loaded = store.load_session("rich")
                self.assertEqual(session.metadata, loaded.metadata)
                self.assertEqual(session.compressed_summary, loaded.compressed_summary)
                self.assertEqual(message.content, loaded.history[0].content)
                self.assertEqual(
                    message.tool_calls[0].arguments,
                    loaded.history[0].tool_calls[0].arguments,
                )
                self.assertEqual(message.reasoning_content, loaded.history[0].reasoning_content)
                self.assertEqual(message.reasoning_field, loaded.history[0].reasoning_field)

    def test_compare_and_set_preserves_revision_aba_protection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            for store in self._stores(Path(temp_dir)):
                store.create_session("anchor")
                store.create_session("target")
                store.set_current_session("target")
                name, revision = store.get_current_session_pointer()
                store.set_current_session("target")

                self.assertFalse(
                    store.compare_and_set_current_session(
                        name,
                        "anchor",
                        expected_revision=revision,
                    )
                )
                self.assertEqual("target", store.get_current_session_name())

    def test_repair_current_session_after_deletion_matches_jsonl_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            for store in self._stores(Path(temp_dir)):
                store.create_session("older")
                store.create_session("deleted")
                store.set_current_session("deleted")
                store.delete_session("deleted")

                replacement = store.repair_current_session_after_deletion("deleted")
                self.assertIsNotNone(replacement)
                self.assertEqual("older", replacement.name)
                self.assertEqual("older", store.get_current_session_name())

    def test_stale_current_pointer_does_not_resurrect_deleted_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            for store in self._stores(Path(temp_dir)):
                store.create_session("survivor")
                store.create_session("deleted")
                store.delete_session("deleted")

                current = store.load_current_session()

                self.assertEqual("survivor", current.name)
                self.assertFalse(store.has_session("deleted"))
                self.assertEqual("survivor", store.get_current_session_name())

    def test_sqlite_uses_wal_and_busy_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "sessions.sqlite3"
            store = SQLiteSessionStore(db_path)
            self.assertEqual("wal", store.connection.execute("PRAGMA journal_mode").fetchone()[0])
            self.assertGreaterEqual(
                store.connection.execute("PRAGMA busy_timeout").fetchone()[0],
                1000,
            )
            self.assertTrue(hasattr(store, "_lock"))

    def test_sqlite_transaction_rolls_back_on_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SQLiteSessionStore(Path(temp_dir) / "sessions.sqlite3")
            with self.assertRaisesRegex(RuntimeError, "rollback"):
                with store.transaction() as connection:
                    connection.execute(
                        "INSERT INTO sessions(name, updated_at, compressed_summary, metadata_json) "
                        "VALUES (?, ?, ?, ?)",
                        ("transient", "now", "", "{}"),
                    )
                    raise RuntimeError("rollback")
            self.assertFalse(store.has_session("transient"))

    def test_sqlite_load_uses_one_read_transaction_for_session_and_messages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SQLiteSessionStore(Path(temp_dir) / "sessions.sqlite3")
            store.create_session("consistent")
            statements: list[str] = []
            store.connection.set_trace_callback(statements.append)

            store.load_session("consistent")

            normalized = [statement.strip().upper() for statement in statements]
            begin_index = next(
                index for index, statement in enumerate(normalized)
                if statement == "BEGIN"
            )
            session_index = next(
                index for index, statement in enumerate(normalized)
                if "FROM SESSIONS WHERE NAME" in statement
            )
            messages_index = next(
                index for index, statement in enumerate(normalized)
                if "FROM MESSAGES WHERE SESSION_NAME" in statement
            )
            commit_index = next(
                index for index, statement in enumerate(normalized)
                if statement == "COMMIT"
            )
            self.assertLess(begin_index, session_index)
            self.assertLess(session_index, messages_index)
            self.assertLess(messages_index, commit_index)

    def test_sqlite_close_is_idempotent_and_releases_connection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SQLiteSessionStore(Path(temp_dir) / "sessions.sqlite3")
            store.create_session("before-close")
            store.close()
            store.close()
            with self.assertRaises(sqlite3.ProgrammingError):
                store.has_session("before-close")

    def test_runtime_context_closes_optional_session_repositories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            context = build_runtime_context(
                RuntimeOptions(
                    workspace=Path(temp_dir),
                    allow_unconfigured_llm=True,
                    no_memory=True,
                    no_tools=True,
                    no_skills=True,
                    no_heartbeat=True,
                    session_store_backend="sqlite",
                ),
                load_session_state=False,
            )
            context.close_session_stores()
            context.close_session_stores()

    def test_repository_cleanup_attempts_every_close_before_reporting_failure(self) -> None:
        calls: list[str] = []

        class FailingRepository:
            def close(self) -> None:
                calls.append("first")
                raise RuntimeError("first close failed")

        class HealthyRepository:
            def close(self) -> None:
                calls.append("second")

        with self.assertRaisesRegex(RuntimeError, "first close failed"):
            close_session_repositories(FailingRepository(), HealthyRepository())

        self.assertEqual(["first", "second"], calls)


class SessionBackendSelectorTests(unittest.TestCase):
    def _options(self, workspace: Path, **kwargs) -> RuntimeOptions:
        return RuntimeOptions(
            workspace=workspace,
            allow_unconfigured_llm=True,
            no_memory=True,
            no_tools=True,
            no_skills=True,
            no_heartbeat=True,
            **kwargs,
        )

    def test_runtime_context_can_select_sqlite_for_both_session_stores(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            context = build_runtime_context(
                self._options(Path(temp_dir), session_store_backend="sqlite"),
                load_session_state=False,
            )
            self.assertIsInstance(context.session_store, SQLiteSessionStore)
            self.assertIsInstance(context.agent_session_store, SQLiteSessionStore)

    def test_runtime_context_can_select_agent_backend_independently(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            context = build_runtime_context(
                self._options(
                    Path(temp_dir),
                    session_store_backend="jsonl",
                    agent_session_store_backend="sqlite",
                ),
                load_session_state=False,
            )
            self.assertIsInstance(context.session_store, SessionStore)
            self.assertIsInstance(context.agent_session_store, SQLiteSessionStore)

    def test_invalid_session_backend_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "session store backend"):
                build_runtime_context(
                    self._options(Path(temp_dir), session_store_backend="redis"),
                    load_session_state=False,
                )

    def test_cli_defaults_to_jsonl_for_both_backends(self) -> None:
        args = build_parser().parse_args(["chat"])
        options = runtime_options_from_args(args)

        self.assertEqual("jsonl", options.session_store_backend)
        self.assertIsNone(options.agent_session_store_backend)

    def test_cli_passes_independent_backend_selectors(self) -> None:
        args = build_parser().parse_args(
            [
                "app",
                "--session-store-backend",
                "sqlite",
                "--agent-session-store-backend",
                "jsonl",
            ]
        )
        options = runtime_options_from_args(args)

        self.assertEqual("sqlite", options.session_store_backend)
        self.assertEqual("jsonl", options.agent_session_store_backend)

    def test_cli_rejects_unknown_backend(self) -> None:
        parser = build_parser()
        with self.assertRaises(SystemExit) as raised:
            parser.parse_args(["chat", "--session-store-backend", "redis"])
        self.assertEqual(2, raised.exception.code)

        with self.assertRaises(SystemExit) as raised:
            parser.parse_args(["chat", "--agent-session-store-backend", "redis"])
        self.assertEqual(2, raised.exception.code)


if __name__ == "__main__":
    unittest.main()
