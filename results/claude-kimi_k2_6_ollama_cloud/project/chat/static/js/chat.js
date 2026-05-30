document.addEventListener('htmx:wsConnecting', function() {
    console.log('WebSocket connecting');
});

document.addEventListener('htmx:wsOpen', function() {
    console.log('WebSocket open');
});

document.addEventListener('htmx:wsClose', function() {
    console.log('WebSocket closed');
});

document.addEventListener('htmx:wsError', function() {
    console.error('WebSocket error');
});

document.addEventListener('htmx:wsBeforeSend', function(evt) {
    const input = document.getElementById('message-input');
    const content = input.value.trim();
    if (!content) {
        evt.preventDefault();
        return;
    }
    evt.detail.headers = {};
    evt.detail.message = JSON.stringify({type: 'chat.message', content: content});
    input.value = '';
    addMessage('user', content);
    showStreaming();
});

document.addEventListener('htmx:wsAfterMessage', function(evt) {
    try {
        const data = JSON.parse(evt.detail.message);
        if (data.type === 'token') {
            appendToken(data.token);
        } else if (data.type === 'status' && data.status === 'done') {
            finalizeStreaming();
        } else if (data.type === 'error') {
            showError(data.message);
        }
    } catch (e) {
        console.error('Failed to parse message', e);
    }
});

function addMessage(role, content) {
    const messages = document.getElementById('messages');
    const div = document.createElement('div');
    div.className = role === 'user'
        ? 'bg-gray-800 rounded-lg p-3 ml-auto max-w-3xl'
        : 'bg-gray-700 rounded-lg p-3 mr-auto max-w-3xl';
    div.textContent = content;
    messages.appendChild(div);
    scrollToBottom();
}

function showStreaming() {
    const status = document.getElementById('status');
    const content = document.getElementById('streaming-content');
    status.classList.remove('hidden');
    content.classList.remove('hidden');
    content.textContent = '';
    scrollToBottom();
}

function appendToken(token) {
    const content = document.getElementById('streaming-content');
    content.textContent += token;
    scrollToBottom();
}

function finalizeStreaming() {
    const status = document.getElementById('status');
    const content = document.getElementById('streaming-content');
    const text = content.textContent;
    status.classList.add('hidden');
    content.classList.add('hidden');
    content.textContent = '';
    if (text) {
        addMessage('assistant', text);
    }
}

function showError(message) {
    const status = document.getElementById('status');
    const content = document.getElementById('streaming-content');
    status.classList.add('hidden');
    content.classList.add('hidden');
    content.textContent = '';
    addMessage('system', 'Error: ' + message);
}

function scrollToBottom() {
    const container = document.getElementById('chat-container');
    container.scrollTop = container.scrollHeight;
}
