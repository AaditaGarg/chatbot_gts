document.addEventListener('DOMContentLoaded', () => {
    const API_BASE = window.API_BASE_URL || '';

    const chatBox = document.getElementById('chat-box');
    const questionInput = document.getElementById('question');
    const sendBtn = document.getElementById('send-btn');
    const clearBtn = document.getElementById('clear-btn');
    const newChatBtn = document.getElementById('new-chat-btn');
    const newUserBtn = document.getElementById('new-user-btn');
    const sessionList = document.getElementById('session-list');
    const chatTitle = document.getElementById('chat-title');
    const userNameEl = document.getElementById('user-name');
    const userIdDisplay = document.getElementById('user-id-display');
    const statusIndicator = document.getElementById('status-indicator');
    const statusText = document.getElementById('status-text');
    const suggestedQuestions = document.getElementById('suggested-questions');
    const sidebar = document.getElementById('sidebar');
    const mobileMenuBtn = document.getElementById('mobile-menu-btn');
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const fileUpload = document.getElementById('file-upload');

    let userId = localStorage.getItem('chat_user_id');
    let sessionId = localStorage.getItem('chat_session_id');
    let displayName = localStorage.getItem('chat_display_name') || 'Guest';
    let isSending = false;

    const api = (path, options = {}) =>
        fetch(`${API_BASE}${path}`, {
            headers: { 'Content-Type': 'application/json', ...options.headers },
            ...options,
        });

    const formatTime = (iso) => {
        if (!iso) return '';
        return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    };

    const truncateId = (id) => (id ? `${id.slice(0, 8)}...` : '');

    const setStatus = (online, label) => {
        statusIndicator.className = `status-dot ${online ? 'online' : 'degraded'}`;
        statusText.textContent = label;
    };

    const updateUserUI = () => {
        userNameEl.textContent = displayName;
        userIdDisplay.textContent = userId ? truncateId(userId) : 'No user';
        userIdDisplay.title = userId || '';
    };

    const appendMessage = (sender, text, options = {}) => {
        const { isLoading = false, sources = [], createdAt = null } = options;
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', `${sender}-message`);

        const avatar = document.createElement('div');
        avatar.classList.add('avatar');
        avatar.innerHTML = sender === 'bot'
            ? '<i class="fas fa-robot"></i>'
            : '<i class="fas fa-user"></i>';

        const textDiv = document.createElement('div');
        textDiv.classList.add('text');

        if (isLoading) {
            textDiv.innerHTML = `
                <div class="loading-indicator">
                    <span class="dot"></span>
                    <span class="dot"></span>
                    <span class="dot"></span>
                </div>`;
        } else {
            textDiv.textContent = text;

            if (sources && sources.length > 0) {
                const sourcesBlock = document.createElement('div');
                sourcesBlock.classList.add('sources-block');
                sourcesBlock.innerHTML = '<div class="sources-label">Sources</div>';
                sources.slice(0, 3).forEach((src) => {
                    const item = document.createElement('div');
                    item.classList.add('source-item');
                    item.textContent = src;
                    sourcesBlock.appendChild(item);
                });
                textDiv.appendChild(sourcesBlock);
            }

            if (createdAt) {
                const timeEl = document.createElement('span');
                timeEl.classList.add('message-time');
                timeEl.textContent = formatTime(createdAt);
                textDiv.appendChild(timeEl);
            }
        }

        messageDiv.appendChild(avatar);
        messageDiv.appendChild(textDiv);
        chatBox.appendChild(messageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
        return messageDiv;
    };

    const clearChatBox = (welcome = true) => {
        chatBox.innerHTML = '';
        if (welcome) {
            appendMessage('bot', 'Hello! How can I help you today?');
        }
    };

    const renderSessions = (sessions) => {
        sessionList.innerHTML = '';
        if (!sessions || sessions.length === 0) {
            sessionList.innerHTML = '<p class="empty-state">No conversations yet</p>';
            return;
        }

        sessions.forEach((s) => {
            const item = document.createElement('div');
            item.classList.add('session-item');
            if (s.session_id === sessionId) item.classList.add('active');
            item.innerHTML = `<i class="fas fa-comment"></i> ${s.title || 'Conversation'}`;
            item.addEventListener('click', () => switchSession(s.session_id, s.title));
            sessionList.appendChild(item);
        });
    };

    const loadSessions = async () => {
        if (!userId) return;
        try {
            const res = await api(`/sessions/${userId}`);
            if (res.ok) {
                const data = await res.json();
                renderSessions(data.sessions);
            }
        } catch (e) {
            console.error('Failed to load sessions:', e);
        }
    };

    const loadHistory = async () => {
        if (!userId || !sessionId) return;
        try {
            const res = await api(`/history/${userId}/${sessionId}`);
            if (!res.ok) return;
            const data = await res.json();
            clearChatBox(false);
            if (data.messages.length === 0) {
                appendMessage('bot', 'New conversation started. Ask me anything!');
                return;
            }
            data.messages.forEach((msg) => {
                appendMessage(msg.role === 'user' ? 'user' : 'bot', msg.content, {
                    sources: msg.sources || [],
                    createdAt: msg.created_at,
                });
            });
            suggestedQuestions.style.display = 'none';
        } catch (e) {
            console.error('Failed to load history:', e);
        }
    };

    const createUser = async (name = 'Guest') => {
        const res = await api('/users', {
            method: 'POST',
            body: JSON.stringify({ display_name: name }),
        });
        if (!res.ok) throw new Error('Could not create user');
        const data = await res.json();
        userId = data.user_id;
        displayName = data.display_name;
        localStorage.setItem('chat_user_id', userId);
        localStorage.setItem('chat_display_name', displayName);
        updateUserUI();
        return data;
    };

    const createSession = async () => {
        const res = await api('/session', {
            method: 'POST',
            body: JSON.stringify({ user_id: userId, title: 'New Conversation' }),
        });
        if (!res.ok) throw new Error('Could not create session');
        const data = await res.json();
        sessionId = data.session_id;
        localStorage.setItem('chat_session_id', sessionId);
        chatTitle.textContent = data.title || 'Support Chat';
        await loadSessions();
        return data;
    };

    const ensureUserAndSession = async () => {
        if (!userId) await createUser(displayName);
        if (!sessionId) await createSession();
    };

    const switchSession = async (newSessionId, title) => {
        sessionId = newSessionId;
        localStorage.setItem('chat_session_id', sessionId);
        chatTitle.textContent = title || 'Support Chat';
        await loadSessions();
        await loadHistory();
        sidebar.classList.remove('open');
    };

    const sendMessage = async (text) => {
        const question = (text || questionInput.value).trim();
        if (!question || isSending) return;

        isSending = true;
        sendBtn.disabled = true;
        suggestedQuestions.style.display = 'none';

        appendMessage('user', question);
        questionInput.value = '';
        questionInput.style.height = 'auto';

        await ensureUserAndSession();

        const botEl = appendMessage('bot', '', { isLoading: true });
        const textDiv = botEl.querySelector('.text');

        try {
            const res = await fetch(`${API_BASE}/chat/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, session_id: sessionId, question }),
            });

            if (!res.ok) {
                let detail = '';
                try {
                    const err = await res.json();
                    detail = err?.detail || err?.message || JSON.stringify(err);
                } catch {
                    detail = `Error ${res.status}`;
                }
                throw new Error(detail);
            }

            textDiv.innerHTML = '';
            textDiv.textContent = '';

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let fullAnswer = '';
            let sources = [];

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const payload = JSON.parse(line.slice(6));
                        if (payload.token) {
                            fullAnswer += payload.token;
                            textDiv.textContent = fullAnswer;
                            chatBox.scrollTop = chatBox.scrollHeight;
                        }
                        if (payload.done) {
                            sources = payload.sources || [];
                        }
                        if (payload.error) {
                            throw new Error(payload.error);
                        }
                    } catch (parseErr) {
                        if (parseErr.message && parseErr.message !== 'Unexpected end of JSON input') {
                            throw parseErr;
                        }
                    }
                }
            }

            if (sources.length > 0) {
                const sourcesBlock = document.createElement('div');
                sourcesBlock.classList.add('sources-block');
                sourcesBlock.innerHTML = '<div class="sources-label">Sources</div>';
                sources.slice(0, 3).forEach((src) => {
                    const item = document.createElement('div');
                    item.classList.add('source-item');
                    item.textContent = src;
                    sourcesBlock.appendChild(item);
                });
                textDiv.appendChild(sourcesBlock);
            }

            await loadSessions();
        } catch (error) {
            if (botEl.parentNode) {
                textDiv.textContent = `Sorry, I couldn't get a response. ${error.message}`;
            } else {
                appendMessage('bot', `Sorry, I couldn't get a response. ${error.message}`);
            }
        } finally {
            isSending = false;
            sendBtn.disabled = false;
            questionInput.focus();
        }
    };

    const clearConversation = async () => {
        if (!userId || !sessionId) return;
        try {
            const res = await api(`/clear/${userId}/${sessionId}`, { method: 'POST' });
            if (!res.ok) {
                let detail = '';
                try {
                    const err = await res.json();
                    detail = err?.detail || err?.message || JSON.stringify(err);
                } catch {
                    try {
                        detail = (await res.text()) || '';
                    } catch {
                        detail = '';
                    }
                }
                throw new Error(detail || `Error ${res.status}`);
            }
            clearChatBox();
            suggestedQuestions.style.display = 'flex';
            await createSession();
            clearChatBox();
            suggestedQuestions.style.display = 'flex';
        } catch (e) {
            appendMessage('bot', 'Could not clear the conversation. Please try again.');
        }
    };

    const checkHealth = async () => {
        try {
            const res = await api('/health');
            if (res.ok) {
                const data = await res.json();
                const allOk = data.redis && data.postgres && data.chromadb;
                setStatus(allOk, allOk ? 'All systems online' : 'Partial connectivity');
            } else {
                setStatus(false, 'Server unreachable');
            }
        } catch {
            setStatus(false, 'Server offline');
        }
    };

    questionInput.addEventListener('input', () => {
        questionInput.style.height = 'auto';
        questionInput.style.height = `${Math.min(questionInput.scrollHeight, 120)}px`;
    });

    questionInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    sendBtn.addEventListener('click', () => sendMessage());
    clearBtn.addEventListener('click', clearConversation);

    newChatBtn.addEventListener('click', async () => {
        await ensureUserAndSession();
        await createSession();
        clearChatBox();
        suggestedQuestions.style.display = 'flex';
        sidebar.classList.remove('open');
    });

    newUserBtn.addEventListener('click', async () => {
        const name = prompt('Enter a display name for the new user:', 'Guest');
        if (name === null) return;
        localStorage.removeItem('chat_session_id');
        sessionId = null;
        await createUser(name.trim() || 'Guest');
        await createSession();
        clearChatBox();
        suggestedQuestions.style.display = 'flex';
    });

    document.querySelectorAll('.suggestion-chip').forEach((chip) => {
        chip.addEventListener('click', () => sendMessage(chip.dataset.q));
    });

    mobileMenuBtn?.addEventListener('click', () => sidebar.classList.toggle('open'));
    sidebarToggle?.addEventListener('click', () => sidebar.classList.toggle('open'));

    fileUpload?.addEventListener('change', async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        await ensureUserAndSession();

        const formData = new FormData();
        formData.append('user_id', userId);
        formData.append('session_id', sessionId);
        formData.append('file', file);

        appendMessage('bot', `Uploading "${file.name}"...`);
        try {
            const res = await fetch(`${API_BASE}/documents/upload`, { method: 'POST', body: formData });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Upload failed');
            appendMessage('bot', data.message || `Indexed ${data.chunk_count} chunks from "${file.name}".`);
        } catch (err) {
            appendMessage('bot', `Upload failed: ${err.message}`);
        }
        fileUpload.value = '';
    });

    const init = async () => {
        updateUserUI();
        await checkHealth();
        try {
            await ensureUserAndSession();
            await loadSessions();
            await loadHistory();
        } catch (e) {
            console.error('Init error:', e);
            appendMessage('bot', 'Could not connect to the server. Make sure the backend is running.');
        }
    };

    init();
});
