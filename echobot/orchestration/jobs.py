from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models import (
    MessageContent,
    message_content_to_text,
    normalize_message_content,
)
from ..runtime.sessions import ChatSession


JOB_CANCELLED_TEXT = "后台任务已停止。"
JOB_INTERRUPTED_TEXT = "任务因 EchoBot 重启而中断。"
RETRYABLE_JOB_STATUSES = frozenset({"failed", "cancelled"})
ACTIVE_JOB_STATUSES = frozenset({"running"})


@dataclass(slots=True)
class OrchestratedTurnResult:
    session: ChatSession
    response_text: str
    delegated: bool
    completed: bool
    response_content: MessageContent = ""
    job_id: str | None = None
    status: str = "completed"
    role_name: str = "default"
    steps: int = 1
    compressed_summary: str = ""


@dataclass(slots=True)
class ConversationJob:
    job_id: str
    session_name: str
    prompt: str
    immediate_response: str
    role_name: str
    status: str
    created_at: str
    updated_at: str
    started_at: str
    finished_at: str
    trace_run_id: str | None = None
    route_mode: str = ""
    response_language: str = ""
    attempt: int = 1
    retry_of_job_id: str | None = None
    image_urls: list[dict[str, str]] = field(default_factory=list)
    file_attachments: list[dict[str, object]] = field(default_factory=list)
    final_response: str = ""
    final_response_content: MessageContent = ""
    error: str = ""
    steps: int = 0
    pending_user_input: dict[str, object] | None = None


CompletionCallback = Callable[[ConversationJob], Awaitable[None]]


class ConversationJobStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self._jobs: dict[str, ConversationJob] = self._load_jobs()
        self._lock = asyncio.Lock()

    async def create(
        self,
        *,
        session_name: str,
        prompt: str,
        immediate_response: str,
        role_name: str,
        route_mode: str = "",
        response_language: str = "",
        image_urls: list[dict[str, str]] | None = None,
        file_attachments: list[dict[str, object]] | None = None,
        trace_run_id: str | None = None,
        attempt: int = 1,
        retry_of_job_id: str | None = None,
    ) -> ConversationJob:
        async with self._lock:
            now_text = _now_text()
            job = ConversationJob(
                job_id=uuid.uuid4().hex,
                session_name=session_name,
                prompt=prompt,
                immediate_response=immediate_response,
                role_name=role_name,
                status="running",
                created_at=now_text,
                updated_at=now_text,
                started_at=now_text,
                finished_at="",
                trace_run_id=trace_run_id,
                route_mode=route_mode,
                response_language=str(response_language or "").strip(),
                attempt=max(int(attempt), 1),
                retry_of_job_id=retry_of_job_id,
                image_urls=_copy_string_mapping_list(image_urls or []),
                file_attachments=_copy_object_mapping_list(file_attachments or []),
            )
            self._jobs[job.job_id] = job
            await self._persist_locked()
            return _copy_job(job)

    async def get(self, job_id: str) -> ConversationJob | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return _copy_job(job)

    async def set_completed(
        self,
        job_id: str,
        *,
        final_response: str,
        final_response_content: MessageContent = "",
        steps: int,
    ) -> ConversationJob | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.status = "completed"
            job.updated_at = _now_text()
            job.finished_at = job.updated_at
            job.final_response = final_response
            job.final_response_content = normalize_message_content(final_response_content)
            job.steps = steps
            job.error = ""
            job.pending_user_input = None
            await self._persist_locked()
            return _copy_job(job)

    async def set_failed(
        self,
        job_id: str,
        *,
        final_response: str,
        final_response_content: MessageContent = "",
        error: str,
        steps: int = 0,
    ) -> ConversationJob | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.status = "failed"
            job.updated_at = _now_text()
            job.finished_at = job.updated_at
            job.final_response = final_response
            job.final_response_content = normalize_message_content(final_response_content)
            job.error = error
            job.steps = steps
            job.pending_user_input = None
            await self._persist_locked()
            return _copy_job(job)

    async def set_cancelled(
        self,
        job_id: str,
        *,
        final_response: str,
        final_response_content: MessageContent = "",
        steps: int = 0,
    ) -> ConversationJob | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.status = "cancelled"
            job.updated_at = _now_text()
            job.finished_at = job.updated_at
            job.final_response = final_response
            job.final_response_content = normalize_message_content(final_response_content)
            job.error = ""
            job.steps = steps
            job.pending_user_input = None
            await self._persist_locked()
            return _copy_job(job)

    async def set_waiting_for_input(
        self,
        job_id: str,
        *,
        final_response: str,
        final_response_content: MessageContent = "",
        steps: int = 0,
        pending_user_input: dict[str, object] | None = None,
    ) -> ConversationJob | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.status = "waiting_for_input"
            job.updated_at = _now_text()
            job.finished_at = job.updated_at
            job.final_response = final_response
            job.final_response_content = normalize_message_content(final_response_content)
            job.error = ""
            job.steps = steps
            job.pending_user_input = dict(pending_user_input or {})
            await self._persist_locked()
            return _copy_job(job)

    async def counts(self) -> dict[str, int]:
        async with self._lock:
            result = {
                "running": 0,
                "waiting_for_input": 0,
                "completed": 0,
                "failed": 0,
                "cancelled": 0,
            }
            for job in self._jobs.values():
                result[job.status] = result.get(job.status, 0) + 1
            return result

    async def list_for_session(
        self,
        session_name: str,
        *,
        status: str | None = None,
    ) -> list[ConversationJob]:
        async with self._lock:
            jobs = [
                _copy_job(job)
                for job in self._jobs.values()
                if job.session_name == session_name
                and (status is None or job.status == status)
            ]
        jobs.sort(key=lambda item: item.created_at)
        return jobs

    async def list_jobs(
        self,
        *,
        session_name: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[ConversationJob]:
        normalized_limit = max(int(limit), 1)
        async with self._lock:
            jobs = [
                _copy_job(job)
                for job in self._jobs.values()
                if (session_name is None or job.session_name == session_name)
                and (status is None or job.status == status)
            ]
        jobs.sort(
            key=lambda item: (item.updated_at, item.created_at, item.job_id),
            reverse=True,
        )
        return jobs[:normalized_limit]

    def _load_jobs(self) -> dict[str, ConversationJob]:
        if self._path is None or not self._path.exists():
            return {}

        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("任务记录文件必须是 JSON 对象")

        jobs: dict[str, ConversationJob] = {}
        recovered_running_job = False
        now_text = _now_text()
        for item in payload.get("jobs", []):
            if not isinstance(item, dict):
                continue
            job = _job_from_dict(item)
            if job.status in ACTIVE_JOB_STATUSES:
                recovered_running_job = True
                job.status = "failed"
                job.updated_at = now_text
                job.finished_at = now_text
                if not job.error:
                    job.error = JOB_INTERRUPTED_TEXT
                if not job.final_response.strip():
                    job.final_response = JOB_INTERRUPTED_TEXT
                if not message_content_to_text(job.final_response_content).strip():
                    job.final_response_content = JOB_INTERRUPTED_TEXT
                job.pending_user_input = None
            jobs[job.job_id] = job

        if recovered_running_job:
            self._save_jobs(jobs)
        return jobs

    def _build_persist_payload(self) -> dict[str, object]:
        ordered_jobs = sorted(
            self._jobs.values(),
            key=lambda item: (item.created_at, item.job_id),
        )
        return {
            "jobs": [_job_to_dict(job) for job in ordered_jobs],
        }

    async def _persist_locked(self) -> None:
        if self._path is None:
            return
        payload = self._build_persist_payload()
        await asyncio.to_thread(self._save_payload, payload)

    def _save_payload(self, payload: dict[str, object]) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _save_jobs(self, jobs: dict[str, ConversationJob]) -> None:
        ordered_jobs = sorted(
            jobs.values(),
            key=lambda item: (item.created_at, item.job_id),
        )
        self._save_payload(
            {
                "jobs": [_job_to_dict(job) for job in ordered_jobs],
            }
        )


def _now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _copy_job(job: ConversationJob) -> ConversationJob:
    return ConversationJob(
        job_id=job.job_id,
        session_name=job.session_name,
        prompt=job.prompt,
        immediate_response=job.immediate_response,
        role_name=job.role_name,
        status=job.status,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        trace_run_id=job.trace_run_id,
        route_mode=job.route_mode,
        response_language=job.response_language,
        attempt=job.attempt,
        retry_of_job_id=job.retry_of_job_id,
        image_urls=_copy_string_mapping_list(job.image_urls),
        file_attachments=_copy_object_mapping_list(job.file_attachments),
        final_response=job.final_response,
        final_response_content=normalize_message_content(job.final_response_content),
        error=job.error,
        steps=job.steps,
        pending_user_input=(
            dict(job.pending_user_input)
            if job.pending_user_input is not None
            else None
        ),
    )


def job_can_retry(job: ConversationJob) -> bool:
    return job.status in RETRYABLE_JOB_STATUSES


def _job_to_dict(job: ConversationJob) -> dict[str, object]:
    return {
        "job_id": job.job_id,
        "session_name": job.session_name,
        "prompt": job.prompt,
        "immediate_response": job.immediate_response,
        "role_name": job.role_name,
        "status": job.status,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "trace_run_id": job.trace_run_id,
        "route_mode": job.route_mode,
        "response_language": job.response_language,
        "attempt": job.attempt,
        "retry_of_job_id": job.retry_of_job_id,
        "image_urls": _copy_string_mapping_list(job.image_urls),
        "file_attachments": _copy_object_mapping_list(job.file_attachments),
        "final_response": job.final_response,
        "final_response_content": normalize_message_content(job.final_response_content),
        "error": job.error,
        "steps": job.steps,
        "pending_user_input": (
            dict(job.pending_user_input)
            if job.pending_user_input is not None
            else None
        ),
    }


def _job_from_dict(data: dict[str, Any]) -> ConversationJob:
    created_at = _optional_text(data.get("created_at")) or _now_text()
    updated_at = _optional_text(data.get("updated_at")) or created_at
    return ConversationJob(
        job_id=str(data.get("job_id", "")).strip(),
        session_name=str(data.get("session_name", "")).strip(),
        prompt=str(data.get("prompt", "")),
        immediate_response=str(data.get("immediate_response", "")),
        role_name=str(data.get("role_name", "")).strip() or "default",
        status=str(data.get("status", "")).strip() or "failed",
        created_at=created_at,
        updated_at=updated_at,
        started_at=_optional_text(data.get("started_at")) or created_at,
        finished_at=_optional_text(data.get("finished_at")) or "",
        trace_run_id=_optional_text(data.get("trace_run_id")),
        route_mode=str(data.get("route_mode", "")).strip(),
        response_language=str(data.get("response_language", "")).strip(),
        attempt=max(_optional_int(data.get("attempt")) or 1, 1),
        retry_of_job_id=_optional_text(data.get("retry_of_job_id")),
        image_urls=_copy_string_mapping_list(data.get("image_urls") or []),
        file_attachments=_copy_object_mapping_list(data.get("file_attachments") or []),
        final_response=str(data.get("final_response", "")),
        final_response_content=normalize_message_content(
            data.get("final_response_content", "")
        ),
        error=str(data.get("error", "")),
        steps=_optional_int(data.get("steps")) or 0,
        pending_user_input=(
            dict(data.get("pending_user_input"))
            if isinstance(data.get("pending_user_input"), dict)
            else None
        ),
    )


def _copy_string_mapping_list(values: object) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    if not isinstance(values, list):
        return normalized
    for item in values:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                str(key): str(value)
                for key, value in item.items()
            }
        )
    return normalized


def _copy_object_mapping_list(values: object) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    if not isinstance(values, list):
        return normalized
    for item in values:
        if not isinstance(item, dict):
            continue
        normalized.append(dict(item))
    return normalized


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
