import { DOM } from "../core/dom.js";
import { chatState, sessionState } from "../core/store.js";
import { scheduleMessagesScrollToBottom } from "../modules/messages.js";

export function createUiStatusController() {
    const features = {
        asr: null,
        chat: null,
        roles: null,
        sessions: null,
    };
    const localizedStatus = {
        connection: {
            key: "",
            params: {},
        },
        run: {
            key: "",
            params: {},
        },
    };

    function bindFeatures(nextFeatures) {
        Object.assign(features, nextFeatures || {});
    }

    function setChatBusy(isBusy) {
        chatState.chatBusy = isBusy;
        if (DOM.sendButton) {
            DOM.sendButton.disabled = isBusy;
        }
        if (DOM.composerFileButton) {
            DOM.composerFileButton.disabled = isBusy || Boolean(chatState.activeChatJobId);
        }
        if (DOM.composerFileInput) {
            DOM.composerFileInput.disabled = isBusy || Boolean(chatState.activeChatJobId);
        }
        if (DOM.composerImageButton) {
            DOM.composerImageButton.disabled = isBusy || Boolean(chatState.activeChatJobId);
        }
        if (DOM.composerImageInput) {
            DOM.composerImageInput.disabled = isBusy || Boolean(chatState.activeChatJobId);
        }
        if (DOM.sessionCreateButton) {
            DOM.sessionCreateButton.disabled = isBusy || sessionState.sessionLoading;
        }
        if (DOM.sessionRefreshButton) {
            DOM.sessionRefreshButton.disabled = isBusy || sessionState.sessionLoading;
        }
        if (DOM.routeModeSelect) {
            DOM.routeModeSelect.disabled = (
                isBusy
                || sessionState.sessionLoading
                || Boolean(chatState.activeChatJobId)
            );
        }

        features.sessions?.renderSessionList(sessionState.sessions);
        features.roles?.updateRoleActionState();
        features.asr?.updateVoiceInputControls();
        updateComposerBackgroundJobState();
        features.chat?.refreshComposerAttachments();
    }

    function setActiveBackgroundJob(jobId) {
        chatState.activeChatJobId = String(jobId || "").trim();
        updateComposerBackgroundJobState();
    }

    function setConnectionState(kind, text, key = "", params = {}) {
        if (!DOM.connectionBadge) {
            return;
        }

        DOM.connectionBadge.className = `status-badge status-${kind}`;
        delete DOM.connectionBadge.dataset.i18nKey;
        localizedStatus.connection.key = String(key || "");
        localizedStatus.connection.params = params || {};
        DOM.connectionBadge.textContent = text;
    }

    function setRunStatus(text, key = "", params = {}) {
        if (DOM.runStatus) {
            delete DOM.runStatus.dataset.i18nKey;
            localizedStatus.run.key = String(key || "");
            localizedStatus.run.params = params || {};
            DOM.runStatus.textContent = text;
        }
    }

    function refreshLocalizedText(t) {
        if (typeof t !== "function") {
            return;
        }
        if (DOM.connectionBadge && localizedStatus.connection.key) {
            DOM.connectionBadge.textContent = t(
                localizedStatus.connection.key,
                localizedStatus.connection.params,
            );
        }
        if (DOM.runStatus && localizedStatus.run.key) {
            DOM.runStatus.textContent = t(
                localizedStatus.run.key,
                localizedStatus.run.params,
            );
        }
    }

    function updateComposerBackgroundJobState() {
        const backgroundJobRunning = Boolean(chatState.activeChatJobId);

        if (DOM.promptInput) {
            DOM.promptInput.disabled = backgroundJobRunning;
        }
        if (DOM.composerFileButton) {
            DOM.composerFileButton.disabled = backgroundJobRunning || chatState.chatBusy;
        }
        if (DOM.composerFileInput) {
            DOM.composerFileInput.disabled = backgroundJobRunning || chatState.chatBusy;
        }
        if (DOM.composerImageButton) {
            DOM.composerImageButton.disabled = backgroundJobRunning || chatState.chatBusy;
        }
        if (DOM.composerImageInput) {
            DOM.composerImageInput.disabled = backgroundJobRunning || chatState.chatBusy;
        }
        if (DOM.composerStatusBanner) {
            DOM.composerStatusBanner.hidden = !backgroundJobRunning;
        }
        if (DOM.stopAgentButton) {
            DOM.stopAgentButton.disabled = !backgroundJobRunning;
            DOM.stopAgentButton.classList.toggle("is-active", backgroundJobRunning);
        }
        if (DOM.routeModeSelect) {
            DOM.routeModeSelect.disabled = (
                backgroundJobRunning
                || chatState.chatBusy
                || sessionState.sessionLoading
            );
        }

        scheduleMessagesScrollToBottom();
        features.chat?.refreshComposerAttachments();
    }

    return {
        bindFeatures,
        setActiveBackgroundJob,
        setChatBusy,
        refreshLocalizedText,
        setConnectionState,
        setRunStatus,
    };
}
