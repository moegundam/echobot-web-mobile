from __future__ import annotations

import asyncio

from .stage_events import StageEventPublishRequest


async def apply_character_emotion_map(
    runtime,
    request: StageEventPublishRequest,
) -> StageEventPublishRequest:
    emotion = str(request.emotion or "").strip()
    if not emotion or (request.expression and request.motion):
        return request

    settings_service = getattr(runtime, "character_profile_settings_service", None)
    context = getattr(runtime, "context", None)
    coordinator = getattr(context, "coordinator", None)
    if settings_service is None or coordinator is None:
        return request

    try:
        role_name = await coordinator.current_role_name(request.session_name)
        mapped = await asyncio.to_thread(
            settings_service.resolve_emotion,
            role_name,
            emotion,
        )
    except ValueError:
        return request

    expression = request.expression or mapped.get("expression", "")
    motion = request.motion or mapped.get("motion", "")
    if expression == request.expression and motion == request.motion:
        return request
    return request.model_copy(
        update={
            "expression": expression,
            "motion": motion,
        },
    )
