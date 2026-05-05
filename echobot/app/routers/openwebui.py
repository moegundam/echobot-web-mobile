from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..schemas import (
    ChatResponse,
    SessionSummaryModel,
    session_summary_model_from_info,
)
from ..services.openwebui_bridge import (
    OpenWebUIBridgeSettings,
    bridge_route_mode,
    bridge_scope_key,
    build_openwebui_tools_openapi,
    normalized_session_name,
    openwebui_bridge_status,
    require_openwebui_bridge,
    resolve_bridge_target_user,
    runtime_for_bridge_target,
)
from ..services.stage_event_enrichment import apply_character_emotion_map
from ..services.stage_events import StageEventModel, StageEventPublishRequest
from ..state import get_app_runtime


router = APIRouter(tags=["openwebui"])


class OpenWebUIStageEventRequest(BaseModel):
    session_name: str
    text: str
    target_user_id: str | None = None
    emotion: str = ""
    expression: str = ""
    motion: str = ""
    speaker: str = "Open WebUI"
    metadata: dict[str, Any] = Field(default_factory=dict)


class OpenWebUIChatRequest(BaseModel):
    session_name: str
    prompt: str
    target_user_id: str | None = None
    route_mode: str | None = None


@router.get("/openwebui/status")
async def get_openwebui_status() -> dict[str, Any]:
    return openwebui_bridge_status()


@router.get("/openwebui/tools/openapi.json")
async def get_openwebui_tools_openapi(
    _settings: OpenWebUIBridgeSettings = Depends(require_openwebui_bridge),
) -> dict[str, Any]:
    return build_openwebui_tools_openapi()


@router.get("/openwebui/sessions", response_model=list[SessionSummaryModel])
async def list_openwebui_sessions(
    target_user_id: str | None = Query(default=None),
    runtime=Depends(get_app_runtime),
    settings: OpenWebUIBridgeSettings = Depends(require_openwebui_bridge),
) -> list[SessionSummaryModel]:
    user_id = resolve_bridge_target_user(target_user_id, settings)
    target_runtime = await runtime_for_bridge_target(runtime, user_id)
    sessions = await target_runtime.session_service.list_sessions()
    return [session_summary_model_from_info(item) for item in sessions]


@router.post("/openwebui/stage/events", response_model=StageEventModel)
async def publish_openwebui_stage_event(
    request: OpenWebUIStageEventRequest,
    runtime=Depends(get_app_runtime),
    settings: OpenWebUIBridgeSettings = Depends(require_openwebui_bridge),
) -> StageEventModel:
    user_id = resolve_bridge_target_user(request.target_user_id, settings)
    target_runtime = await runtime_for_bridge_target(runtime, user_id)
    payload = await apply_character_emotion_map(
        target_runtime,
        StageEventPublishRequest(
            kind="assistant_final",
            session_name=normalized_session_name(request.session_name),
            text=request.text,
            emotion=request.emotion,
            expression=request.expression,
            motion=request.motion,
            speaker=request.speaker,
            source="openwebui",
            metadata={
                **dict(request.metadata or {}),
                "target_user_id": user_id,
            },
        ),
    )
    return await runtime.stage_event_broker.publish(
        scope_key=bridge_scope_key(user_id),
        request=payload,
    )


@router.post("/openwebui/chat", response_model=ChatResponse)
async def run_openwebui_chat(
    request: OpenWebUIChatRequest,
    runtime=Depends(get_app_runtime),
    settings: OpenWebUIBridgeSettings = Depends(require_openwebui_bridge),
) -> ChatResponse:
    user_id = resolve_bridge_target_user(request.target_user_id, settings)
    target_runtime = await runtime_for_bridge_target(runtime, user_id)
    route_mode = bridge_route_mode(request.route_mode, settings)
    result = await target_runtime.chat_service.run_prompt(
        normalized_session_name(request.session_name),
        request.prompt,
        route_mode=route_mode,
    )
    if result.response_text.strip():
        payload = await apply_character_emotion_map(
            target_runtime,
            StageEventPublishRequest(
                kind="assistant_final",
                session_name=result.session.name,
                text=result.response_text,
                speaker="Echo",
                source="openwebui",
                metadata={
                    "target_user_id": user_id,
                    "openwebui_operation": "chat",
                },
            ),
        )
        await runtime.stage_event_broker.publish(
            scope_key=bridge_scope_key(user_id),
            request=payload,
        )
    return ChatResponse(
        session_name=result.session.name,
        response=result.response_text,
        response_content=result.response_content,
        updated_at=result.session.updated_at,
        steps=result.steps,
        compressed_summary=result.compressed_summary,
        delegated=result.delegated,
        completed=result.completed,
        job_id=result.job_id,
        status=result.status,
        role_name=result.role_name,
    )
