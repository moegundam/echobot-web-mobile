from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from ...models import FileInput, ImageInput
from ...orchestration import (
    ConversationCoordinator,
    ConversationJob,
    OrchestratedTurnResult,
    RouteMode,
)


StreamCallback = Callable[[str], Awaitable[None]]


class CurrentSessionService(Protocol):
    async def set_current_session(self, name: str) -> None:
        ...


class ChatService:
    def __init__(
        self,
        coordinator: ConversationCoordinator,
        session_service: CurrentSessionService,
    ) -> None:
        self._coordinator = coordinator
        self._session_service = session_service

    async def run_prompt(
        self,
        session_name: str,
        prompt: str,
        *,
        image_urls: list[ImageInput] | None = None,
        file_attachments: list[FileInput] | None = None,
        role_name: str | None = None,
        route_mode: RouteMode | None = None,
        response_language: str | None = None,
    ) -> OrchestratedTurnResult:
        result = await self._coordinator.handle_user_turn(
            session_name,
            prompt,
            image_urls=image_urls,
            file_attachments=file_attachments,
            role_name=role_name,
            route_mode=route_mode,
            response_language=response_language,
        )
        await self._session_service.set_current_session(result.session.name)
        return result

    async def run_prompt_stream(
        self,
        session_name: str,
        prompt: str,
        *,
        image_urls: list[ImageInput] | None = None,
        file_attachments: list[FileInput] | None = None,
        role_name: str | None = None,
        route_mode: RouteMode | None = None,
        on_chunk: StreamCallback | None = None,
        response_language: str | None = None,
    ) -> OrchestratedTurnResult:
        result = await self._coordinator.handle_user_turn_stream(
            session_name,
            prompt,
            image_urls=image_urls,
            file_attachments=file_attachments,
            role_name=role_name,
            route_mode=route_mode,
            on_chunk=on_chunk,
            response_language=response_language,
        )
        await self._session_service.set_current_session(result.session.name)
        return result

    async def set_role(
        self,
        session_name: str,
        role_name: str,
    ):
        session = await self._coordinator.set_session_role(session_name, role_name)
        await self._session_service.set_current_session(session.name)
        return session

    async def current_role_name(self, session_name: str) -> str:
        return await self._coordinator.current_role_name(session_name)

    async def set_route_mode(
        self,
        session_name: str,
        route_mode: RouteMode,
    ):
        session = await self._coordinator.set_session_route_mode(
            session_name,
            route_mode,
        )
        await self._session_service.set_current_session(session.name)
        return session

    async def current_route_mode(self, session_name: str) -> RouteMode:
        return await self._coordinator.current_route_mode(session_name)

    def available_roles(self) -> list[str]:
        return self._coordinator.available_roles()

    async def get_job(self, job_id: str) -> ConversationJob | None:
        return await self._coordinator.get_job(job_id)

    async def list_jobs(
        self,
        *,
        session_name: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[ConversationJob]:
        return await self._coordinator.list_jobs(
            session_name=session_name,
            status=status,
            limit=limit,
        )

    async def get_job_trace(
        self,
        job_id: str,
    ) -> tuple[ConversationJob | None, list[dict[str, Any]]]:
        return await self._coordinator.get_job_trace(job_id)

    async def cancel_job(self, job_id: str) -> ConversationJob | None:
        return await self._coordinator.cancel_job(job_id)

    async def retry_job(self, job_id: str) -> OrchestratedTurnResult:
        result = await self._coordinator.retry_job(job_id)
        await self._session_service.set_current_session(result.session.name)
        return result
