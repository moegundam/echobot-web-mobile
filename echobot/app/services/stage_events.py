from __future__ import annotations

import asyncio
import json
import threading
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, Field

from ...runtime.sessions import normalize_session_name


MAX_STAGE_EVENT_TEXT_LENGTH = 8192
MAX_STAGE_EVENT_METADATA_BYTES = 4096
MAX_STAGE_EVENT_DIRECTIVE_LENGTH = 256
DEFAULT_STAGE_EVENT_HISTORY_LIMIT = 100
DEFAULT_STAGE_EVENT_QUEUE_LIMIT = 100
DEFAULT_STAGE_EVENT_CHANNEL_LIMIT = 256
DEFAULT_STAGE_EVENT_HEARTBEAT_SECONDS = 15.0
STAGE_EVENT_QUEUE_PRESSURE_POLICY = "drop_oldest"
VALID_STAGE_EVENT_KINDS = {
    "assistant_delta",
    "assistant_final",
    "character_state",
    "state",
    "subtitle",
}


class StageEventPublishRequest(BaseModel):
    kind: str
    session_name: str
    text: str = ""
    emotion: str = ""
    expression: str = ""
    motion: str = ""
    speaker: str = "Echo"
    source: str = "console"
    metadata: dict[str, Any] = Field(default_factory=dict)


class StageEventModel(BaseModel):
    event_id: str
    kind: str
    session_name: str
    text: str = ""
    emotion: str = ""
    expression: str = ""
    motion: str = ""
    speaker: str = "Echo"
    source: str = "console"
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class StageEventSubscriptionProtocol(Protocol):
    """Consumer contract for a bounded Stage event subscription."""

    pressure_policy: str

    @property
    def dropped_event_count(self) -> int:
        ...

    async def next_event(self) -> StageEventModel:
        ...

    async def close(self) -> None:
        ...


@runtime_checkable
class StageEventBrokerProtocol(Protocol):
    """Publish and cursor-aware subscription contract for Stage events."""

    heartbeat_interval: float

    async def publish(
        self,
        *,
        scope_key: str,
        request: StageEventPublishRequest,
    ) -> StageEventModel:
        ...

    async def subscribe(
        self,
        *,
        scope_key: str,
        session_name: str,
        replay_history: bool = True,
        after_event_id: str | None = None,
    ) -> StageEventSubscriptionProtocol:
        ...


class StageEventBrokerCapacityError(ValueError):
    """Raised when no inactive Stage channel can be evicted."""


@dataclass(slots=True)
class _StageEventChannel:
    history: deque[StageEventModel]
    subscribers: set["StageEventSubscription"] = field(default_factory=set)


class StageEventSubscription:
    pressure_policy = STAGE_EVENT_QUEUE_PRESSURE_POLICY

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
        self._dropped_event_count = 0

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

    @property
    def dropped_event_count(self) -> int:
        return self._dropped_event_count

    def offer(self, event: StageEventModel) -> None:
        if self._closed:
            return
        if self._queue.full():
            try:
                self._queue.get_nowait()
                self._dropped_event_count += 1
            except asyncio.QueueEmpty:
                pass
        self._queue.put_nowait(event)


class StageEventBroker:
    def __init__(
        self,
        *,
        history_limit: int = DEFAULT_STAGE_EVENT_HISTORY_LIMIT,
        queue_limit: int = DEFAULT_STAGE_EVENT_QUEUE_LIMIT,
        max_channels: int = DEFAULT_STAGE_EVENT_CHANNEL_LIMIT,
        heartbeat_interval: float = DEFAULT_STAGE_EVENT_HEARTBEAT_SECONDS,
    ) -> None:
        self.history_limit = max(history_limit, 1)
        self.queue_limit = max(queue_limit, 1)
        self.max_channels = max(max_channels, 1)
        self.heartbeat_interval = max(float(heartbeat_interval), 0.1)
        self._channels: OrderedDict[
            tuple[str, str],
            _StageEventChannel,
        ] = OrderedDict()
        self._lock = threading.RLock()

    @property
    def channel_count(self) -> int:
        with self._lock:
            return len(self._channels)

    async def publish(
        self,
        *,
        scope_key: str,
        request: StageEventPublishRequest,
    ) -> StageEventModel:
        event = build_stage_event(request, event_id="")
        channel_key = self._channel_key(scope_key, event.session_name)
        with self._lock:
            channel = self._get_or_create_channel(channel_key)
            event = event.model_copy(
                update={"event_id": f"evt_{uuid4().hex}"},
            )
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
        after_event_id: str | None = None,
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
            if replay_history:
                history = self._history_after_cursor(
                    channel.history,
                    after_event_id=after_event_id,
                )
            else:
                history = []
            for event in history:
                subscription.offer(event)
            channel.subscribers.add(subscription)
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
            self._channels.move_to_end(channel_key)
            return list(channel.history)

    def _get_or_create_channel(
        self,
        channel_key: tuple[str, str],
    ) -> _StageEventChannel:
        channel = self._channels.get(channel_key)
        if channel is not None:
            self._channels.move_to_end(channel_key)
            return channel

        if len(self._channels) >= self.max_channels:
            inactive_key = next(
                (
                    key
                    for key, candidate in self._channels.items()
                    if not candidate.subscribers
                ),
                None,
            )
            if inactive_key is None:
                raise StageEventBrokerCapacityError(
                    "Stage event broker is at channel capacity; "
                    "all channels have active subscriptions",
                )
            del self._channels[inactive_key]

        channel = _StageEventChannel(
            history=deque(maxlen=self.history_limit),
        )
        self._channels[channel_key] = channel
        return channel

    @staticmethod
    def _history_after_cursor(
        history: deque[StageEventModel],
        *,
        after_event_id: str | None,
    ) -> list[StageEventModel]:
        retained_events = list(history)
        cleaned_cursor = str(after_event_id or "").strip()
        if not cleaned_cursor:
            return retained_events

        for index, event in enumerate(retained_events):
            if event.event_id == cleaned_cursor:
                return retained_events[index + 1:]

        # An unknown or evicted cursor gets an at-least-once replay of what remains.
        return retained_events

    @staticmethod
    def _channel_key(scope_key: str, session_name: str) -> tuple[str, str]:
        cleaned_scope = str(scope_key or "default").strip() or "default"
        return cleaned_scope, normalize_session_name(session_name)


def build_stage_event(
    request: StageEventPublishRequest,
    *,
    event_id: str,
) -> StageEventModel:
    kind = request.kind.strip()
    if kind not in VALID_STAGE_EVENT_KINDS:
        raise ValueError("Stage event kind is invalid")

    text = str(request.text or "")
    if len(text) > MAX_STAGE_EVENT_TEXT_LENGTH:
        raise ValueError("Stage event text is too large")

    metadata = dict(request.metadata or {})
    metadata_bytes = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
    if len(metadata_bytes) > MAX_STAGE_EVENT_METADATA_BYTES:
        raise ValueError("Stage event metadata is too large")

    return StageEventModel(
        event_id=event_id,
        kind=kind,
        session_name=normalize_session_name(request.session_name),
        text=text,
        emotion=_clean_directive("emotion", request.emotion),
        expression=_clean_directive("expression", request.expression),
        motion=_clean_directive("motion", request.motion),
        speaker=str(request.speaker or "Echo").strip() or "Echo",
        source=str(request.source or "console").strip() or "console",
        created_at=datetime.now().astimezone().isoformat(timespec="microseconds"),
        metadata=metadata,
    )


def _clean_directive(field_name: str, value: str) -> str:
    cleaned = str(value or "").strip()
    if len(cleaned) > MAX_STAGE_EVENT_DIRECTIVE_LENGTH:
        raise ValueError(f"Stage event {field_name} is too large")
    return cleaned


def stage_event_to_sse(event: StageEventModel) -> str:
    payload = event.model_dump(mode="json")
    return (
        f"id: {event.event_id}\n"
        f"event: {event.kind}\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    )
