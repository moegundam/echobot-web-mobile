from __future__ import annotations

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
from ..services.runtime_profile_composer import apply_runtime_profile_for_role
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
    await apply_runtime_profile_for_role(
        runtime,
        role_name,
    )
