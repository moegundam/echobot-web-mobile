import { DOM } from "../../core/dom.js";
import { asrState, audioState, chatState } from "../../core/store.js";

export function createVoicePromptQueue(deps) {
    const {
        setRunStatus,
        t = (key) => key,
    } = deps;

    function enqueueVoicePrompt(text, sourceLabel) {
        const prompt = String(text || "").trim();
        if (!prompt) {
            return;
        }

        asrState.voicePromptQueue.push({
            text: prompt,
            sourceLabel: sourceLabel || t("console.voiceSource"),
        });
        void drainVoicePromptQueue();
    }

    async function drainVoicePromptQueue() {
        if (
            chatState.chatBusy
            || audioState.speaking
            || !asrState.voicePromptQueue.length
        ) {
            return;
        }

        const nextPrompt = asrState.voicePromptQueue.shift();
        if (!nextPrompt || !DOM.promptInput) {
            return;
        }

        const chatForm = document.getElementById("chat-form");
        if (!chatForm || typeof chatForm.requestSubmit !== "function") {
            return;
        }

        DOM.promptInput.value = nextPrompt.text;
        setRunStatus(t("console.voiceRecognizedSending", { source: nextPrompt.sourceLabel }));
        chatForm.requestSubmit();
    }

    return {
        drainVoicePromptQueue: drainVoicePromptQueue,
        enqueueVoicePrompt: enqueueVoicePrompt,
    };
}
