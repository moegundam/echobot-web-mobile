from __future__ import annotations

from fastapi import HTTPException, Request, WebSocket

from .auth import (
    TRUSTED_USER_STATE_KEY,
    AccessRole,
    AdminAccessConfig,
    OperatorAccessConfig,
    TrustedUserConfig,
    is_protected_path,
    resolve_access_role,
    resolve_trusted_user_id,
)
from .runtime import AppRuntime


async def get_app_runtime(request: Request):
    runtime = _runtime_from_app_state(request.app.state)
    user_id = getattr(request.state, TRUSTED_USER_STATE_KEY, "")
    if user_id:
        return await runtime.for_user(user_id)
    return runtime


async def require_admin_user(request: Request) -> str:
    if not request_is_admin(request):
        raise HTTPException(status_code=403, detail="Admin access is required")
    return getattr(request.state, TRUSTED_USER_STATE_KEY, "")


async def require_operator_user(request: Request) -> str:
    if not request_can_operate(request):
        raise HTTPException(status_code=403, detail="Operator access is required")
    return getattr(request.state, TRUSTED_USER_STATE_KEY, "")


async def get_request_is_admin(request: Request) -> bool:
    return request_is_admin(request)


async def get_request_access_role(request: Request) -> AccessRole:
    return request_access_role(request)


async def get_request_can_operate(request: Request) -> bool:
    return request_can_operate(request)


def request_is_admin(request: Request) -> bool:
    return request_access_role(request) is AccessRole.ADMIN


def request_can_operate(request: Request) -> bool:
    return request_access_role(request) in {AccessRole.ADMIN, AccessRole.OPERATOR}


def request_access_role(request: Request) -> AccessRole:
    admin_config = getattr(
        request.app.state,
        "admin_access_config",
        AdminAccessConfig(),
    )
    operator_config = getattr(
        request.app.state,
        "operator_access_config",
        OperatorAccessConfig(),
    )
    user_id = getattr(request.state, TRUSTED_USER_STATE_KEY, "")
    trusted_user_config = getattr(
        request.app.state,
        "trusted_user_config",
        TrustedUserConfig(),
    )
    return resolve_access_role(
        user_id,
        trusted_user_config,
        admin_config,
        operator_config,
    )


async def get_app_runtime_for_websocket(websocket: WebSocket):
    runtime = getattr(websocket.app.state, "runtime", None)
    if runtime is None:
        await websocket.close(code=1011, reason="EchoBot runtime is not ready")
        return None
    config = getattr(
        websocket.app.state,
        "trusted_user_config",
        TrustedUserConfig(),
    )
    try:
        user_id = resolve_trusted_user_id(websocket.headers, config)
    except ValueError:
        await websocket.close(code=1008, reason="Trusted user header is invalid")
        return None
    if config.enabled and is_protected_path(websocket.url.path):
        if not user_id and config.required:
            await websocket.close(code=1008, reason="Trusted user header is required")
            return None
    if user_id:
        return await runtime.for_user(user_id)
    return runtime


def _runtime_from_app_state(app_state) -> AppRuntime:
    runtime = getattr(app_state, "runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="EchoBot runtime is not ready")
    return runtime
