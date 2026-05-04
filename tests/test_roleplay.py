from __future__ import annotations

import unittest
from pathlib import Path

from echobot import AgentCore, LLMMessage, LLMResponse
from echobot.orchestration import RoleCardRegistry, RoleplayEngine
from echobot.providers.base import LLMProvider
from echobot.runtime.sessions import ChatSession


_HISTORY_MARKER = "OLD_HISTORY_MARKER"


class HistoryAwareProvider(LLMProvider):
    async def generate(
        self,
        messages,
        *,
        tools=None,
        tool_choice=None,
        temperature=None,
        max_tokens=None,
    ) -> LLMResponse:
        del tools, tool_choice, temperature, max_tokens
        visible_text = "\n".join(
            message.content_text
            for message in messages
            if getattr(message, "role", "") != "system"
        )
        content = "history-present" if _HISTORY_MARKER in visible_text else "history-missing"
        return LLMResponse(
            message=LLMMessage(role="assistant", content=content),
            model="history-aware-provider",
        )

    async def stream_generate(
        self,
        messages,
        *,
        tools=None,
        tool_choice=None,
        temperature=None,
        max_tokens=None,
    ):
        response = await self.generate(
            messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        yield response.message.content


class FailingProvider(LLMProvider):
    async def generate(
        self,
        messages,
        *,
        tools=None,
        tool_choice=None,
        temperature=None,
        max_tokens=None,
    ) -> LLMResponse:
        del messages, tools, tool_choice, temperature, max_tokens
        raise RuntimeError("roleplay exploded")


class TruncatedProvider(LLMProvider):
    def __init__(self, content: str) -> None:
        self._content = content

    async def generate(
        self,
        messages,
        *,
        tools=None,
        tool_choice=None,
        temperature=None,
        max_tokens=None,
    ) -> LLMResponse:
        del messages, tools, tool_choice, temperature, max_tokens
        return LLMResponse(
            message=LLMMessage(role="assistant", content=self._content),
            model="truncated-provider",
            finish_reason="length",
        )


class EmptyAfterStreamFailureProvider(LLMProvider):
    async def generate(
        self,
        messages,
        *,
        tools=None,
        tool_choice=None,
        temperature=None,
        max_tokens=None,
    ) -> LLMResponse:
        del messages, tools, tool_choice, temperature, max_tokens
        return LLMResponse(
            message=LLMMessage(role="assistant", content=""),
            model="empty-after-stream-failure",
        )

    async def stream_generate(
        self,
        messages,
        *,
        tools=None,
        tool_choice=None,
        temperature=None,
        max_tokens=None,
    ):
        del messages, tools, tool_choice, temperature, max_tokens
        if False:  # pragma: no cover
            yield ""
        raise RuntimeError("stream roleplay exploded")


class EmptyStreamProvider(LLMProvider):
    async def generate(
        self,
        messages,
        *,
        tools=None,
        tool_choice=None,
        temperature=None,
        max_tokens=None,
    ) -> LLMResponse:
        del messages, tools, tool_choice, temperature, max_tokens
        return LLMResponse(
            message=LLMMessage(role="assistant", content="non-stream recovery"),
            model="empty-stream-provider",
        )

    async def stream_generate(
        self,
        messages,
        *,
        tools=None,
        tool_choice=None,
        temperature=None,
        max_tokens=None,
    ):
        del messages, tools, tool_choice, temperature, max_tokens
        if False:  # pragma: no cover
            yield ""
        return


class EmptyThenSuccessProvider(LLMProvider):
    def __init__(self) -> None:
        self.calls = 0

    async def generate(
        self,
        messages,
        *,
        tools=None,
        tool_choice=None,
        temperature=None,
        max_tokens=None,
    ) -> LLMResponse:
        del messages, tools, tool_choice, temperature, max_tokens
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                message=LLMMessage(
                    role="assistant",
                    content="",
                    reasoning_content="hidden local-model reasoning",
                ),
                model="empty-then-success-provider",
            )
        return LLMResponse(
            message=LLMMessage(role="assistant", content="visible recovery"),
            model="empty-then-success-provider",
        )

    async def stream_generate(
        self,
        messages,
        *,
        tools=None,
        tool_choice=None,
        temperature=None,
        max_tokens=None,
    ):
        del messages, tools, tool_choice, temperature, max_tokens
        if False:  # pragma: no cover
            yield ""
        return


class CapturingProvider(LLMProvider):
    def __init__(self, content: str = "ok") -> None:
        self.content = content
        self.messages = []

    async def generate(
        self,
        messages,
        *,
        tools=None,
        tool_choice=None,
        temperature=None,
        max_tokens=None,
    ) -> LLMResponse:
        del tools, tool_choice, temperature, max_tokens
        self.messages = list(messages)
        return LLMResponse(
            message=LLMMessage(role="assistant", content=self.content),
            model="capturing-provider",
        )

    async def stream_generate(
        self,
        messages,
        *,
        tools=None,
        tool_choice=None,
        temperature=None,
        max_tokens=None,
    ):
        response = await self.generate(
            messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        yield response.message.content


class RoleplayEngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_delegated_ack_does_not_include_history(self) -> None:
        engine, role_card = self._build_engine()
        session = self._session_with_history()
        chunks: list[str] = []

        async def on_chunk(chunk: str) -> None:
            chunks.append(chunk)

        result = await engine.stream_delegated_ack(
            session=session,
            user_input="帮我查询天气",
            role_card=role_card,
            on_chunk=on_chunk,
        )

        self.assertEqual("history-missing", result)
        self.assertEqual(["history-missing"], chunks)

    async def test_chat_reply_still_includes_history(self) -> None:
        engine, role_card = self._build_engine()
        session = self._session_with_history()

        result = await engine.chat_reply(
            session=session,
            user_input="继续聊刚才的话题",
            role_card=role_card,
        )

        self.assertEqual("history-present", result)

    async def test_chat_reply_includes_response_language_instruction(self) -> None:
        provider = CapturingProvider()
        engine, role_card = self._build_engine(provider)
        session = self._session_with_history()

        result = await engine.chat_reply(
            session=session,
            user_input="請介紹你自己",
            role_card=role_card,
            response_language="zh-Hant",
        )

        self.assertEqual("ok", result)
        system_text = "\n".join(
            message.content_text
            for message in provider.messages
            if getattr(message, "role", "") == "system"
        )
        self.assertIn("Default response language: Traditional Chinese", system_text)
        self.assertIn("do not reply in Simplified Chinese by default", system_text)
        self.assertIn("If the user's latest prompt explicitly requests another response language", system_text)

    async def test_chat_reply_logs_failure_before_returning_fallback(self) -> None:
        engine, role_card = self._build_engine(FailingProvider())
        session = self._session_with_history()

        with self.assertLogs("echobot.orchestration.roleplay", level="ERROR") as logs:
            result = await engine.chat_reply(
                session=session,
                user_input="继续聊天",
                role_card=role_card,
            )

        self.assertEqual("I am here.", result)
        self.assertIn("Roleplay generation failed", logs.output[0])
        self.assertEqual("roleplay exploded", str(logs.records[0].exc_info[1]))

    async def test_stream_chat_reply_logs_failure_before_returning_fallback(self) -> None:
        engine, role_card = self._build_engine(EmptyAfterStreamFailureProvider())
        session = self._session_with_history()
        chunks: list[str] = []

        async def on_chunk(chunk: str) -> None:
            chunks.append(chunk)

        with self.assertLogs("echobot.orchestration.roleplay", level="ERROR") as logs:
            result = await engine.stream_chat_reply(
                session=session,
                user_input="继续聊天",
                role_card=role_card,
                on_chunk=on_chunk,
            )

        self.assertEqual("I am here.", result)
        self.assertEqual([], chunks)
        self.assertIn("Roleplay streaming failed", logs.output[0])
        self.assertEqual("stream roleplay exploded", str(logs.records[0].exc_info[1]))

    async def test_stream_chat_reply_recovers_when_provider_stream_has_no_chunks(self) -> None:
        engine, role_card = self._build_engine(EmptyStreamProvider())
        session = self._session_with_history()
        chunks: list[str] = []

        async def on_chunk(chunk: str) -> None:
            chunks.append(chunk)

        result = await engine.stream_chat_reply(
            session=session,
            user_input="继续聊天",
            role_card=role_card,
            on_chunk=on_chunk,
        )

        self.assertEqual("non-stream recovery", result)
        self.assertEqual(["non-stream recovery"], chunks)

    async def test_chat_reply_retries_when_generation_has_no_visible_content(self) -> None:
        provider = EmptyThenSuccessProvider()
        engine, role_card = self._build_engine(provider)
        session = self._session_with_history()

        with self.assertLogs("echobot.orchestration.roleplay", level="WARNING") as logs:
            result = await engine.chat_reply(
                session=session,
                user_input="继续聊天",
                role_card=role_card,
            )

        self.assertEqual("visible recovery", result)
        self.assertEqual(2, provider.calls)
        self.assertIn("empty visible content", logs.output[0])

    async def test_delegated_ack_logs_warning_when_response_is_truncated(self) -> None:
        engine, role_card = self._build_engine(TruncatedProvider(""))
        session = self._session_with_history()

        with self.assertLogs("echobot.orchestration.roleplay", level="WARNING") as logs:
            result = await engine.delegated_ack(
                session=session,
                user_input="帮我启动后台任务",
                role_card=role_card,
            )

        self.assertEqual(
            "I started working on that and will share the result shortly.",
            result,
        )
        self.assertIn("Roleplay generation hit max_tokens limit", logs.output[0])

    async def test_present_user_input_request_keeps_roleplay_as_lead_in_only(self) -> None:
        engine, role_card = self._build_engine(TruncatedProvider("先和你确认一下。"))
        session = self._session_with_history()

        result = await engine.present_user_input_request(
            session=session,
            follow_up_prompt="请确认要修改哪个文件。",
            choices=["src/app.py", "src/api.py"],
            why_needed="需要定位修改目标",
            role_card=role_card,
        )

        self.assertEqual("先和你确认一下。", result)

    def _build_engine(
        self,
        provider: LLMProvider | None = None,
    ) -> tuple[RoleplayEngine, object]:
        role_registry = RoleCardRegistry(project_root=Path.cwd())
        engine = RoleplayEngine(
            AgentCore(provider or HistoryAwareProvider()),
            role_registry,
        )
        role_card = role_registry.require(None)
        return engine, role_card

    def _session_with_history(self) -> ChatSession:
        return ChatSession(
            name="demo",
            history=[
                LLMMessage(role="user", content=_HISTORY_MARKER),
                LLMMessage(role="assistant", content="之前的回复"),
            ],
            updated_at="",
        )
