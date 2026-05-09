from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..schemas import (
    CreateSessionRequest,
    RenameSessionRequest,
    SetSessionChannelBindingRequest,
    SessionDetailModel,
    SessionSummaryModel,
    SetSessionRouteModeRequest,
    SetSessionRoleRequest,
    SetCurrentSessionRequest,
    session_detail_model_from_session,
    session_summary_model_from_info,
)
from ..state import get_app_runtime
from ..services.session_application import SessionApplicationService


router = APIRouter(tags=["sessions"])


@router.get("/sessions", response_model=list[SessionSummaryModel])
async def list_sessions(runtime=Depends(get_app_runtime)) -> list[SessionSummaryModel]:
    sessions = await _session_app(runtime).list_sessions()
    return [session_summary_model_from_info(item) for item in sessions]


@router.get("/sessions/current", response_model=SessionDetailModel)
async def get_current_session(runtime=Depends(get_app_runtime)) -> SessionDetailModel:
    session = await _session_app(runtime).current_session()
    return session_detail_model_from_session(session)


@router.put("/sessions/current", response_model=SessionDetailModel)
async def set_current_session(
    request: SetCurrentSessionRequest,
    runtime=Depends(get_app_runtime),
) -> SessionDetailModel:
    try:
        session = await _session_app(runtime).switch_session(request.name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return session_detail_model_from_session(session)


@router.post("/sessions", response_model=SessionDetailModel)
async def create_session(
    request: CreateSessionRequest,
    runtime=Depends(get_app_runtime),
) -> SessionDetailModel:
    try:
        session = await _session_app(runtime).create_session(
            name=request.name,
            role_name=request.role_name,
            route_mode=request.route_mode,
            channel_type=request.channel_type,
            channel_integration_id=request.channel_integration_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return session_detail_model_from_session(session)


@router.get("/sessions/{session_name}", response_model=SessionDetailModel)
async def get_session(
    session_name: str,
    runtime=Depends(get_app_runtime),
) -> SessionDetailModel:
    try:
        session = await _session_app(runtime).load_session(session_name)
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
        session = await _session_app(runtime).rename_session(session_name, request.name)
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
        session = await _session_app(runtime).set_role(session_name, request.role_name)
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
        session = await _session_app(runtime).set_route_mode(
            session_name,
            request.route_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return session_detail_model_from_session(session)


@router.put("/sessions/{session_name}/channel-binding", response_model=SessionDetailModel)
async def set_session_channel_binding(
    session_name: str,
    request: SetSessionChannelBindingRequest,
    runtime=Depends(get_app_runtime),
) -> SessionDetailModel:
    try:
        session = await _session_app(runtime).set_channel_binding(
            session_name,
            channel_type=request.channel_type,
            channel_integration_id=request.channel_integration_id,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return session_detail_model_from_session(session)


@router.delete("/sessions/{session_name}")
async def delete_session(
    session_name: str,
    runtime=Depends(get_app_runtime),
) -> dict[str, bool]:
    deleted = await _session_app(runtime).delete_session(session_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_name}")
    return {"deleted": True}


def _session_app(runtime) -> SessionApplicationService:
    return SessionApplicationService(runtime)
