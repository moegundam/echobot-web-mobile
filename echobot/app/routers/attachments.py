from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse

from ..schemas import FileAttachmentResponse, ImageAttachmentResponse
from ..state import get_app_runtime


router = APIRouter(tags=["attachments"])
_UPLOAD_READ_CHUNK_BYTES = 1024 * 1024


@router.post("/attachments/images", response_model=ImageAttachmentResponse)
async def upload_image_attachment(
    file: UploadFile = File(...),
    runtime=Depends(get_app_runtime),
) -> ImageAttachmentResponse:
    try:
        image_bytes = await _read_upload_bytes(
            file,
            max_bytes=runtime.context.attachment_store.image_budget.max_input_bytes,
            label="Chat image",
        )
        attachment = await asyncio.to_thread(
            runtime.context.attachment_store.create_image_attachment,
            image_bytes,
            content_type=file.content_type,
            filename=file.filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()

    return ImageAttachmentResponse(
        attachment_id=attachment.attachment_id,
        url=attachment.attachment_url,
        preview_url=attachment.preview_url,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        width=attachment.width,
        height=attachment.height,
        original_filename=attachment.original_filename,
    )


@router.post("/attachments/files", response_model=FileAttachmentResponse)
async def upload_file_attachment(
    file: UploadFile = File(...),
    runtime=Depends(get_app_runtime),
) -> FileAttachmentResponse:
    try:
        await file.seek(0)
        attachment = await asyncio.to_thread(
            runtime.context.attachment_store.create_file_attachment_from_stream,
            file.file,
            content_type=file.content_type,
            filename=file.filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()

    return FileAttachmentResponse(
        attachment_id=attachment.attachment_id,
        url=attachment.attachment_url,
        download_url=attachment.download_url,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        original_filename=attachment.original_filename,
        workspace_path=_workspace_relative_attachment_path(
            runtime.context.workspace,
            runtime.context.attachment_store.base_dir / attachment.relative_path,
        ),
    )


@router.delete("/attachments/{attachment_id}", status_code=204)
async def delete_attachment(
    attachment_id: str,
    runtime=Depends(get_app_runtime),
) -> Response:
    try:
        await asyncio.to_thread(
            runtime.context.attachment_store.delete_attachment,
            attachment_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


@router.get("/attachments/{attachment_id}/content")
async def get_attachment_content(
    attachment_id: str,
    runtime=Depends(get_app_runtime),
) -> FileResponse:
    try:
        attachment, attachment_path = await asyncio.to_thread(
            _resolve_attachment_download,
            runtime.context.attachment_store,
            attachment_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return FileResponse(
        attachment_path,
        media_type=attachment.content_type,
        filename=attachment.download_filename,
    )


def _resolve_attachment_download(attachment_store, attachment_id: str):
    return attachment_store.resolve_attachment_download(attachment_id)


async def _read_upload_bytes(
    upload: UploadFile,
    *,
    max_bytes: int,
    label: str,
) -> bytes:
    chunks: list[bytes] = []
    total_bytes = 0
    while True:
        chunk = await upload.read(_UPLOAD_READ_CHUNK_BYTES)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise ValueError(
                f"{label} exceeds the upload size limit ({total_bytes} bytes > {max_bytes} bytes)"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _workspace_relative_attachment_path(workspace: Path, attachment_path: Path) -> str:
    return str(attachment_path.resolve().relative_to(workspace.resolve())).replace("\\", "/")
