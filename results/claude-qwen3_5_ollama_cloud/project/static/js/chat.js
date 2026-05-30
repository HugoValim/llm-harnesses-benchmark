/**
 * Chat WebSocket client - handles real-time streaming from Ollama.
 */

(function() {
    'use strict';

    // DOM elements
    const messagesContainer = document.getElementById('messages-container');
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    const chatForm = document.getElementById('chat-form');
    const connectionStatus = document.getElementById('connection-status');
    const statusText = connectionStatus.querySelector('.status-text');
    const statusIndicator = connectionStatus.querySelector('.status-indicator');
    const typingIndicator = document.getElementById('typing-indicator');
    const modelNameEl = document.getElementById('model-name');
    const errorToast = document.getElementById('error-toast');
    const errorMessage = document.getElementById('error-message');

    // WebSocket connection
    let ws = null;
    let reconnectAttempts = 0;
    const MAX_RECONNECT_ATTEMPTS = 5;
    const RECONNECT_DELAY = 2000;

    // Current streaming state
    let currentMessageEl = null;
    let isStreaming = false;

    // Initialize WebSocket connection
    function initWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/chat/`;

        ws = new WebSocket(wsUrl);

        ws.onopen = function() {
            console.log('WebSocket connected');
            setConnected(true);
            reconnectAttempts = 0;
            enableInput(true);
        };

        ws.onclose = function(event) {
            console.log('WebSocket closed:', event.code, event.reason);
            setConnected(false);
            enableInput(false);

            if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
                reconnectAttempts++;
                setTimeout(initWebSocket, RECONNECT_DELAY);
            } else {
                showError('Connection lost. Please refresh the page.');
            }
        };

        ws.onerror = function(error) {
            console.error('WebSocket error:', error);
            showError('Connection error. Check if the server is running.');
        };

        ws.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                handleMessage(data);
            } catch (e) {
                console.error('Failed to parse message:', e);
            }
        };
    }

    // Handle incoming WebSocket messages
    function handleMessage(data) {
        switch (data.type) {
            case 'connection_ack':
                console.log('Connection acknowledged');
                break;

            case 'response_start':
                isStreaming = true;
                currentMessageEl = createMessageElement('ai');
                messagesContainer.appendChild(currentMessageEl);
                scrollToBottom();
                break;

            case 'token':
                if (currentMessageEl) {
                    const contentEl = currentMessageEl.querySelector('.message-content');
                    contentEl.textContent += data.content;
                    scrollToBottom();
                }
                break;

            case 'response_end':
                isStreaming = false;
                currentMessageEl = null;
                typingIndicator.style.display = 'none';
                break;

            case 'error':
                isStreaming = false;
                typingIndicator.style.display = 'none';
                showError(data.message || 'An error occurred');
                if (data.code === 'ollama_unreachable') {
                    enableInput(false);
                }
                break;

            default:
                console.log('Unknown message type:', data.type);
        }
    }

    // Create a message DOM element
    function createMessageElement(role) {
        const messageEl = document.createElement('div');
        messageEl.className = `message ${role}-message`;
        messageEl.innerHTML = `
            <div class="message-role">${role === 'human' ? 'You' : 'AI'}</div>
            <div class="message-content"></div>
        `;
        return messageEl;
    }

    // Add user message to chat
    function addUserMessage(text) {
        const messageEl = createMessageElement('human');
        messageEl.querySelector('.message-content').textContent = text;
        messagesContainer.appendChild(messageEl);
        scrollToBottom();
    }

    // Scroll to bottom of messages
    function scrollToBottom() {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    // Update connection status UI
    function setConnected(connected) {
        if (connected) {
            statusIndicator.classList.remove('disconnected');
            statusIndicator.classList.add('connected');
            statusText.textContent = 'Connected';
            modelNameEl.textContent = 'Loading...';
            fetchConfig();
        } else {
            statusIndicator.classList.remove('connected');
            statusIndicator.classList.add('disconnected');
            statusText.textContent = 'Disconnected';
            modelNameEl.textContent = '—';
        }
    }

    // Enable/disable input
    function enableInput(enabled) {
        messageInput.disabled = !enabled;
        sendButton.disabled = !enabled || !messageInput.value.trim();
    }

    // Fetch and display model configuration
    function fetchConfig() {
        fetch('/config/')
            .then(r => r.json())
            .then(data => {
                modelNameEl.textContent = data.ollama_model || 'Unknown';
            })
            .catch(err => {
                console.error('Failed to fetch config:', err);
                modelNameEl.textContent = 'Unknown';
            });
    }

    // Show error toast
    function showError(message) {
        errorMessage.textContent = message;
        errorToast.style.display = 'flex';
        setTimeout(() => {
            errorToast.style.display = 'none';
        }, 5000);
    }

    // Dismiss error toast
    window.dismissError = function() {
        errorToast.style.display = 'none';
    };

    // Handle form submission
    chatForm.addEventListener('submit', function(e) {
        e.preventDefault();

        const text = messageInput.value.trim();
        if (!text || !ws || ws.readyState !== WebSocket.OPEN) {
            return;
        }

        // Add user message to UI
        addUserMessage(text);

        // Send to server
        ws.send(JSON.stringify({ message: text }));

        // Clear input
        messageInput.value = '';
        sendButton.disabled = true;

        // Show typing indicator
        typingIndicator.style.display = 'flex';
    });

    // Handle input changes
    messageInput.addEventListener('input', function() {
        sendButton.disabled = !this.value.trim();

        // Auto-resize textarea
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 150) + 'px';
    });

    // Handle Enter key (Shift+Enter for newline)
    messageInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event('submit'));
        }
    });

    // Initialize on page load
    document.addEventListener('DOMContentLoaded', function() {
        initWebSocket();
        enableInput(false);
    });
})();
