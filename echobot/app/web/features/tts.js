import { createTtsOptionsController } from "./tts/options.js?v=site-public-7";
import { createTtsPlaybackController } from "./tts/playback.js?v=site-public-6";

export function createTtsModule(deps) {
    let hooks = {
        syncAlwaysListenPauseState() {},
        updateVoiceInputControls() {},
    };

    const options = createTtsOptionsController({
        requestJson: deps.requestJson,
        t: deps.t,
    });
    const playback = createTtsPlaybackController({
        addMessage: deps.addMessage,
        applyMouthValue: deps.applyMouthValue,
        clamp: deps.clamp,
        getHooks: () => hooks,
        responseToError: deps.responseToError,
        setConnectionState: deps.setConnectionState,
        setRunStatus: deps.setRunStatus,
        smoothValue: deps.smoothValue,
        t: deps.t,
    });

    function bindHooks(nextHooks) {
        hooks = {
            ...hooks,
            ...(nextHooks || {}),
        };
    }

    return {
        applyRuntimeVoiceProfile: options.applyRuntimeVoiceProfile,
        bindHooks: bindHooks,
        createSpeechSession: playback.createSpeechSession,
        ensureAudioContextReady: playback.ensureAudioContextReady,
        finalizeSpeechSession: playback.finalizeSpeechSession,
        handleTtsProviderChange: options.handleTtsProviderChange,
        handleVoiceSelectionChange: options.handleVoiceSelectionChange,
        loadTtsOptions: options.loadTtsOptions,
        queueSpeechSessionText: playback.queueSpeechSessionText,
        refreshLocalizedText: options.refreshLocalizedText,
        speakText: playback.speakText,
        stopSpeechPlayback: playback.stopSpeechPlayback,
    };
}
