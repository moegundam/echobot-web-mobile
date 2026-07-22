export function createMessengerMicrophoneController({
    recordButton,
    input,
    i18n,
    setStatus,
    currentStatusKey,
}) {
    let recognition = null;
    let recording = false;

    function toggleRecording() {
        if (recording) {
            stopRecording();
            return;
        }
        startRecording();
    }

    function startRecording() {
        recognition = recognition || createSpeechRecognition();
        if (!recognition) {
            setStatus("console.microphoneCaptureUnsupported");
            updateRecordButton();
            return;
        }

        recognition.lang = speechRecognitionLanguage();
        recognition.onresult = (event) => {
            let transcript = "";
            for (let index = event.resultIndex; index < event.results.length; index += 1) {
                transcript += event.results[index][0].transcript;
            }
            appendTranscript(transcript);
        };
        recognition.onerror = (event) => {
            console.warn("Messenger speech recognition error", event);
            recording = false;
            setStatus(speechRecognitionErrorStatusKey(event && event.error));
            updateRecordButton();
        };
        recognition.onend = () => {
            const wasRecording = recording;
            recording = false;
            if (wasRecording && currentStatusKey() === "messenger.recording") {
                setStatus("messenger.status.ready");
            }
            updateRecordButton();
        };

        try {
            recognition.start();
            recording = true;
            setStatus("messenger.recording");
            updateRecordButton();
        } catch (error) {
            console.warn("Unable to start messenger speech recognition", error);
            recording = false;
            setStatus("console.microphoneStartFailed");
            updateRecordButton();
        }
    }

    function stopRecording() {
        if (!recognition) {
            recording = false;
            updateRecordButton();
            return;
        }
        const wasRecording = recording;
        recording = false;
        try {
            recognition.stop();
        } catch (_error) {
            // Browser speech recognition can throw when already stopped.
        }
        if (wasRecording && currentStatusKey() === "messenger.recording") {
            setStatus("messenger.status.ready");
        }
        updateRecordButton();
    }

    function createSpeechRecognition() {
        const SpeechRecognitionConstructor = window.SpeechRecognition
            || window.webkitSpeechRecognition;
        if (!SpeechRecognitionConstructor) {
            return null;
        }
        const speechRecognition = new SpeechRecognitionConstructor();
        speechRecognition.continuous = false;
        speechRecognition.interimResults = false;
        return speechRecognition;
    }

    function speechRecognitionErrorStatusKey(errorCode) {
        switch (String(errorCode || "").toLowerCase()) {
        case "not-allowed":
        case "service-not-allowed":
            return "console.microphonePermissionDenied";
        case "audio-capture":
            return "console.microphoneNotFound";
        case "no-speech":
            return "console.noValidSpeech";
        case "network":
            return "console.realtimeAsrConnectionFailed";
        case "aborted":
            return "messenger.status.ready";
        default:
            return "console.asrFailed";
        }
    }

    function speechRecognitionLanguage() {
        if (i18n.language === "zh-Hans") {
            return "zh-CN";
        }
        if (i18n.language === "zh-Hant") {
            return "zh-TW";
        }
        return "en-US";
    }

    function appendTranscript(transcript) {
        const text = String(transcript || "").trim();
        if (!text || !input) {
            return;
        }
        const existing = String(input.value || "").trim();
        input.value = existing ? `${existing} ${text}` : text;
        input.focus();
    }

    function updateRecordButton() {
        if (!recordButton) {
            return;
        }
        recordButton.textContent = i18n.t(recording
            ? "messenger.stopRecording"
            : "messenger.startRecording");
        recordButton.setAttribute("aria-pressed", recording ? "true" : "false");
    }

    function bindLifecycle() {
        document.addEventListener("visibilitychange", () => {
            if (document.hidden) {
                stopRecording();
            }
        });
        window.addEventListener("pagehide", () => {
            stopRecording();
        });
    }

    return {
        bindLifecycle,
        createSpeechRecognition,
        isRecording: () => recording,
        refresh: updateRecordButton,
        speechRecognitionErrorStatusKey,
        startRecording,
        stopRecording,
        toggleRecording,
    };
}
