/**
 * WebSocket chat client with HTMX partial update support.
 */

(function () {
  "use strict";

  let ws = null;
  let isConnected = false;
  let pendingUserMessage = null;

  const messagesContainer = document.getElementById("chat-messages");
  const messageInput = document.getElementById("message-input");
  const sendButton = document.getElementById("send-button");

  function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  function setInputEnabled(enabled) {
    messageInput.disabled = !enabled;
    sendButton.disabled = !enabled;
  }

  function clearEmptyState() {
    const empty = messagesContainer.querySelector(".empty-state");
    if (empty) {
      empty.remove();
    }
  }

  function createUserMessageDiv(content) {
    const div = document.createElement("div");
    div.className = "message user";
    div.setAttribute("data-role", "user");
    div.textContent = content;
    return div;
  }

  function createAssistantDiv() {
    const div = document.createElement("div");
    div.className = "message assistant streaming";
    div.setAttribute("data-role", "assistant");
    div.setAttribute("data-streaming", "true");
    div.textContent = "";
    return div;
  }

  function createTypingIndicator() {
    const div = document.createElement("div");
    div.className = "typing-indicator";
    div.innerHTML = "<span></span><span></span><span></span>";
    return div;
  }

  function removeTypingIndicator() {
    const typing = messagesContainer.querySelector(".typing-indicator");
    if (typing) {
      typing.remove();
    }
  }

  function appendAssistantChunk(chunk, assistantDiv) {
    assistantDiv.textContent += chunk;
    scrollToBottom();
  }

  function finalizeAssistantDiv(assistantDiv) {
    assistantDiv.classList.remove("streaming");
    assistantDiv.removeAttribute("data-streaming");
    scrollToBottom();
  }

  function showError(content) {
    const div = document.createElement("div");
    div.className = "message error";
    div.textContent = "Error: " + content;
    messagesContainer.appendChild(div);
    scrollToBottom();
  }

  function connect() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = protocol + "//" + window.location.host + "/ws/chat/";

    ws = new WebSocket(wsUrl);

    ws.onopen = function () {
      isConnected = true;
    };

    ws.onmessage = function (event) {
      const data = JSON.parse(event.data);

      if (data.type === "text") {
        removeTypingIndicator();
        if (!pendingUserMessage) return;
        const userDiv = createUserMessageDiv(pendingUserMessage);
        messagesContainer.appendChild(userDiv);
        pendingUserMessage = null;

        const assistantDiv = createAssistantDiv();
        messagesContainer.appendChild(assistantDiv);
        appendAssistantChunk(data.content, assistantDiv);
      } else if (data.type === "error") {
        removeTypingIndicator();
        if (pendingUserMessage) {
          showError(data.content);
          pendingUserMessage = null;
        } else {
          showError(data.content);
        }
        setInputEnabled(true);
      } else if (data.type === "done") {
        const assistantDivs = messagesContainer.querySelectorAll(
          ".message.assistant[data-streaming='true']"
        );
        assistantDivs.forEach(finalizeAssistantDiv);
        setInputEnabled(true);
      }
    };

    ws.onclose = function () {
      isConnected = false;
      setInputEnabled(true);
    };

    ws.onerror = function () {
      isConnected = false;
    };
  }

  function sendMessage(text) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      showError("WebSocket not connected");
      return;
    }

    pendingUserMessage = text;
    setInputEnabled(false);
    messagesContainer.appendChild(createTypingIndicator());
    scrollToBottom();

    ws.send(JSON.stringify({ message: text }));
  }

  sendButton.addEventListener("click", function () {
    const text = messageInput.value.trim();
    if (!text) return;

    clearEmptyState();
    messageInput.value = "";
    sendMessage(text);
  });

  messageInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendButton.click();
    }
  });

  messageInput.addEventListener("input", function () {
    messageInput.style.height = "auto";
    messageInput.style.height = Math.min(messageInput.scrollHeight, 200) + "px";
  });

  connect();
})();