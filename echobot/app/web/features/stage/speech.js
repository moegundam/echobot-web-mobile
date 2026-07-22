import { synthesizeStageTts } from "./api.js";


export function createStageSpeechController({
    audioButton,
    i18n,
    getContext,
    getSessionName,
    onStatus,
    live2d,
}) {
    let audioUnlocked = false;
    let audioElement = null;
    let activeAudioUrl = "";
    let audioContext = null;
    let audioSourceNode = null;
    let audioAnalyser = null;
    let volumeBuffer = null;
    let lipSyncFrameId = 0;
    let currentMouthValue = 0;
    let playbackToken = 0;

    function updateAudioButtonText() {
        if (!audioButton) {
            return;
        }
        audioButton.textContent = i18n.t(
            audioUnlocked ? "stage.audio.enabled" : "stage.audio.enable",
        );
    }

    function bind() {
        audioButton?.addEventListener("click", async () => {
            audioUnlocked = true;
            audioButton.disabled = true;
            updateAudioButtonText();
            await ensureAudioContextReady();
            onStatus("stage.status.audioReady");
            await stopCurrentAudio();
        });
    }

    async function playTts(text) {
        const spokenText = String(text || "").trim();
        if (!spokenText) {
            return;
        }
        const currentPlaybackToken = ++playbackToken;
        const playbackSessionName = getSessionName();

        try {
            onStatus("stage.status.tts");
            const audioBlob = await synthesizeStageTts(stageTtsRequestBody(spokenText));
            if (
                currentPlaybackToken !== playbackToken
                || playbackSessionName !== getSessionName()
            ) {
                return;
            }
            await stopCurrentAudio();
            if (!audioUnlocked) {
                onStatus("stage.status.tapAudio");
            }
            if (await canUseAudioContext()) {
                await playBlobWithAudioContext(audioBlob, currentPlaybackToken, playbackSessionName);
            } else {
                await playBlobWithHtmlAudio(audioBlob, currentPlaybackToken, playbackSessionName);
            }
            if (
                currentPlaybackToken !== playbackToken
                || playbackSessionName !== getSessionName()
            ) {
                return;
            }
            audioUnlocked = true;
            updateAudioButtonText();
        } catch (error) {
            console.warn("TTS playback failed", error);
            if (
                currentPlaybackToken !== playbackToken
                || playbackSessionName !== getSessionName()
            ) {
                return;
            }
            onStatus(audioUnlocked ? "stage.status.ttsFailed" : "stage.status.tapAudio");
            if (audioButton && !audioUnlocked) {
                audioButton.disabled = false;
                updateAudioButtonText();
            }
        }
    }

    function stageTtsRequestBody(text) {
        const body = { text };
        const context = getContext();
        const voiceProfile = context && typeof context.voice_profile === "object"
            ? context.voice_profile
            : {};
        const tts = voiceProfile.tts && typeof voiceProfile.tts === "object"
            ? voiceProfile.tts
            : {};
        const provider = String(tts.provider || "").trim();
        const voice = String(tts.voice || "").trim();
        if (provider) {
            body.provider = provider;
        }
        if (voice) {
            body.voice = voice;
        }
        return body;
    }

    async function stopCurrentAudio() {
        if (audioSourceNode) {
            try {
                audioSourceNode.stop();
            } catch (_error) {
                // Source nodes can only be stopped once.
            }
            try {
                audioSourceNode.disconnect();
            } catch (_error) {
                // Already disconnected.
            }
            audioSourceNode = null;
        }
        if (audioAnalyser) {
            try {
                audioAnalyser.disconnect();
            } catch (_error) {
                // Already disconnected.
            }
            audioAnalyser = null;
        }
        volumeBuffer = null;
        stopLipSyncLoop();

        if (audioElement) {
            audioElement.pause();
            audioElement.removeAttribute("src");
            audioElement.load();
            audioElement = null;
        }
        if (activeAudioUrl) {
            URL.revokeObjectURL(activeAudioUrl);
            activeAudioUrl = "";
        }
        live2d.applyMouthValue(0);
    }

    async function cancelPlayback() {
        playbackToken += 1;
        await stopCurrentAudio();
    }

    async function playBlobWithHtmlAudio(audioBlob, currentPlaybackToken, playbackSessionName) {
        activeAudioUrl = URL.createObjectURL(audioBlob);
        const currentAudioElement = new Audio(activeAudioUrl);
        audioElement = currentAudioElement;
        currentAudioElement.addEventListener("ended", () => {
            if (
                currentPlaybackToken === playbackToken
                && playbackSessionName === getSessionName()
                && audioElement === currentAudioElement
            ) {
                onStatus("stage.status.live");
            }
        }, { once: true });
        currentAudioElement.addEventListener("error", () => {
            if (
                currentPlaybackToken === playbackToken
                && playbackSessionName === getSessionName()
                && audioElement === currentAudioElement
            ) {
                onStatus("stage.status.audioError");
            }
        }, { once: true });
        await currentAudioElement.play();
    }

    async function playBlobWithAudioContext(audioBlob, currentPlaybackToken, playbackSessionName) {
        const context = await ensureAudioContextReady();
        if (!context) {
            await playBlobWithHtmlAudio(audioBlob, currentPlaybackToken, playbackSessionName);
            return;
        }

        const arrayBuffer = await audioBlob.arrayBuffer();
        const audioBuffer = await context.decodeAudioData(arrayBuffer.slice(0));
        const sourceNode = context.createBufferSource();
        const analyserNode = context.createAnalyser();
        analyserNode.fftSize = 1024;
        sourceNode.buffer = audioBuffer;
        sourceNode.connect(analyserNode);
        analyserNode.connect(context.destination);

        audioSourceNode = sourceNode;
        audioAnalyser = analyserNode;
        volumeBuffer = new Uint8Array(analyserNode.fftSize);
        const playbackEnded = new Promise((resolve) => {
            sourceNode.onended = resolve;
        });
        startLipSyncLoop();
        sourceNode.start(0);
        await playbackEnded;
        if (
            currentPlaybackToken !== playbackToken
            || playbackSessionName !== getSessionName()
            || audioSourceNode !== sourceNode
        ) {
            return;
        }
        await stopCurrentAudio();
        onStatus("stage.status.live");
    }

    async function canUseAudioContext() {
        if (!window.AudioContext && !window.webkitAudioContext) {
            return false;
        }
        try {
            return Boolean(await ensureAudioContextReady());
        } catch (error) {
            console.warn("AudioContext unavailable", error);
            return false;
        }
    }

    async function ensureAudioContextReady() {
        if (!window.AudioContext && !window.webkitAudioContext) {
            return null;
        }
        if (!audioContext) {
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            audioContext = new AudioContextClass();
        }
        if (audioContext.state === "suspended") {
            await audioContext.resume();
        }
        return audioContext;
    }

    function startLipSyncLoop() {
        if (!audioAnalyser || !volumeBuffer) {
            return;
        }

        const updateFrame = () => {
            if (!audioAnalyser || !volumeBuffer) {
                return;
            }

            audioAnalyser.getByteTimeDomainData(volumeBuffer);
            let total = 0;
            for (let index = 0; index < volumeBuffer.length; index += 1) {
                const sample = (volumeBuffer[index] - 128) / 128;
                total += sample * sample;
            }

            const rms = Math.sqrt(total / volumeBuffer.length);
            const scaledValue = clamp((rms - 0.02) * 5.4, 0, 1);
            currentMouthValue = smoothValue(currentMouthValue, scaledValue, 0.38);
            live2d.applyMouthValue(currentMouthValue);
            lipSyncFrameId = window.requestAnimationFrame(updateFrame);
        };

        stopLipSyncLoop();
        lipSyncFrameId = window.requestAnimationFrame(updateFrame);
    }

    function stopLipSyncLoop() {
        if (lipSyncFrameId) {
            window.cancelAnimationFrame(lipSyncFrameId);
            lipSyncFrameId = 0;
        }
        currentMouthValue = 0;
    }

    return {
        bind,
        cancelPlayback,
        getAudioUnlocked: () => audioUnlocked,
        playTts,
        refreshLocalizedText: updateAudioButtonText,
        stopCurrentAudio,
    };
}


function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}


function smoothValue(previousValue, nextValue, factor) {
    return previousValue + (nextValue - previousValue) * factor;
}
