import { DOM } from "../core/dom.js";
import {
    ASR_STATUS_POLL_INTERVAL_MS,
    asrState,
    audioState,
    chatState,
} from "../core/store.js";
import { buildWavBlob, createAsrAudioCaptureController } from "./asr/audio.js?v=site-public-6";
import { findAsrProviderStatus, normalizeAsrConfig } from "./asr/config.js";
import { createVoicePromptQueue } from "./asr/prompts.js?v=site-public-6";
import { createRealtimeAsrClient } from "./asr/realtime.js?v=site-public-6";

export function createAsrModule(deps) {
    const {
        addSystemMessage,
        clamp,
        ensureAudioContextReady,
        requestJson,
        responseToError,
        setRunStatus,
        stopSpeechPlayback,
        t = (key) => key,
    } = deps;

    const promptQueue = createVoicePromptQueue({
        setRunStatus: setRunStatus,
        t: t,
    });
    const audioCapture = createAsrAudioCaptureController({
        clamp: clamp,
        ensureAudioContextReady: ensureAudioContextReady,
        getTargetSampleRate: currentSampleRate,
        onChunk: handleCapturedPcmChunk,
        t: t,
    });
    const realtimeClient = createRealtimeAsrClient({
        onEvent: handleRealtimeEvent,
        onUnexpectedClose: handleUnexpectedSocketClose,
        t: t,
    });

    function applyAsrStatus(asrConfig) {
        asrState.asrConfig = normalizeAsrConfig(asrConfig);
        renderAsrProviderOptions(asrState.asrConfig);
        if (DOM.asrDetail) {
            DOM.asrDetail.textContent = buildAsrDetailText();
        }
        updateVoiceInputControls();
        if (!shouldPollAsrStatus(asrState.asrConfig)) {
            stopAsrStatusPolling();
        }
    }

    function startAsrStatusPolling() {
        if (asrState.asrStatusPollTimerId || !shouldPollAsrStatus(asrState.asrConfig)) {
            return;
        }

        asrState.asrStatusPollTimerId = window.setInterval(() => {
            void refreshAsrStatus();
        }, ASR_STATUS_POLL_INTERVAL_MS);
    }

    function updateVoiceInputControls() {
        const asrReady = Boolean(asrState.asrConfig && asrState.asrConfig.available);
        const manualRecording = asrState.microphoneCaptureMode === "manual";
        const backgroundJobRunning = Boolean(chatState.activeChatJobId);

        if (DOM.recordButton) {
            DOM.recordButton.disabled = !manualRecording && (
                !asrReady
                || asrState.alwaysListenEnabled
                || chatState.chatBusy
            );
            DOM.recordButton.classList.toggle("is-recording", manualRecording);
            DOM.recordButton.setAttribute("aria-pressed", manualRecording ? "true" : "false");
            const recordLabel = manualRecording
                ? t("console.stopRecording")
                : t("console.startRecording");
            DOM.recordButton.setAttribute("title", recordLabel);
            DOM.recordButton.setAttribute("aria-label", recordLabel);
        }

        if (DOM.alwaysListenCheckbox) {
            DOM.alwaysListenCheckbox.checked = asrState.alwaysListenEnabled;
            DOM.alwaysListenCheckbox.disabled = !asrReady
                || !(asrState.asrConfig && asrState.asrConfig.always_listen_supported)
                || manualRecording
                || (backgroundJobRunning && !asrState.alwaysListenEnabled);
        }

        if (DOM.asrProviderSelect) {
            const providerCount = asrState.asrConfig && Array.isArray(asrState.asrConfig.asr_providers)
                ? asrState.asrConfig.asr_providers.length
                : 0;
            DOM.asrProviderSelect.disabled = providerCount <= 1
                || manualRecording
                || asrState.asrProviderUpdating;
        }

        if (DOM.asrDetail) {
            DOM.asrDetail.textContent = buildAsrDetailText();
        }
    }

    async function handleAsrProviderChange() {
        if (!DOM.asrProviderSelect || !asrState.asrConfig) {
            return;
        }

        const nextProvider = String(DOM.asrProviderSelect.value || "").trim();
        const currentProvider = String(asrState.asrConfig.selected_asr_provider || "").trim();
        if (!nextProvider || nextProvider === currentProvider) {
            DOM.asrProviderSelect.value = currentProvider;
            return;
        }

        if (asrState.microphoneCaptureMode === "manual") {
            DOM.asrProviderSelect.value = currentProvider;
            addSystemMessage(t("console.stopRecordingBeforeAsrSwitch"));
            return;
        }

        if (asrState.alwaysListenEnabled) {
            if (DOM.alwaysListenCheckbox) {
                DOM.alwaysListenCheckbox.checked = false;
            }
            await stopAlwaysListen();
        }

        asrState.asrProviderUpdating = true;
        updateVoiceInputControls();
        setRunStatus(t("console.switchingAsrProvider"));

        try {
            const payload = await requestJson("/api/web/asr/provider", {
                method: "PATCH",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    provider: nextProvider,
                }),
            });
            applyAsrStatus(payload);
            const providerStatus = findAsrProviderStatus(payload, nextProvider);
            setRunStatus(
                providerStatus && providerStatus.available
                    ? t("console.providerEnabled", { provider: providerStatus.label })
                    : t("console.asrProviderWaiting"),
            );
        } catch (error) {
            console.error(error);
            DOM.asrProviderSelect.value = currentProvider;
            addSystemMessage(`${t("console.asrProviderSwitchFailed")}: ${error.message || error}`);
            setRunStatus(error.message || t("console.asrProviderSwitchFailed"));
        } finally {
            asrState.asrProviderUpdating = false;
            updateVoiceInputControls();
        }
    }

    async function handleRecordButtonClick() {
        if (asrState.microphoneCaptureMode === "manual") {
            await stopManualRecording();
            return;
        }

        try {
            await startManualRecording();
        } catch (error) {
            console.error(error);
            asrState.microphoneCaptureMode = "idle";
            asrState.manualRecordingChunks = [];
            audioCapture.stopMicrophoneCapture();
            updateVoiceInputControls();
            const message = voiceInputErrorMessage(error);
            addSystemMessage(`${t("console.recordingStartFailed")}: ${message}`);
            setRunStatus(message);
        }
    }

    async function handleAlwaysListenToggle() {
        if (!DOM.alwaysListenCheckbox) {
            return;
        }

        if (DOM.alwaysListenCheckbox.checked) {
            try {
                await startAlwaysListen();
            } catch (error) {
                console.error(error);
                DOM.alwaysListenCheckbox.checked = false;
                asrState.alwaysListenEnabled = false;
                asrState.microphoneCaptureMode = "idle";
                updateVoiceInputControls();
                addSystemMessage(`${t("console.alwaysListenStartFailed")}: ${error.message || error}`);
            }
            return;
        }

        await stopAlwaysListen();
    }

    function handleBeforeUnload() {
        void realtimeClient.close();
        audioCapture.stopMicrophoneCapture();
    }

    async function handlePageHidden() {
        if (document.visibilityState && document.visibilityState !== "hidden") {
            return;
        }
        await stopVoiceInputForPageHide();
    }

    return {
        applyAsrStatus: applyAsrStatus,
        drainVoicePromptQueue: promptQueue.drainVoicePromptQueue,
        handleAlwaysListenToggle: handleAlwaysListenToggle,
        handleAsrProviderChange: handleAsrProviderChange,
        handleBeforeUnload: handleBeforeUnload,
        handlePageHidden: handlePageHidden,
        handleRecordButtonClick: handleRecordButtonClick,
        refreshLocalizedText: updateVoiceInputControls,
        syncAlwaysListenPauseState: syncAlwaysListenPauseState,
        startAsrStatusPolling: startAsrStatusPolling,
        updateVoiceInputControls: updateVoiceInputControls,
    };

    function renderAsrProviderOptions(asrConfig) {
        if (!DOM.asrProviderSelect) {
            return;
        }

        DOM.asrProviderSelect.innerHTML = "";
        const providers = Array.isArray(asrConfig && asrConfig.asr_providers)
            ? asrConfig.asr_providers
            : [];

        providers.forEach((providerStatus) => {
            const option = document.createElement("option");
            option.value = providerStatus.name;
            option.textContent = providerStatus.available
                ? providerStatus.label
                : t("console.providerNotReady", { provider: providerStatus.label });
            DOM.asrProviderSelect.appendChild(option);
        });

        DOM.asrProviderSelect.disabled = providers.length <= 1 || asrState.asrProviderUpdating;
        if (asrConfig && asrConfig.selected_asr_provider) {
            DOM.asrProviderSelect.value = asrConfig.selected_asr_provider;
        }
    }

    function shouldPollAsrStatus(asrConfig) {
        if (!asrConfig) {
            return true;
        }
        if (!asrConfig.available) {
            return true;
        }
        return Boolean(
            asrConfig.selected_vad_provider
            && !asrConfig.always_listen_supported,
        );
    }

    function buildAsrDetailText() {
        if (asrState.microphoneCaptureMode === "manual") {
            return t("console.asrRecording");
        }
        if (asrState.alwaysListenEnabled) {
            return asrState.alwaysListenPaused
                ? t("console.alwaysListenPaused")
                : t("console.alwaysListenWaiting");
        }
        if (!asrState.asrConfig) {
            return t("console.asrNotInitialized");
        }
        return asrState.asrConfig.detail || t("console.asrNotReady");
    }

    function stopAsrStatusPolling() {
        if (!asrState.asrStatusPollTimerId) {
            return;
        }
        window.clearInterval(asrState.asrStatusPollTimerId);
        asrState.asrStatusPollTimerId = 0;
    }

    async function refreshAsrStatus() {
        try {
            applyAsrStatus(await requestJson("/api/web/asr/status"));
        } catch (error) {
            console.error("Failed to refresh ASR status", error);
            if (DOM.asrDetail && !asrState.asrConfig) {
                DOM.asrDetail.textContent = error.message || t("console.asrStatusFailed");
            }
        }
    }

    async function startManualRecording() {
        if (!asrState.asrConfig || !asrState.asrConfig.available) {
            addSystemMessage(t("console.asrNotReadyYet"));
            return;
        }
        if (chatState.chatBusy) {
            addSystemMessage(t("console.waitReplyBeforeRecording"));
            return;
        }
        if (asrState.alwaysListenEnabled) {
            if (DOM.alwaysListenCheckbox) {
                DOM.alwaysListenCheckbox.checked = false;
            }
            await stopAlwaysListen();
        }

        if (audioState.activeSpeechSession || audioState.audioSourceNode || audioState.speaking) {
            stopSpeechPlayback();
        }
        await audioCapture.ensureMicrophoneCaptureReady();
        asrState.manualRecordingChunks = [];
        asrState.microphoneCaptureMode = "manual";
        updateVoiceInputControls();
        setRunStatus(t("console.recording"));
    }

    async function stopManualRecording() {
        if (asrState.microphoneCaptureMode !== "manual") {
            return;
        }

        asrState.microphoneCaptureMode = "idle";
        updateVoiceInputControls();
        const wavBlob = buildWavBlob(asrState.manualRecordingChunks, currentSampleRate());
        asrState.manualRecordingChunks = [];
        audioCapture.stopMicrophoneCapture();

        if (!wavBlob) {
            setRunStatus(t("console.noValidSpeech"));
            addSystemMessage(t("console.noValidSpeech"));
            return;
        }

        try {
            await transcribeAndQueueWavBlob(wavBlob);
        } catch (error) {
            console.error(error);
            addSystemMessage(`${t("console.asrFailed")}: ${error.message || error}`);
            setRunStatus(error.message || t("console.asrFailed"));
        }
    }

    async function startAlwaysListen() {
        if (!asrState.asrConfig || !asrState.asrConfig.available) {
            throw new Error(t("console.asrNotReadyYet"));
        }
        if (!asrState.asrConfig.always_listen_supported) {
            throw new Error(t("console.alwaysListenUnsupported"));
        }
        if (asrState.microphoneCaptureMode === "manual") {
            await stopManualRecording();
        }

        try {
            await audioCapture.ensureMicrophoneCaptureReady();
            await realtimeClient.open();
        } catch (error) {
            audioCapture.stopMicrophoneCapture();
            throw error;
        }

        asrState.alwaysListenEnabled = true;
        asrState.alwaysListenPaused = chatState.chatBusy || audioState.speaking;
        asrState.microphoneCaptureMode = "always";
        updateVoiceInputControls();
        setRunStatus(
            asrState.alwaysListenPaused
                ? t("console.alwaysListenPaused")
                : t("console.alwaysListenEnabled"),
        );
    }

    async function stopAlwaysListen(options = {}) {
        const flushFirst = options.flushFirst !== false;
        asrState.alwaysListenEnabled = false;
        asrState.alwaysListenPaused = false;
        asrState.microphoneCaptureMode = "idle";
        updateVoiceInputControls();

        await realtimeClient.close({ flushFirst });
        audioCapture.stopMicrophoneCapture();
        setRunStatus(t("console.alwaysListenStopped"));
    }

    function handleCapturedPcmChunk(pcmChunk) {
        if (asrState.microphoneCaptureMode === "manual") {
            asrState.manualRecordingChunks.push(pcmChunk);
            return;
        }

        if (!asrState.alwaysListenEnabled || asrState.microphoneCaptureMode !== "always") {
            return;
        }

        syncAlwaysListenPauseState();
        if (asrState.alwaysListenPaused) {
            return;
        }

        realtimeClient.sendChunk(pcmChunk);
    }

    function syncAlwaysListenPauseState() {
        if (!asrState.alwaysListenEnabled || asrState.microphoneCaptureMode !== "always") {
            return;
        }

        const shouldPause = chatState.chatBusy || audioState.speaking;
        if (shouldPause && !asrState.alwaysListenPaused) {
            asrState.alwaysListenPaused = true;
            realtimeClient.sendControl("reset");
            updateVoiceInputControls();
            return;
        }

        if (!shouldPause && asrState.alwaysListenPaused) {
            asrState.alwaysListenPaused = false;
            updateVoiceInputControls();
            setRunStatus(t("console.alwaysListenEnabled"));
        }
    }

    async function stopVoiceInputForPageHide() {
        if (asrState.alwaysListenEnabled) {
            await stopAlwaysListen({ flushFirst: false });
            return;
        }

        if (asrState.microphoneCaptureMode !== "manual") {
            return;
        }

        asrState.microphoneCaptureMode = "idle";
        asrState.manualRecordingChunks = [];
        audioCapture.stopMicrophoneCapture();
        updateVoiceInputControls();
        setRunStatus(t("console.pageHiddenRecordingStopped"));
    }

    async function transcribeAndQueueWavBlob(wavBlob) {
        setRunStatus(t("console.transcribingSpeech"));
        const response = await fetch("/api/web/asr", {
            method: "POST",
            headers: {
                "Content-Type": "audio/wav",
            },
            body: wavBlob,
        });

        if (!response.ok) {
            throw await responseToError(response);
        }

        const payload = await response.json();
        const text = String((payload && payload.text) || "").trim();
        if (!text) {
            addSystemMessage(t("console.noClearSpeech"));
            setRunStatus(t("console.noClearSpeech"));
            return;
        }

        promptQueue.enqueueVoicePrompt(text, t("console.recordingSource"));
    }

    function handleRealtimeEvent(payload) {
        if (payload.type === "ready") {
            if (asrState.asrConfig) {
                applyAsrStatus({
                    ...asrState.asrConfig,
                    available: true,
                    sample_rate: Number(payload.sample_rate) || asrState.asrConfig.sample_rate,
                    state: String(payload.state || "ready"),
                    detail: String(payload.detail || asrState.asrConfig.detail || ""),
                });
            }
            return;
        }
        if (payload.type === "speech_start") {
            setRunStatus(t("console.listening"));
            return;
        }
        if (payload.type === "speech_end") {
            setRunStatus(t("console.transcribingSpeech"));
            return;
        }
        if (payload.type === "transcript") {
            promptQueue.enqueueVoicePrompt(payload.text, t("console.voiceSource"));
            return;
        }
        if (payload.type === "error") {
            addSystemMessage(`${t("console.realtimeAsrFailed")}: ${payload.message || t("console.unknownError")}`);
        }
    }

    function handleUnexpectedSocketClose() {
        if (!asrState.alwaysListenEnabled) {
            return;
        }

        asrState.alwaysListenEnabled = false;
        asrState.alwaysListenPaused = false;
        asrState.microphoneCaptureMode = "idle";
        if (DOM.alwaysListenCheckbox) {
            DOM.alwaysListenCheckbox.checked = false;
        }
        audioCapture.stopMicrophoneCapture();
        updateVoiceInputControls();
        addSystemMessage(t("console.realtimeAsrDisconnected"));
    }

    function currentSampleRate() {
        const sampleRate = Number(asrState.asrConfig && asrState.asrConfig.sample_rate);
        return sampleRate > 0 ? sampleRate : 16000;
    }

    function voiceInputErrorMessage(error) {
        const rawMessage = String((error && error.message) || error || "").trim();
        const errorName = String((error && error.name) || "").trim();
        if (errorName === "NotAllowedError" || /permission|denied|notallowed/i.test(rawMessage)) {
            return t("console.microphonePermissionDenied");
        }
        if (errorName === "NotFoundError" || /notfound|device/i.test(rawMessage)) {
            return t("console.microphoneNotFound");
        }
        if (/AudioWorklet/i.test(rawMessage)) {
            return t("console.audioWorkletUnsupported");
        }
        if (/Web Audio/i.test(rawMessage)) {
            return t("console.webAudioUnsupported");
        }
        return rawMessage || t("console.microphoneStartFailed");
    }
}
