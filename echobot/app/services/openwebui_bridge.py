from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request

from ...orchestration import RouteMode, normalize_route_mode
from ...runtime.sessions import normalize_session_name
from ..auth import is_valid_trusted_user_id, user_storage_key


BRIDGE_TOKEN_ENV = "ECHOBOT_OPENWEBUI_BRIDGE_TOKEN"
BRIDGE_DEFAULT_USER_ENV = "ECHOBOT_OPENWEBUI_BRIDGE_USER_ID"
BRIDGE_AGENT_ENABLED_ENV = "ECHOBOT_OPENWEBUI_OPERATOR_AGENT_ENABLED"
BRIDGE_ALLOWED_TARGET_USERS_ENV = "ECHOBOT_OPENWEBUI_ALLOWED_TARGET_USERS"
BRIDGE_REQUIRE_TARGET_USER_ENV = "ECHOBOT_OPENWEBUI_REQUIRE_TARGET_USER"


@dataclass(slots=True, frozen=True)
class OpenWebUIBridgeSettings:
    token: str = ""
    default_user_id: str = ""
    operator_agent_enabled: bool = False
    allowed_target_users: frozenset[str] = frozenset()
    require_target_user: bool = True

    @classmethod
    def from_env(cls) -> "OpenWebUIBridgeSettings":
        return cls(
            token=os.environ.get(BRIDGE_TOKEN_ENV, "").strip(),
            default_user_id=os.environ.get(BRIDGE_DEFAULT_USER_ENV, "").strip(),
            operator_agent_enabled=_env_bool(BRIDGE_AGENT_ENABLED_ENV, False),
            allowed_target_users=frozenset(
                _normalize_user_id(item)
                for item in _csv_env(BRIDGE_ALLOWED_TARGET_USERS_ENV)
                if _normalize_user_id(item)
            ),
            require_target_user=_env_bool(BRIDGE_REQUIRE_TARGET_USER_ENV, True),
        )

    @property
    def token_configured(self) -> bool:
        return bool(self.token)


async def require_openwebui_bridge(request: Request) -> OpenWebUIBridgeSettings:
    settings = OpenWebUIBridgeSettings.from_env()
    if not settings.token_configured:
        raise HTTPException(
            status_code=503,
            detail="Open WebUI bridge token is not configured",
        )

    supplied_token = _bearer_token(request.headers.get("authorization", ""))
    if not supplied_token or not hmac.compare_digest(supplied_token, settings.token):
        raise HTTPException(status_code=401, detail="Open WebUI bridge token is invalid")
    return settings


def openwebui_bridge_status() -> dict[str, Any]:
    settings = OpenWebUIBridgeSettings.from_env()
    return {
        "token_configured": settings.token_configured,
        "default_user_configured": bool(settings.default_user_id),
        "operator_agent_enabled": settings.operator_agent_enabled,
        "allowed_target_users_configured": bool(settings.allowed_target_users),
        "require_target_user": settings.require_target_user,
        "tool_spec_url": "/api/openwebui/tools/openapi.json",
        "stage_event_url": "/api/openwebui/stage/events",
        "chat_url": "/api/openwebui/chat",
        "sessions_url": "/api/openwebui/sessions",
        "model_provider_recommendation": "Connect Open WebUI directly to a private LiteLLM, Ollama, or another OpenAI-compatible model provider. Use EchoBot only as the operator bridge.",
    }


def resolve_bridge_target_user(
    target_user_id: str | None,
    settings: OpenWebUIBridgeSettings,
) -> str:
    user_id = str(target_user_id or "").strip() or settings.default_user_id
    if not user_id:
        if settings.require_target_user:
            raise HTTPException(status_code=400, detail="target_user_id is required")
        return ""
    if not is_valid_trusted_user_id(user_id):
        raise HTTPException(status_code=400, detail="target_user_id is invalid")
    allowed_users = settings.allowed_target_users
    if allowed_users and _normalize_user_id(user_id) not in allowed_users:
        raise HTTPException(status_code=403, detail="target_user_id is not allowed")
    return user_id


async def runtime_for_bridge_target(runtime, user_id: str):
    if user_id:
        return await runtime.for_user(user_id)
    return runtime


def bridge_scope_key(user_id: str) -> str:
    if user_id:
        return user_storage_key(user_id)
    return "default"


def bridge_route_mode(
    route_mode: str | None,
    settings: OpenWebUIBridgeSettings,
) -> RouteMode:
    if not route_mode:
        return "chat_only"

    normalized_route_mode = normalize_route_mode(route_mode)
    if normalized_route_mode != "chat_only" and not settings.operator_agent_enabled:
        raise HTTPException(
            status_code=403,
            detail="Open WebUI operator-agent mode is disabled",
        )
    return normalized_route_mode


def build_openwebui_tools_openapi() -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "EchoBot Open WebUI Bridge",
            "version": "1.0.0",
            "description": "Narrow OpenAPI tool surface for Open WebUI operator workflows.",
        },
        "servers": [{"url": "/"}],
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "EchoBot Open WebUI bridge token",
                }
            }
        },
        "security": [{"BearerAuth": []}],
        "paths": {
            "/api/openwebui/stage/events": {
                "post": {
                    "operationId": "send_to_echobot_stage",
                    "summary": "Send text to the EchoBot Stage subtitle/TTS channel.",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": [
                                        "session_name",
                                        "text",
                                        "target_user_id",
                                    ],
                                    "properties": {
                                        "session_name": {"type": "string"},
                                        "text": {"type": "string"},
                                        "target_user_id": {"type": "string"},
                                        "speaker": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Stage event published"}},
                }
            },
            "/api/openwebui/chat": {
                "post": {
                    "operationId": "send_echobot_chat",
                    "summary": "Send an operator message to an EchoBot session.",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": [
                                        "session_name",
                                        "prompt",
                                        "target_user_id",
                                    ],
                                    "properties": {
                                        "session_name": {"type": "string"},
                                        "prompt": {"type": "string"},
                                        "target_user_id": {"type": "string"},
                                        "route_mode": {
                                            "type": "string",
                                            "enum": ["chat_only", "auto", "force_agent"],
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "EchoBot chat response"}},
                }
            },
            "/api/openwebui/sessions": {
                "get": {
                    "operationId": "list_echobot_sessions",
                    "summary": "List EchoBot sessions visible to the bridge target.",
                    "parameters": [
                        {
                            "name": "target_user_id",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Session list"}},
                }
            },
        },
    }


def normalized_session_name(value: str) -> str:
    try:
        return normalize_session_name(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _bearer_token(authorization: str) -> str:
    prefix = "bearer "
    cleaned = str(authorization or "").strip()
    if not cleaned.lower().startswith(prefix):
        return ""
    return cleaned[len(prefix) :].strip()


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    cleaned = raw_value.strip().lower()
    if not cleaned:
        return default
    return cleaned not in {"0", "false", "no", "off"}


def _csv_env(name: str) -> list[str]:
    return [
        item.strip()
        for item in os.environ.get(name, "").split(",")
        if item.strip()
    ]


def _normalize_user_id(user_id: str) -> str:
    return str(user_id or "").strip().lower()
