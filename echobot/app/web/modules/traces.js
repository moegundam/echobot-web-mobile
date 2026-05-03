import { messageContentToText } from "./content.js";
import { DOM } from "../core/dom.js";

const SKILL_TOOL_NAMES = new Set([
    "activate_skill",
    "list_skill_resources",
    "read_skill_resource",
]);

export function createTraceModule(deps = {}) {
    const t = typeof deps.t === "function" ? deps.t : (key, params = {}) => {
        return String(key).replace(/\{([A-Za-z0-9_]+)\}/g, (_match, name) => {
            return Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : "";
        });
    };
    let currentJobId = "";
    let lastPayload = null;

    function resetTracePanel() {
        currentJobId = "";
        lastPayload = null;

        if (DOM.agentTracePanel) {
            DOM.agentTracePanel.hidden = true;
            DOM.agentTracePanel.open = false;
        }
        if (DOM.agentTraceSummaryText) {
            DOM.agentTraceSummaryText.textContent = t("console.waitingBackgroundJob");
        }
        if (DOM.agentTraceCount) {
            DOM.agentTraceCount.textContent = t("console.traceCount", { count: 0 });
        }
        if (DOM.agentTraceEvents) {
            DOM.agentTraceEvents.replaceChildren(
                buildEmptyState(t("console.traceEmpty")),
            );
        }
    }

    function startTracePanel(jobId) {
        const normalizedJobId = String(jobId || "").trim();
        if (!normalizedJobId) {
            resetTracePanel();
            return;
        }

        currentJobId = normalizedJobId;
        renderTracePayload({
            job_id: normalizedJobId,
            status: "running",
            events: [],
        });
    }

    function applyTracePayload(jobId, payload) {
        const normalizedJobId = String(jobId || "").trim();
        if (!normalizedJobId || normalizedJobId !== currentJobId) {
            return;
        }
        renderTracePayload(payload);
    }

    function renderTracePayload(payload) {
        lastPayload = payload || null;
        if (
            !DOM.agentTracePanel
            || !DOM.agentTraceSummaryText
            || !DOM.agentTraceCount
            || !DOM.agentTraceEvents
        ) {
            return;
        }

        const status = String(payload?.status || "running");
        const events = Array.isArray(payload?.events) ? payload.events : [];
        DOM.agentTracePanel.hidden = false;
        DOM.agentTraceSummaryText.textContent = buildTraceSummaryText(
            t,
            status,
            events.length,
        );
        DOM.agentTraceCount.textContent = t("console.traceCount", { count: events.length });

        if (!events.length) {
            DOM.agentTraceEvents.replaceChildren(
                buildEmptyState(buildEmptyStateText(t, status)),
            );
            return;
        }

        DOM.agentTraceEvents.replaceChildren(
            ...events.map((event, index) => buildTraceEventCard(t, event, index)),
        );
    }

    function refreshLocalizedText() {
        if (lastPayload) {
            renderTracePayload(lastPayload);
            return;
        }
        if (currentJobId) {
            startTracePanel(currentJobId);
            return;
        }
        resetTracePanel();
    }

    return {
        applyTracePayload: applyTracePayload,
        refreshLocalizedText: refreshLocalizedText,
        resetTracePanel: resetTracePanel,
        startTracePanel: startTracePanel,
    };
}

function buildTraceSummaryText(t, status, eventCount) {
    if (status === "failed") {
        return t("console.traceSummaryFailed", { count: eventCount });
    }
    if (status === "cancelled") {
        return t("console.traceSummaryCancelled", { count: eventCount });
    }
    if (status === "waiting_for_input") {
        return t("console.traceSummaryWaiting", { count: eventCount });
    }
    if (status === "completed") {
        return t("console.traceSummaryCompleted", { count: eventCount });
    }
    if (eventCount > 0) {
        return t("console.traceSummaryRunning", { count: eventCount });
    }
    return t("console.traceSummaryStarted");
}

function buildEmptyStateText(t, status) {
    if (status === "failed") {
        return t("console.traceEmptyFailed");
    }
    if (status === "cancelled") {
        return t("console.traceEmptyCancelled");
    }
    if (status === "waiting_for_input") {
        return t("console.traceEmptyWaiting");
    }
    if (status === "completed") {
        return t("console.traceEmptyCompleted");
    }
    return t("console.traceEmptyStarted");
}

function buildEmptyState(text) {
    const element = document.createElement("p");
    element.className = "agent-trace-empty";
    element.textContent = text;
    return element;
}

function buildTraceEventCard(t, event, index) {
    const article = document.createElement("article");
    article.className = `agent-trace-event ${resolveTraceEventClassName(event)}`;

    const header = document.createElement("div");
    header.className = "agent-trace-event-header";

    const title = document.createElement("strong");
    title.className = "agent-trace-event-title";
    title.textContent = buildTraceEventTitle(t, event);

    const meta = document.createElement("span");
    meta.className = "muted-text agent-trace-event-meta";
    meta.textContent = buildTraceEventMeta(t, event, index);

    header.appendChild(title);
    header.appendChild(meta);
    article.appendChild(header);

    const summary = buildTraceEventSummary(t, event);
    if (summary) {
        const summaryElement = document.createElement("p");
        summaryElement.className = "agent-trace-event-summary";
        summaryElement.textContent = summary;
        article.appendChild(summaryElement);
    }

    const details = buildTraceEventDetails(event);
    if (details) {
        const detailsElement = document.createElement("pre");
        detailsElement.className = "agent-trace-event-details";
        detailsElement.textContent = details;
        article.appendChild(detailsElement);
    }

    return article;
}

function resolveTraceEventClassName(event) {
    if (event?.event === "turn_completed") {
        if (event?.status === "waiting_for_input") {
            return "";
        }
        return "agent-trace-event-success";
    }
    if (event?.event === "turn_failed" || event?.is_error) {
        return "agent-trace-event-error";
    }
    return "";
}

function buildTraceEventMeta(t, event, index) {
    const parts = [`#${index + 1}`];
    if (Number.isFinite(event?.step)) {
        parts.push(t("console.traceStep", { step: event.step }));
    }
    const timeText = formatTraceTime(event?.created_at);
    if (timeText) {
        parts.push(timeText);
    }
    return parts.join(" · ");
}

function buildTraceEventTitle(t, event) {
    const eventName = String(event?.event || "");
    if (eventName === "turn_started") {
        return t("console.traceTitleStarted");
    }
    if (eventName === "turn_completed") {
        if (event?.status === "waiting_for_input") {
            return t("console.traceTitleWaiting");
        }
        return t("console.traceTitleCompleted");
    }
    if (eventName === "turn_failed") {
        return t("console.traceTitleFailed");
    }
    if (eventName === "assistant_message") {
        const toolCalls = Array.isArray(event?.message?.tool_calls)
            ? event.message.tool_calls
            : [];
        if (toolCalls.length === 1) {
            return buildToolCallTraceTitle(toolCalls[0]?.name);
        }
        if (toolCalls.length > 1) {
            return `[tool-call] ${toolCalls
                .map((item) => String(item?.name || "unknown-tool"))
                .join(", ")}`;
        }
        return t("console.traceTitleAssistantMessage");
    }
    if (eventName === "tool_result") {
        return buildToolResultTraceTitle(
            String(event?.tool_name || "unknown-tool"),
            traceMessageRawContent(event?.message),
        );
    }
    const customTitle = String(event?.title || "").trim();
    if (customTitle) {
        return customTitle;
    }
    return eventName || "trace";
}

function buildTraceEventSummary(t, event) {
    const eventName = String(event?.event || "");
    if (eventName === "turn_started") {
        return t("console.traceEventStarted");
    }
    if (eventName === "assistant_message") {
        const toolCalls = Array.isArray(event?.message?.tool_calls)
            ? event.message.tool_calls
            : [];
        if (toolCalls.length > 0) {
            return t("console.traceToolPlan", { count: toolCalls.length });
        }
        const content = traceMessageText(event?.message).trim();
        if (content) {
            return buildExcerpt(content);
        }
        return t("console.traceAssistantEmpty");
    }
    if (eventName === "tool_result") {
        return event?.is_error ? t("console.traceToolFailed") : t("console.traceToolCompleted");
    }
    if (eventName === "turn_completed") {
        if (event?.status === "waiting_for_input") {
            return t("console.traceTurnWaiting");
        }
        const steps = Number.isFinite(event?.steps) ? event.steps : null;
        if (steps !== null) {
            return t("console.traceTurnCompletedWithSteps", { steps });
        }
        return t("console.traceTurnCompleted");
    }
    if (eventName === "turn_failed") {
        return String(event?.error || t("console.traceTurnFailed"));
    }
    const customSummary = String(event?.summary || "").trim();
    if (customSummary) {
        return customSummary;
    }
    return "";
}

function buildTraceEventDetails(event) {
    const eventName = String(event?.event || "");
    if (eventName === "assistant_message") {
        const toolCalls = Array.isArray(event?.message?.tool_calls)
            ? event.message.tool_calls
            : [];
        if (toolCalls.length > 0) {
            return buildToolCallDetails(toolCalls);
        }
        return traceMessageText(event?.message).trim();
    }
    if (eventName === "tool_result") {
        return formatJsonText(traceMessageRawContent(event?.message));
    }
    if (eventName === "turn_completed") {
        const finalText = traceMessageText(event?.final_message).trim();
        if (finalText) {
            return finalText;
        }
        return "";
    }
    if (eventName === "turn_failed") {
        return String(event?.error || "").trim();
    }
    const customDetails = String(event?.details || "").trim();
    if (customDetails) {
        return customDetails;
    }
    return "";
}

function buildToolCallDetails(toolCalls) {
    return toolCalls
        .map((toolCall) => {
            const toolName = String(toolCall?.name || "unknown-tool");
            const argumentsText = formatJsonText(String(toolCall?.arguments || ""));
            return `${buildToolCallTraceTitle(toolName)}\n${argumentsText}`;
        })
        .join("\n\n");
}

function buildExcerpt(text, maxLength = 120) {
    const cleaned = String(text || "").replace(/\s+/g, " ").trim();
    if (cleaned.length <= maxLength) {
        return cleaned;
    }
    return `${cleaned.slice(0, maxLength - 1).trimEnd()}…`;
}

function formatTraceTime(createdAt) {
    const rawText = String(createdAt || "").trim();
    if (!rawText) {
        return "";
    }
    const date = new Date(rawText);
    if (Number.isNaN(date.getTime())) {
        return rawText;
    }
    const locale = document.documentElement.lang || undefined;
    return date.toLocaleTimeString(locale, { hour12: false });
}

function buildToolCallTraceTitle(toolName) {
    if (SKILL_TOOL_NAMES.has(toolName)) {
        return `[skill-call] ${toolName}`;
    }
    return `[tool-call] ${toolName}`;
}

function buildToolResultTraceTitle(toolName, content) {
    const payload = parseJsonText(content);
    if (!payload || Array.isArray(payload)) {
        return `[tool-result] ${toolName}`;
    }

    const result = payload.result;
    if (!result || Array.isArray(result) || typeof result !== "object") {
        return `[tool-result] ${toolName}`;
    }

    const kind = String(result.kind || "");
    const skillName = String(result.name || "").trim();

    if (toolName === "activate_skill" && kind === "skill_activation") {
        const suffix = result.already_active ? " (already active)" : "";
        return `[skill-activate] ${skillName || "unknown-skill"}${suffix}`;
    }
    if (toolName === "list_skill_resources" && kind === "skill_resource_list") {
        const folderName = String(result.folder || "all").trim() || "all";
        return `[skill-resources] ${skillName || "unknown-skill"} (${folderName})`;
    }
    if (toolName === "read_skill_resource" && kind === "skill_resource_content") {
        const resourcePath = String(result.path || "").trim();
        if (resourcePath) {
            return `[skill-resource] ${skillName || "unknown-skill"} | ${resourcePath}`;
        }
        return `[skill-resource] ${skillName || "unknown-skill"}`;
    }

    return `[tool-result] ${toolName}`;
}

function formatJsonText(text) {
    const parsed = parseJsonText(text);
    if (parsed === null) {
        return text;
    }
    return JSON.stringify(parsed, null, 2);
}

function parseJsonText(text) {
    try {
        return JSON.parse(text);
    } catch (_error) {
        return null;
    }
}

function traceMessageText(message) {
    const explicitText = String(message?.content_text || "").trim();
    if (explicitText) {
        return explicitText;
    }
    return messageContentToText(message?.content);
}

function traceMessageRawContent(message) {
    if (typeof message?.content === "string") {
        return message.content;
    }
    return traceMessageText(message);
}
