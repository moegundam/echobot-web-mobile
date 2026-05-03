from __future__ import annotations

import asyncio
from json import JSONDecodeError

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from ..auth import user_storage_key
from ..services.stage_events import (
    StageEventModel,
    StageEventPublishRequest,
    stage_event_to_sse,
)
from ..state import get_app_runtime


router = APIRouter(tags=["stage"])


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
