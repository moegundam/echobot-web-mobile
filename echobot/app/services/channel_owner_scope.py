from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...channels import MessageBus
from .channels import ChannelService


@dataclass(frozen=True)
class ChannelOwnerScope:
    """Owner-scoped channel runtime dependencies.

    Channel credentials and gateway processes are configured once for the app
    owner. Trusted-user runtimes may read or administer them through auth-gated
    routes, but they do not own separate channel credentials.
    """

    runtime: Any
    service: ChannelService
    bus: MessageBus | None


def channel_owner_scope(runtime: Any) -> ChannelOwnerScope:
    owner_runtime = getattr(runtime, "parent", runtime)
    service = getattr(owner_runtime, "channel_service", None)
    if service is None:
        raise RuntimeError("Channel service is not ready")
    return ChannelOwnerScope(
        runtime=owner_runtime,
        service=service,
        bus=getattr(owner_runtime, "bus", None),
    )
