/** UI polish for the chat composer (not used for WebSocket streaming). */
(function () {
  const input = document.getElementById("message-input");
  const form = document.getElementById("chat-form");
  if (!input || !form) {
    return;
  }

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", () => {
    window.setTimeout(() => {
      input.value = "";
      input.focus();
    }, 0);
  });
})();
