const messagesContainer = document.getElementById('messages');
const queryInput = document.getElementById('query-input');
const sendBtn = document.getElementById('send-btn');

// Fetch the server-generated thread_id on load.
// A new thread_id is created each time the server starts, so restarting
// the server automatically begins a fresh conversation.
let _threadId = null;
async function initSession() {
    try {
        const res = await fetch('/session');
        const data = await res.json();
        _threadId = data.thread_id;
    } catch (e) {
        // Fallback: generate client-side if /session is unreachable
        _threadId = 'conversation_' + new Date().toISOString().replace(/[:.]/g, '-');
    }
}
initSession();

function addMessage(content, isUser = false) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${isUser ? 'user' : 'system'}`;
    const contentDiv = document.createElement('div');
    contentDiv.className = 'content';

    if (typeof marked !== 'undefined') {
        contentDiv.innerHTML = marked.parse(content);
    } else {
        contentDiv.innerHTML = content
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\n/g, '<br>');
    }

    for (let link of contentDiv.getElementsByTagName('a')) {
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
    }

    msgDiv.appendChild(contentDiv);
    messagesContainer.appendChild(msgDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function addThinking() {
    const div = document.createElement('div');
    div.className = 'message system thinking';
    div.id = 'thinking-indicator';
    div.innerHTML = '<div class="content"><em>RoamMate is thinking…</em></div>';
    messagesContainer.appendChild(div);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function removeThinking() {
    const el = document.getElementById('thinking-indicator');
    if (el) el.remove();
}

async function sendQuery() {
    const query = queryInput.value.trim();
    if (!query) return;

    addMessage(query, true);
    queryInput.value = '';
    queryInput.disabled = true;
    addThinking();

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: query,
                thread_id: _threadId
            })
        });

        removeThinking();

        if (!response.ok) {
            const errText = await response.text();
            throw new Error(`Server error ${response.status}: ${errText}`);
        }

        const data = await response.json();
        // API returns { response: string, thread_id: string, phase: string }
        const text = data.response || data.message || JSON.stringify(data);
        addMessage(text);

    } catch (err) {
        removeThinking();
        addMessage(`⚠️ ${err.message}`);
    } finally {
        queryInput.disabled = false;
        queryInput.focus();
    }
}

sendBtn.addEventListener('click', sendQuery);
queryInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendQuery();
});
