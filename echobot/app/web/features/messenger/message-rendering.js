export function createMessengerMessageRenderer({
    messagesElement,
    emptyStateElement,
    messageRoleLabel,
    scrollThreshold,
}) {
    function appendMessage(role, text, scrollIfNeeded) {
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
        const append = () => {
            setEmptyConversationVisible(false);
            messagesElement?.appendChild(row);
        };
        if (scrollIfNeeded) {
            scrollIfNeeded(append);
        } else {
            append();
        }
        return bubble;
    }

    function setEmptyConversationVisible(isVisible) {
        if (emptyStateElement) {
            emptyStateElement.hidden = !isVisible;
        }
    }

    function isMessagesNearBottom(element = messagesElement) {
        if (!element) {
            return false;
        }
        return element.scrollHeight - element.scrollTop - element.clientHeight
            <= scrollThreshold;
    }

    function scrollMessagesToBottom(element = messagesElement) {
        if (element) {
            element.scrollTop = element.scrollHeight;
        }
    }

    function scrollMessagesIfNearBottom(update, element = messagesElement) {
        if (!element) {
            update?.();
            return;
        }
        const shouldScroll = isMessagesNearBottom(element);
        update?.();
        if (shouldScroll) {
            scrollMessagesToBottom(element);
        }
    }

    function refreshLocalizedLabels() {
        document.querySelectorAll("[data-message-role]").forEach((label) => {
            label.textContent = messageRoleLabel(label.dataset.messageRole);
        });
    }

    return {
        appendMessage,
        isMessagesNearBottom,
        refreshLocalizedLabels,
        scrollMessagesIfNearBottom,
        scrollMessagesToBottom,
        setEmptyConversationVisible,
    };
}
