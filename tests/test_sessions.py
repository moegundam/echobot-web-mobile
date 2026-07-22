from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from echobot import ChatSession, LLMMessage, SessionStore, ToolCall
from echobot.runtime.sessions import MAX_SESSION_NAME_LENGTH, normalize_session_name


class SessionStoreTests(unittest.TestCase):
    def test_session_name_length_is_bounded_before_filesystem_use(self) -> None:
        with self.assertRaisesRegex(ValueError, "128 characters or fewer"):
            normalize_session_name("a" * (MAX_SESSION_NAME_LENGTH + 1))

    def test_compare_and_set_current_session_preserves_newer_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_store = SessionStore(Path(temp_dir) / "sessions")
            for name in ("anchor", "operation", "newer"):
                session_store.create_session(name)

            session_store.set_current_session("operation")
            self.assertTrue(
                session_store.compare_and_set_current_session("operation", "anchor"),
            )
            self.assertEqual("anchor", session_store.get_current_session_name())

            session_store.set_current_session("newer")
            self.assertFalse(
                session_store.compare_and_set_current_session("operation", "anchor"),
            )
            self.assertEqual("newer", session_store.get_current_session_name())

            self.assertTrue(
                session_store.compare_and_set_current_session("newer", None),
            )
            self.assertIsNone(session_store.get_current_session_name())

    def test_pointer_revision_rejects_same_name_aba(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_store = SessionStore(Path(temp_dir) / "sessions")
            session_store.create_session("anchor")
            session_store.create_session("target")
            session_store.set_current_session("target")
            pointer_name, pointer_revision = (
                session_store.get_current_session_pointer()
            )

            session_store.set_current_session("target")

            self.assertFalse(
                session_store.compare_and_set_current_session(
                    pointer_name,
                    "anchor",
                    expected_revision=pointer_revision,
                ),
            )
            self.assertEqual("target", session_store.get_current_session_name())

    def test_repair_current_session_after_deletion_is_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_store = SessionStore(Path(temp_dir) / "sessions")
            session_store.create_session("anchor")
            session_store.create_session("deleted")
            session_store.set_current_session("deleted")
            session_store.delete_session("deleted")

            replacement = session_store.repair_current_session_after_deletion(
                "deleted",
            )
            self.assertIsNotNone(replacement)
            self.assertEqual("anchor", replacement.name)
            self.assertEqual("anchor", session_store.get_current_session_name())

            session_store.create_session("later-deleted")
            session_store.create_session("newer")
            session_store.set_current_session("later-deleted")
            session_store.delete_session("later-deleted")
            session_store.set_current_session("newer")

            self.assertIsNone(
                session_store.repair_current_session_after_deletion("later-deleted"),
            )
            self.assertEqual("newer", session_store.get_current_session_name())

    def test_repair_current_session_after_last_deletion_creates_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_store = SessionStore(Path(temp_dir) / "sessions")
            session_store.create_session("last")
            session_store.delete_session("last")

            replacement = session_store.repair_current_session_after_deletion("last")

            self.assertIsNotNone(replacement)
            self.assertEqual("default", replacement.name)
            self.assertEqual("default", session_store.get_current_session_name())

    def test_load_current_session_creates_default_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_store = SessionStore(Path(temp_dir) / "sessions")

            session = session_store.load_current_session()

            self.assertEqual("default", session.name)
            self.assertEqual("default", session_store.get_current_session_name())
            self.assertTrue((Path(temp_dir) / "sessions" / "default.jsonl").exists())

    def test_save_and_load_session_preserves_history_and_tool_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_store = SessionStore(Path(temp_dir) / "sessions")
            session = ChatSession(
                name="demo",
                history=[
                    LLMMessage(role="user", content="hello"),
                    LLMMessage(
                        role="assistant",
                        content="",
                        reasoning_content="I should call the file reader.",
                        tool_calls=[
                            ToolCall(
                                id="call_1",
                                name="read_text_file",
                                arguments='{"path":"README.md"}',
                            )
                        ],
                    ),
                    LLMMessage(
                        role="tool",
                        content='{"ok":true}',
                        tool_call_id="call_1",
                    ),
                ],
                updated_at="",
                compressed_summary="previous summary",
            )

            session_store.save_session(session)
            loaded_session = session_store.load_session("demo")

            self.assertEqual("demo", loaded_session.name)
            self.assertEqual("previous summary", loaded_session.compressed_summary)
            self.assertEqual(3, len(loaded_session.history))
            self.assertEqual("user", loaded_session.history[0].role)
            self.assertEqual("read_text_file", loaded_session.history[1].tool_calls[0].name)
            self.assertEqual(
                "I should call the file reader.",
                loaded_session.history[1].reasoning_content,
            )
            self.assertEqual("call_1", loaded_session.history[2].tool_call_id)

            lines = (Path(temp_dir) / "sessions" / "demo.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertEqual(4, len(lines))
            self.assertIn('"type": "session"', lines[0])
            self.assertIn('"type": "message"', lines[1])

    def test_save_and_load_session_preserves_structured_message_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_store = SessionStore(Path(temp_dir) / "sessions")
            session = ChatSession(
                name="vision",
                history=[
                    LLMMessage(
                        role="user",
                        content=[
                            {"type": "text", "text": "look at this"},
                            {
                                "type": "image_url",
                                "image_url": {"url": "data:image/png;base64,AAAA"},
                            },
                        ],
                    ),
                ],
                updated_at="",
            )

            session_store.save_session(session)
            loaded_session = session_store.load_session("vision")

            self.assertEqual(1, len(loaded_session.history))
            self.assertIsInstance(loaded_session.history[0].content, list)
            self.assertEqual("text", loaded_session.history[0].content[0]["type"])
            self.assertEqual(
                "data:image/png;base64,AAAA",
                loaded_session.history[0].content[1]["image_url"]["url"],
            )

    def test_list_sessions_returns_saved_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_store = SessionStore(Path(temp_dir) / "sessions")
            first_session = ChatSession(
                name="first",
                history=[LLMMessage(role="user", content="one")],
                updated_at="",
            )
            second_session = ChatSession(
                name="second",
                history=[
                    LLMMessage(role="user", content="one"),
                    LLMMessage(role="assistant", content="two"),
                ],
                updated_at="",
                compressed_summary="summary",
            )

            session_store.save_session(first_session)
            session_store.save_session(second_session)
            session_store.set_current_session(second_session.name)
            sessions = session_store.list_sessions()

            self.assertEqual({"first", "second"}, {item.name for item in sessions})
            counts = {item.name: item.message_count for item in sessions}
            self.assertEqual(1, counts["first"])
            self.assertEqual(2, counts["second"])

    def test_create_session_rejects_duplicate_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_store = SessionStore(Path(temp_dir) / "sessions")
            session_store.create_session("demo")

            with self.assertRaisesRegex(ValueError, "Session already exists"):
                session_store.create_session("demo")

    def test_create_session_supports_chinese_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_store = SessionStore(Path(temp_dir) / "sessions")

            created = session_store.create_session("项目讨论")
            loaded = session_store.load_session("项目讨论")

            self.assertEqual("项目讨论", created.name)
            self.assertEqual("项目讨论", loaded.name)
            self.assertTrue((Path(temp_dir) / "sessions" / "项目讨论.jsonl").exists())


class SessionNameTests(unittest.TestCase):
    def test_normalize_session_name_keeps_simple_ascii_name(self) -> None:
        self.assertEqual("demo-session_1", normalize_session_name(" Demo Session_1 "))

    def test_normalize_session_name_keeps_chinese_name(self) -> None:
        self.assertEqual("项目-讨论_1", normalize_session_name(" 项目 讨论_1 "))

    def test_normalize_session_name_rejects_empty_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            normalize_session_name("   ")
