from __future__ import annotations

from pathlib import Path

from echobot.app.services.character_profiles import CharacterProfileSettingsService


def test_settings_for_roles_reads_store_once(monkeypatch, tmp_path: Path) -> None:
    service = CharacterProfileSettingsService(tmp_path)
    service.set_emotion_maps(
        "alpha",
        [{"emotion": "joy", "expression": "smile", "motion": "wave"}],
    )
    service.set_runtime_bindings("alpha", {"llm_model_id": "llm-a"})
    service.set_runtime_bindings("beta", {"voice_profile_id": "voice-b"})
    original_load = service._load_state_unlocked
    load_count = 0

    def counted_load() -> dict[str, object]:
        nonlocal load_count
        load_count += 1
        return original_load()

    monkeypatch.setattr(service, "_load_state_unlocked", counted_load)

    snapshot = service.settings_for_roles(["alpha", "beta"])

    assert load_count == 1
    assert snapshot["alpha"]["emotion_maps"][0]["emotion"] == "joy"
    assert snapshot["alpha"]["runtime_bindings"]["llm_model_id"] == "llm-a"
    assert snapshot["beta"]["runtime_bindings"]["voice_profile_id"] == "voice-b"
