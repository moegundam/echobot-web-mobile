from __future__ import annotations

import asyncio
import logging

from ..channels import InboundMessage, MessageBus, OutboundMessage
from ..channels.types import DeliveryTarget
from ..commands.bindings import GatewayCommandContext, dispatch_gateway_command
from ..commands.route_sessions import parse_route_session_command
from ..models import MessageContent, is_message_content_empty, message_content_to_text
from ..runtime.scheduled_tasks import (
    build_cron_job_executor as build_shared_cron_job_executor,
    build_heartbeat_executor as build_shared_heartbeat_executor,
)
from ..runtime.bootstrap import RuntimeContext
from ..runtime.session_service import SessionLifecycleService
from ..turn_inputs import (
    has_file_processing_capability,
    resolve_attachment_files,
    resolve_file_attachment_route_mode,
)
from .delivery import DeliveryStore
from .route_sessions import RouteSessionStore
from .session_service import GatewaySessionService


logger = logging.getLogger(__name__)


class GatewayRuntime:
    def __init__(
        self,
        context: RuntimeContext,
        bus: MessageBus,
        session_service: GatewaySessionService | None = None,
        delivery_store: DeliveryStore | None = None,
        route_session_store: RouteSessionStore | None = None,
        *,
        max_inflight_messages: int = 32,
    ) -> None:
        self._context = context
        self._bus = bus
        if session_service is None:
            delivery_store = delivery_store or DeliveryStore(
                context.workspace / ".echobot" / "delivery.json",
            )
            route_session_store = route_session_store or RouteSessionStore(
                context.workspace / ".echobot" / "route_sessions.json",
            )
            core_session_service = SessionLifecycleService(
                context.session_store,
                context.agent_session_store,
                coordinator=context.coordinator,
            )
            session_service = GatewaySessionService(
                core_session_service,
                route_session_store=route_session_store,
                delivery_store=delivery_store,
            )
        self._session_service = session_service
        self._inflight_tasks: set[asyncio.Task[None]] = set()
        self._inflight_semaphore = asyncio.Semaphore(max(max_inflight_messages, 1))
        self._route_locks: dict[str, asyncio.Lock] = {}
        self._route_locks_guard = asyncio.Lock()

    async def run(self) -> None:
        self._context.cron_service.on_job = self._build_cron_job_executor()
        if self._context.heartbeat_service is not None:
            self._context.heartbeat_service.on_execute = (
                self._build_heartbeat_executor()
            )
            self._context.heartbeat_service.on_notify = self._notify_latest

        await self._context.cron_service.start()
        if self._context.heartbeat_service is not None:
            await self._context.heartbeat_service.start()

        logger.info("Gateway runtime started")
        try:
            while True:
                await self._inflight_semaphore.acquire()
                message = await self._bus.consume_inbound()
                task = asyncio.create_task(self._handle_inbound_message_task(message))
                self._inflight_tasks.add(task)
                task.add_done_callback(self._inflight_tasks.discard)
        finally:
            await self._shutdown()

    async def handle_inbound_message(self, message: InboundMessage) -> None:
        route_lock = await self._route_lock(message.route_key)
        async with route_lock:
            await self._handle_inbound_message(message)

    async def _handle_inbound_message_task(self, message: InboundMessage) -> None:
        try:
            await self.handle_inbound_message(message)
        finally:
            self._inflight_semaphore.release()

    async def _handle_inbound_message(self, message: InboundMessage) -> None:
        route_key = message.route_key
        delete_session_name = await self._route_delete_session_name(message)
        command_result = await dispatch_gateway_command(
            GatewayCommandContext(
                coordinator=self._context.coordinator,
                runtime_controls=self._context.runtime_controls,
                workspace=self._context.workspace,
                session_service=self._session_service,
                route_key=route_key,
                address=message.address,
                metadata=message.metadata,
            ),
            message.text,
        )
        if command_result is not None:
            if delete_session_name:
                await self._discard_async_results_for_session(
                    message,
                    delete_session_name,
                )
            await self._bus.publish_outbound(
                OutboundMessage(
                    address=message.address,
                    text=command_result.text,
                    metadata=dict(message.metadata),
                )
            )
            return

        route_session = await self._session_service.current_route_session(
            route_key,
        )
        await self._session_service.remember_delivery_target(
            route_session.session_name,
            message.address,
            message.metadata,
        )
        immediate_response_sent = asyncio.Event()
        try:
            image_urls = (
                list(message.image_urls)
                if self._context.supports_image_input
                else []
            )
            file_attachments = await _resolve_gateway_files(
                message,
                self._context.attachment_store,
                self._context.workspace,
            )
            execution = await self._context.coordinator.handle_user_turn(
                route_session.session_name,
                message.text,
                image_urls=image_urls,
                file_attachments=file_attachments,
                route_mode=await self._resolve_effective_route_mode(
                    route_session.session_name,
                    has_file_attachments=bool(file_attachments),
                ),
                completion_callback=self._completion_callback_for_session(
                    route_session.session_name,
                    immediate_response_sent=immediate_response_sent,
                ),
            )
            content: MessageContent = execution.response_content
            if execution.delegated and not execution.completed:
                try:
                    if not is_message_content_empty(content):
                        await self._bus.publish_outbound(
                            OutboundMessage(
                                address=message.address,
                                content=content,
                                metadata=dict(message.metadata),
                            )
                        )
                finally:
                    immediate_response_sent.set()
                await self._session_service.touch_route_session(
                    route_key,
                    route_session.session_name,
                    updated_at=execution.session.updated_at,
                )
                return
            immediate_response_sent.set()
            await self._session_service.touch_route_session(
                route_key,
                route_session.session_name,
                updated_at=execution.session.updated_at,
            )
            if is_message_content_empty(content):
                content = "Model returned no text content."
        except ValueError as exc:
            immediate_response_sent.set()
            content = str(exc)
        except RuntimeError as exc:
            immediate_response_sent.set()
            content = f"Request failed: {exc}"
        await self._bus.publish_outbound(
            OutboundMessage(
                address=message.address,
                content=content,
                metadata=dict(message.metadata),
            )
        )

    def _completion_callback_for_session(
        self,
        session_name: str,
        *,
        immediate_response_sent: asyncio.Event | None = None,
    ):
        async def notify(job) -> None:
            if immediate_response_sent is not None:
                await immediate_response_sent.wait()
            await self._publish_session_response(
                session_name,
                job.final_response_content,
                metadata={
                    "async_result": True,
                    "echobot_session_name": session_name,
                    "job_id": job.job_id,
                    "job_status": job.status,
                },
            )

        return notify

    async def _route_delete_session_name(self, message: InboundMessage) -> str:
        command = parse_route_session_command(message.text)
        if command is None or command.action != "delete":
            return ""

        current = await self._session_service.current_route_session(message.route_key)
        return current.session_name

    async def _discard_async_results_for_session(
        self,
        message: InboundMessage,
        session_name: str,
    ) -> None:
        await self._bus.discard_outbound(
            lambda outbound: (
                outbound.address == message.address
                and bool(outbound.metadata.get("async_result"))
                and outbound.metadata.get("echobot_session_name") == session_name
            )
        )

    def _build_cron_job_executor(self):
        return build_shared_cron_job_executor(
            self._context.session_runner,
            self._context.coordinator,
            self._notify_schedule,
        )

    def _build_heartbeat_executor(self):
        return build_shared_heartbeat_executor(self._context.session_runner)

    async def _notify_session(
        self,
        session_name: str,
        content: MessageContent,
        *,
        kind: str,
        title: str,
    ) -> None:
        target = await self._session_service.get_session_target(session_name)
        await self._publish_notification(
            target,
            content,
            kind=kind,
            title=title,
        )

    async def _publish_session_response(
        self,
        session_name: str,
        content: MessageContent,
        *,
        metadata: dict[str, object] | None = None,
    ) -> None:
        target = await self._session_service.get_session_target(session_name)
        if target is None:
            logger.info("[reply] %s", message_content_to_text(content))
            return
        next_metadata = dict(target.metadata)
        if metadata is not None:
            next_metadata.update(metadata)
        await self._bus.publish_outbound(
            OutboundMessage(
                address=target.address,
                content=content,
                metadata=next_metadata,
            )
        )

    async def _notify_latest(self, content: MessageContent) -> None:
        target = await self._session_service.get_latest_target()
        await self._publish_notification(
            target,
            content,
            kind="heartbeat",
            title="Periodic check-in",
        )

    async def _publish_notification(
        self,
        target: DeliveryTarget | None,
        content: MessageContent,
        *,
        kind: str,
        title: str,
    ) -> None:
        if target is None:
            logger.info("[%s] %s", kind, title)
            text_content = message_content_to_text(content)
            for line in text_content.splitlines() or [text_content]:
                logger.info("[%s] %s", kind, line)
            return
        metadata = dict(target.metadata)
        metadata["scheduled"] = True
        metadata["schedule_kind"] = kind
        metadata["schedule_title"] = title
        await self._bus.publish_outbound(
            OutboundMessage(
                address=target.address,
                content=content,
                metadata=metadata,
            )
        )

    async def _notify_schedule(
        self,
        session_name: str,
        kind: str,
        title: str,
        content: MessageContent,
    ) -> None:
        await self._notify_session(
            session_name,
            content,
            kind=kind,
            title=title,
        )

    async def _resolve_effective_route_mode(
        self,
        session_name: str,
        *,
        has_file_attachments: bool,
    ):
        can_process_files = False
        current_route_mode = None
        if has_file_attachments:
            can_process_files = has_file_processing_capability(
                self._context.skill_registry,
                getattr(self._context, "tool_registry_factory", None),
                session_name,
            )
        if can_process_files:
            current_route_mode = await self._context.coordinator.current_route_mode(
                session_name,
            )

        return resolve_file_attachment_route_mode(
            requested_route_mode=None,
            current_route_mode=current_route_mode,
            has_file_attachments=has_file_attachments,
            can_process_files=can_process_files,
        )

    async def _shutdown(self) -> None:
        tasks = list(self._inflight_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self._context.cron_service.stop()
        if self._context.heartbeat_service is not None:
            await self._context.heartbeat_service.stop()
        await self._context.coordinator.close()
        if self._context.memory_support is not None:
            await self._context.memory_support.close()

    async def _route_lock(self, route_key: str) -> asyncio.Lock:
        async with self._route_locks_guard:
            lock = self._route_locks.get(route_key)
            if lock is None:
                lock = asyncio.Lock()
                self._route_locks[route_key] = lock
            return lock


async def _resolve_gateway_files(
    message: InboundMessage,
    attachment_store,
    workspace,
) -> list[dict[str, object]]:
    if not message.files:
        return []

    return await asyncio.to_thread(
        resolve_attachment_files,
        attachment_store,
        workspace,
        message.files,
    )
