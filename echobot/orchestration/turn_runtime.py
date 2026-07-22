from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ..providers.base import LLMProvider


@dataclass(frozen=True, slots=True)
class ConversationTurnRuntime:
    agent_provider: LLMProvider | None = None
    decision_provider: LLMProvider | None = None
    roleplay_provider: LLMProvider | None = None
    temperature: float | None = None
    max_tokens: int | None = None


TurnRuntimeResolver = Callable[
    [str, str],
    Awaitable[ConversationTurnRuntime],
]
