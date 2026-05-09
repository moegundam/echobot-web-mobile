from __future__ import annotations

from ...channels import ChannelsConfig, OutboundMessage
from ...models import message_content_to_text
from .stage_events import StageEventBroker, StageEventPublishRequest


class StageEventPublisher:
    """Publish gateway responses into the user/session scoped Stage broker."""

    def __init__(self, stage_event_broker: StageEventBroker) -> None:
        self.stage_event_broker = stage_event_broker

    async def publish_gateway_event(
        self,
        *,
        channels_config: ChannelsConfig | None,
        scope_key: str,
        session_name: str,
        outbound: OutboundMessage,
    ) -> None:
        if channels_config is None:
            return
        channel_config = channels_config.get(outbound.address.channel)
        if not bool(getattr(channel_config, "mirror_to_stage", False)):
            return

        # Formal activity is session-centered. Legacy channel stage_session_name is
        # kept only as a fallback when no runtime session was supplied.
        stage_session_name = session_name or (
            str(getattr(channel_config, "stage_session_name", "") or "").strip()
        )
        text = message_content_to_text(outbound.content or outbound.text).strip()
        if not text:
            return

        await self.stage_event_broker.publish(
            scope_key=scope_key,
            request=StageEventPublishRequest(
                kind="assistant_final",
                session_name=stage_session_name,
                text=text,
                speaker="Echo",
                source=outbound.address.channel,
                metadata={
                    "gateway_channel": outbound.address.channel,
                    "gateway_session_name": session_name,
                },
            ),
        )
