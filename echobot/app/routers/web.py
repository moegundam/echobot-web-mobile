from __future__ import annotations

import asyncio
from dataclasses import asdict

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response

from ..auth import AccessRole
from ..schemas import (
    ASRTranscriptionResponse,
    TTSRequest,
    TTSVoiceModel,
    TTSVoicesResponse,
    UpdateWebASRProviderRequest,
    UpdateWebLive2DAnnotationRequest,
    UpdateWebLive2DHotkeyRequest,
    UpdateWebRuntimeConfigRequest,
    WebASRConfigModel,
    WebAccessContextModel,
    WebLive2DAnnotationResponse,
    WebConfigResponse,
    WebLive2DConfigModel,
    WebLive2DHotkeyResponse,
    WebRuntimeConfigModel,
    WebStageConfigModel,
)
from ..services.web_console import Live2DUploadFile
from ..services.runtime_context_events import notify_all_runtime_contexts_changed
from ..services.web_console.live2d.constants import (
    MAX_LIVE2D_UPLOAD_FILES,
    MAX_LIVE2D_UPLOAD_TOTAL_BYTES,
)
from ..services.web_console.stage import MAX_STAGE_BACKGROUND_BYTES
from ..services.access_projection import project_web_config_payload
from ..services.model_profile_compat import model_profiles_payload
from ..state import (
    get_app_runtime,
    get_app_runtime_for_websocket,
    get_request_access_role,
    require_admin_user,
)
from ...runtime.settings import RuntimeSettingsManager


router = APIRouter(tags=["web"])
MAX_ASR_REQUEST_BYTES = 16 * 1024 * 1024
MAX_ASR_WEBSOCKET_FRAME_BYTES = 1024 * 1024
UPLOAD_READ_CHUNK_BYTES = 64 * 1024


@router.get("/access", response_model=WebAccessContextModel)
async def get_access_context(
    access_role: AccessRole = Depends(get_request_access_role),
) -> WebAccessContextModel:
    return _web_access_context(access_role)


@router.get("/web/config", response_model=WebConfigResponse)
async def get_web_config(
    runtime=Depends(get_app_runtime),
    access_role: AccessRole = Depends(get_request_access_role),
) -> WebConfigResponse:
    if runtime.session_service is None or runtime.context is None:
        raise HTTPException(status_code=503, detail="EchoBot runtime is not ready")

    current_session = await runtime.session_service.load_current_session()
    role_name = await runtime.context.coordinator.current_role_name(
        current_session.name,
    )
    route_mode = await runtime.context.coordinator.current_route_mode(
        current_session.name,
    )
    runtime_snapshot = await asyncio.to_thread(
        _runtime_settings_manager(runtime).snapshot,
    )
    payload = await runtime.web_console_service.build_frontend_config(
        session_name=current_session.name,
        role_name=role_name,
        route_mode=route_mode,
        runtime_config=runtime_snapshot,
    )
    payload["model_profile_scope"] = _model_profile_scope(runtime)
    payload["access"] = _web_access_context(access_role).model_dump()
    if runtime.model_profile_service is not None:
        payload["model_profiles"] = await model_profiles_payload(runtime)
    return WebConfigResponse(**project_web_config_payload(payload, access_role))


def _web_access_context(access_role: AccessRole) -> WebAccessContextModel:
    return WebAccessContextModel(
        role=access_role.value,
        can_access_console=access_role in {AccessRole.ADMIN, AccessRole.OPERATOR},
        can_manage_admin=access_role is AccessRole.ADMIN,
        can_use_agent=access_role is AccessRole.ADMIN,
    )


@router.patch("/web/runtime", response_model=WebRuntimeConfigModel)
async def update_web_runtime_config(
    request: UpdateWebRuntimeConfigRequest,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> WebRuntimeConfigModel:
    if runtime.context is None:
        raise HTTPException(status_code=503, detail="EchoBot runtime is not ready")

    updates = {
        "delegated_ack_enabled": request.delegated_ack_enabled,
        "shell_safety_mode": request.shell_safety_mode,
        "file_write_enabled": request.file_write_enabled,
        "cron_mutation_enabled": request.cron_mutation_enabled,
        "web_private_network_enabled": request.web_private_network_enabled,
    }

    try:
        snapshot = await asyncio.to_thread(
            _runtime_settings_manager(runtime).apply_updates,
            updates,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return WebRuntimeConfigModel(**snapshot)


@router.post("/web/runtime/reset", response_model=WebRuntimeConfigModel)
async def reset_web_runtime_config(
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> WebRuntimeConfigModel:
    if runtime.context is None:
        raise HTTPException(status_code=503, detail="EchoBot runtime is not ready")

    snapshot = await asyncio.to_thread(
        _runtime_settings_manager(runtime).reset_overrides,
        runtime.context.default_runtime_config.to_dict(),
    )
    return WebRuntimeConfigModel(**snapshot)


@router.get("/web/live2d/{asset_path:path}")
async def get_live2d_asset(
    asset_path: str,
    runtime=Depends(get_app_runtime),
) -> Response:
    try:
        asset_file = runtime.web_console_service.resolve_live2d_asset(asset_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Live2D asset not found: {asset_path}") from exc

    if asset_file.name.endswith(".model3.json"):
        model_json = await runtime.web_console_service.render_live2d_model_json(asset_path)
        return Response(content=model_json, media_type="application/json")

    return FileResponse(asset_file)


@router.get("/web/stage/backgrounds/{asset_path:path}")
async def get_stage_background_asset(
    asset_path: str,
    runtime=Depends(get_app_runtime),
) -> FileResponse:
    try:
        asset_file = runtime.web_console_service.resolve_stage_background_asset(asset_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Stage background not found: {asset_path}") from exc
    return FileResponse(asset_file)


@router.post("/web/stage/backgrounds", response_model=WebStageConfigModel)
async def upload_stage_background(
    image: UploadFile = File(...),
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> WebStageConfigModel:
    try:
        file_bytes = await _read_upload_file_limited(
            image,
            max_bytes=MAX_STAGE_BACKGROUND_BYTES,
            label="Background file",
        )
        payload = await runtime.web_console_service.save_stage_background(
            filename=image.filename or "",
            content_type=image.content_type,
            file_bytes=file_bytes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return WebStageConfigModel(**payload)


@router.post("/web/live2d", response_model=WebLive2DConfigModel)
async def upload_live2d_directory(
    files: list[UploadFile] = File(...),
    relative_paths: list[str] = Form(...),
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> WebLive2DConfigModel:
    try:
        if len(files) != len(relative_paths):
            raise ValueError("Uploaded Live2D files and paths do not match")
        if len(files) > MAX_LIVE2D_UPLOAD_FILES:
            raise HTTPException(
                status_code=413,
                detail="Too many files in Live2D folder",
            )

        uploaded_files: list[Live2DUploadFile] = []
        total_bytes = 0
        for upload, relative_path in zip(files, relative_paths, strict=True):
            file_bytes = await _read_upload_file_limited(
                upload,
                max_bytes=MAX_LIVE2D_UPLOAD_TOTAL_BYTES - total_bytes,
                label="Live2D folder",
            )
            total_bytes += len(file_bytes)
            uploaded_files.append(
                Live2DUploadFile(
                    relative_path=relative_path,
                    file_bytes=file_bytes,
                )
            )

        payload = await runtime.web_console_service.save_live2d_directory(
            uploaded_files=uploaded_files,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await notify_all_runtime_contexts_changed(
        runtime,
        reason="live2d_asset_catalog_updated",
    )
    return WebLive2DConfigModel(**payload)


@router.patch("/web/live2d/annotations", response_model=WebLive2DAnnotationResponse)
async def update_live2d_annotation(
    request: UpdateWebLive2DAnnotationRequest,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> WebLive2DAnnotationResponse:
    try:
        payload = await runtime.web_console_service.save_live2d_annotation(
            selection_key=request.selection_key,
            kind=request.kind,
            file=request.file,
            note=request.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await notify_all_runtime_contexts_changed(
        runtime,
        reason="live2d_asset_catalog_updated",
    )
    return WebLive2DAnnotationResponse(**payload)


@router.patch("/web/live2d/hotkeys", response_model=WebLive2DHotkeyResponse)
async def update_live2d_hotkey(
    request: UpdateWebLive2DHotkeyRequest,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> WebLive2DHotkeyResponse:
    try:
        payload = await runtime.web_console_service.save_live2d_hotkey(
            selection_key=request.selection_key,
            hotkey_key=request.hotkey_key,
            shortcut_tokens=request.shortcut_tokens,
            restore_default=request.restore_default,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await notify_all_runtime_contexts_changed(
        runtime,
        reason="live2d_asset_catalog_updated",
    )
    return WebLive2DHotkeyResponse(**payload)


@router.get("/web/tts/voices", response_model=TTSVoicesResponse)
async def get_tts_voices(
    provider: str | None = Query(default=None),
    runtime=Depends(get_app_runtime),
) -> TTSVoicesResponse:
    try:
        voices = await runtime.web_console_service.tts_service.list_voices(provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    provider_name = provider or runtime.web_console_service.tts_service.default_provider
    return TTSVoicesResponse(
        provider=provider_name,
        voices=[
            TTSVoiceModel(
                name=voice.name,
                short_name=voice.short_name,
                locale=voice.locale,
                gender=voice.gender,
                display_name=voice.display_name,
            )
            for voice in voices
        ],
    )


@router.post("/web/tts")
async def synthesize_tts(
    request: TTSRequest,
    runtime=Depends(get_app_runtime),
) -> Response:
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="TTS text must not be empty")

    try:
        speech = await runtime.web_console_service.tts_service.synthesize(
            text=text,
            provider_name=request.provider,
            voice=request.voice,
            rate=request.rate,
            volume=request.volume,
            pitch=request.pitch,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return Response(
        content=speech.audio_bytes,
        media_type=speech.content_type,
        headers={
            "X-TTS-Provider": speech.provider,
            "X-TTS-Voice": speech.voice,
        },
    )


@router.get("/web/asr/status", response_model=WebASRConfigModel)
async def get_asr_status(runtime=Depends(get_app_runtime)) -> WebASRConfigModel:
    snapshot = await runtime.web_console_service.asr_service.status_snapshot()
    return WebASRConfigModel(**asdict(snapshot))


@router.patch("/web/asr/provider", response_model=WebASRConfigModel)
async def update_asr_provider(
    request: UpdateWebASRProviderRequest,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> WebASRConfigModel:
    try:
        payload = await runtime.web_console_service.set_selected_asr_provider(
            request.provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return WebASRConfigModel(**payload)


@router.post("/web/asr", response_model=ASRTranscriptionResponse)
async def transcribe_audio(
    request: Request,
    runtime=Depends(get_app_runtime),
) -> ASRTranscriptionResponse:
    audio_bytes = await _read_request_body_limited(
        request,
        max_bytes=MAX_ASR_REQUEST_BYTES,
        label="ASR audio body",
    )
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="ASR audio body must not be empty")

    try:
        result = await runtime.web_console_service.asr_service.transcribe_wav_bytes(audio_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return ASRTranscriptionResponse(text=result.text, language=result.language)


@router.websocket("/web/asr/ws")
async def asr_websocket(websocket: WebSocket) -> None:
    runtime = await get_app_runtime_for_websocket(websocket)
    if runtime is None:
        return
    if runtime is None or runtime.web_console_service is None:
        await websocket.close(code=1011, reason="EchoBot runtime is not ready")
        return

    await websocket.accept()

    try:
        session = await runtime.web_console_service.asr_service.create_realtime_session()
    except RuntimeError as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close(code=1013, reason="ASR is not ready")
        return

    snapshot = await runtime.web_console_service.asr_service.status_snapshot()
    await websocket.send_json(
        {
            "type": "ready",
            "sample_rate": snapshot.sample_rate,
            "state": snapshot.state,
            "detail": snapshot.detail,
        }
    )

    try:
        while True:
            message = await websocket.receive()

            event_type = message.get("type")
            if event_type == "websocket.disconnect":
                break

            payload_bytes = message.get("bytes")
            if payload_bytes is not None:
                if len(payload_bytes) > MAX_ASR_WEBSOCKET_FRAME_BYTES:
                    await websocket.close(
                        code=1009,
                        reason="ASR audio frame is too large",
                    )
                    return
                events = await session.accept_audio_bytes(payload_bytes)
                for event in events:
                    await websocket.send_json(event)
                continue

            payload_text = message.get("text")
            if payload_text == "flush":
                events = await session.flush()
                for event in events:
                    await websocket.send_json(event)
                await websocket.send_json({"type": "flush_complete"})
                continue
            if payload_text == "reset":
                await session.reset()
                await websocket.send_json({"type": "reset"})
                continue
    except WebSocketDisconnect:
        pass
    finally:
        try:
            events = await session.flush()
        except Exception:
            return
        for event in events:
            try:
                await websocket.send_json(event)
            except RuntimeError:
                break


def _runtime_settings_manager(runtime) -> RuntimeSettingsManager:
    return RuntimeSettingsManager(
        runtime.context.workspace,
        coordinator=runtime.context.coordinator,
        runtime_controls=runtime.context.runtime_controls,
        storage_root=runtime.context.storage_root,
    )


def _model_profile_scope(runtime) -> str:
    storage_root = getattr(runtime, "storage_root", None)
    if storage_root is not None:
        return storage_root.name or "default"
    if runtime.context is not None:
        root = runtime.context.storage_root or runtime.context.workspace / ".echobot"
        return root.name or "default"
    return "default"


async def _read_upload_file_limited(
    upload: UploadFile,
    *,
    max_bytes: int,
    label: str,
) -> bytes:
    if max_bytes < 1:
        raise HTTPException(status_code=413, detail=f"{label} is too large")

    payload = bytearray()
    while True:
        chunk = await upload.read(min(UPLOAD_READ_CHUNK_BYTES, max_bytes + 1))
        if not chunk:
            break
        if len(payload) + len(chunk) > max_bytes:
            raise HTTPException(status_code=413, detail=f"{label} is too large")
        payload.extend(chunk)
    return bytes(payload)


async def _read_request_body_limited(
    request: Request,
    *,
    max_bytes: int,
    label: str,
) -> bytes:
    content_length = request.headers.get("content-length", "").strip()
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise HTTPException(status_code=413, detail=f"{label} is too large")
        except ValueError:
            raise HTTPException(status_code=400, detail="Content-Length is invalid") from None

    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > max_bytes:
            raise HTTPException(status_code=413, detail=f"{label} is too large")
        payload.extend(chunk)
    return bytes(payload)
