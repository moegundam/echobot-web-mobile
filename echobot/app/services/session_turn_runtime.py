from __future__ import annotations

import asyncio
from typing import Any

from ...orchestration import ConversationTurnRuntime
from .runtime_profile_applier import build_chat_model_provider
from .runtime_profile_composer import (
    llm_runtime_profile,
    model_profile_id_for_role,
    runtime_bindings_for_role,
)


async def resolve_session_turn_runtime(
    runtime,
    session_name: str,
    role_name: str,
) -> ConversationTurnRuntime:
    context = getattr(runtime, "context", None)
    if context is None:
        return ConversationTurnRuntime()

    live_override = await _session_override(runtime, session_name)
    runtime_bindings = await runtime_bindings_for_role(runtime, role_name)
    bound_profile_id = await model_profile_id_for_role(runtime, role_name)
    llm_profile_id = str(
        live_override.get("llm_model_id")
        or runtime_bindings.get("llm_model_id")
        or live_override.get("model_profile_id")
        or bound_profile_id
        or "",
    ).strip()
    llm_profile = await _resolve_llm_profile(runtime, llm_profile_id)
    chat = _section(llm_profile, "chat")
    profile_provider = build_chat_model_provider(context, chat)

    decision_provider = profile_provider
    if context.dedicated_decision_provider:
        decision_provider = context.decision_provider

    roleplay_provider = profile_provider
    if context.dedicated_roleplay_provider:
        roleplay_provider = context.roleplay_provider

    return ConversationTurnRuntime(
        agent_provider=profile_provider,
        decision_provider=decision_provider,
        roleplay_provider=roleplay_provider,
        temperature=_optional_float(
            chat.get("temperature"),
            default=context.default_temperature,
        ),
        max_tokens=_optional_int(
            chat.get("max_tokens"),
            default=context.default_max_tokens,
        ),
    )


async def _session_override(runtime, session_name: str) -> dict[str, Any]:
    service = getattr(runtime, "session_runtime_override_service", None)
    if service is None:
        return {}
    return await asyncio.to_thread(service.get_override, session_name)


async def _resolve_llm_profile(runtime, profile_id: str) -> dict[str, Any]:
    if profile_id:
        return await llm_runtime_profile(runtime, profile_id)

    service = getattr(runtime, "llm_model_service", None)
    if service is not None:
        return await asyncio.to_thread(service.active_runtime_profile)

    legacy_service = getattr(runtime, "model_profile_service", None)
    if legacy_service is not None:
        return await asyncio.to_thread(legacy_service.active_profile_for_runtime)
    return {}


def _section(profile: dict[str, Any], section_name: str) -> dict[str, Any]:
    value = profile.get(section_name)
    return value if isinstance(value, dict) else {}


def _optional_float(value: object, *, default: float | None) -> float | None:
    if value is None or value == "":
        return default
    return float(value)


def _optional_int(value: object, *, default: int | None) -> int | None:
    if value is None or value == "":
        return default
    return int(value)
