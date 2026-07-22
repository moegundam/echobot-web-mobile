from __future__ import annotations

import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .stage_event_redis import (
    DEFAULT_REDIS_STAGE_EVENT_READ_BLOCK_MS,
    DEFAULT_REDIS_STAGE_EVENT_STREAM_KEY_PREFIX,
    DEFAULT_REDIS_STAGE_EVENT_STREAM_TTL_SECONDS,
    RedisClientFactory,
    RedisStreamsStageEventBroker,
)
from .stage_events import (
    DEFAULT_STAGE_EVENT_CHANNEL_LIMIT,
    DEFAULT_STAGE_EVENT_HEARTBEAT_SECONDS,
    DEFAULT_STAGE_EVENT_HISTORY_LIMIT,
    DEFAULT_STAGE_EVENT_QUEUE_LIMIT,
    StageEventBroker,
    StageEventBrokerProtocol,
)


STAGE_BROKER_ENV = "ECHOBOT_STAGE_BROKER"
STAGE_WORKER_COUNT_ENV = "ECHOBOT_STAGE_WORKER_COUNT"
STAGE_REDIS_URL_ENV = "ECHOBOT_STAGE_REDIS_URL"
STAGE_HISTORY_LIMIT_ENV = "ECHOBOT_STAGE_HISTORY_LIMIT"
STAGE_QUEUE_LIMIT_ENV = "ECHOBOT_STAGE_QUEUE_LIMIT"
STAGE_MAX_CHANNELS_ENV = "ECHOBOT_STAGE_MAX_CHANNELS"
STAGE_HEARTBEAT_SECONDS_ENV = "ECHOBOT_STAGE_HEARTBEAT_SECONDS"
STAGE_REDIS_TTL_SECONDS_ENV = "ECHOBOT_STAGE_REDIS_TTL_SECONDS"
STAGE_REDIS_READ_BLOCK_MS_ENV = "ECHOBOT_STAGE_REDIS_READ_BLOCK_MS"
STAGE_REDIS_STREAM_KEY_PREFIX_ENV = "ECHOBOT_STAGE_REDIS_STREAM_KEY_PREFIX"
STANDARD_WORKER_COUNT_ENVS = ("WEB_CONCURRENCY", "UVICORN_WORKERS")

SUPPORTED_STAGE_BROKERS = frozenset({"memory", "redis"})
_STRICT_INTEGER = re.compile(r"^[0-9]+$")


class StageBrokerConfigurationError(ValueError):
    """Raised when Stage broker configuration cannot be used safely."""


@dataclass(frozen=True, slots=True)
class StageEventBrokerConfig:
    """Validated configuration shared by the memory and Redis broker paths."""

    backend: str = "memory"
    worker_count: int = 1
    history_limit: int = DEFAULT_STAGE_EVENT_HISTORY_LIMIT
    queue_limit: int = DEFAULT_STAGE_EVENT_QUEUE_LIMIT
    max_channels: int = DEFAULT_STAGE_EVENT_CHANNEL_LIMIT
    heartbeat_seconds: float = DEFAULT_STAGE_EVENT_HEARTBEAT_SECONDS
    redis_url: str | None = None
    redis_ttl_seconds: int = DEFAULT_REDIS_STAGE_EVENT_STREAM_TTL_SECONDS
    redis_read_block_ms: int = DEFAULT_REDIS_STAGE_EVENT_READ_BLOCK_MS
    redis_stream_key_prefix: str = DEFAULT_REDIS_STAGE_EVENT_STREAM_KEY_PREFIX

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        worker_count: int | None = None,
    ) -> "StageEventBrokerConfig":
        source = os.environ if env is None else env
        backend = _read_text(source, STAGE_BROKER_ENV, default="memory").lower()
        config = cls(
            backend=backend,
            worker_count=(
                _parse_positive_int(worker_count, STAGE_WORKER_COUNT_ENV)
                if worker_count is not None
                else _read_worker_count(source)
            ),
            history_limit=_read_positive_int(
                source,
                STAGE_HISTORY_LIMIT_ENV,
                default=DEFAULT_STAGE_EVENT_HISTORY_LIMIT,
            ),
            queue_limit=_read_positive_int(
                source,
                STAGE_QUEUE_LIMIT_ENV,
                default=DEFAULT_STAGE_EVENT_QUEUE_LIMIT,
            ),
            max_channels=_read_positive_int(
                source,
                STAGE_MAX_CHANNELS_ENV,
                default=DEFAULT_STAGE_EVENT_CHANNEL_LIMIT,
            ),
            heartbeat_seconds=_read_positive_float(
                source,
                STAGE_HEARTBEAT_SECONDS_ENV,
                default=DEFAULT_STAGE_EVENT_HEARTBEAT_SECONDS,
            ),
            redis_url=_optional_text(source, STAGE_REDIS_URL_ENV),
            redis_ttl_seconds=_read_positive_int(
                source,
                STAGE_REDIS_TTL_SECONDS_ENV,
                default=DEFAULT_REDIS_STAGE_EVENT_STREAM_TTL_SECONDS,
            ),
            redis_read_block_ms=_read_positive_int(
                source,
                STAGE_REDIS_READ_BLOCK_MS_ENV,
                default=DEFAULT_REDIS_STAGE_EVENT_READ_BLOCK_MS,
            ),
            redis_stream_key_prefix=_read_text(
                source,
                STAGE_REDIS_STREAM_KEY_PREFIX_ENV,
                default=DEFAULT_REDIS_STAGE_EVENT_STREAM_KEY_PREFIX,
            ),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.backend not in SUPPORTED_STAGE_BROKERS:
            supported = ", ".join(sorted(SUPPORTED_STAGE_BROKERS))
            raise StageBrokerConfigurationError(
                f"{STAGE_BROKER_ENV} must be one of {supported}; "
                f"received {self.backend!r}",
            )
        if self.backend == "memory" and self.worker_count > 1:
            raise StageBrokerConfigurationError(
                f"{STAGE_BROKER_ENV}=memory is single-worker only, but "
                f"{STAGE_WORKER_COUNT_ENV}={self.worker_count}; set "
                f"{STAGE_BROKER_ENV}=redis and provide {STAGE_REDIS_URL_ENV} "
                "for multiple workers",
            )
        if self.backend == "redis" and not self.redis_url:
            raise StageBrokerConfigurationError(
                f"{STAGE_BROKER_ENV}=redis requires a non-empty "
                f"{STAGE_REDIS_URL_ENV}; refusing to fall back to memory",
            )


def create_stage_event_broker(
    *,
    env: Mapping[str, str] | None = None,
    worker_count: int | None = None,
    redis_client: Any | None = None,
    redis_client_factory: RedisClientFactory | None = None,
) -> StageEventBrokerProtocol:
    """Build the configured Stage broker without silently changing backends.

    ``redis_client`` and ``redis_client_factory`` are dependency-injection hooks
    for tests or an application-owned Redis lifecycle. Redis mode still
    requires ``ECHOBOT_STAGE_REDIS_URL`` so a production configuration cannot
    accidentally become an unconfigured in-memory broker.
    """

    if redis_client is not None and redis_client_factory is not None:
        raise StageBrokerConfigurationError(
            "Provide only one Redis injection: redis_client or "
            "redis_client_factory",
        )

    config = StageEventBrokerConfig.from_env(env, worker_count=worker_count)
    if config.backend == "memory":
        if redis_client is not None or redis_client_factory is not None:
            raise StageBrokerConfigurationError(
                "Redis injection was provided while "
                f"{STAGE_BROKER_ENV}=memory; select redis explicitly",
            )
        return StageEventBroker(
            history_limit=config.history_limit,
            queue_limit=config.queue_limit,
            max_channels=config.max_channels,
            heartbeat_interval=config.heartbeat_seconds,
        )

    redis_kwargs: dict[str, Any] = {
        "stream_key_prefix": config.redis_stream_key_prefix,
        "history_limit": config.history_limit,
        "queue_limit": config.queue_limit,
        "stream_ttl_seconds": config.redis_ttl_seconds,
        "heartbeat_interval": config.heartbeat_seconds,
        "read_block_ms": config.redis_read_block_ms,
    }
    if redis_client is not None:
        redis_kwargs["client"] = redis_client
    elif redis_client_factory is not None:
        redis_kwargs["client_factory"] = redis_client_factory
    else:
        redis_kwargs["redis_url"] = config.redis_url
    return RedisStreamsStageEventBroker(**redis_kwargs)


def _read_text(
    env: Mapping[str, str],
    key: str,
    *,
    default: str,
) -> str:
    value = env.get(key)
    if value is None:
        return default
    return str(value).strip()


def _optional_text(env: Mapping[str, str], key: str) -> str | None:
    value = _read_text(env, key, default="")
    return value or None


def _read_positive_int(
    env: Mapping[str, str],
    key: str,
    *,
    default: int,
) -> int:
    value = env.get(key)
    if value is None:
        return default
    return _parse_positive_int(value, key)


def _read_worker_count(env: Mapping[str, str]) -> int:
    if STAGE_WORKER_COUNT_ENV in env:
        return _read_positive_int(env, STAGE_WORKER_COUNT_ENV, default=1)
    for key in STANDARD_WORKER_COUNT_ENVS:
        if key in env:
            return _read_positive_int(env, key, default=1)
    return 1


def _parse_positive_int(value: Any, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise StageBrokerConfigurationError(
            f"{key} must be a strict positive integer",
        )
    raw = str(value).strip()
    if not _STRICT_INTEGER.fullmatch(raw):
        raise StageBrokerConfigurationError(
            f"{key} must be a strict positive integer; received {raw!r}",
        )
    parsed = int(raw)
    if parsed <= 0:
        raise StageBrokerConfigurationError(
            f"{key} must be a strict positive integer; received {raw!r}",
        )
    return parsed


def _read_positive_float(
    env: Mapping[str, str],
    key: str,
    *,
    default: float,
) -> float:
    value = env.get(key)
    if value is None:
        return default
    raw = str(value).strip()
    try:
        parsed = float(raw)
    except (TypeError, ValueError) as exc:
        raise StageBrokerConfigurationError(
            f"{key} must be a finite positive number; received {raw!r}",
        ) from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise StageBrokerConfigurationError(
            f"{key} must be a finite positive number; received {raw!r}",
        )
    return parsed
