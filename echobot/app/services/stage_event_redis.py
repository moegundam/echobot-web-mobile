from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import re
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from ...runtime.sessions import normalize_session_name
from .stage_events import (
    DEFAULT_STAGE_EVENT_HEARTBEAT_SECONDS,
    DEFAULT_STAGE_EVENT_HISTORY_LIMIT,
    DEFAULT_STAGE_EVENT_QUEUE_LIMIT,
    STAGE_EVENT_QUEUE_PRESSURE_POLICY,
    StageEventModel,
    StageEventPublishRequest,
    build_stage_event,
)


DEFAULT_REDIS_STAGE_EVENT_STREAM_KEY_PREFIX = "echobot:stage-events"
DEFAULT_REDIS_STAGE_EVENT_STREAM_TTL_SECONDS = 86400
DEFAULT_REDIS_STAGE_EVENT_READ_BLOCK_MS = 1000
_REDIS_STREAM_ID_PATTERN = re.compile(r"^\d+-\d+$")

RedisClientFactory = Callable[[], Any | Awaitable[Any]]


class RedisStreamsStageEventSubscription:
    pressure_policy = STAGE_EVENT_QUEUE_PRESSURE_POLICY

    def __init__(
        self,
        *,
        client: Any,
        stream_key: str,
        cursor: str,
        queue_limit: int,
        read_block_ms: int,
    ) -> None:
        self._client = client
        self._stream_key = stream_key
        self._cursor = cursor
        self._queue_limit = max(queue_limit, 1)
        self._read_block_ms = max(read_block_ms, 1)
        self._queue: deque[StageEventModel] = deque()
        self._dropped_event_count = 0
        self._closed = False

    @property
    def dropped_event_count(self) -> int:
        return self._dropped_event_count

    async def next_event(self) -> StageEventModel:
        while not self._closed:
            if self._queue:
                return self._queue.popleft()

            response = await self._client.xread(
                {self._stream_key: self._cursor},
                count=self._queue_limit,
                block=self._read_block_ms,
            )
            if not response:
                await asyncio.sleep(0)
                continue

            self._accept_entries(response)

        raise RuntimeError("Stage event subscription is closed")

    async def close(self) -> None:
        self._closed = True
        self._queue.clear()

    def _accept_entries(self, response: object) -> None:
        if not isinstance(response, (list, tuple)):
            return

        for stream_result in response:
            if not isinstance(stream_result, (list, tuple)) or len(stream_result) != 2:
                continue
            entries = stream_result[1]
            if not isinstance(entries, (list, tuple)):
                continue

            for entry in entries:
                if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                    continue
                stream_id = _decode_text(entry[0])
                if not stream_id:
                    continue
                self._cursor = stream_id
                fields = _decode_fields(entry[1])
                event = _event_from_stream_entry(stream_id, fields)
                if event is not None:
                    self._offer(event)

    def _offer(self, event: StageEventModel) -> None:
        if len(self._queue) >= self._queue_limit:
            self._queue.popleft()
            self._dropped_event_count += 1
        self._queue.append(event)


class RedisStreamsStageEventBroker:
    """Optional Redis Streams broker with one bounded key per Stage channel."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        client_factory: RedisClientFactory | None = None,
        redis_url: str | None = None,
        stream_key_prefix: str = DEFAULT_REDIS_STAGE_EVENT_STREAM_KEY_PREFIX,
        history_limit: int = DEFAULT_STAGE_EVENT_HISTORY_LIMIT,
        queue_limit: int = DEFAULT_STAGE_EVENT_QUEUE_LIMIT,
        stream_ttl_seconds: int = DEFAULT_REDIS_STAGE_EVENT_STREAM_TTL_SECONDS,
        heartbeat_interval: float = DEFAULT_STAGE_EVENT_HEARTBEAT_SECONDS,
        read_block_ms: int = DEFAULT_REDIS_STAGE_EVENT_READ_BLOCK_MS,
    ) -> None:
        configured_clients = sum(
            value is not None for value in (client, client_factory, redis_url)
        )
        if configured_clients > 1:
            raise ValueError(
                "Configure only one of client, client_factory, or redis_url",
            )

        self.stream_key_prefix = str(stream_key_prefix or "").strip().rstrip(":")
        if not self.stream_key_prefix:
            raise ValueError("Redis Stage event stream key prefix is required")

        self.stream_ttl_seconds = int(stream_ttl_seconds)
        if self.stream_ttl_seconds <= 0:
            raise ValueError("Redis Stage event stream TTL must be positive")

        self.history_limit = max(history_limit, 1)
        self.queue_limit = max(queue_limit, 1)
        self.heartbeat_interval = max(float(heartbeat_interval), 0.1)
        self.read_block_ms = max(read_block_ms, 1)
        self._client = client
        self._client_factory = client_factory
        self._redis_url = str(redis_url or "").strip()
        self._client_lock = asyncio.Lock()

    async def publish(
        self,
        *,
        scope_key: str,
        request: StageEventPublishRequest,
    ) -> StageEventModel:
        event = build_stage_event(request, event_id="")
        stream_key = self._stream_key(scope_key, event.session_name)
        client = await self._get_client()
        stream_id = await client.xadd(
            stream_key,
            _stream_fields(event),
            maxlen=self.history_limit,
            approximate=False,
        )
        if not await client.expire(stream_key, self.stream_ttl_seconds):
            raise RuntimeError("Redis client failed to expire Stage event stream")
        event_id = _decode_text(stream_id)
        if not event_id:
            raise RuntimeError("Redis client returned an empty stream event ID")
        return event.model_copy(update={"event_id": event_id})

    async def subscribe(
        self,
        *,
        scope_key: str,
        session_name: str,
        replay_history: bool = True,
        after_event_id: str | None = None,
    ) -> RedisStreamsStageEventSubscription:
        stream_key = self._stream_key(scope_key, session_name)
        client = await self._get_client()
        if replay_history:
            cursor = await self._replay_cursor(
                client,
                stream_key,
                after_event_id,
            )
        else:
            cursor = await self._latest_stream_id(client, stream_key)

        return RedisStreamsStageEventSubscription(
            client=client,
            stream_key=stream_key,
            cursor=cursor,
            queue_limit=self.queue_limit,
            read_block_ms=self.read_block_ms,
        )

    async def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        async with self._client_lock:
            if self._client is not None:
                return self._client

            if self._client_factory is not None:
                client = self._client_factory()
                if inspect.isawaitable(client):
                    client = await client
            elif self._redis_url:
                client = self._client_from_url(self._redis_url)
            else:
                raise RuntimeError(
                    "Redis client is not configured; inject a client, "
                    "client_factory, or redis_url",
                )

            if client is None:
                raise RuntimeError("Redis client factory returned no client")
            self._client = client
            return client

    @staticmethod
    def _client_from_url(redis_url: str) -> Any:
        try:
            from redis import asyncio as redis_asyncio
        except ImportError as exc:
            raise RuntimeError(
                "Redis client dependency is unavailable; install redis or "
                "inject a compatible async client",
            ) from exc
        return redis_asyncio.from_url(redis_url)

    async def _latest_stream_id(self, client: Any, stream_key: str) -> str:
        entries = await client.xrevrange(stream_key, count=1)
        if not entries:
            return "0-0"
        stream_id = _decode_text(entries[0][0])
        return stream_id or "0-0"

    async def _replay_cursor(
        self,
        client: Any,
        stream_key: str,
        after_event_id: str | None,
    ) -> str:
        cursor = _normalize_replay_cursor(after_event_id)
        if cursor == "0-0":
            return cursor
        entries = await client.xrange(
            stream_key,
            min=cursor,
            max=cursor,
            count=1,
        )
        return cursor if entries else "0-0"

    def _stream_key(self, scope_key: str, session_name: str) -> str:
        scope_hash = _hash_key_component("scope", _normalize_scope_key(scope_key))
        session_hash = _hash_key_component(
            "session",
            normalize_session_name(session_name),
        )
        return f"{self.stream_key_prefix}:{scope_hash}:{session_hash}"


def _stream_fields(event: StageEventModel) -> dict[str, str]:
    return {
        "kind": event.kind,
        "session_name": event.session_name,
        "text": event.text,
        "emotion": event.emotion,
        "expression": event.expression,
        "motion": event.motion,
        "speaker": event.speaker,
        "source": event.source,
        "created_at": event.created_at,
        "metadata": json.dumps(event.metadata, ensure_ascii=False),
    }


def _event_from_stream_entry(
    stream_id: str,
    fields: Mapping[str, str],
) -> StageEventModel | None:
    try:
        metadata = json.loads(fields.get("metadata", "{}"))
        if not isinstance(metadata, dict):
            return None
        return StageEventModel.model_validate(
            {
                "event_id": stream_id,
                "kind": fields.get("kind", ""),
                "session_name": fields.get("session_name", ""),
                "text": fields.get("text", ""),
                "emotion": fields.get("emotion", ""),
                "expression": fields.get("expression", ""),
                "motion": fields.get("motion", ""),
                "speaker": fields.get("speaker", "Echo"),
                "source": fields.get("source", "console"),
                "created_at": fields.get("created_at", ""),
                "metadata": metadata,
            },
        )
    except (TypeError, ValueError):
        return None


def _decode_fields(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        _decode_text(key): _decode_text(field_value)
        for key, field_value in value.items()
    }


def _decode_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def _normalize_scope_key(scope_key: str) -> str:
    return str(scope_key or "default").strip() or "default"


def _hash_key_component(label: str, value: str) -> str:
    encoded_value = f"{label}\0{value}".encode("utf-8")
    return hashlib.sha256(encoded_value).hexdigest()


def _normalize_replay_cursor(after_event_id: str | None) -> str:
    cursor = str(after_event_id or "").strip()
    if _REDIS_STREAM_ID_PATTERN.fullmatch(cursor):
        return cursor
    return "0-0"
