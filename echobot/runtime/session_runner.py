from __future__ import annotations

import asyncio
from collections.abc import Sequence
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..agent import AgentCore, AgentRunResult, TraceCallback
from ..models import FileInput, ImageInput, LLMMessage, message_content_to_text
from ..skill_support import SkillRegistry
from ..tools import ToolRegistry
from .agent_traces import AgentTraceStore
from .sessions import ChatSession, SessionStore
from .turns import run_agent_turn


ToolRegistryFactory = Callable[[str, bool], ToolRegistry | None]


@dataclass(slots=True)
class SessionRunResult:
    session: ChatSession
    agent_result: AgentRunResult
    trace_run_id: str | None = None


class SessionAgentRunner:
    def __init__(
        self,
        agent: AgentCore,
        session_store: SessionStore,
        *,
        skill_registry: SkillRegistry | None = None,
        tool_registry_factory: ToolRegistryFactory | None = None,
        default_temperature: float | None = None,
        default_max_tokens: int | None = None,
        default_max_steps: int = 50,
        trace_store: AgentTraceStore | None = None,
    ) -> None:
        self._agent = agent
        self._session_store = session_store
        self._skill_registry = skill_registry
        self._tool_registry_factory = tool_registry_factory
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens
        self._default_max_steps = max(int(default_max_steps), 1)
        self._trace_store = trace_store
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()
        self._deleted_sessions: set[str] = set()
        self._deleted_sessions_guard = asyncio.Lock()

    def set_provider(self, provider) -> None:
        self._agent.provider = provider

    def set_generation_defaults(
        self,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self._default_temperature = temperature
        self._default_max_tokens = max_tokens

    async def load_session(self, session_name: str) -> ChatSession:
        lock = await self._session_lock(session_name)
        async with lock:
            return await asyncio.to_thread(
                self._session_store.load_or_create_session,
                session_name,
            )

    async def mark_session_deleted(self, session_name: str) -> None:
        async with self._deleted_sessions_guard:
            self._deleted_sessions.add(session_name)

    async def restore_session(self, session_name: str) -> None:
        async with self._deleted_sessions_guard:
            self._deleted_sessions.discard(session_name)

    async def run_prompt(
        self,
        session_name: str,
        prompt: str,
        *,
        image_urls: Sequence[ImageInput] | None = None,
        file_attachments: Sequence[FileInput] | None = None,
        scheduled_context: bool = False,
        extra_system_messages: Sequence[str] | None = None,
        transient_system_messages: Sequence[str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        trace_run_id: str | None = None,
    ) -> SessionRunResult:
        lock = await self._session_lock(session_name)
        async with lock:
            deleted = await self._is_session_deleted(session_name)
            if deleted:
                raise RuntimeError(f"Session is deleted: {session_name}")
            session = await asyncio.to_thread(
                self._session_store.load_or_create_session,
                session_name,
            )
            tool_registry = None
            if self._tool_registry_factory is not None:
                tool_registry = await asyncio.to_thread(
                    self._tool_registry_factory,
                    session.name,
                    scheduled_context,
                )

            trace_callback, active_trace_run_id = self._build_trace_callback(
                session.name,
                trace_run_id=trace_run_id,
            )
            if trace_callback is not None:
                await trace_callback(
                    "turn_started",
                    {
                        "prompt": prompt,
                        "image_count": len(image_urls or []),
                        "file_count": len(file_attachments or []),
                        "scheduled_context": scheduled_context,
                        "history_length": len(session.history),
                        "tool_names": tool_registry.names() if tool_registry is not None else [],
                        "extra_system_messages_count": len(extra_system_messages or []),
                        "transient_system_messages_count": len(
                            transient_system_messages or []
                        ),
                    },
                )

            try:
                result = await run_agent_turn(
                    self._agent,
                    prompt,
                    list(session.history),
                    image_urls=image_urls,
                    file_attachments=file_attachments,
                    compressed_summary=session.compressed_summary,
                    skill_registry=self._skill_registry,
                    tool_registry=tool_registry,
                    extra_system_messages=extra_system_messages,
                    transient_system_messages=transient_system_messages,
                    temperature=(
                        self._default_temperature
                        if temperature is None
                        else temperature
                    ),
                    max_tokens=(
                        self._default_max_tokens
                        if max_tokens is None
                        else max_tokens
                    ),
                    max_steps=self._default_max_steps,
                    trace_callback=trace_callback,
                )
                session.history = list(result.history)
                session.compressed_summary = result.compressed_summary
                deleted = await self._is_session_deleted(session.name)
                if not deleted:
                    await asyncio.to_thread(self._session_store.save_session, session)
            except Exception as exc:
                if trace_callback is not None:
                    await trace_callback(
                        "turn_failed",
                        {
                            "error": str(exc),
                            "error_type": type(exc).__name__,
                        },
                    )
                raise

            if trace_callback is not None:
                await trace_callback(
                    "turn_completed",
                    {
                        "steps": result.steps,
                        "status": result.status,
                        "history_length": len(session.history),
                        "final_message": _message_to_trace_dict(result.response.message),
                        "usage": result.response.usage.to_dict(),
                        "compressed_summary": session.compressed_summary,
                        "pending_user_input": result.pending_user_input,
                    },
                )
            return SessionRunResult(
                session=session,
                agent_result=result,
                trace_run_id=active_trace_run_id,
            )

    async def append_assistant_message(
        self,
        session_name: str,
        content: str,
    ) -> ChatSession:
        lock = await self._session_lock(session_name)
        async with lock:
            deleted = await self._is_session_deleted(session_name)
            if deleted:
                return ChatSession(
                    name=session_name,
                    history=[],
                    updated_at="",
                )
            session = await asyncio.to_thread(
                self._session_store.load_or_create_session,
                session_name,
            )
            session.history.append(LLMMessage(role="assistant", content=content))
            deleted = await self._is_session_deleted(session.name)
            if not deleted:
                await asyncio.to_thread(self._session_store.save_session, session)
            return session

    async def load_trace_events(
        self,
        session_name: str,
        run_id: str,
    ) -> list[dict[str, Any]]:
        if self._trace_store is None or not run_id.strip():
            return []
        return await asyncio.to_thread(
            self._trace_store.read_events,
            session_name,
            run_id,
        )

    def create_trace_run_id(self) -> str | None:
        if self._trace_store is None:
            return None
        return self._trace_store.create_run_id()

    async def _session_lock(self, session_name: str) -> asyncio.Lock:
        async with self._locks_guard:
            lock = self._locks.get(session_name)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[session_name] = lock
            return lock

    async def _is_session_deleted(self, session_name: str) -> bool:
        async with self._deleted_sessions_guard:
            return session_name in self._deleted_sessions

    def _build_trace_callback(
        self,
        session_name: str,
        *,
        trace_run_id: str | None = None,
    ) -> tuple[TraceCallback | None, str | None]:
        if self._trace_store is None:
            return None, None

        run_id = trace_run_id or self._trace_store.create_run_id()

        async def callback(event: str, data: dict[str, Any]) -> None:
            await asyncio.to_thread(
                self._trace_store.append_event,
                session_name,
                run_id,
                event,
                dict(data),
            )

        return callback, run_id


def _message_to_trace_dict(message: LLMMessage) -> dict[str, Any]:
    return {
        "role": message.role,
        "content": message.content,
        "content_text": message_content_to_text(message.content),
        "name": message.name,
        "tool_call_id": message.tool_call_id,
        "tool_calls": [
            {
                "id": tool_call.id,
                "name": tool_call.name,
                "arguments": tool_call.arguments,
            }
            for tool_call in message.tool_calls
        ],
    }
