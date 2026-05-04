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

const DEFAULT_ROUTE_MODE = "chat_only";
const stageDirectivePattern = /^\s*\[(emotion|expression|motion)\s*[:=]\s*([^\]\r\n]{1,256})\]\s*/i;
let currentStatusKey = "messenger.status.ready";
let messengerStageTargets = [];
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
        loadStageTargets();
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

async function loadStageTargets() {
    if (!sessionSelect) {
        return;
    }
    try {
        const response = await fetch("/api/channels/stage-targets");
        if (!response.ok) {
            throw await responseToError(response);
        }
        const payload = await response.json();
        messengerStageTargets = Array.isArray(payload.targets) ? payload.targets : [];
        renderStageTargetOptions(messengerStageTargets);
    } catch (error) {
        console.warn("Unable to load messenger targets", error);
        messengerStageTargets = [];
        renderStageTargetOptions([]);
        setStatus("messenger.sessionTargetLoadFailed");
    }
}

function renderStageTargetOptions(targets) {
    if (!sessionSelect) {
        return;
    }
    const currentSession = String((sessionInput && sessionInput.value) || "default").trim() || "default";
    const options = buildStageTargetOptions(targets, currentSession);
    sessionSelect.replaceChildren(...options);
    sessionSelect.value = currentSession;
}

function buildStageTargetOptions(targets, currentSession) {
    const options = [];
    const seenSessions = new Set();
    for (const target of targets) {
        const sessionName = String((target && target.session_name) || "").trim();
        if (!sessionName || seenSessions.has(sessionName)) {
            continue;
        }
        seenSessions.add(sessionName);
        const option = document.createElement("option");
        option.value = sessionName;
        option.textContent = stageTargetLabel(target);
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

function stageTargetLabel(target) {
    const baseLabel = String(
        (target && target.display_name) || (target && target.session_name) || "default",
    );
    if (target && target.enabled === false) {
        return `${baseLabel} · ${i18n.t("channelTargets.disabled")}`;
    }
    if (target && target.running === false) {
        return `${baseLabel} · ${i18n.t("channelTargets.notRunning")}`;
    }
    return baseLabel;
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
    const prompt = String((input && input.value) || "").trim();
    if (!prompt) {
        return;
    }

    const sessionName = currentSessionName();
    appendMessage("user", prompt);
    if (input) {
        input.value = "";
    }

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
                prompt: prompt,
                session_name: sessionName,
                route_mode: DEFAULT_ROUTE_MODE,
                response_language: i18n.language,
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
    renderStageTargetOptions(messengerStageTargets);
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
