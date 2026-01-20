const messagesContainer = document.getElementById('messages');
const queryInput = document.getElementById('query-input');
const sendBtn = document.getElementById('send-btn');

// Basic Markdown parser fallback if marked is not loaded
function simpleMarkdown(text) {
    // Bold
    text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Links [text](url)
    text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    // Newlines to <br>
    text = text.replace(/\n/g, '<br>');
    return text;
}

function addMessage(content, isUser = false) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${isUser ? 'user' : 'system'}`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'content';

    // Parse Markdown
    contentDiv.innerHTML = marked.parse(content);

    // Ensure links open in new tab
    const links = contentDiv.getElementsByTagName('a');
    for (let link of links) {
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
    }

    msgDiv.appendChild(contentDiv);
    messagesContainer.appendChild(msgDiv);

    // Scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

async function sendQuery() {
    const query = queryInput.value.trim();
    if (!query) return;

    // Add user message
    addMessage(query, true);
    queryInput.value = '';
    queryInput.disabled = true;

    // Add loading indicator? For now just wait
    // Could add a temporary "Thinking..." message

    try {
        const response = await fetch('/query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ query: query })
        });

        if (!response.ok) {
            throw new Error(`Error: ${response.status}`);
        }

        const data = await response.json();
        const messages = data.messages || [];

        // Display responses
        // We might get multiple messages if the tool calls return stuff, but the current API structure 
        // in main.py seems to return {"messages": [...]}.
        // We'll just JSON stringify complex objects for now if they aren't strings

        // Actually, looking at main.py, it returns whatever client.process_query returns.
        // Assuming it returns a list of strings or message objects.
        // Let's handle string or objects.

        if (Array.isArray(messages)) {
            // Clear current messages to avoid duplication
            messagesContainer.innerHTML = '';

            messages.forEach(msg => {
                let text = '';
                const isUser = msg.role === 'user';

                if (typeof msg.content === 'string') {
                    text = msg.content;
                } else if (Array.isArray(msg.content)) {
                    // Filter out tool_use and tool_result blocks to remove "garbage"
                    text = msg.content
                        .filter(block => block.type === 'text')
                        .map(block => block.text)
                        .join('\n');
                }

                // Only add message if there is actual text content (omits raw tool blocks)
                if (text.trim()) {
                    addMessage(text, isUser);
                }
            });
        }

    } catch (err) {
        addMessage(`Error: ${err.message}`);
    } finally {
        queryInput.disabled = false;
        queryInput.focus();
    }
}

sendBtn.addEventListener('click', sendQuery);

queryInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendQuery();
    }
});
