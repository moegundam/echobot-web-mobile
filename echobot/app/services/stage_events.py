from __future__ import annotations

import asyncio
import json
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ...runtime.sessions import normalize_session_name


MAX_STAGE_EVENT_TEXT_LENGTH = 8192
MAX_STAGE_EVENT_METADATA_BYTES = 4096
DEFAULT_STAGE_EVENT_HISTORY_LIMIT = 100
DEFAULT_STAGE_EVENT_QUEUE_LIMIT = 100
DEFAULT_STAGE_EVENT_HEARTBEAT_SECONDS = 15.0
VALID_STAGE_EVENT_KINDS = {
    "assistant_delta",
    "assistant_final",
    "state",
    "subtitle",
}


class StageEventPublishRequest(BaseModel):
    kind: str
    session_name: str
    text: str = ""
    speaker: str = "Echo"
    source: str = "console"
    metadata: dict[str, Any] = Field(default_factory=dict)


class StageEventModel(BaseModel):
    event_id: str
    kind: str
    session_name: str
    text: str = ""
    speaker: str = "Echo"
    source: str = "console"
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(slots=True)
class _StageEventChannel:
    history: deque[StageEventModel]
    subscribers: set["StageEventSubscription"] = field(default_factory=set)


class StageEventSubscription:
    def __init__(
        self,
        broker: "StageEventBroker",
        channel_key: tuple[str, str],
        *,
        queue_limit: int,
    ) -> None:
        self._broker = broker
        self._channel_key = channel_key
        self._queue: asyncio.Queue[StageEventModel] = asyncio.Queue(
            maxsize=max(queue_limit, 1),
        )
        self._closed = False

    async def next_event(self) -> StageEventModel:
        return await self._queue.get()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._broker.unsubscribe(self)

    @property
    def channel_key(self) -> tuple[str, str]:
        return self._channel_key

    def offer(self, event: StageEventModel) -> None:
        if self._closed:
            return
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        self._queue.put_nowait(event)


class StageEventBroker:
    def __init__(
        self,
        *,
        history_limit: int = DEFAULT_STAGE_EVENT_HISTORY_LIMIT,
        queue_limit: int = DEFAULT_STAGE_EVENT_QUEUE_LIMIT,
        heartbeat_interval: float = DEFAULT_STAGE_EVENT_HEARTBEAT_SECONDS,
    ) -> None:
        self.history_limit = max(history_limit, 1)
        self.queue_limit = max(queue_limit, 1)
        self.heartbeat_interval = max(float(heartbeat_interval), 0.1)
        self._channels: dict[tuple[str, str], _StageEventChannel] = {}
        self._event_counter = 0
        self._lock = threading.RLock()

    async def publish(
        self,
        *,
        scope_key: str,
        request: StageEventPublishRequest,
    ) -> StageEventModel:
        event = self._build_event(request)
        channel_key = self._channel_key(scope_key, event.session_name)
        with self._lock:
            channel = self._get_or_create_channel(channel_key)
            channel.history.append(event)
            subscribers = list(channel.subscribers)

        for subscriber in subscribers:
            subscriber.offer(event)
        return event

    async def subscribe(
        self,
        *,
        scope_key: str,
        session_name: str,
        replay_history: bool = True,
    ) -> StageEventSubscription:
        normalized_session = normalize_session_name(session_name)
        channel_key = self._channel_key(scope_key, normalized_session)
        subscription = StageEventSubscription(
            self,
            channel_key,
            queue_limit=self.queue_limit,
        )
        with self._lock:
            channel = self._get_or_create_channel(channel_key)
            channel.subscribers.add(subscription)
            history = list(channel.history) if replay_history else []

        for event in history:
            subscription.offer(event)
        return subscription

    def unsubscribe(self, subscription: StageEventSubscription) -> None:
        with self._lock:
            channel = self._channels.get(subscription.channel_key)
            if channel is None:
                return
            channel.subscribers.discard(subscription)

    def history(self, scope_key: str, session_name: str) -> list[StageEventModel]:
        normalized_session = normalize_session_name(session_name)
        channel_key = self._channel_key(scope_key, normalized_session)
        with self._lock:
            channel = self._channels.get(channel_key)
            if channel is None:
                return []
            return list(channel.history)

    def _build_event(self, request: StageEventPublishRequest) -> StageEventModel:
        kind = request.kind.strip()
        if kind not in VALID_STAGE_EVENT_KINDS:
            raise ValueError("Stage event kind is invalid")

        normalized_session = normalize_session_name(request.session_name)
        text = str(request.text or "")
        if len(text) > MAX_STAGE_EVENT_TEXT_LENGTH:
            raise ValueError("Stage event text is too large")

        metadata = dict(request.metadata or {})
        metadata_bytes = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
        if len(metadata_bytes) > MAX_STAGE_EVENT_METADATA_BYTES:
            raise ValueError("Stage event metadata is too large")

        with self._lock:
            self._event_counter += 1
            event_id = f"evt_{self._event_counter:06d}"

        return StageEventModel(
            event_id=event_id,
            kind=kind,
            session_name=normalized_session,
            text=text,
            speaker=str(request.speaker or "Echo").strip() or "Echo",
            source=str(request.source or "console").strip() or "console",
            created_at=datetime.now().astimezone().isoformat(timespec="microseconds"),
            metadata=metadata,
        )

    def _get_or_create_channel(
        self,
        channel_key: tuple[str, str],
    ) -> _StageEventChannel:
        channel = self._channels.get(channel_key)
        if channel is None:
            channel = _StageEventChannel(
                history=deque(maxlen=self.history_limit),
            )
            self._channels[channel_key] = channel
        return channel

    @staticmethod
    def _channel_key(scope_key: str, session_name: str) -> tuple[str, str]:
        cleaned_scope = str(scope_key or "default").strip() or "default"
        return cleaned_scope, normalize_session_name(session_name)


def stage_event_to_sse(event: StageEventModel) -> str:
    payload = event.model_dump(mode="json")
    return (
        f"id: {event.event_id}\n"
        f"event: {event.kind}\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    )
