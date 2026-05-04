from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ...scheduling.cron import summarize_job
from ..schemas import (
    CronDeleteResponse,
    CronJobModel,
    CronJobsResponse,
    CronStatusResponse,
)
from ..state import get_app_runtime, require_admin_user


router = APIRouter(tags=["cron"])


@router.get("/cron/status", response_model=CronStatusResponse)
async def get_cron_status(
    runtime=Depends(get_app_runtime),
) -> CronStatusResponse:
    if runtime.context is None:
        raise HTTPException(status_code=503, detail="EchoBot runtime is not ready")

    payload = await runtime.context.cron_service.status()
    return CronStatusResponse(
        enabled=bool(payload.get("enabled", False)),
        jobs=int(payload.get("jobs", 0)),
        next_run_at=_optional_text(payload.get("next_run_at")),
    )


@router.get("/cron/jobs", response_model=CronJobsResponse)
async def list_cron_jobs(
    include_disabled: bool = Query(default=False),
    runtime=Depends(get_app_runtime),
) -> CronJobsResponse:
    if runtime.context is None:
        raise HTTPException(status_code=503, detail="EchoBot runtime is not ready")

    jobs = await runtime.context.cron_service.list_jobs(
        include_disabled=include_disabled,
    )
    return CronJobsResponse(
        jobs=[
            CronJobModel(**summarize_job(job))
            for job in jobs
        ]
    )


@router.delete("/cron/jobs/{job_id}", response_model=CronDeleteResponse)
async def delete_cron_job(
    job_id: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> CronDeleteResponse:
    if runtime.context is None:
        raise HTTPException(status_code=503, detail="EchoBot runtime is not ready")

    removed = await runtime.context.cron_service.remove_job(job_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Cron job not found: {job_id}")
    return CronDeleteResponse(deleted=True, job_id=job_id)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
