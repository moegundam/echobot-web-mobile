from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...orchestration import DEFAULT_ROLE_NAME, RoleCard
from ..schemas import (
    CreateRoleRequest,
    RoleDetailModel,
    RoleSummaryModel,
    UpdateRoleRequest,
)
from ..state import get_app_runtime, require_admin_user


router = APIRouter(tags=["roles"])


@router.get("/roles", response_model=list[RoleSummaryModel])
async def list_roles(runtime=Depends(get_app_runtime)) -> list[RoleSummaryModel]:
    return [
        _summary_model_from_role_card(card)
        for card in await runtime.role_service.list_roles()
    ]


@router.get("/roles/{role_name}", response_model=RoleDetailModel)
async def get_role(
    role_name: str,
    runtime=Depends(get_app_runtime),
) -> RoleDetailModel:
    try:
        card = await runtime.role_service.get_role(role_name)
    except ValueError as exc:
        raise _role_http_exception(exc) from exc
    return _detail_model_from_role_card(card)


@router.post("/roles", response_model=RoleDetailModel)
async def create_role(
    request: CreateRoleRequest,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> RoleDetailModel:
    try:
        card = await runtime.role_service.create_role(
            request.name,
            request.prompt,
        )
    except ValueError as exc:
        raise _role_http_exception(exc) from exc
    return _detail_model_from_role_card(card)


@router.put("/roles/{role_name}", response_model=RoleDetailModel)
async def update_role(
    role_name: str,
    request: UpdateRoleRequest,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> RoleDetailModel:
    try:
        card = await runtime.role_service.update_role(
            role_name,
            request.prompt,
        )
    except ValueError as exc:
        raise _role_http_exception(exc) from exc
    return _detail_model_from_role_card(card)


@router.delete("/roles/{role_name}")
async def delete_role(
    role_name: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> dict[str, object]:
    try:
        deleted_name = await runtime.role_service.delete_role(role_name)
    except ValueError as exc:
        raise _role_http_exception(exc) from exc
    return {
        "deleted": True,
        "name": deleted_name,
    }


def _summary_model_from_role_card(card: RoleCard) -> RoleSummaryModel:
    is_default = card.name == DEFAULT_ROLE_NAME
    return RoleSummaryModel(
        name=card.name,
        editable=not is_default,
        deletable=not is_default,
        source_path=str(card.source_path) if card.source_path is not None else None,
    )


def _detail_model_from_role_card(card: RoleCard) -> RoleDetailModel:
    summary = _summary_model_from_role_card(card)
    return RoleDetailModel(
        name=summary.name,
        editable=summary.editable,
        deletable=summary.deletable,
        source_path=summary.source_path,
        prompt=card.prompt,
    )


def _role_http_exception(exc: ValueError) -> HTTPException:
    message = str(exc)
    if "not found" in message.lower() or "unknown role" in message.lower():
        return HTTPException(status_code=404, detail=message)
    if "already exists" in message.lower():
        return HTTPException(status_code=409, detail=message)
    return HTTPException(status_code=400, detail=message)
