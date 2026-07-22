from __future__ import annotations

import unittest

from echobot.app.auth import AccessRole
from echobot.app.schemas import SessionRuntimeContextResponse
from echobot.app.services.access_projection import (
    project_health_payload,
    project_session_runtime_context,
    project_web_config_payload,
)


class AccessProjectionTests(unittest.TestCase):
    def test_operator_web_config_hides_admin_only_runtime_and_provider_details(self) -> None:
        payload = {
            "route_mode": "force_agent",
            "runtime": {
                "delegated_ack_enabled": True,
                "shell_safety_mode": "danger-full-access",
                "file_write_enabled": True,
                "cron_mutation_enabled": True,
                "web_private_network_enabled": True,
            },
            "model_profiles": {
                "active_profile_id": "a",
                "role_bindings": {"default": "a"},
                "profiles": [
                    {
                        "profile_id": "a",
                        "label": "Local model",
                        "chat": {
                            "provider": "openai-compatible",
                            "model": "local-model",
                            "base_url": "http://private-provider.test/v1",
                            "temperature": 0.4,
                            "max_tokens": 4096,
                            "api_key_configured": True,
                            "api_key_source": "environment",
                        },
                        "tts": {
                            "provider": "edge",
                            "model": "",
                            "base_url": "http://private-tts.test/v1",
                            "voice": "voice-a",
                            "api_key_configured": True,
                            "api_key_source": "profile",
                        },
                        "asr": {
                            "provider": "local-asr",
                            "model": "asr-a",
                            "base_url": "http://private-asr.test/v1",
                            "language": "zh-TW",
                            "api_key_configured": True,
                            "api_key_source": "profile",
                        },
                        "live2d": {"selection_key": "echo"},
                        "updated_at": "2026-07-20T00:00:00Z",
                    },
                ],
            },
            "asr": {
                "detail": "ASR resources at /private/asr",
                "asr_providers": [
                    {
                        "name": "local-asr",
                        "detail": "Loaded from /private/asr",
                        "resource_directory": "/private/asr",
                    },
                ],
                "vad_providers": [
                    {
                        "name": "local-vad",
                        "detail": "Loaded from /private/vad",
                        "resource_directory": "/private/vad",
                    },
                ],
            },
            "tts": {
                "providers": [
                    {
                        "name": "local-tts",
                        "detail": "Connected to private provider",
                    },
                ],
            },
        }

        projected = project_web_config_payload(payload, AccessRole.OPERATOR)

        self.assertEqual("force_agent", payload["route_mode"])
        self.assertEqual(
            "http://private-provider.test/v1",
            payload["model_profiles"]["profiles"][0]["chat"]["base_url"],
        )
        self.assertEqual("chat_only", projected["route_mode"])
        self.assertIsNone(projected["runtime"])
        profile = projected["model_profiles"]["profiles"][0]
        self.assertEqual("local-model", profile["chat"]["model"])
        self.assertEqual("", profile["chat"]["base_url"])
        self.assertFalse(profile["chat"]["api_key_configured"])
        self.assertEqual("", profile["chat"]["api_key_source"])
        self.assertEqual("edge", profile["tts"]["provider"])
        self.assertEqual("voice-a", profile["tts"]["voice"])
        self.assertEqual("", profile["tts"]["base_url"])
        self.assertEqual("zh-TW", profile["asr"]["language"])
        self.assertEqual("", profile["asr"]["base_url"])
        self.assertEqual("echo", profile["live2d"]["selection_key"])
        self.assertEqual("", projected["asr"]["detail"])
        self.assertEqual(
            "",
            projected["asr"]["asr_providers"][0]["resource_directory"],
        )
        self.assertEqual("", projected["asr"]["asr_providers"][0]["detail"])
        self.assertEqual(
            "",
            projected["asr"]["vad_providers"][0]["resource_directory"],
        )
        self.assertEqual("", projected["tts"]["providers"][0]["detail"])

    def test_admin_web_config_keeps_full_provider_details(self) -> None:
        payload = {
            "route_mode": "force_agent",
            "runtime": {"shell_safety_mode": "danger-full-access"},
            "model_profiles": {
                "profiles": [
                    {
                        "chat": {
                            "base_url": "http://private-provider.test/v1",
                            "api_key_configured": True,
                        },
                    },
                ],
            },
        }

        projected = project_web_config_payload(payload, AccessRole.ADMIN)

        self.assertEqual(payload, projected)
        self.assertIsNot(payload, projected)

    def test_operator_runtime_context_hides_provider_and_channel_configuration(self) -> None:
        context = SessionRuntimeContextResponse.model_validate(
            {
                "session_name": "demo",
                "role_name": "default",
                "route_mode": "force_agent",
                "llm_model": {
                    "id": "llm-a",
                    "name": "Local model",
                    "provider": "openai-compatible",
                    "model": "local-model",
                    "base_url": "http://private-provider.test/v1",
                    "api_key_configured": True,
                    "api_key_source": "profile",
                },
                "voice_profile": {
                    "id": "voice-a",
                    "name": "Voice A",
                    "tts": {
                        "provider": "edge",
                        "base_url": "http://private-tts.test/v1",
                        "voice": "voice-a",
                        "api_key_configured": True,
                        "api_key_source": "profile",
                    },
                    "stt": {
                        "provider": "local-asr",
                        "base_url": "http://private-asr.test/v1",
                        "language": "zh-TW",
                        "api_key_configured": True,
                        "api_key_source": "profile",
                    },
                },
                "channel": {
                    "id": "telegram-main",
                    "type": "telegram",
                    "name": "Telegram",
                    "config": {"bot_username": "private_bot"},
                },
            },
        )

        projected = project_session_runtime_context(context, AccessRole.OPERATOR)

        self.assertEqual("force_agent", context.route_mode)
        self.assertEqual("chat_only", projected.route_mode)
        self.assertEqual("local-model", projected.llm_model.model)
        self.assertEqual("", projected.llm_model.base_url)
        self.assertFalse(projected.llm_model.api_key_configured)
        self.assertEqual("", projected.llm_model.api_key_source)
        self.assertEqual("voice-a", projected.voice_profile.tts.voice)
        self.assertEqual("", projected.voice_profile.tts.base_url)
        self.assertEqual("", projected.voice_profile.stt.base_url)
        self.assertEqual({}, projected.channel.config)

    def test_non_admin_health_hides_owner_global_runtime_status(self) -> None:
        payload = {
            "status": "ok",
            "workspace_name": "private-workspace",
            "storage_scope": "user",
            "trusted_user": "operator@example.test",
            "current_session": "demo",
            "current_role": "default",
            "channels": {"telegram": {"configured": True}},
            "bus": {"inbound_size": 2, "outbound_size": 1},
            "jobs": {"running": 1},
        }

        operator_payload = project_health_payload(payload, AccessRole.OPERATOR)
        admin_payload = project_health_payload(payload, AccessRole.ADMIN)

        self.assertNotIn("workspace_name", operator_payload)
        self.assertNotIn("channels", operator_payload)
        self.assertNotIn("bus", operator_payload)
        self.assertEqual("demo", operator_payload["current_session"])
        self.assertEqual({"running": 1}, operator_payload["jobs"])
        self.assertEqual(payload, admin_payload)
        self.assertEqual("private-workspace", payload["workspace_name"])


if __name__ == "__main__":
    unittest.main()
