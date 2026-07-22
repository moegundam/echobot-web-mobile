import { requestJson } from "./modules/api.js";

export async function fetchSessionRuntimeContext(sessionName) {
    return await requestJson(
        `/api/sessions/${encodeURIComponent(sessionName)}/runtime-context`,
    );
}

export function runtimeContextSummaryItems(context, t) {
    const safeContext = context && typeof context === "object" ? context : {};
    const character = safeContext.character && typeof safeContext.character === "object"
        ? safeContext.character
        : {};
    const llm = safeContext.llm_model && typeof safeContext.llm_model === "object"
        ? safeContext.llm_model
        : {};
    const voice = safeContext.voice_profile && typeof safeContext.voice_profile === "object"
        ? safeContext.voice_profile
        : {};
    const live2d = safeContext.live2d_model && typeof safeContext.live2d_model === "object"
        ? safeContext.live2d_model
        : {};
    const channel = safeContext.channel && typeof safeContext.channel === "object"
        ? safeContext.channel
        : {};

    return [
        {
            key: "session",
            label: t("runtimeContext.session"),
            value: stringValue(safeContext.session_name) || "default",
        },
        {
            key: "character",
            label: t("runtimeContext.character"),
            value: stringValue(character.name) || stringValue(safeContext.role_name) || "default",
        },
        {
            key: "llm",
            label: t("runtimeContext.llm"),
            value: stringValue(llm.name) || stringValue(llm.model) || t("runtimeContext.notSet"),
        },
        {
            key: "voice",
            label: t("runtimeContext.voice"),
            value: voiceProfileLabel(voice) || t("runtimeContext.notSet"),
        },
        {
            key: "live2d",
            label: t("runtimeContext.live2d"),
            value: stringValue(live2d.name) || stringValue(live2d.selection_key)
                || t("runtimeContext.notSet"),
        },
        {
            key: "channel",
            label: t("runtimeContext.channel"),
            value: stringValue(channel.name) || t("runtimeContext.internalWeb"),
        },
    ];
}

export function runtimeContextValue(context, key, t) {
    const item = runtimeContextSummaryItems(context, t)
        .find((summaryItem) => summaryItem.key === key);
    return item ? item.value : t("runtimeContext.notSet");
}

function voiceProfileLabel(voice) {
    const label = stringValue(voice.name);
    const tts = voice.tts && typeof voice.tts === "object" ? voice.tts : {};
    const stt = voice.stt && typeof voice.stt === "object" ? voice.stt : {};
    const voiceName = stringValue(tts.voice) || stringValue(tts.model);
    const sttName = stringValue(stt.model);
    if (label && (voiceName || sttName)) {
        return `${label} · ${[voiceName, sttName].filter(Boolean).join(" / ")}`;
    }
    return label || voiceName || sttName;
}

function stringValue(value) {
    return String(value || "").trim();
}
