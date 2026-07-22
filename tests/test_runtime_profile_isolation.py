from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

from echobot.app.services.runtime_profile_applier import RuntimeProfileApplier
from echobot.runtime.bootstrap import RuntimeOptions, build_runtime_context


def test_chat_profile_preserves_dedicated_decision_and_roleplay_providers() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir)
        with patch.dict(
            "os.environ",
            {
                "LLM_API_KEY": "main-key",
                "LLM_MODEL": "main-model",
                "LLM_BASE_URL": "http://main.test/v1",
                "DECIDER_LLM_API_KEY": "decision-key",
                "DECIDER_LLM_MODEL": "decision-model",
                "DECIDER_LLM_BASE_URL": "http://decision.test/v1",
                "ROLE_LLM_API_KEY": "role-key",
                "ROLE_LLM_MODEL": "role-model",
                "ROLE_LLM_BASE_URL": "http://role.test/v1",
            },
            clear=False,
        ):
            context = build_runtime_context(
                RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                load_session_state=False,
            )

            RuntimeProfileApplier(
                context=context,
                web_console_service=None,
            ).apply_chat(
                {
                    "model": "profile-model",
                    "base_url": "http://profile.test/v1",
                    "api_key": "profile-key",
                }
            )

            assert context.agent.provider.settings.model == "profile-model"
            assert (
                context.coordinator._decision_engine._decider_agent.provider.settings.model
                == "decision-model"
            )
            assert (
                context.coordinator._roleplay_engine._role_agent.provider.settings.model
                == "role-model"
            )

            asyncio.run(context.coordinator.close())
