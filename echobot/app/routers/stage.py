from __future__ import annotations

import asyncio
from json import JSONDecodeError

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from ..auth import user_storage_key
from ..schemas import StageContextResponse
from ..services.stage_events import (
    StageEventModel,
    StageEventPublishRequest,
    stage_event_to_sse,
)
from ..services.stage_event_enrichment import apply_character_emotion_map
from ..state import get_app_runtime


router = APIRouter(tags=["stage"])


@router.get("/stage/context", response_model=StageContextResponse)
async def get_stage_context(
    session_name: str = "default",
    runtime=Depends(get_app_runtime),
) -> StageContextResponse:
    if runtime.context is None:
        raise HTTPException(status_code=503, detail="EchoBot runtime is not ready")

    normalized_session_name = str(session_name or "").strip() or "default"
    role_name = await runtime.context.coordinator.current_role_name(
        normalized_session_name,
    )
    model_profile_id = ""
    model_profile_label = ""
    model_profile_source = ""

    if runtime.model_profile_service is not None:
        payload = await asyncio.to_thread(runtime.model_profile_service.list_profiles)
        role_bindings = dict(payload.get("role_bindings", {}))
        active_profile_id = str(payload.get("active_profile_id") or "")
        model_profile_id = str(role_bindings.get(role_name) or active_profile_id)
        model_profile_source = "role_binding" if role_bindings.get(role_name) else "active"
        model_profile_label = _model_profile_label(
            payload.get("profiles", []),
            model_profile_id,
        )

    return StageContextResponse(
        session_name=normalized_session_name,
        role_name=role_name,
        model_profile_id=model_profile_id,
        model_profile_label=model_profile_label,
        model_profile_source=model_profile_source,
    )


@router.post("/stage/events", response_model=StageEventModel)
async def publish_stage_event(
    request: Request,
    runtime=Depends(get_app_runtime),
) -> StageEventModel:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type != "application/json":
        raise HTTPException(status_code=415, detail="Content-Type must be application/json")

    try:
        request_payload = await request.json()
        payload = StageEventPublishRequest.model_validate(request_payload)
        payload = await apply_character_emotion_map(runtime, payload)
        return await runtime.stage_event_broker.publish(
            scope_key=_stage_event_scope_key(runtime),
            request=payload,
        )
    except JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON") from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/stage/events")
async def subscribe_stage_events(
    session_name: str,
    runtime=Depends(get_app_runtime),
) -> StreamingResponse:
    try:
        subscription = await runtime.stage_event_broker.subscribe(
            scope_key=_stage_event_scope_key(runtime),
            session_name=session_name,
            replay_history=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def body():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        subscription.next_event(),
                        timeout=runtime.stage_event_broker.heartbeat_interval,
                    )
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                yield stage_event_to_sse(event)
        finally:
            await subscription.close()

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _stage_event_scope_key(runtime) -> str:
    user_id = getattr(runtime, "user_id", "")
    if user_id:
        return user_storage_key(user_id)
    return "default"


def _model_profile_label(profiles: object, profile_id: str) -> str:
    if not isinstance(profiles, list) or not profile_id:
        return ""
    for item in profiles:
        if not isinstance(item, dict):
            continue
        if str(item.get("profile_id") or "") == profile_id:
            return str(item.get("label") or profile_id)
    return profile_id
