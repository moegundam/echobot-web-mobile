from __future__ import annotations

from ..models import LLMMessage, normalize_message_content
from ..orchestration import role_name_from_metadata, route_mode_from_metadata
from ..runtime.sessions import ChatSession, SessionInfo
from .schemas import (
    MessageModel,
    SessionDetailModel,
    SessionSummaryModel,
    ToolCallModel,
)
from .session_metadata import (
    channel_integration_id_from_metadata,
    channel_type_from_metadata,
)


def message_model_from_message(
    message: LLMMessage,
    *,
    sanitize_user_content: bool = False,
) -> MessageModel:
    del sanitize_user_content
    content = normalize_message_content(message.content)
    return MessageModel(
        role=message.role,
        content=content,
        name=message.name,
        tool_call_id=message.tool_call_id,
        tool_calls=[
            ToolCallModel(
                id=tool_call.id,
                name=tool_call.name,
                arguments=tool_call.arguments,
            )
            for tool_call in message.tool_calls
        ],
    )


def session_summary_model_from_info(info: SessionInfo) -> SessionSummaryModel:
    return SessionSummaryModel(
        name=info.name,
        message_count=info.message_count,
        updated_at=info.updated_at,
        role_name=role_name_from_metadata(info.metadata),
        route_mode=route_mode_from_metadata(info.metadata),
        channel_type=channel_type_from_metadata(info.metadata),
        channel_integration_id=channel_integration_id_from_metadata(info.metadata),
    )


def session_detail_model_from_session(session: ChatSession) -> SessionDetailModel:
    return SessionDetailModel(
        name=session.name,
        updated_at=session.updated_at,
        compressed_summary=session.compressed_summary,
        role_name=role_name_from_metadata(session.metadata),
        route_mode=route_mode_from_metadata(session.metadata),
        channel_type=channel_type_from_metadata(session.metadata),
        channel_integration_id=channel_integration_id_from_metadata(session.metadata),
        history=[
            message_model_from_message(
                message,
                sanitize_user_content=True,
            )
            for message in session.history
        ],
    )
