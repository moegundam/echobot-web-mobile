import { initShellI18n } from "./shell-i18n.js?v=session-runtime-p1-3&uiux=2";
import { initShellDisplayMode } from "./shell-display-mode.js?v=session-centered-2";
import { initShellAccessContext } from "./shell-access.js?v=rbac-nav-1";
import {
    initShellSessionLinks,
    rememberShellSessionName,
} from "./shell-session-links.js?v=site-public-6";
import {
    fetchSessionRuntimeContext,
    runtimeContextSummaryItems,
} from "./session-runtime-context.js?v=session-runtime-context-1";
import {
    createMessengerAttachmentController,
} from "./features/messenger/attachments.js?v=messenger-modular-1";
import {
    createMessengerMessageController,
    extractStageDirectives as extractStageDirectivesModule,
    promptWithUrl as promptWithUrlModule,
} from "./features/messenger/message-stream.js?v=messenger-modular-1";
import {
    createMessengerMessageRenderer,
} from "./features/messenger/message-rendering.js?v=messenger-modular-1";
import {
    createMessengerMicrophoneController,
} from "./features/messenger/microphone.js?v=messenger-modular-1";
import {
    createMessengerSessionController,
} from "./features/messenger/session-runtime.js?v=messenger-modular-1&session-fallback=1";
import {
    requestChatStream,
    requestJson,
    uploadChatFile,
    uploadChatImage,
} from "./modules/api.js";
const form = document.getElementById("messenger-form");
const input = document.getElementById("messenger-input");
const sendButton = document.getElementById("messenger-send");
const messagesElement = document.getElementById("messenger-messages");
const emptyStateElement = document.getElementById("messenger-empty-state");
const sessionInput = document.getElementById("messenger-session");
const sessionSelect = document.getElementById("messenger-session-select");
const statusElement = document.getElementById("messenger-status");
const recordButton = document.getElementById("messenger-record");
const fileInput = document.getElementById("messenger-file-input");
const fileButton = document.getElementById("messenger-file-button");
const fileSummary = document.getElementById("messenger-file-summary");
const urlInput = document.getElementById("messenger-url");
const attachmentsElement = document.getElementById("messenger-attachments");
const runtimeContextElement = document.getElementById("messenger-runtime-context");
const FALLBACK_ROUTE_MODE = "chat_only";
const MESSAGE_SCROLL_THRESHOLD_PX = 64;
const SESSION_API_PATH = "/api/sessions";
const STAGE_TARGETS_API_PATH = "/api/channels/stage-targets";
const stageDirectivePattern = /^\s*\[(emotion|expression|motion)\s*[:=]\s*([^\]\r\n]{1,256})\]\s*/i;
const messengerMicrophoneStatusKeys = [
    "console.microphonePermissionDenied",
    "console.microphoneNotFound",
    "console.noValidSpeech",
    "console.asrFailed",
    "console.microphoneCaptureUnsupported",
    "console.microphoneStartFailed",
];
let currentStatusKey = "messenger.status.ready";
let messengerSessions = [];
let messengerStageTargets = [];
let messengerRuntimeContext = null;
let pendingAttachments = [];
let messengerRuntimeContextRequestToken = 0;
let messengerBusy = false;
let attachmentUploadPromise = null;
let messengerSendToken = 0;
let activeChatAbortController = null;

const i18n = initShellI18n({
    onChange: () => {
        refreshLocalizedMessengerText();
        displayMode.refresh();
    },
});
const displayMode = initShellDisplayMode({ t: i18n.t });
void initShellAccessContext({ t: i18n.t });
initShellSessionLinks();

function setStatus(key) {
    currentStatusKey = key;
    if (statusElement) {
        statusElement.textContent = i18n.t(key);
    }
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
    if (fileButton) {
        fileButton.disabled = isBusy;
    }
    if (urlInput) {
        urlInput.disabled = isBusy;
    }
    if (recordButton) {
        recordButton.disabled = isBusy && !microphoneController.isRecording();
    }
    if (sessionSelect) {
        sessionSelect.disabled = isBusy;
    }
    if (sessionInput) {
        sessionInput.disabled = isBusy;
    }
}

function setMessengerBusy(isBusy) {
    messengerBusy = isBusy;
    setBusy(isBusy);
}

const messageRenderer = createMessengerMessageRenderer({
    messagesElement,
    emptyStateElement,
    messageRoleLabel,
    scrollThreshold: MESSAGE_SCROLL_THRESHOLD_PX,
});

const attachmentController = createMessengerAttachmentController({
    fileInput,
    fileSummary,
    attachmentsElement,
    i18n,
    uploadChatFile,
    uploadChatImage,
    setStatus,
});

const microphoneController = createMessengerMicrophoneController({
    recordButton,
    input,
    i18n,
    setStatus,
    currentStatusKey: () => currentStatusKey,
});

const sessionController = createMessengerSessionController({
    sessionInput,
    sessionSelect,
    runtimeContextElement,
    i18n,
    requestJson,
    fetchSessionRuntimeContext,
    runtimeContextSummaryItems,
    sessionApiPath: SESSION_API_PATH,
    stageTargetsApiPath: STAGE_TARGETS_API_PATH,
    fallbackRouteMode: FALLBACK_ROUTE_MODE,
    rememberShellSessionName,
    initShellSessionLinks,
    updateSessionUrl,
    setStatus,
    isBusy: () => messengerBusy,
    stopRecording: () => microphoneController.stopRecording(),
    onSessionsChanged: ({ sessions, stageTargets }) => {
        messengerSessions = sessions;
        messengerStageTargets = stageTargets;
    },
    onRuntimeContextChanged: (context) => {
        messengerRuntimeContext = context;
    },
});

const messageController = createMessengerMessageController({
    input,
    urlInput,
    i18n,
    setStatus,
    setBusy: setMessengerBusy,
    getBusy: () => messengerBusy,
    getPendingAttachments: () => pendingAttachments,
    clearPendingAttachments: () => {
        pendingAttachments = [];
    },
    renderPendingAttachments: () => renderPendingAttachments(),
    getAttachmentUploadPromise: () => attachmentUploadPromise,
    currentSessionName,
    selectedSessionName,
    activeRouteMode,
    getResponseLanguagePayload: messengerRequestLanguagePayload,
    getSendToken: () => messengerSendToken,
    appendMessage,
    scrollMessagesIfNearBottom,
    publishStageStreamStart,
    publishStageDelta,
    publishStageFinal,
    streamChat,
});

initMessengerSessionControls();
microphoneController.bindLifecycle();
refreshLocalizedMessengerText();

form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitMessage();
});

fileInput?.addEventListener("change", () => {
    updateFileSelectionSummary();
    const uploadPromise = uploadSelectedFiles();
    attachmentUploadPromise = uploadPromise;
    setBusy(true);
    void uploadPromise.finally(() => {
        if (attachmentUploadPromise === uploadPromise) {
            attachmentUploadPromise = null;
        }
        setBusy(messengerBusy);
    });
});

fileButton?.addEventListener("click", () => {
    fileInput?.click();
});

recordButton?.addEventListener("click", () => {
    microphoneController.toggleRecording();
});

window.addEventListener("pagehide", () => {
    messengerSendToken += 1;
    activeChatAbortController?.abort();
    activeChatAbortController = null;
});

function initMessengerSessionControls() {
    sessionController.init();
}

function selectedSessionName() {
    return sessionController.selectedSessionName();
}

function currentSessionName() {
    return sessionController.currentSessionName();
}

function loadSessions() {
    return sessionController.loadSessions();
}

function loadMessengerRuntimeContext(nextSessionName) {
    messengerRuntimeContextRequestToken += 1;
    return sessionController.loadMessengerRuntimeContext(nextSessionName);
}

function activeRouteMode(sessionName) {
    return sessionController.activeRouteMode(sessionName);
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

async function submitMessage() {
    if (messengerBusy) {
        return;
    }
    const sendToken = ++messengerSendToken;
    const abortController = new AbortController();
    activeChatAbortController = abortController;
    try {
        await messageController.submitMessage(abortController, sendToken);
    } finally {
        if (activeChatAbortController === abortController) {
            activeChatAbortController = null;
        }
    }
}

function promptWithUrl(rawPrompt) {
    return promptWithUrlModule(
        rawPrompt,
        String((urlInput && urlInput.value) || "").trim(),
    );
}

async function uploadSelectedFiles() {
    return attachmentController.uploadSelectedFiles(
        () => pendingAttachments,
        (attachments) => {
            pendingAttachments = attachments;
        },
    );
}

async function uploadMessengerAttachment(file) {
    return attachmentController.uploadMessengerAttachment(file);
}

function updateFileSelectionSummary() {
    attachmentController.updateFileSelectionSummary();
}

function renderPendingAttachments() {
    attachmentController.renderPendingAttachments(
        () => pendingAttachments,
        (attachments) => {
            pendingAttachments = attachments;
        },
    );
}

function createSpeechRecognition() {
    return microphoneController.createSpeechRecognition();
}

function speechRecognitionErrorStatusKey(errorCode) {
    return microphoneController.speechRecognitionErrorStatusKey(errorCode);
}

function isMessagesNearBottom(element = messagesElement) {
    return messageRenderer.isMessagesNearBottom(element);
}

function scrollMessagesToBottom(element = messagesElement) {
    return messageRenderer.scrollMessagesToBottom(element);
}

function scrollMessagesIfNearBottom(update, element = messagesElement) {
    return messageRenderer.scrollMessagesIfNearBottom(update, element, () => {
        scrollMessagesToBottom(element);
    });
}

function appendMessage(role, text) {
    return messageRenderer.appendMessage(role, text, (update) => {
        scrollMessagesIfNearBottom(() => update());
    });
}

function refreshLocalizedMessengerText() {
    if (statusElement) {
        statusElement.textContent = i18n.t(currentStatusKey);
    }
    messageRenderer.refreshLocalizedLabels();
    sessionController.refresh();
    renderPendingAttachments();
    updateFileSelectionSummary();
    microphoneController.refresh();
}

function messageRoleLabel(role) {
    return role === "user"
        ? i18n.t("messenger.userLabel")
        : i18n.t("messenger.assistantLabel");
}

function messengerRequestLanguagePayload() {
    return { response_language: i18n.language };
}

function extractStageDirectives(text) {
    return extractStageDirectivesModule(text, stageDirectivePattern);
}

async function streamChat(payload, handlers, signal) {
    return await requestChatStream(payload, handlers, {
        signal,
        allowFallback: false,
        streamUnavailableMessage: i18n.t("messenger.error.chatStreamUnavailable"),
        streamEndedMessage: i18n.t("messenger.error.streamEnded"),
    });
}

async function publishStageEvent(kind, sessionName, text, metadata = {}, state = {}) {
    try {
        await requestJson("/api/stage/events", {
            method: "POST",
            body: JSON.stringify({
                kind,
                session_name: sessionName,
                text: String(text || ""),
                emotion: String(state.emotion || ""),
                expression: String(state.expression || ""),
                motion: String(state.motion || ""),
                speaker: "EchoBot",
                source: "messenger",
                metadata,
            }),
        });
    } catch (error) {
        console.warn("Unable to publish stage event", error);
    }
}

async function publishStageStreamStart(sessionName) {
    await publishStageEvent("subtitle", sessionName, "", {
        reason: "assistant_stream_start",
    });
}

async function publishStageDelta(sessionName, delta) {
    await publishStageEvent("assistant_delta", sessionName, delta);
}

async function publishStageFinal(sessionName, stageMessage) {
    await publishStageEvent("assistant_final", sessionName, stageMessage.text, {}, {
        emotion: stageMessage.emotion,
        expression: stageMessage.expression,
        motion: stageMessage.motion,
    });
}
