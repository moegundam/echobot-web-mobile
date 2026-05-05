import { initShellI18n } from "./shell-i18n.js?v=site-public-6";
import { initShellDisplayMode } from "./shell-display-mode.js?v=site-public-6";
import { rememberShellSessionName } from "./shell-session-links.js?v=site-public-6";

const form = document.getElementById("messenger-form");
const input = document.getElementById("messenger-input");
const sendButton = document.getElementById("messenger-send");
const messagesElement = document.getElementById("messenger-messages");
const sessionInput = document.getElementById("messenger-session");
const sessionSelect = document.getElementById("messenger-session-select");
const statusElement = document.getElementById("messenger-status");
const recordButton = document.getElementById("messenger-record");
const fileInput = document.getElementById("messenger-file-input");
const urlInput = document.getElementById("messenger-url");
const attachmentsElement = document.getElementById("messenger-attachments");

const DEFAULT_ROUTE_MODE = "chat_only";
const stageDirectivePattern = /^\s*\[(emotion|expression|motion)\s*[:=]\s*([^\]\r\n]{1,256})\]\s*/i;
let currentStatusKey = "messenger.status.ready";
let messengerSessions = [];
let pendingAttachments = [];
let recognition = null;
let recording = false;
const i18n = initShellI18n({
    onChange: () => {
        refreshLocalizedMessengerText();
        displayMode.refresh();
    },
});
const displayMode = initShellDisplayMode({ t: i18n.t });

initMessengerSessionControls();
refreshLocalizedMessengerText();

if (form) {
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        await submitMessage();
    });
}
if (fileInput) {
    fileInput.addEventListener("change", () => {
        void uploadSelectedFiles();
    });
}
if (recordButton) {
    recordButton.addEventListener("click", () => {
        toggleRecording();
    });
}
document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
        stopRecording();
    }
});
window.addEventListener("pagehide", () => {
    stopRecording();
});

function resolveInitialSessionName() {
    const params = new URLSearchParams(window.location.search);
    return String(params.get("session_name") || "default").trim() || "default";
}

function currentSessionName() {
    if (sessionSelect && sessionSelect.value) {
        setActiveSessionName(sessionSelect.value);
    }
    return rememberShellSessionName(
        String((sessionInput && sessionInput.value) || "default").trim() || "default",
    );
}

function initMessengerSessionControls() {
    const initialSessionName = rememberShellSessionName(resolveInitialSessionName());
    if (sessionInput) {
        sessionInput.value = initialSessionName;
    }
    if (sessionSelect) {
        sessionSelect.addEventListener("change", () => {
            setActiveSessionName(sessionSelect.value, { updateUrl: true });
        });
        loadSessions();
    }
}

function setActiveSessionName(value, options = {}) {
    const nextSessionName = rememberShellSessionName(
        String(value || "").trim() || "default",
    );
    if (sessionInput) {
        sessionInput.value = nextSessionName;
    }
    if (sessionSelect && sessionSelect.value !== nextSessionName) {
        sessionSelect.value = nextSessionName;
    }
    if (options.updateUrl) {
        updateSessionUrl(nextSessionName);
    }
    return nextSessionName;
}

async function loadSessions() {
    if (!sessionSelect) {
        return;
    }
    try {
        const response = await fetch("/api/sessions");
        if (!response.ok) {
            throw await responseToError(response);
        }
        const payload = await response.json();
        messengerSessions = Array.isArray(payload) ? payload : [];
        renderSessionOptions(messengerSessions);
    } catch (error) {
        console.warn("Unable to load messenger sessions", error);
        messengerSessions = [];
        renderSessionOptions([]);
        setStatus("messenger.sessionLoadFailed");
    }
}

function renderSessionOptions(sessions) {
    if (!sessionSelect) {
        return;
    }
    const currentSession = String((sessionInput && sessionInput.value) || "default").trim() || "default";
    const options = buildSessionOptions(sessions, currentSession);
    sessionSelect.replaceChildren(...options);
    sessionSelect.value = currentSession;
}

function buildSessionOptions(sessions, currentSession) {
    const options = [];
    const seenSessions = new Set();
    for (const session of sessions) {
        const sessionName = String((session && session.name) || "").trim();
        if (!sessionName || seenSessions.has(sessionName)) {
            continue;
        }
        seenSessions.add(sessionName);
        const option = document.createElement("option");
        option.value = sessionName;
        option.textContent = sessionName;
        options.push(option);
    }

    if (!seenSessions.has(currentSession)) {
        const fallbackOption = document.createElement("option");
        fallbackOption.value = currentSession;
        fallbackOption.textContent = i18n.t("messenger.sessionFallback", {
            session: currentSession,
        });
        options.unshift(fallbackOption);
    }
    return options;
}

function updateSessionUrl(sessionName) {
    try {
        const url = new URL(window.location.href);
        url.searchParams.set("session_name", sessionName);
        window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
    } catch (_error) {
        // Keeping the hidden input in sync is enough for the message flow.
    }
}

function setStatus(key) {
    currentStatusKey = key;
    if (statusElement) {
        statusElement.textContent = i18n.t(key);
    }
}

async function submitMessage() {
    const attachments = [...pendingAttachments];
    const prompt = promptWithUrl(String((input && input.value) || "").trim());
    const messagePrompt = prompt || (
        attachments.length > 0 ? i18n.t("messenger.attachmentOnlyPrompt") : ""
    );
    if (!messagePrompt) {
        return;
    }

    const sessionName = currentSessionName();
    appendMessage("user", messagePrompt);
    if (input) {
        input.value = "";
    }
    if (urlInput) {
        urlInput.value = "";
    }
    pendingAttachments = [];
    renderPendingAttachments();

    const assistantNode = appendMessage("assistant", "");
    let assistantText = "";
    setBusy(true);
    setStatus("messenger.status.streaming");

    try {
        await publishStageEvent("subtitle", sessionName, "", {
            reason: "assistant_stream_start",
        });
        await streamChat(
            {
                prompt: messagePrompt,
                session_name: sessionName,
                route_mode: DEFAULT_ROUTE_MODE,
                response_language: i18n.language,
                images: attachments
                    .filter((item) => item.kind === "image")
                    .map((item) => ({ attachment_id: item.attachment_id })),
                files: attachments
                    .filter((item) => item.kind === "file")
                    .map((item) => ({ attachment_id: item.attachment_id })),
            },
            {
                onChunk: async (delta) => {
                    assistantText += delta;
                    assistantNode.textContent = assistantText;
                    await publishStageEvent("assistant_delta", sessionName, delta);
                },
                onDone: async (event) => {
                    const finalText = String(event.response || event.response_content || assistantText || "");
                    const stageMessage = extractStageDirectives(finalText);
                    assistantText = stageMessage.text;
                    assistantNode.textContent = stageMessage.text;
                    await publishStageEvent("assistant_final", sessionName, stageMessage.text, {}, {
                        emotion: stageMessage.emotion,
                        expression: stageMessage.expression,
                        motion: stageMessage.motion,
                    });
                },
            },
        );
        setStatus("messenger.status.ready");
    } catch (error) {
        console.error(error);
        assistantNode.textContent = `${i18n.t("messenger.errorPrefix")}：${error.message || error}`;
        setStatus("messenger.status.error");
    } finally {
        setBusy(false);
    }
}

function promptWithUrl(rawPrompt) {
    const prompt = String(rawPrompt || "").trim();
    const url = String((urlInput && urlInput.value) || "").trim();
    if (!url) {
        return prompt;
    }
    const urlBlock = `URL:\n${url}`;
    return prompt ? `${prompt}\n\n${urlBlock}` : urlBlock;
}

async function uploadSelectedFiles() {
    if (!fileInput) {
        return;
    }
    const files = Array.from(fileInput.files || []);
    if (files.length === 0) {
        return;
    }

    setBusy(true);
    setStatus("messenger.uploading");
    try {
        for (const file of files) {
            pendingAttachments.push(await uploadMessengerAttachment(file));
            renderPendingAttachments();
        }
        setStatus("messenger.attached");
    } catch (error) {
        console.error(error);
        setStatus("messenger.uploadFailed");
    } finally {
        fileInput.value = "";
        setBusy(false);
    }
}

async function uploadMessengerAttachment(file) {
    const kind = String(file && file.type || "").startsWith("image/") ? "image" : "file";
    const endpoint = kind === "image" ? "/api/attachments/images" : "/api/attachments/files";
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(endpoint, {
        method: "POST",
        body: formData,
    });
    if (!response.ok) {
        throw await responseToError(response);
    }
    const payload = await response.json();
    const attachmentId = String((payload && payload.attachment_id) || "");
    if (!attachmentId) {
        throw new Error(i18n.t("messenger.uploadFailed"));
    }
    return {
        kind: kind,
        attachment_id: attachmentId,
        label: String(
            (payload && payload.original_filename) || (file && file.name) || attachmentId,
        ),
    };
}

function renderPendingAttachments() {
    if (!attachmentsElement) {
        return;
    }
    const chips = pendingAttachments.map((item, index) => {
        const chip = document.createElement("span");
        chip.className = "messenger-attachment-chip";

        const label = document.createElement("span");
        label.textContent = `${i18n.t("messenger.attached")}: ${item.label}`;

        const removeButton = document.createElement("button");
        removeButton.type = "button";
        removeButton.textContent = i18n.t("messenger.removeAttachment");
        removeButton.addEventListener("click", () => {
            removePendingAttachment(index);
        });

        chip.append(label, removeButton);
        return chip;
    });
    attachmentsElement.replaceChildren(...chips);
}

function removePendingAttachment(index) {
    pendingAttachments = pendingAttachments.filter((_item, itemIndex) => itemIndex !== index);
    renderPendingAttachments();
}

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
        setStatus("messenger.recordingUnsupported");
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
        setStatus("messenger.recordingUnsupported");
        updateRecordButton();
    };
    recognition.onend = () => {
        const wasRecording = recording;
        recording = false;
        if (wasRecording && currentStatusKey === "messenger.recording") {
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
        setStatus("messenger.recordingUnsupported");
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
    if (wasRecording && currentStatusKey === "messenger.recording") {
        setStatus("messenger.status.ready");
    }
    updateRecordButton();
}

function createSpeechRecognition() {
    const SpeechRecognitionConstructor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognitionConstructor) {
        return null;
    }
    const speechRecognition = new SpeechRecognitionConstructor();
    speechRecognition.continuous = false;
    speechRecognition.interimResults = false;
    return speechRecognition;
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

function appendMessage(role, text) {
    const row = document.createElement("article");
    row.className = `message message-${role}`;

    const label = document.createElement("span");
    label.className = "message-label";
    label.dataset.messageRole = role;
    label.textContent = messageRoleLabel(role);

    const bubble = document.createElement("p");
    bubble.className = "message-bubble";
    bubble.textContent = String(text || "");

    row.append(label, bubble);
    if (messagesElement) {
        messagesElement.appendChild(row);
        messagesElement.scrollTop = messagesElement.scrollHeight;
    }
    return bubble;
}

function setBusy(isBusy) {
    if (sendButton) {
        sendButton.disabled = isBusy;
    }
    if (input) {
        input.disabled = isBusy;
    }
    if (fileInput) {
        fileInput.disabled = isBusy;
    }
    if (urlInput) {
        urlInput.disabled = isBusy;
    }
    if (recordButton) {
        recordButton.disabled = isBusy && !recording;
    }
}

async function streamChat(payload, handlers) {
    const response = await fetch("/api/chat/stream", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        throw await responseToError(response);
    }
    if (!response.body) {
        throw new Error(i18n.t("messenger.error.chatStreamUnavailable"));
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let sawDone = false;

    while (true) {
        const { done, value } = await reader.read();
        if (done) {
            break;
        }
        buffer += decoder.decode(value, { stream: true });
        const result = await consumeNdjson(buffer, handlers);
        buffer = result.buffer;
        sawDone = sawDone || result.sawDone;
    }

    buffer += decoder.decode();
    const result = await consumeNdjson(`${buffer}\n`, handlers);
    sawDone = sawDone || result.sawDone;
    if (!sawDone) {
        throw new Error(i18n.t("messenger.error.streamEnded"));
    }
}

async function consumeNdjson(buffer, handlers) {
    let remaining = buffer;
    let sawDone = false;

    while (true) {
        const newlineIndex = remaining.indexOf("\n");
        if (newlineIndex === -1) {
            break;
        }

        const line = remaining.slice(0, newlineIndex).trim();
        remaining = remaining.slice(newlineIndex + 1);
        if (!line) {
            continue;
        }

        let event;
        try {
            event = JSON.parse(line);
        } catch (_error) {
            throw new Error(i18n.t("messenger.error.invalidStreamEvent", {
                line: line,
            }));
        }

        if (event.type === "chunk") {
            if (handlers && typeof handlers.onChunk === "function") {
                await handlers.onChunk(String(event.delta || ""));
            }
            continue;
        }
        if (event.type === "done") {
            sawDone = true;
            if (handlers && typeof handlers.onDone === "function") {
                await handlers.onDone(event);
            }
            continue;
        }
        if (event.type === "error") {
            throw new Error(event.message || i18n.t("messenger.error.chatStreamFailed"));
        }
    }

    return {
        buffer: remaining,
        sawDone: sawDone,
    };
}

function refreshLocalizedMessengerText() {
    if (statusElement) {
        statusElement.textContent = i18n.t(currentStatusKey);
    }
    document.querySelectorAll("[data-message-role]").forEach((label) => {
        label.textContent = messageRoleLabel(label.dataset.messageRole);
    });
    renderSessionOptions(messengerSessions);
    renderPendingAttachments();
    updateRecordButton();
}

function messageRoleLabel(role) {
    return role === "user"
        ? i18n.t("messenger.userLabel")
        : i18n.t("messenger.assistantLabel");
}

function extractStageDirectives(text) {
    const directives = {
        text: String(text || ""),
        emotion: "",
        expression: "",
        motion: "",
    };
    let remaining = directives.text;

    while (true) {
        const match = remaining.match(stageDirectivePattern);
        if (!match) {
            break;
        }
        const key = String(match[1] || "").toLowerCase();
        const value = String(match[2] || "").trim();
        if (key && Object.prototype.hasOwnProperty.call(directives, key)) {
            directives[key] = value;
        }
        remaining = remaining.slice(match[0].length);
    }

    directives.text = remaining.trimStart();
    return directives;
}

async function publishStageEvent(kind, sessionName, text, metadata = {}, state = {}) {
    try {
        const response = await fetch("/api/stage/events", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                kind: kind,
                session_name: sessionName,
                text: String(text || ""),
                emotion: String(state.emotion || ""),
                expression: String(state.expression || ""),
                motion: String(state.motion || ""),
                speaker: "EchoBot",
                source: "messenger",
                metadata: metadata,
            }),
        });
        if (!response.ok) {
            throw await responseToError(response);
        }
    } catch (error) {
        console.warn("Unable to publish stage event", error);
    }
}

async function responseToError(response) {
    let detail = `${response.status} ${response.statusText}`;
    try {
        const payload = await response.json();
        if (payload && typeof payload.detail === "string") {
            detail = payload.detail;
        }
    } catch (_error) {
        return new Error(detail);
    }
    return new Error(detail);
}
