// UI polish only. All message streaming is handled by the HTMX WebSocket
// extension (hx-ext="ws" / ws-send / ws-connect) in the rendered HTML; nothing
// here opens or reads a WebSocket.
(function () {
  "use strict";

  const form = document.getElementById("chat-form");
  const input = document.getElementById("message-input");
  const messages = document.getElementById("messages");

  function scrollToBottom() {
    if (messages) {
      messages.scrollTop = messages.scrollHeight;
      messages.lastElementChild?.scrollIntoView({ block: "end" });
    }
  }

  // Submit on Enter, allow Shift+Enter for newlines.
  if (input && form) {
    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        if (input.value.trim().length > 0) {
          form.requestSubmit();
        }
      }
    });
  }

  // Clear the composer once HTMX has sent the message over the socket.
  if (form) {
    form.addEventListener("htmx:wsAfterSend", function () {
      if (input) {
        input.value = "";
        input.focus();
      }
    });
  }

  // Keep the latest message in view as tokens stream in.
  document.body.addEventListener("htmx:wsAfterMessage", scrollToBottom);
  document.body.addEventListener("htmx:wsAfterSend", scrollToBottom);
})();
