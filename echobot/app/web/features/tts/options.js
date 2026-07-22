import { DOM } from "../../core/dom.js";
import { appState, audioState } from "../../core/store.js";

const VOICE_SEARCH_INPUT_ID = "voice-search";

export function createTtsOptionsController(deps) {
    const { requestJson } = deps;
    const t = typeof deps.t === "function" ? deps.t : (key, params = {}) => {
        return String(key).replace(/\{([A-Za-z0-9_]+)\}/g, (_match, name) => {
            return Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : "";
        });
    };
    let availableVoices = [];
    let availableVoicesProvider = "";
    const voiceSearchInput = DOM.voiceSearch
        || document.getElementById(VOICE_SEARCH_INPUT_ID);

    bindVoiceSearch();

    function bindVoiceSearch() {
        if (!voiceSearchInput || voiceSearchInput.dataset.bound === "true") {
            return;
        }
        voiceSearchInput.dataset.bound = "true";
        voiceSearchInput.addEventListener("input", () => {
            renderVoiceOptions(
                availableVoices,
                audioState.selectedVoice,
                availableVoicesProvider || audioState.selectedTtsProvider,
                false,
                voiceSearchInput.value,
            );
        });
    }

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
        if (!DOM.voiceSelect.value) {
            return;
        }
        audioState.selectedVoice = DOM.voiceSelect.value;
        persistTtsVoice(audioState.selectedTtsProvider, audioState.selectedVoice);
    }

    async function applyRuntimeVoiceProfile(voiceProfile) {
        if (!appState.config || !appState.config.tts) {
            return;
        }
        const ttsProfile = voiceProfile && typeof voiceProfile.tts === "object"
            ? voiceProfile.tts
            : {};
        const provider = String(ttsProfile.provider || "").trim();
        if (!provider || !findTtsProviderStatus(appState.config.tts, provider)) {
            return;
        }
        audioState.selectedTtsProvider = provider;
        renderTtsProviderOptions(appState.config.tts, provider);
        await loadVoiceOptions(appState.config.tts, provider, {
            persistSelection: false,
            preferredVoice: String(ttsProfile.voice || "").trim(),
        });
    }

    async function loadVoiceOptions(ttsConfig, provider, options = {}) {
        const providerName = provider || audioState.selectedTtsProvider || ttsConfig.default_provider || "edge";
        if (availableVoicesProvider && availableVoicesProvider !== providerName && voiceSearchInput) {
            voiceSearchInput.value = "";
        }
        const defaultVoices = ttsConfig.default_voices || {};
        const selectedVoiceFromStorage = loadSavedTtsVoice(providerName);
        const defaultVoice = String(options.preferredVoice || "").trim()
            || selectedVoiceFromStorage
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
            renderVoiceOptions(
                payload.voices,
                defaultVoice,
                providerName,
                options.persistSelection !== false,
            );
        } catch (error) {
            console.error(error);
            DOM.voiceSelect.innerHTML = "";
            DOM.voiceSelect.disabled = true;
            DOM.ttsDetail.textContent = error.message || t("console.voiceListLoadFailed");
        }
    }

    function renderVoiceOptions(
        voices,
        selectedVoice,
        provider,
        persistSelection = true,
        searchQuery = voiceSearchInput?.value,
    ) {
        availableVoices = Array.isArray(voices) ? [...voices] : [];
        availableVoicesProvider = String(provider || "").trim();
        const normalizedQuery = normalizeVoiceSearchText(searchQuery);
        DOM.voiceSelect.innerHTML = "";

        if (availableVoices.length === 0) {
            DOM.voiceSelect.disabled = true;
            DOM.ttsDetail.textContent = t("console.noVoices");
            renderVoiceSearchStatus(0, false);
            return;
        }

        const preferredVoices = availableVoices
            .slice()
            .sort((left, right) => {
                const leftScore = scoreVoiceOption(left);
                const rightScore = scoreVoiceOption(right);
                if (leftScore !== rightScore) {
                    return rightScore - leftScore;
                }
                return `${left.locale}-${left.short_name}`.localeCompare(`${right.locale}-${right.short_name}`);
            });
        const visibleVoices = normalizedQuery
            ? preferredVoices.filter((voice) => voiceSearchText(voice).includes(normalizedQuery))
            : preferredVoices;

        if (visibleVoices.length === 0) {
            const option = document.createElement("option");
            option.value = "";
            option.textContent = t("console.voiceSearchNoMatches");
            DOM.voiceSelect.appendChild(option);
            DOM.voiceSelect.disabled = true;
            renderVoiceSearchStatus(0, true);
            return;
        }

        visibleVoices.forEach((voice) => {
            const option = document.createElement("option");
            option.value = voice.short_name;
            option.textContent = buildVoiceLabel(voice);
            DOM.voiceSelect.appendChild(option);
        });

        const finalVoice = visibleVoices.some((item) => item.short_name === selectedVoice)
            ? selectedVoice
            : (normalizedQuery ? "" : visibleVoices[0].short_name);

        if (finalVoice) {
            DOM.voiceSelect.value = finalVoice;
        } else {
            const placeholder = document.createElement("option");
            placeholder.value = "";
            placeholder.disabled = true;
            placeholder.textContent = t("console.voiceSearchCount", { count: visibleVoices.length });
            DOM.voiceSelect.prepend(placeholder);
            DOM.voiceSelect.value = "";
        }
        DOM.voiceSelect.disabled = false;
        if (finalVoice) {
            audioState.selectedVoice = finalVoice;
        }
        if (persistSelection && finalVoice) {
            persistTtsVoice(provider, finalVoice);
        }
        renderVoiceSearchStatus(visibleVoices.length, Boolean(normalizedQuery));
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
        if (availableVoices.length > 0) {
            renderVoiceOptions(
                availableVoices,
                audioState.selectedVoice,
                availableVoicesProvider || providerName,
                false,
                voiceSearchInput?.value,
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

    function voiceSearchText(voice) {
        return normalizeVoiceSearchText([
            voice && voice.display_name,
            voice && voice.short_name,
            voice && voice.name,
            voice && voice.locale,
            voice && voice.gender,
        ].filter(Boolean).join(" "));
    }

    function normalizeVoiceSearchText(value) {
        return String(value || "").trim().toLocaleLowerCase();
    }

    function renderVoiceSearchStatus(count, filtered) {
        if (!DOM.voiceSearchStatus) {
            return;
        }
        DOM.voiceSearchStatus.textContent = filtered && count === 0
            ? t("console.voiceSearchNoMatches")
            : t("console.voiceSearchCount", { count });
    }

    return {
        applyRuntimeVoiceProfile: applyRuntimeVoiceProfile,
        handleTtsProviderChange: handleTtsProviderChange,
        handleVoiceSelectionChange: handleVoiceSelectionChange,
        loadTtsOptions: loadTtsOptions,
        refreshLocalizedText: refreshLocalizedText,
    };
}
