export const MODEL_PROFILE_UPDATE_STORAGE_KEY = "echobot.modelProfiles.updated";

const LIVE2D_SELECTION_STORAGE_KEY = "echobot.web.live2d.selection";
const TTS_PROVIDER_STORAGE_KEY = "echobot.web.tts.provider";

export function activeModelProfileFromConfig(config) {
    const payload = config && config.model_profiles;
    if (!payload || !Array.isArray(payload.profiles)) {
        return null;
    }
    return payload.profiles.find((item) => item.profile_id === payload.active_profile_id)
        || payload.profiles[0]
        || null;
}

export function modelProfileScopeFromConfig(config) {
    return String(config && config.model_profile_scope || "default").trim() || "default";
}

export function applyModelProfileToLocalPreferences(profile) {
    if (!profile) {
        return;
    }
    const live2dSelectionKey = String(
        profile.live2d && profile.live2d.selection_key || "",
    ).trim();
    if (live2dSelectionKey) {
        writeLocalPreference(LIVE2D_SELECTION_STORAGE_KEY, live2dSelectionKey);
    } else {
        removeLocalPreference(LIVE2D_SELECTION_STORAGE_KEY);
    }

    const previousTtsProvider = readLocalPreference(TTS_PROVIDER_STORAGE_KEY);
    const ttsProvider = String(profile.tts && profile.tts.provider || "").trim();
    if (ttsProvider) {
        writeLocalPreference(TTS_PROVIDER_STORAGE_KEY, ttsProvider);
        const voice = String(profile.tts && profile.tts.voice || "").trim();
        if (voice) {
            writeLocalPreference(ttsVoiceStorageKey(ttsProvider), voice);
        } else {
            removeLocalPreference(ttsVoiceStorageKey(ttsProvider));
        }
    } else {
        if (previousTtsProvider) {
            removeLocalPreference(ttsVoiceStorageKey(previousTtsProvider));
        }
        removeLocalPreference(TTS_PROVIDER_STORAGE_KEY);
    }
}

export function notifyModelProfileChanged(profileId, scope = "default") {
    writeLocalPreference(
        MODEL_PROFILE_UPDATE_STORAGE_KEY,
        JSON.stringify({
            profile_id: String(profileId || ""),
            scope: String(scope || "default"),
            updated_at: Date.now(),
        }),
    );
}

function ttsVoiceStorageKey(provider) {
    const normalizedProvider = String(provider || "default").trim() || "default";
    return `echobot.web.tts.voice.${normalizedProvider}`;
}

function writeLocalPreference(key, value) {
    try {
        window.localStorage.setItem(key, value);
    } catch (_error) {
        // localStorage can be unavailable in restricted browsing contexts.
    }
}

function readLocalPreference(key) {
    try {
        return String(window.localStorage.getItem(key) || "").trim();
    } catch (_error) {
        return "";
    }
}

function removeLocalPreference(key) {
    try {
        window.localStorage.removeItem(key);
    } catch (_error) {
        // localStorage can be unavailable in restricted browsing contexts.
    }
}
