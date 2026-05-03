import { asrState, audioState } from "../../core/store.js";

export function createAsrAudioCaptureController(deps) {
    const {
        clamp,
        ensureAudioContextReady,
        getTargetSampleRate,
        onChunk,
        t = (key) => key,
    } = deps;

    async function ensureMicrophoneCaptureReady() {
        const targetSampleRate = resolveTargetSampleRate();
        if (asrState.microphoneStream && asrState.microphoneProcessorNode) {
            refreshResampler(targetSampleRate);
            return;
        }
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error(t("console.microphoneCaptureUnsupported"));
        }

        await ensureAudioContextReady();
        if (!audioState.audioContext) {
            throw new Error(t("console.webAudioUnsupported"));
        }
        if (!audioState.audioContext.audioWorklet || typeof AudioWorkletNode === "undefined") {
            throw new Error(t("console.audioWorkletUnsupported"));
        }

        if (!asrState.microphoneWorkletLoaded) {
            await audioState.audioContext.audioWorklet.addModule("/web/assets/pcm-recorder-worklet.js");
            asrState.microphoneWorkletLoaded = true;
        }

        const stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            },
        });

        const sourceNode = audioState.audioContext.createMediaStreamSource(stream);
        const processorNode = new AudioWorkletNode(
            audioState.audioContext,
            "pcm-recorder-processor",
        );
        const muteNode = audioState.audioContext.createGain();
        muteNode.gain.value = 0;

        processorNode.port.onmessage = handleMicrophoneChunk;
        sourceNode.connect(processorNode);
        processorNode.connect(muteNode);
        muteNode.connect(audioState.audioContext.destination);

        asrState.microphoneStream = stream;
        asrState.microphoneSourceNode = sourceNode;
        asrState.microphoneProcessorNode = processorNode;
        asrState.microphoneMuteNode = muteNode;
        refreshResampler(targetSampleRate);
    }

    function stopMicrophoneCapture() {
        if (asrState.microphoneSourceNode) {
            try {
                asrState.microphoneSourceNode.disconnect();
            } catch (error) {
                console.warn("Microphone source disconnect ignored", error);
            }
        }
        if (asrState.microphoneProcessorNode) {
            try {
                asrState.microphoneProcessorNode.port.onmessage = null;
                asrState.microphoneProcessorNode.disconnect();
            } catch (error) {
                console.warn("Microphone processor disconnect ignored", error);
            }
        }
        if (asrState.microphoneMuteNode) {
            try {
                asrState.microphoneMuteNode.disconnect();
            } catch (error) {
                console.warn("Microphone mute disconnect ignored", error);
            }
        }
        if (asrState.microphoneStream) {
            asrState.microphoneStream.getTracks().forEach((track) => {
                track.stop();
            });
        }

        asrState.microphoneStream = null;
        asrState.microphoneSourceNode = null;
        asrState.microphoneProcessorNode = null;
        asrState.microphoneMuteNode = null;
        asrState.microphoneChunkResampler = null;
        if (asrState.microphoneCaptureMode !== "always") {
            asrState.microphoneCaptureMode = "idle";
        }
    }

    function handleMicrophoneChunk(event) {
        const rawChunk = event && event.data ? event.data : null;
        if (!(rawChunk instanceof Float32Array) || !asrState.microphoneChunkResampler) {
            return;
        }

        const pcmChunk = asrState.microphoneChunkResampler.push(rawChunk);
        if (!pcmChunk.length) {
            return;
        }

        onChunk(pcmChunk);
    }

    function refreshResampler(targetSampleRate) {
        if (!audioState.audioContext) {
            return;
        }

        if (
            asrState.microphoneChunkResampler
            && asrState.microphoneChunkResampler.inputSampleRate === audioState.audioContext.sampleRate
            && asrState.microphoneChunkResampler.outputSampleRate === targetSampleRate
        ) {
            return;
        }

        asrState.microphoneChunkResampler = new PcmChunkResampler(
            audioState.audioContext.sampleRate,
            targetSampleRate,
            clamp,
        );
    }

    function resolveTargetSampleRate() {
        const sampleRate = Number(getTargetSampleRate() || 16000);
        return sampleRate > 0 ? sampleRate : 16000;
    }

    return {
        ensureMicrophoneCaptureReady: ensureMicrophoneCaptureReady,
        stopMicrophoneCapture: stopMicrophoneCapture,
    };
}

export function buildWavBlob(chunks, sampleRate) {
    const validChunks = Array.isArray(chunks)
        ? chunks.filter((chunk) => chunk instanceof Int16Array && chunk.length > 0)
        : [];
    if (!validChunks.length) {
        return null;
    }

    const totalSamples = validChunks.reduce((sum, chunk) => sum + chunk.length, 0);
    const pcmBytes = totalSamples * 2;
    const buffer = new ArrayBuffer(44 + pcmBytes);
    const view = new DataView(buffer);
    const merged = new Int16Array(buffer, 44, totalSamples);

    let offset = 0;
    validChunks.forEach((chunk) => {
        merged.set(chunk, offset);
        offset += chunk.length;
    });

    writeAscii(view, 0, "RIFF");
    view.setUint32(4, 36 + pcmBytes, true);
    writeAscii(view, 8, "WAVE");
    writeAscii(view, 12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeAscii(view, 36, "data");
    view.setUint32(40, pcmBytes, true);

    return new Blob([buffer], { type: "audio/wav" });
}

function writeAscii(view, offset, text) {
    for (let index = 0; index < text.length; index += 1) {
        view.setUint8(offset + index, text.charCodeAt(index));
    }
}

function mergeFloat32Chunks(leftChunk, rightChunk) {
    if (!leftChunk.length) {
        return rightChunk;
    }
    if (!rightChunk.length) {
        return leftChunk;
    }

    const output = new Float32Array(leftChunk.length + rightChunk.length);
    output.set(leftChunk, 0);
    output.set(rightChunk, leftChunk.length);
    return output;
}

function floatChunkToInt16(floatChunk, clamp) {
    const output = new Int16Array(floatChunk.length);
    for (let index = 0; index < floatChunk.length; index += 1) {
        output[index] = floatToInt16Sample(floatChunk[index], clamp);
    }
    return output;
}

function floatToInt16Sample(value, clamp) {
    const sample = clamp(Number(value) || 0, -1, 1);
    if (sample < 0) {
        return Math.round(sample * 32768);
    }
    return Math.round(sample * 32767);
}

class PcmChunkResampler {
    constructor(inputSampleRate, outputSampleRate, clamp) {
        this.inputSampleRate = Number(inputSampleRate) || outputSampleRate;
        this.outputSampleRate = Number(outputSampleRate) || 16000;
        this.pendingChunk = new Float32Array(0);
        this._clamp = clamp;
    }

    push(floatChunk) {
        if (!(floatChunk instanceof Float32Array) || !floatChunk.length) {
            return new Int16Array(0);
        }

        const mergedChunk = mergeFloat32Chunks(this.pendingChunk, floatChunk);
        if (!mergedChunk.length) {
            return new Int16Array(0);
        }

        if (this.inputSampleRate === this.outputSampleRate) {
            this.pendingChunk = new Float32Array(0);
            return floatChunkToInt16(mergedChunk, this._clamp);
        }

        const ratio = this.inputSampleRate / this.outputSampleRate;
        const outputLength = Math.floor(mergedChunk.length / ratio);
        if (outputLength <= 0) {
            this.pendingChunk = mergedChunk;
            return new Int16Array(0);
        }

        const resampled = new Float32Array(outputLength);
        for (let index = 0; index < outputLength; index += 1) {
            const sourceIndex = index * ratio;
            const leftIndex = Math.floor(sourceIndex);
            const rightIndex = Math.min(leftIndex + 1, mergedChunk.length - 1);
            const offset = sourceIndex - leftIndex;
            resampled[index] = mergedChunk[leftIndex] * (1 - offset) + mergedChunk[rightIndex] * offset;
        }

        const consumedSamples = Math.floor(outputLength * ratio);
        this.pendingChunk = consumedSamples < mergedChunk.length
            ? mergedChunk.slice(consumedSamples)
            : new Float32Array(0);
        return floatChunkToInt16(resampled, this._clamp);
    }
}
