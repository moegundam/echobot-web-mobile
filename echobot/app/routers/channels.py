from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from ...channels import InboundMessage
from ...channels.types import ChannelAddress
from ...runtime.sessions import normalize_session_name
from ..schemas import channel_config_payload
from ..state import get_app_runtime, require_admin_user


router = APIRouter(tags=["channels"])


class DiscordWebhookMessageRequest(BaseModel):
    channel_id: str = Field(..., max_length=128)
    user_id: str = Field(..., max_length=128)
    text: str = Field(..., max_length=8192)
    thread_id: str | None = Field(default=None, max_length=128)
    username: str = Field(default="", max_length=128)
    session_name: str | None = Field(default=None, max_length=128)


@router.get("/channels/definitions")
async def get_channel_definitions(runtime=Depends(get_app_runtime)) -> list[dict[str, Any]]:
    return runtime.channel_service.get_definitions()


@router.get("/channels/config")
async def get_channel_config(runtime=Depends(get_app_runtime)) -> dict[str, Any]:
    config = await runtime.channel_service.get_config()
    return channel_config_payload(config)


@router.put("/channels/config")
async def update_channel_config(
    raw_config: dict[str, Any],
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> dict[str, Any]:
    try:
        updated = await runtime.channel_service.update_config(raw_config)
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return channel_config_payload(updated)


@router.get("/channels/status")
async def get_channel_status(runtime=Depends(get_app_runtime)) -> dict[str, dict[str, bool]]:
    return await runtime.channel_service.get_status()


@router.get("/channels/stage-targets")
async def get_channel_stage_targets(runtime=Depends(get_app_runtime)) -> dict[str, Any]:
    return await runtime.channel_service.get_stage_targets()


@router.post("/channels/{channel_name}/smoke")
async def smoke_channel(
    channel_name: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> dict[str, Any]:
    try:
        return await runtime.channel_service.smoke_channel(channel_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown channel") from exc


@router.post("/channels/discord/webhook")
async def receive_discord_webhook(
    request: DiscordWebhookMessageRequest,
    runtime=Depends(get_app_runtime),
    x_echobot_discord_secret: str = Header(default=""),
) -> dict[str, Any]:
    if runtime.bus is None or runtime.channel_service is None:
        raise HTTPException(status_code=503, detail="Discord gateway is not ready")
    config = await runtime.channel_service.get_config()
    discord_config = config.get("discord", {}) if isinstance(config, dict) else {}
    if not isinstance(discord_config, dict):
        discord_config = {}
    configured_secret = str(discord_config.get("webhook_secret") or "").strip()
    if not configured_secret:
        raise HTTPException(
            status_code=503,
            detail="Discord webhook secret is not configured",
        )
    supplied_secret = str(x_echobot_discord_secret or "").strip()
    if not supplied_secret or not hmac.compare_digest(supplied_secret, configured_secret):
        raise HTTPException(status_code=401, detail="Discord webhook secret is invalid")
    if not bool(discord_config.get("enabled")):
        raise HTTPException(status_code=403, detail="Discord channel is disabled")
    allow_from = [str(item) for item in discord_config.get("allow_from", []) or []]
    if allow_from and "*" not in allow_from and request.user_id not in allow_from:
        raise HTTPException(status_code=403, detail="Discord sender is not allowed")

    session_name = ""
    if request.session_name:
        try:
            session_name = normalize_session_name(request.session_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    await runtime.bus.publish_inbound(
        InboundMessage(
            address=ChannelAddress(
                channel="discord",
                chat_id=request.channel_id,
                thread_id=request.thread_id,
            ),
            sender_id=request.user_id,
            text=request.text,
            metadata={
                "username": request.username,
                "discord_user_id": request.user_id,
                "webhook": True,
                "session_name": session_name,
            },
        )
    )
    return {
        "accepted": True,
        "channel": "discord",
        "session_name": session_name,
    }
