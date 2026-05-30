document.addEventListener("DOMContentLoaded", function () {
    var chatMessages = document.getElementById("chat-messages");
    var emptyState = document.getElementById("empty-state");
    var currentAssistantEl = null;

    function hideEmptyState() {
        if (emptyState) emptyState.style.display = "none";
    }

    function createUserBubble(text) {
        hideEmptyState();
        var div = document.createElement("div");
        div.className = "flex gap-3 justify-end";
        var bubble = document.createElement("div");
        bubble.className = "max-w-[80%] rounded-lg px-4 py-2 text-sm bg-blue-600 text-white";
        bubble.textContent = text;
        div.appendChild(bubble);
        if (chatMessages) {
            chatMessages.appendChild(div);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }

    function getOrCreateAssistantBubble() {
        if (currentAssistantEl) return currentAssistantEl;
        hideEmptyState();
        var div = document.createElement("div");
        div.className = "flex gap-3 justify-start";
        var bubble = document.createElement("div");
        bubble.className = "max-w-[80%] rounded-lg px-4 py-2 text-sm bg-gray-800 text-gray-100";
        div.appendChild(bubble);
        if (chatMessages) {
            chatMessages.appendChild(div);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
        currentAssistantEl = bubble;
        return bubble;
    }

    function appendToken(token) {
        var bubble = getOrCreateAssistantBubble();
        bubble.textContent += token;
        if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function finalizeMessage(content) {
        var bubble = getOrCreateAssistantBubble();
        bubble.textContent = content;
        currentAssistantEl = null;
        if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function showError(error) {
        hideEmptyState();
        var div = document.createElement("div");
        div.className = "flex gap-3 justify-start";
        var bubble = document.createElement("div");
        bubble.className = "max-w-[80%] rounded-lg px-4 py-2 text-sm bg-red-900 text-red-200";
        bubble.textContent = error;
        div.appendChild(bubble);
        if (chatMessages) {
            chatMessages.appendChild(div);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
        currentAssistantEl = null;
    }

    document.body.addEventListener("htmx:wsMessage", function (e) {
        var detail = e.detail;
        if (!detail || !detail.message) return;
        var data;
        try {
            data = JSON.parse(detail.message);
        } catch (ex) {
            return;
        }
        switch (data.type) {
            case "token":
                appendToken(data.content);
                break;
            case "done":
                finalizeMessage(data.content);
                break;
            case "error":
                showError(data.content);
                break;
        }
    });

    var form = document.querySelector("form[ws-send]");
    if (form) {
        form.addEventListener("htmx:wsMessageSent", function () {
            var input = form.querySelector("input[name=message]");
            if (input && input.value) {
                createUserBubble(input.value);
                input.value = "";
            }
        });
    }

    document.body.addEventListener("htmx:wsClose", function () {
        showError("WebSocket disconnected. Reconnecting...");
    });
});