document.addEventListener('DOMContentLoaded', () => {
    const chatBox = document.getElementById('chat-box');
    const questionInput = document.getElementById('question');
    const sendBtn = document.getElementById('send-btn');
    const clearBtn = document.getElementById('clear-btn');
    let sessionId = localStorage.getItem('chat_session_id');

    // Function to create a new session on the server
    const createNewSession = async () => {
        try {
            const response = await fetch('/session', { method: 'POST' });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            sessionId = data.session_id;
            localStorage.setItem('chat_session_id', sessionId);
            console.log('New session created:', sessionId);
        } catch (error) {
            console.error('Failed to create new session:', error);
            appendMessage('bot', 'Error: Could not start a new session. Please refresh the page.');
        }
    };

    // Function to ensure a session exists
    const ensureSession = async () => {
        if (!sessionId) {
            await createNewSession();
        }
    };

    // Function to append a message to the chat box
    const appendMessage = (sender, text, isLoading = false) => {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', `${sender}-message`);

        const avatar = document.createElement('div');
        avatar.classList.add('avatar');
        avatar.innerHTML = sender === 'bot' ? '<i class="fas fa-robot"></i>' : '<i class="fas fa-user"></i>';
        
        const textDiv = document.createElement('div');
        textDiv.classList.add('text');

        if (isLoading) {
            textDiv.innerHTML = `
                <div class="loading-indicator">
                    <span class="dot"></span>
                    <span class="dot"></span>
                    <span class="dot"></span>
                </div>
            `;
        } else {
            textDiv.textContent = text;
        }

        messageDiv.appendChild(avatar);
        messageDiv.appendChild(textDiv);
        chatBox.appendChild(messageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
        return messageDiv;
    };

    // Function to handle sending a message
    const sendMessage = async () => {
        const question = questionInput.value.trim();
        if (!question) return;

        appendMessage('user', question);
        questionInput.value = '';
        const loadingIndicator = appendMessage('bot', '', true);

        await ensureSession();

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: question, session_id: sessionId })
            });

            chatBox.removeChild(loadingIndicator);

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            
            if (data.error) {
                appendMessage('bot', `Sorry, an error occurred: ${data.error}`);
            } else {
                appendMessage('bot', data.answer);
            }

        } catch (error) {
            console.error('Error sending message:', error);
            chatBox.removeChild(loadingIndicator);
            appendMessage('bot', `Sorry, I couldn't get a response. Error: ${error.message}`);
        }
    };

    // Function to clear conversation
    const clearConversation = async () => {
        if (!sessionId) return;
        try {
            await fetch(`/clear/${sessionId}`, { method: 'POST' });
            chatBox.innerHTML = ''; // Clear UI
            appendMessage('bot', 'Conversation cleared. How can I help you now?');
            // We can start a new session or keep the old one
            await createNewSession(); // Start a fresh session
            chatBox.innerHTML = '';
            appendMessage('bot', 'New conversation started. Ask me anything!');

        } catch (error) {
            console.error('Failed to clear conversation:', error);
            appendMessage('bot', 'Error: Could not clear the conversation on the server.');
        }
    };

    // Event Listeners
    sendBtn.addEventListener('click', sendMessage);
    questionInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });
    clearBtn.addEventListener('click', clearConversation);

    // Initialize session on load
    ensureSession();
});
