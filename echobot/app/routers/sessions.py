from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from ..schemas import (
    CreateSessionRequest,
    RenameSessionRequest,
    SessionDetailModel,
    SessionSummaryModel,
    SetSessionRouteModeRequest,
    SetSessionRoleRequest,
    SetCurrentSessionRequest,
    session_detail_model_from_session,
    session_summary_model_from_info,
)
from ..state import get_app_runtime
from ...orchestration import role_name_from_metadata


router = APIRouter(tags=["sessions"])


@router.get("/sessions", response_model=list[SessionSummaryModel])
async def list_sessions(runtime=Depends(get_app_runtime)) -> list[SessionSummaryModel]:
    sessions = await runtime.session_service.list_sessions()
    return [session_summary_model_from_info(item) for item in sessions]


@router.get("/sessions/current", response_model=SessionDetailModel)
async def get_current_session(runtime=Depends(get_app_runtime)) -> SessionDetailModel:
    session = await runtime.session_service.load_current_session()
    return session_detail_model_from_session(session)


@router.put("/sessions/current", response_model=SessionDetailModel)
async def set_current_session(
    request: SetCurrentSessionRequest,
    runtime=Depends(get_app_runtime),
) -> SessionDetailModel:
    try:
        session = await runtime.session_service.switch_session(request.name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return session_detail_model_from_session(session)


@router.post("/sessions", response_model=SessionDetailModel)
async def create_session(
    request: CreateSessionRequest,
    runtime=Depends(get_app_runtime),
) -> SessionDetailModel:
    try:
        session = await runtime.session_service.create_session(request.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return session_detail_model_from_session(session)


@router.get("/sessions/{session_name}", response_model=SessionDetailModel)
async def get_session(
    session_name: str,
    runtime=Depends(get_app_runtime),
) -> SessionDetailModel:
    try:
        session = await runtime.session_service.load_session(session_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return session_detail_model_from_session(session)


@router.patch("/sessions/{session_name}", response_model=SessionDetailModel)
async def rename_session(
    session_name: str,
    request: RenameSessionRequest,
    runtime=Depends(get_app_runtime),
) -> SessionDetailModel:
    try:
        session = await runtime.session_service.rename_session(session_name, request.name)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return session_detail_model_from_session(session)


@router.put("/sessions/{session_name}/role", response_model=SessionDetailModel)
async def set_session_role(
    session_name: str,
    request: SetSessionRoleRequest,
    runtime=Depends(get_app_runtime),
) -> SessionDetailModel:
    try:
        session = await runtime.chat_service.set_role(
            session_name,
            request.role_name,
        )
        await _apply_bound_model_profile_for_role(
            runtime,
            role_name_from_metadata(session.metadata),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return session_detail_model_from_session(session)


@router.put("/sessions/{session_name}/route-mode", response_model=SessionDetailModel)
async def set_session_route_mode(
    session_name: str,
    request: SetSessionRouteModeRequest,
    runtime=Depends(get_app_runtime),
) -> SessionDetailModel:
    try:
        session = await runtime.chat_service.set_route_mode(
            session_name,
            request.route_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return session_detail_model_from_session(session)


@router.delete("/sessions/{session_name}")
async def delete_session(
    session_name: str,
    runtime=Depends(get_app_runtime),
) -> dict[str, bool]:
    deleted = await runtime.session_service.delete_session(session_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_name}")
    return {"deleted": True}


async def _apply_bound_model_profile_for_role(runtime, role_name: str) -> None:
    if runtime.model_profile_service is None:
        return
    profile_id = await asyncio.to_thread(
        runtime.model_profile_service.profile_id_for_role,
        role_name,
    )
    runtime_bindings = {}
    if runtime.character_profile_settings_service is not None:
        runtime_bindings = await asyncio.to_thread(
            runtime.character_profile_settings_service.runtime_bindings_for_role,
            role_name,
        )
    has_split_bindings = any(
        runtime_bindings.get(field_name)
        for field_name in ("llm_model_id", "voice_profile_id", "live2d_model_id")
    )
    if not profile_id and not has_split_bindings:
        return

    if not has_split_bindings:
        payload = await asyncio.to_thread(
            runtime.model_profile_service.activate_profile,
            profile_id,
        )
        active_profile = await asyncio.to_thread(
            runtime.model_profile_service.get_profile_for_runtime,
            payload["active_profile_id"],
        )
        await runtime.apply_model_profile(active_profile)
        return

    state = await asyncio.to_thread(runtime.model_profile_service.list_profiles)
    base_profile_id = profile_id or str(state.get("active_profile_id") or "a")
    llm_profile_id = str(runtime_bindings.get("llm_model_id") or base_profile_id)
    voice_profile_id = str(runtime_bindings.get("voice_profile_id") or base_profile_id)
    live2d_profile_id = str(runtime_bindings.get("live2d_model_id") or base_profile_id)
    await asyncio.to_thread(
        runtime.model_profile_service.activate_profile,
        llm_profile_id,
    )
    base_profile = await asyncio.to_thread(
        runtime.model_profile_service.get_profile_for_runtime,
        base_profile_id,
    )
    llm_profile = await asyncio.to_thread(
        runtime.model_profile_service.get_profile_for_runtime,
        llm_profile_id,
    )
    voice_profile = await asyncio.to_thread(
        runtime.model_profile_service.get_profile_for_runtime,
        voice_profile_id,
    )
    live2d_profile = await asyncio.to_thread(
        runtime.model_profile_service.get_profile_for_runtime,
        live2d_profile_id,
    )
    composed_profile = dict(base_profile)
    composed_profile["profile_id"] = llm_profile_id
    composed_profile["label"] = str(base_profile.get("label") or role_name)
    composed_profile["chat"] = llm_profile.get("chat", {})
    composed_profile["tts"] = voice_profile.get("tts", {})
    composed_profile["asr"] = voice_profile.get("asr", {})
    composed_profile["live2d"] = live2d_profile.get("live2d", {})
    await runtime.apply_model_profile(composed_profile)
