from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from ..agent import AgentCore, AgentRunResult
from ..commands.bindings import CliCommandContext, dispatch_cli_command
from ..memory import ReMeLightSupport
from ..models import LLMMessage
from ..orchestration import ConversationCoordinator
from ..runtime.bootstrap import (
    RuntimeOptions,
    build_runtime_context,
    close_session_repositories,
)
from ..runtime.scheduled_tasks import (
    build_cron_job_executor as build_shared_cron_job_executor,
    build_heartbeat_executor as build_shared_heartbeat_executor,
)
from ..runtime.session_runner import SessionAgentRunner
from ..runtime.session_service import SessionService
from ..runtime.sessions import ChatSession, SessionStore
from ..runtime.turns import run_agent_turn
from ..skill_support import SkillRegistry
from ..tools import ToolRegistry
from .common import add_runtime_arguments, runtime_options_from_args
from .session_commands import (
    clear_history,
    save_session_state,
)


EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit"}
CLEAR_COMMANDS = {"clear", "/clear"}


class CliRuntimeCleanupError(RuntimeError):
    """Reports CLI shutdown failures after every resource was attempted."""

    def __init__(self, failures: list[tuple[str, Exception]]) -> None:
        self.failures = tuple(failures)
        details = "; ".join(
            f"{name}: {type(error).__name__}: {error}"
            for name, error in failures
        )
        super().__init__(f"CLI runtime cleanup failed: {details}")


def configure_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    add_runtime_arguments(parser, include_session=True)
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show tool calls and tool outputs during each turn.",
    )
    parser.set_defaults(handler=run)
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a multi-turn EchoBot chat.",
    )
    return configure_parser(parser)


def print_help(
    *,
    tool_registry: ToolRegistry | None,
    skill_registry: SkillRegistry | None,
    session: ChatSession,
    memory_support: ReMeLightSupport | None,
    cron_store_path: Path | None = None,
    heartbeat_file_path: Path | None = None,
    heartbeat_interval_seconds: int | None = None,
) -> None:
    print("Chat started.")
    print("Type exit or quit to stop.")
    print("Type clear or /clear to clear the conversation history.")
    print("Type /help to show all commands.")
    print("Type /session help to manage saved sessions.")
    print("Type /role help to manage role cards.")
    print("Type /route help to manage the route mode for this session.")
    print("Type /runtime help to manage runtime options.")
    print(f"Current session: {session.name}")
    print(f"Memory support enabled: {'yes' if memory_support is not None else 'no'}")
    if memory_support is not None:
        print(f"Memory workspace: {memory_support.working_dir}")
    print(f"Basic tools enabled: {'yes' if tool_registry is not None else 'no'}")
    if tool_registry is not None:
        print("Available tools: " + ", ".join(tool_registry.names()))
    print(f"Project skills enabled: {'yes' if skill_registry is not None else 'no'}")
    if skill_registry is not None and skill_registry.names():
        print("Available skills: " + ", ".join(skill_registry.names()))
        print("Use /skill-name or $skill-name to activate a skill explicitly.")
    if cron_store_path is not None:
        print(f"Cron store: {cron_store_path}")
    if heartbeat_file_path is not None and heartbeat_interval_seconds is not None:
        print(
            "Heartbeat: "
            f"{heartbeat_file_path} "
            f"(every {heartbeat_interval_seconds}s while this process is running)"
        )
    print()


async def run_turn(
    agent: AgentCore,
    prompt: str,
    history: list[LLMMessage],
    *,
    compressed_summary: str,
    skill_registry: SkillRegistry | None,
    tool_registry: ToolRegistry | None,
    temperature: float | None,
    max_tokens: int | None,
) -> AgentRunResult:
    return await run_agent_turn(
        agent,
        prompt,
        history,
        compressed_summary=compressed_summary,
        skill_registry=skill_registry,
        tool_registry=tool_registry,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def build_runtime(
    args: argparse.Namespace,
) -> tuple[
    AgentCore,
    SessionStore,
    ChatSession,
    ToolRegistry | None,
    SkillRegistry | None,
]:
    context = build_runtime_context(
        _build_runtime_options(args),
        load_session_state=True,
    )
    if context.session is None:
        raise RuntimeError("Chat runtime failed to load the current session")
    return (
        context.agent,
        context.session_store,
        context.session,
        context.tool_registry,
        context.skill_registry,
    )


def read_prompt(session_name: str) -> str | None:
    try:
        return input(f"You[{session_name}]> ").strip()
    except EOFError:
        print()
        return None
    except KeyboardInterrupt:
        print()
        return None


async def _main_async(args: argparse.Namespace) -> None:
    context = build_runtime_context(
        _build_runtime_options(args),
        load_session_state=True,
    )
    if context.session is None:
        raise RuntimeError("Chat runtime failed to load the current session")

    session_store = context.session_store
    session = context.session
    session_service = SessionService(
        session_store,
        context.agent_session_store,
        coordinator=context.coordinator,
    )
    tool_registry = context.tool_registry
    skill_registry = context.skill_registry
    coordinator = context.coordinator
    command_context = CliCommandContext(
        coordinator=coordinator,
        runtime_controls=context.runtime_controls,
        workspace=context.workspace,
        session_service=session_service,
        session_name=session.name,
    )
    heartbeat_interval_seconds = (
        context.heartbeat_service.interval_seconds
        if context.heartbeat_service is not None
        else context.heartbeat_interval_seconds
    )
    if context.heartbeat_service is not None:
        context.heartbeat_service.on_notify = _build_schedule_notifier(
            "heartbeat",
            "Periodic check-in",
        )

    print_help(
        tool_registry=tool_registry,
        skill_registry=skill_registry,
        session=session,
        memory_support=context.memory_support,
        cron_store_path=context.cron_service.store_path,
        heartbeat_file_path=context.heartbeat_file_path,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
    )

    try:
        context.cron_service.on_job = _build_cron_job_executor(
            context.session_runner,
            coordinator,
        )
        await context.cron_service.start()
        if context.heartbeat_service is not None:
            context.heartbeat_service.on_execute = _build_heartbeat_executor(
                context.session_runner,
            )
            await context.heartbeat_service.start()
        while True:
            prompt = await asyncio.to_thread(read_prompt, session.name)
            if prompt is None:
                break

            if not prompt:
                continue
            if prompt in EXIT_COMMANDS:
                break
            if prompt in CLEAR_COMMANDS:
                session = await coordinator.load_session(session.name)
                await asyncio.to_thread(clear_history, session_store, session)
                await asyncio.to_thread(
                    context.agent_session_store.delete_session,
                    session.name,
                )
                command_context.session_name = session.name
                print("History cleared.")
                print()
                continue
            try:
                command_result = await dispatch_cli_command(
                    command_context,
                    prompt,
                )
            except ValueError as exc:
                print(f"Session error: {exc}")
                print()
                continue
            if command_result is not None:
                session = await coordinator.load_session(command_context.session_name)
                print(command_result.text)
                print()
                continue

            try:
                on_chunk, stream_started = _build_streamed_assistant_writer()

                execution = await coordinator.handle_user_turn_stream(
                    command_context.session_name,
                    prompt,
                    on_chunk=on_chunk,
                    completion_callback=_build_async_cli_notifier(
                        command_context.session_name
                    ),
                )
            except ValueError as exc:
                print(f"Role error: {exc}")
                print()
                continue
            except RuntimeError as exc:
                print(f"Request failed: {exc}")
                print()
                continue

            session = execution.session
            command_context.session_name = session.name
            await asyncio.to_thread(save_session_state, session_store, session)
            content = execution.response_text.strip()
            if not content and execution.delegated and not execution.completed:
                print()
                continue
            if not content:
                content = "Model returned no text content."
            if stream_started():
                print()
            else:
                print(f"Assistant> {content}")
            print()
    finally:
        await cleanup_cli_runtime_resources(context, coordinator)


def run(args: argparse.Namespace) -> None:
    asyncio.run(_main_async(args))


async def cleanup_cli_runtime_resources(context, coordinator) -> None:
    failures: list[tuple[str, Exception]] = []

    async def attempt(name: str, cleanup) -> None:
        try:
            await cleanup()
        except Exception as exc:
            failures.append((name, exc))

    await attempt("cron", context.cron_service.stop)
    if context.heartbeat_service is not None:
        await attempt("heartbeat", context.heartbeat_service.stop)
    await attempt("coordinator", coordinator.close)
    if context.memory_support is not None:
        await attempt("memory", context.memory_support.close)
    try:
        close_session_repositories(
            context.session_store,
            context.agent_session_store,
        )
    except Exception as exc:
        failures.append(("session repositories", exc))

    if failures:
        raise CliRuntimeCleanupError(failures)


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    run(args)


def _build_cron_job_executor(
    session_runner: SessionAgentRunner,
    coordinator: ConversationCoordinator,
):
    return build_shared_cron_job_executor(
        session_runner,
        coordinator,
        _notify_cli_schedule,
    )


def _build_heartbeat_executor(session_runner: SessionAgentRunner):
    return build_shared_heartbeat_executor(session_runner)


async def _notify_cli_schedule(
    _session_name: str,
    kind: str,
    title: str,
    content: str,
) -> None:
    await _build_schedule_notifier(kind, title)(content)


def _build_schedule_notifier(kind: str, title: str):
    async def notify(content: str) -> None:
        print()
        if title.strip() != content.strip():
            print(f"[{kind}] {title}")
        for line in content.splitlines() or [content]:
            print(f"[{kind}] {line}")
        print()

    return notify


def _build_async_cli_notifier(session_name: str):
    async def notify(job) -> None:
        print()
        print(f"Assistant[{session_name}]> {job.final_response}")
        print()

    return notify


def _build_streamed_assistant_writer() -> tuple[
    Callable[[str], Awaitable[None]],
    Callable[[], bool],
]:
    state = {"started": False}

    async def on_chunk(chunk: str) -> None:
        if not state["started"]:
            print("Assistant> ", end="", flush=True)
            state["started"] = True
        print(chunk, end="", flush=True)

    def started() -> bool:
        return state["started"]

    return on_chunk, started


def _build_runtime_options(args: argparse.Namespace) -> RuntimeOptions:
    return runtime_options_from_args(args)
