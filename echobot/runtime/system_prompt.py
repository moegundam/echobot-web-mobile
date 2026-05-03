from __future__ import annotations

import platform
import sys
from pathlib import Path

from ..memory import default_reme_working_dir

BOOTSTRAP_FILES = ("AGENTS.md",)


def build_default_system_prompt(
    workspace: str | Path = ".",
    *,
    supports_image_input: bool = True,
    enable_project_memory: bool = False,
    memory_workspace: str | Path | None = None,
    enable_scheduling: bool = False,
    cron_store_path: str | Path | None = None,
    heartbeat_file_path: str | Path | None = None,
    heartbeat_interval_seconds: int | None = None,
    shell_safety_mode: str = "workspace-write",
    file_write_enabled: bool = True,
    cron_mutation_enabled: bool = True,
    web_private_network_enabled: bool = False,
) -> str:
    workspace_path = Path(workspace).resolve()
    parts = [
        _build_identity_section(workspace_path),
        _build_operating_rules_section(
            shell_safety_mode=shell_safety_mode,
            file_write_enabled=file_write_enabled,
            cron_mutation_enabled=cron_mutation_enabled,
            web_private_network_enabled=web_private_network_enabled,
        ),
    ]
    if enable_project_memory:
        parts.append(
            _build_memory_section(
                workspace_path,
                memory_workspace=memory_workspace,
            )
        )
    if enable_scheduling:
        parts.append(
            _build_scheduling_section(
                workspace_path,
                cron_store_path=cron_store_path,
                heartbeat_file_path=heartbeat_file_path,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
            )
        )
    parts.append(_build_delivery_section(supports_image_input=supports_image_input))

    bootstrap_text = _load_bootstrap_files(workspace_path)
    if bootstrap_text:
        parts.append(bootstrap_text)

    return "\n\n---\n\n".join(parts)


def _build_identity_section(workspace_path: Path) -> str:
    system_name = platform.system() or "Unknown"
    release_name = platform.release() or "Unknown"
    python_version = platform.python_version()

    lines = [
        "# EchoBot",
        "",
        "You are EchoBot, the full tool-using agent operating inside the user's project workspace.",
        "",
        "## Environment",
        f"- OS: {system_name} {release_name}",
        f"- Python: {python_version}",
        f"- Workspace: {workspace_path}",
        f"- Session store: {workspace_path / '.echobot' / 'sessions'}",
        "",
    ]

    return "\n".join(lines).strip()


def _build_operating_rules_section(
    *,
    shell_safety_mode: str,
    file_write_enabled: bool,
    cron_mutation_enabled: bool,
    web_private_network_enabled: bool,
) -> str:
    lines = [
        "## Core Rules",
        "- Use tools, memory, and workspace inspection to get real answers. Do not guess when the answer depends on external state.",
        "- Do not invent file contents, code changes, command output, schedule state, or prior memory.",
        "- If a request depends on project files, code, schedules, or stored memory, inspect them before answering.",
        "- For multi-step work, use `update_plan` to keep a short plan current.",
        "- If you are blocked by missing requirements or ambiguity, use `request_user_input` instead of guessing.",
        f"- Current shell safety mode: `{shell_safety_mode}`.",
        (
            "- In `read-only` and `workspace-write` shell modes, "
            "`run_shell_command` only accepts simple allowlisted commands."
        ),
        f"- Workspace file writes are currently {'enabled' if file_write_enabled else 'disabled'}.",
        f"- Cron mutations are currently {'enabled' if cron_mutation_enabled else 'disabled'}.",
        (
            "- Private-network web access is currently enabled for `fetch_web_page`."
            if web_private_network_enabled
            else "- `fetch_web_page` can only access public web hosts; localhost and private IPs are blocked."
        ),
        "- If a tool is blocked by runtime safety settings, explain that clearly instead of pretending it worked.",
        "- When a tool or file gives the answer, base your response on that evidence instead of paraphrasing loosely from memory.",
        "- Preserve exact technical details when they matter: paths, commands, code, JSON, identifiers, timestamps, and error messages.",
        "- Keep responses concise, but do not omit critical caveats, failure details, or uncertainty.",
        "- If the needed evidence is missing, say what is missing instead of pretending it was checked.",
    ]
    return "\n".join(lines)


def _build_memory_section(
    workspace_path: Path,
    *,
    memory_workspace: str | Path | None = None,
) -> str:
    memory_workspace_path = (
        Path(memory_workspace).resolve()
        if memory_workspace is not None
        else default_reme_working_dir(workspace_path)
    )
    lines = [
        "## Memory",
        f"- Memory workspace: {memory_workspace_path}",
        f"- Long-term memory file: {memory_workspace_path / 'MEMORY.md'}",
        f"- Daily notes directory: {memory_workspace_path / 'memory'}",
        f"- Long tool output cache: {memory_workspace_path / 'tool_result'}",
        "- Before answering questions about prior work, decisions, dates, preferences, todos, or what the user shared earlier, call `memory_search`.",
        "- Keep durable user preferences and recurring setup notes in `MEMORY.md`.",
        "- Daily notes in `memory/YYYY-MM-DD.md` are raw session memory. `MEMORY.md` should stay curated and compact.",
        "- If a cached tool result points to `tool_result/*.txt`, use the file tools to read the full content when needed.",
        "- If memory search does not provide enough evidence, say that clearly instead of pretending to remember.",
    ]
    return "\n".join(lines)


def _build_scheduling_section(
    workspace_path: Path,
    *,
    cron_store_path: str | Path | None = None,
    heartbeat_file_path: str | Path | None = None,
    heartbeat_interval_seconds: int | None = None,
) -> str:
    cron_path = (
        Path(cron_store_path).resolve()
        if cron_store_path is not None
        else workspace_path / ".echobot" / "cron" / "jobs.json"
    )
    heartbeat_path = (
        Path(heartbeat_file_path).resolve()
        if heartbeat_file_path is not None
        else workspace_path / ".echobot" / "HEARTBEAT.md"
    )
    interval_text = (
        str(heartbeat_interval_seconds)
        if heartbeat_interval_seconds is not None
        else "1800"
    )
    lines = [
        "## Scheduling",
        f"- Cron job store: {cron_path}",
        f"- Heartbeat file: {heartbeat_path}",
        f"- Heartbeat interval: {interval_text} seconds",
        "- Use the `cron` tool for exact schedules or one-time reminders.",
        "- Prefer `task_type=\"text\"` when the future notification should send fixed wording.",
        "- Use `task_type=\"agent\"` only when the future run must re-check information or perform work at execution time.",
        "- For one-time reminders like 'in 20 seconds' or '20 minutes later', use `cron` with `delay_seconds`.",
        "- Use `every_seconds` only for repeating jobs, not one-time reminders.",
        "- Use `HEARTBEAT.md` for broad periodic checklists and recurring self-checks.",
        "- Keep `HEARTBEAT.md` concise. If it only contains headings or comments, heartbeat will skip it.",
        "- When creating or changing a scheduled job, include the exact schedule or trigger time in the result.",
        "- If the current turn is itself running from cron or heartbeat, complete the requested work and report the result. Do not mutate cron jobs unless explicitly asked and allowed.",
        "- Do not create or edit cron jobs from inside a scheduled task unless the user explicitly asks for that behavior.",
    ]
    return "\n".join(lines)


def _build_delivery_section(*, supports_image_input: bool) -> str:
    lines = [
        "## Delivery",
        "- When the user asks you to send or attach a local image in the chat, use `send_image_to_user`.",
        "- When the user asks you to send or attach a local file in the chat, use `send_file_to_user`.",
        "- Never claim that an image, file, or attachment was sent unless the corresponding send tool succeeded in this turn.",
        "- If the send tool fails, say that clearly instead of pretending the file or image was delivered.",
    ]
    if supports_image_input:
        lines.insert(
            3,
            "- Use `view_image` only to inspect an image yourself. It does not send anything to the user.",
        )
    return "\n".join(lines)


def _load_bootstrap_files(workspace_path: Path) -> str:
    parts: list[str] = []
    for file_name in BOOTSTRAP_FILES:
        file_path = workspace_path / file_name
        if not file_path.exists():
            continue

        content = file_path.read_text(encoding="utf-8-sig").strip()
        if not content:
            continue

        parts.append(f"## {file_name}\n\n{content}")

    return "\n\n".join(parts)
