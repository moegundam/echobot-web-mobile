from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class FallbackMsg:
    name: str
    role: str
    content: Any

    def get_content_blocks(self) -> list[dict[str, Any]]:
        if isinstance(self.content, list):
            return [
                block
                for block in self.content
                if isinstance(block, dict)
            ]
        text = str(self.content).strip()
        if not text:
            return []
        return [{"type": "text", "text": text}]


try:
    from agentscope.agent import ReActAgent
    from agentscope.message import Msg
    from reme.reme_light import ReMeLight
except ImportError:  # pragma: no cover - optional dependency
    ReActAgent = None  # type: ignore[assignment]
    Msg = FallbackMsg  # type: ignore[assignment]
    ReMeLight = None  # type: ignore[assignment]


__all__ = ["FallbackMsg", "Msg", "ReActAgent", "ReMeLight"]
