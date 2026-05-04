from __future__ import annotations

import asyncio
import gc
import tempfile
import unittest
import warnings
from pathlib import Path

from echobot import AgentCore, LLMMessage, LLMResponse
from echobot.orchestration import (
    ConversationCoordinator,
    ConversationJobStore,
    DecisionEngine,
    RoleCardRegistry,
    RoleplayEngine,
)
from echobot.models import ToolCall
from echobot.orchestration.jobs import JOB_CANCELLED_TEXT
from echobot.providers.base import LLMProvider
from echobot.runtime.session_runner import SessionAgentRunner
from echobot.runtime.sessions import SessionStore
from echobot.tools import RequestUserInputTool, ToolRegistry


class FakeRoleplayProvider(LLMProvider):
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
        system_text = "\n".join(
            message.content_text
            for message in messages
            if getattr(message, "role", "") == "system"
        )
        user_text = messages[-1].content_text if messages else ""
        if "The system decided this request needs the full agent" in system_text:
            content = "working"
        elif user_text.startswith("The full agent needs one follow-up answer before continuing."):
            content = "让我先确认一下。"
        elif user_text.startswith("The full agent finished the task."):
            content = "done"
        elif user_text.startswith("The full agent failed while handling the task."):
            content = "failed"
        else:
            content = "pong"
        return LLMResponse(
            message=LLMMessage(role="assistant", content=content),
            model="fake-roleplay-model",
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


class SlowAgentProvider(LLMProvider):
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
        await asyncio.sleep(5)
        return LLMResponse(
            message=LLMMessage(role="assistant", content="done-late"),
            model="slow-agent-model",
        )


class CapturingAgentProvider(LLMProvider):
    def __init__(self) -> None:
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
            message=LLMMessage(role="assistant", content="done"),
            model="capturing-agent-model",
        )


class AskUserInputProvider(LLMProvider):
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
        tool_calls = [
            ToolCall(
                id="call_need_input",
                name="request_user_input",
                arguments='{"prompt":"请确认要修改哪个文件。"}',
            )
        ]
        return LLMResponse(
            message=LLMMessage(
                role="assistant",
                content="",
                tool_calls=tool_calls,
            ),
            model="ask-input-model",
            tool_calls=tool_calls,
        )


class AskThenContinueProvider(LLMProvider):
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
            tool_calls = [
                ToolCall(
                    id="call_need_input",
                    name="request_user_input",
                    arguments='{"prompt":"请确认要修改哪个文件。"}',
                )
            ]
            return LLMResponse(
                message=LLMMessage(
                    role="assistant",
                    content="",
                    tool_calls=tool_calls,
                ),
                model="ask-input-model",
                tool_calls=tool_calls,
            )

        return LLMResponse(
            message=LLMMessage(role="assistant", content="done-after-input"),
            model="continue-model",
        )


class ConversationCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_delegated_ack_can_be_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            coordinator, session_store = self._build_coordinator(
                Path(temp_dir),
                agent_provider=FakeRoleplayProvider(),
                delegated_ack_enabled=False,
            )

            result = await coordinator.handle_user_turn(
                "demo",
                "Please set a cron reminder",
            )

            job = None
            for _ in range(20):
                job = await coordinator.get_job(result.job_id or "")
                if job is not None and job.status != "running":
                    break
                await asyncio.sleep(0.01)

            session = session_store.load_session("demo")
            await coordinator.close()

            assert job is not None
            self.assertTrue(result.delegated)
            self.assertFalse(result.completed)
            self.assertEqual("", result.response_text)
            self.assertEqual("", job.immediate_response)
            self.assertEqual("completed", job.status)
            self.assertEqual(
                ["Please set a cron reminder", "done"],
                [message.content for message in session.history],
            )

    async def test_response_language_reaches_agent_without_persisting_instruction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            agent_provider = CapturingAgentProvider()
            coordinator, session_store = self._build_coordinator(
                Path(temp_dir),
                agent_provider=agent_provider,
                delegated_ack_enabled=False,
            )

            result = await coordinator.handle_user_turn(
                "demo",
                "Please set a cron reminder",
                response_language="zh-Hant",
            )

            job = None
            for _ in range(20):
                job = await coordinator.get_job(result.job_id or "")
                if job is not None and job.status != "running":
                    break
                await asyncio.sleep(0.01)

            session = session_store.load_session("demo")
            await coordinator.close()

            assert job is not None
            self.assertEqual("zh-Hant", job.response_language)
            system_text = "\n".join(
                message.content_text
                for message in agent_provider.messages
                if getattr(message, "role", "") == "system"
            )
            self.assertIn("Default response language: Traditional Chinese", system_text)
            self.assertIn("If the user's latest prompt explicitly requests another response language", system_text)
            history_text = "\n".join(str(message.content) for message in session.history)
            self.assertNotIn("Default response language", history_text)

    async def test_close_cancels_pending_job_without_runtime_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            coordinator, session_store = self._build_coordinator(Path(temp_dir))

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                result = await coordinator.handle_user_turn(
                    "demo",
                    "Please set a cron reminder",
                )
                await coordinator.close()
                job = await coordinator.get_job(result.job_id or "")

                self.assertIsNotNone(job)
                assert job is not None
                self.assertEqual("cancelled", job.status)
                self.assertEqual(JOB_CANCELLED_TEXT, job.final_response)

                session = session_store.load_session("demo")
                self.assertEqual(
                    ["Please set a cron reminder", "working"],
                    [message.content for message in session.history],
                )

                coordinator = None
                gc.collect()

            self.assertEqual([], self._never_awaited_warnings(caught))

    async def test_cancel_job_before_runner_starts_does_not_leave_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            coordinator, session_store = self._build_coordinator(Path(temp_dir))

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                result = await coordinator.handle_user_turn(
                    "demo",
                    "Please set a cron reminder",
                )
                job = await coordinator.cancel_job(result.job_id or "")

                self.assertIsNotNone(job)
                assert job is not None
                self.assertEqual("cancelled", job.status)
                self.assertEqual(JOB_CANCELLED_TEXT, job.final_response)

                session = session_store.load_session("demo")
                self.assertEqual(
                    [
                        "Please set a cron reminder",
                        "working",
                        JOB_CANCELLED_TEXT,
                    ],
                    [message.content for message in session.history],
                )

                await coordinator.close()
                coordinator = None
                gc.collect()

            self.assertEqual([], self._never_awaited_warnings(caught))

    async def test_background_job_can_pause_for_user_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            coordinator, session_store = self._build_coordinator(
                Path(temp_dir),
                agent_provider=AskUserInputProvider(),
                tool_registry_factory=lambda *_args: ToolRegistry([RequestUserInputTool()]),
            )

            result = await coordinator.handle_user_turn(
                "demo",
                "Please set a cron reminder",
            )

            job = None
            for _ in range(20):
                job = await coordinator.get_job(result.job_id or "")
                if job is not None and job.status != "running":
                    break
                await asyncio.sleep(0.01)

            session = session_store.load_session("demo")
            await coordinator.close()

            assert job is not None
            self.assertEqual("waiting_for_input", job.status)
            self.assertEqual(
                "请确认要修改哪个文件。",
                job.pending_user_input["prompt"],
            )
            self.assertIn("让我先确认一下。", job.final_response)
            self.assertIn("请确认要修改哪个文件。", job.final_response)
            self.assertIn("让我先确认一下。", session.history[-1].content_text)
            self.assertIn("请确认要修改哪个文件。", session.history[-1].content_text)

    async def test_reply_to_pending_user_input_forces_agent_continuation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            coordinator, session_store = self._build_coordinator(
                Path(temp_dir),
                agent_provider=AskThenContinueProvider(),
                tool_registry_factory=lambda *_args: ToolRegistry([RequestUserInputTool()]),
            )

            first_result = await coordinator.handle_user_turn(
                "demo",
                "Please set a cron reminder",
            )
            for _ in range(20):
                first_job = await coordinator.get_job(first_result.job_id or "")
                if first_job is not None and first_job.status != "running":
                    break
                await asyncio.sleep(0.01)

            second_result = await coordinator.handle_user_turn(
                "demo",
                "src/app.py",
            )

            second_job = None
            for _ in range(20):
                second_job = await coordinator.get_job(second_result.job_id or "")
                if second_job is not None and second_job.status != "running":
                    break
                await asyncio.sleep(0.01)

            session = session_store.load_session("demo")
            await coordinator.close()

            assert second_job is not None
            self.assertTrue(second_result.delegated)
            self.assertEqual("completed", second_job.status)
            self.assertEqual("done", second_job.final_response)
            self.assertNotIn("pending_user_input", session.metadata)

    async def test_job_store_restores_running_job_as_failed_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "jobs.json"
            store = ConversationJobStore(store_path)
            created = await store.create(
                session_name="demo",
                prompt="Please set a cron reminder",
                immediate_response="working",
                role_name="default",
            )

            reloaded_store = ConversationJobStore(store_path)
            restored = await reloaded_store.get(created.job_id)

            self.assertIsNotNone(restored)
            assert restored is not None
            self.assertEqual("failed", restored.status)
            self.assertEqual("任务因 EchoBot 重启而中断。", restored.final_response)
            self.assertEqual("任务因 EchoBot 重启而中断。", restored.error)

    async def test_job_store_persists_concurrent_creates_without_losing_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "jobs.json"
            store = ConversationJobStore(store_path)

            await asyncio.gather(
                store.create(
                    session_name="alpha",
                    prompt="first",
                    immediate_response="",
                    role_name="default",
                ),
                store.create(
                    session_name="beta",
                    prompt="second",
                    immediate_response="",
                    role_name="default",
                ),
                store.create(
                    session_name="gamma",
                    prompt="third",
                    immediate_response="",
                    role_name="default",
                ),
            )

            reloaded_store = ConversationJobStore(store_path)
            jobs = await reloaded_store.list_jobs(limit=10)

            self.assertEqual(3, len(jobs))
            self.assertEqual(
                {"alpha", "beta", "gamma"},
                {job.session_name for job in jobs},
            )

    def _build_coordinator(
        self,
        workspace: Path,
        *,
        agent_provider: LLMProvider | None = None,
        delegated_ack_enabled: bool = True,
        tool_registry_factory=None,
    ) -> tuple[ConversationCoordinator, SessionStore]:
        session_store = SessionStore(workspace / "sessions")
        agent_session_store = SessionStore(workspace / "agent_sessions")
        role_registry = RoleCardRegistry.discover(project_root=workspace)
        coordinator = ConversationCoordinator(
            session_store=session_store,
            agent_runner=SessionAgentRunner(
                AgentCore(agent_provider or SlowAgentProvider()),
                agent_session_store,
                tool_registry_factory=tool_registry_factory,
            ),
            decision_engine=DecisionEngine(),
            roleplay_engine=RoleplayEngine(
                AgentCore(FakeRoleplayProvider()),
                role_registry,
            ),
            role_registry=role_registry,
            delegated_ack_enabled=delegated_ack_enabled,
        )
        return coordinator, session_store

    def _never_awaited_warnings(
        self,
        caught: list[warnings.WarningMessage],
    ) -> list[warnings.WarningMessage]:
        return [
            warning
            for warning in caught
            if issubclass(warning.category, RuntimeWarning)
            and "was never awaited" in str(warning.message)
        ]
