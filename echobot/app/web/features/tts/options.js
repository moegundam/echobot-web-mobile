import { DOM } from "../../core/dom.js";
import { appState, audioState } from "../../core/store.js";

export function createTtsOptionsController(deps) {
    const { requestJson } = deps;
    const t = typeof deps.t === "function" ? deps.t : (key, params = {}) => {
        return String(key).replace(/\{([A-Za-z0-9_]+)\}/g, (_match, name) => {
            return Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : "";
        });
    };

    function loadSavedTtsProvider() {
        return String(window.localStorage.getItem("echobot.web.tts.provider") || "").trim();
    }

    function persistTtsProvider(provider) {
        window.localStorage.setItem("echobot.web.tts.provider", provider);
    }

    function ttsVoiceStorageKey(provider) {
        const normalizedProvider = String(provider || "default").trim() || "default";
        return `echobot.web.tts.voice.${normalizedProvider}`;
    }

    function loadSavedTtsVoice(provider) {
        return String(window.localStorage.getItem(ttsVoiceStorageKey(provider)) || "").trim();
    }

    function persistTtsVoice(provider, voice) {
        window.localStorage.setItem(ttsVoiceStorageKey(provider), voice);
    }

    function resolveInitialTtsProvider(ttsConfig) {
        const providers = Array.isArray(ttsConfig && ttsConfig.providers)
            ? ttsConfig.providers
            : [];
        const providerNames = providers
            .map((item) => String((item && item.name) || ""))
            .filter(Boolean);
        const savedProvider = loadSavedTtsProvider();
        if (providerNames.includes(savedProvider)) {
            return savedProvider;
        }

        const defaultProvider = String((ttsConfig && ttsConfig.default_provider) || "edge");
        if (providerNames.includes(defaultProvider)) {
            return defaultProvider;
        }

        return providerNames[0] || defaultProvider;
    }

    function findTtsProviderStatus(ttsConfig, provider) {
        const providers = Array.isArray(ttsConfig && ttsConfig.providers)
            ? ttsConfig.providers
            : [];
        return providers.find((item) => item.name === provider) || null;
    }

    function renderTtsProviderOptions(ttsConfig, selectedProvider) {
        if (!DOM.ttsProviderSelect) {
            return;
        }

        DOM.ttsProviderSelect.innerHTML = "";
        const providers = Array.isArray(ttsConfig && ttsConfig.providers)
            ? ttsConfig.providers
            : [];

        providers.forEach((providerStatus) => {
            const option = document.createElement("option");
            option.value = providerStatus.name;
            option.textContent = providerStatus.available
                ? providerStatus.label
                : t("console.providerNotReady", { provider: providerStatus.label });
            DOM.ttsProviderSelect.appendChild(option);
        });

        DOM.ttsProviderSelect.disabled = providers.length <= 1;
        if (selectedProvider) {
            DOM.ttsProviderSelect.value = selectedProvider;
        }
    }

    function buildTtsDetail(providerStatus) {
        if (!providerStatus) {
            return t("console.noTtsProvider");
        }
        if (providerStatus.available) {
            return t("console.providerEnabled", { provider: providerStatus.label });
        }
        return providerStatus.detail || t("console.providerNotReady", { provider: providerStatus.label });
    }

    async function loadTtsOptions(ttsConfig) {
        const provider = resolveInitialTtsProvider(ttsConfig);
        audioState.selectedTtsProvider = provider;
        renderTtsProviderOptions(ttsConfig, provider);
        persistTtsProvider(provider);
        await loadVoiceOptions(ttsConfig, provider);
    }

    async function handleTtsProviderChange() {
        if (!DOM.ttsProviderSelect || !appState.config || !appState.config.tts) {
            return;
        }

        const provider = DOM.ttsProviderSelect.value;
        audioState.selectedTtsProvider = provider;
        persistTtsProvider(provider);
        await loadVoiceOptions(appState.config.tts, provider);
    }

    function handleVoiceSelectionChange() {
        audioState.selectedVoice = DOM.voiceSelect.value;
        persistTtsVoice(audioState.selectedTtsProvider, audioState.selectedVoice);
    }

    async function loadVoiceOptions(ttsConfig, provider) {
        const providerName = provider || audioState.selectedTtsProvider || ttsConfig.default_provider || "edge";
        const defaultVoices = ttsConfig.default_voices || {};
        const selectedVoiceFromStorage = loadSavedTtsVoice(providerName);
        const defaultVoice = selectedVoiceFromStorage
            || defaultVoices[providerName]
            || "";
        audioState.selectedVoice = defaultVoice;
        audioState.selectedTtsProvider = providerName;

        if (DOM.ttsProviderSelect) {
            DOM.ttsProviderSelect.value = providerName;
        }

        DOM.ttsDetail.textContent = buildTtsDetail(
            findTtsProviderStatus(ttsConfig, providerName),
        );

        try {
            const payload = await requestJson(
                `/api/web/tts/voices?provider=${encodeURIComponent(providerName)}`,
            );
            renderVoiceOptions(payload.voices, defaultVoice, providerName);
        } catch (error) {
            console.error(error);
            DOM.voiceSelect.innerHTML = "";
            DOM.voiceSelect.disabled = true;
            DOM.ttsDetail.textContent = error.message || t("console.voiceListLoadFailed");
        }
    }

    function renderVoiceOptions(voices, selectedVoice, provider) {
        DOM.voiceSelect.innerHTML = "";

        if (!voices || voices.length === 0) {
            DOM.voiceSelect.disabled = true;
            DOM.ttsDetail.textContent = t("console.noVoices");
            return;
        }

        const preferredVoices = voices
            .slice()
            .sort((left, right) => {
                const leftScore = scoreVoiceOption(left);
                const rightScore = scoreVoiceOption(right);
                if (leftScore !== rightScore) {
                    return rightScore - leftScore;
                }
                return `${left.locale}-${left.short_name}`.localeCompare(`${right.locale}-${right.short_name}`);
            });

        preferredVoices.forEach((voice) => {
            const option = document.createElement("option");
            option.value = voice.short_name;
            option.textContent = buildVoiceLabel(voice);
            DOM.voiceSelect.appendChild(option);
        });

        const finalVoice = preferredVoices.some((item) => item.short_name === selectedVoice)
            ? selectedVoice
            : preferredVoices[0].short_name;

        DOM.voiceSelect.value = finalVoice;
        DOM.voiceSelect.disabled = false;
        audioState.selectedVoice = finalVoice;
        persistTtsVoice(provider, finalVoice);
    }

    function refreshLocalizedText() {
        const ttsConfig = appState.config && appState.config.tts;
        if (!ttsConfig) {
            if (DOM.ttsDetail) {
                DOM.ttsDetail.textContent = t("console.ttsLoading");
            }
            return;
        }
        const providerName = audioState.selectedTtsProvider
            || resolveInitialTtsProvider(ttsConfig);
        renderTtsProviderOptions(ttsConfig, providerName);
        if (DOM.ttsDetail) {
            DOM.ttsDetail.textContent = buildTtsDetail(
                findTtsProviderStatus(ttsConfig, providerName),
            );
        }
    }

    function buildVoiceLabel(voice) {
        const primaryName = voice.display_name || voice.short_name || voice.name;
        const parts = [primaryName];
        if (voice.short_name && voice.short_name !== primaryName) {
            parts.push(voice.short_name);
        }
        if (voice.locale) {
            parts.push(voice.locale);
        }
        if (voice.gender) {
            parts.push(voice.gender);
        }
        return parts.join(" · ");
    }

    function scoreVoiceOption(voice) {
        let score = 0;
        if ((voice.locale || "").startsWith("zh-CN")) {
            score += 30;
        } else if ((voice.locale || "").startsWith("zh-")) {
            score += 20;
        }
        if ((voice.short_name || "").includes("Xiaoxiao")) {
            score += 8;
        }
        if ((voice.short_name || "").includes("Neural")) {
            score += 4;
        }
        return score;
    }

    return {
        handleTtsProviderChange: handleTtsProviderChange,
        handleVoiceSelectionChange: handleVoiceSelectionChange,
        loadTtsOptions: loadTtsOptions,
        refreshLocalizedText: refreshLocalizedText,
    };
}
