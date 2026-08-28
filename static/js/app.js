/**
 * Antigravity Hub Bridge WebUI JavaScript Client - Mobile & Desktop
 */

document.addEventListener('DOMContentLoaded', () => {
    // Initialize Lucide Icons
    lucide.createIcons();

    // DOM Elements
    const elements = {
        sidebar: document.getElementById('sidebar'),
        sidebarBackdrop: document.getElementById('sidebar-backdrop'),
        btnToggleSidebar: document.getElementById('btn-toggle-sidebar'),
        btnCloseSidebar: document.getElementById('btn-close-sidebar'),
        btnNewChat: document.getElementById('btn-new-chat'),
        selectModel: document.getElementById('select-model'),
        effortBtns: document.querySelectorAll('.effort-btn'),
        inputWorkspace: document.getElementById('input-workspace'),
        btnSaveWorkspace: document.getElementById('btn-save-workspace'),
        toggleAutoApprove: document.getElementById('toggle-auto-approve'),
        conversationsList: document.getElementById('conversations-list'),
        btnClearHistory: document.getElementById('btn-clear-history'),
        currentModelBadge: document.getElementById('current-model-badge'),
        currentWorkspaceBadge: document.getElementById('current-workspace-badge'),
        statusIndicator: document.getElementById('status-indicator'),
        statusDot: document.getElementById('status-dot'),
        statusText: document.getElementById('status-text'),
        btnCancelTask: document.getElementById('btn-cancel-task'),
        messagesContainer: document.getElementById('messages-container'),
        welcomeCard: document.getElementById('welcome-card'),
        attachmentsTray: document.getElementById('attachments-tray'),
        inputPrompt: document.getElementById('input-prompt'),
        fileUpload: document.getElementById('file-upload'),
        typingIndicator: document.getElementById('typing-indicator'),
        btnSendPrompt: document.getElementById('btn-send-prompt'),
        statLatency: document.getElementById('stat-latency'),
        statTokens: document.getElementById('stat-tokens'),
        btnOpenSystemModal: document.getElementById('btn-open-system-modal'),
        modalSystem: document.getElementById('modal-system'),
        btnCloseModal: document.getElementById('btn-close-modal'),
        modalCpuVal: document.getElementById('modal-cpu-val'),
        modalRamVal: document.getElementById('modal-ram-val'),
        modalDiskVal: document.getElementById('modal-disk-val'),
        whitelistCountBadge: document.getElementById('whitelist-count-badge'),
        inputNewWhitelistId: document.getElementById('input-new-whitelist-id'),
        inputNewWhitelistName: document.getElementById('input-new-whitelist-name'),
        btnAddWhitelist: document.getElementById('btn-add-whitelist'),
        modalWhitelistList: document.getElementById('modal-whitelist-list'),
        quickChips: document.querySelectorAll('.quick-chip'),
    };

    // State
    const state = {
        userId: 0,
        conversationId: null,
        model: 'gemini-3.7-flash-high',
        effort: 'high',
        workspace: '/root',
        autoApprove: true,
        isStreaming: false,
        activeAbortController: null,
        attachments: [], // Array of { filename, saved_path }
    };

    // Global copy code helper
    window.copyCode = function(btn) {
        try {
            const wrapper = btn.closest('.code-block-wrapper');
            const codeEl = wrapper ? wrapper.querySelector('code') : null;
            if (codeEl) {
                navigator.clipboard.writeText(codeEl.innerText).then(() => {
                    btn.innerHTML = '<span>Kopyalandı!</span>';
                    setTimeout(() => {
                        btn.innerHTML = '<i data-lucide="copy" class="w-3 h-3"></i> Kopyala';
                        lucide.createIcons();
                    }, 2000);
                });
            }
        } catch (err) {
            console.error('Copy failed:', err);
        }
    };

    // Configure Marked.js renderer
    const renderer = new marked.Renderer();
    renderer.code = function(code, language) {
        let text = typeof code === 'object' && code !== null ? (code.text || '') : (code || '');
        let lang = typeof code === 'object' && code !== null ? (code.lang || '') : (language || '');
        const validLang = lang && hljs.getLanguage(lang) ? lang : 'plaintext';
        let highlighted = '';
        try {
            highlighted = hljs.highlight(text, { language: validLang, ignoreIllegals: true }).value;
        } catch (e) {
            try {
                highlighted = hljs.highlightAuto(text).value;
            } catch (err) {
                highlighted = escapeHtml(text);
            }
        }
        return `
            <div class="code-block-wrapper">
                <div class="code-block-header">
                    <span>${validLang}</span>
                    <button type="button" class="code-copy-btn" onclick="window.copyCode(this)">
                        <i data-lucide="copy" class="w-3 h-3"></i> Kopyala
                    </button>
                </div>
                <pre><code class="hljs language-${validLang}">${highlighted}</code></pre>
            </div>
        `;
    };

    marked.setOptions({
        renderer: renderer,
        breaks: true,
        gfm: true
    });

    // ---------------- Initial Setup & API Calls ---------------- //

    async function init() {
        await loadStatus();
        await loadConversations();
        setupEventListeners();
        autoResizeTextarea(elements.inputPrompt);
    }

    async function loadStatus() {
        try {
            const res = await fetch('/api/status');
            if (!res.ok) return;
            const data = await res.json();

            // Populate models
            if (data.available_models && data.available_models.length > 0) {
                elements.selectModel.innerHTML = '';
                data.available_models.forEach(m => {
                    const opt = document.createElement('option');
                    opt.value = m;
                    opt.textContent = m;
                    elements.selectModel.appendChild(opt);
                });
            }

            // Sync session
            if (data.session) {
                state.conversationId = data.session.conversation_id;
                state.model = data.session.model || state.model;
                state.effort = data.session.effort || state.effort;
                state.workspace = data.session.workspace || state.workspace;
                state.autoApprove = !!data.session.auto_approve;

                elements.selectModel.value = state.model;
                elements.inputWorkspace.value = state.workspace;
                elements.toggleAutoApprove.checked = state.autoApprove;
                updateEffortUI(state.effort);
                updateBadges();
            }

            // System stats
            if (data.system) {
                updateSystemStatsUI(data.system, data.whitelist_count);
            }
        } catch (e) {
            console.error('Failed to load status:', e);
        }
    }

    function updateBadges() {
        elements.currentModelBadge.textContent = state.model;
        if (elements.currentWorkspaceBadge) {
            elements.currentWorkspaceBadge.textContent = state.workspace;
        }
    }

    function updateEffortUI(effort) {
        state.effort = effort;
        elements.effortBtns.forEach(btn => {
            if (btn.dataset.effort === effort) {
                btn.className = 'effort-btn py-2 sm:py-1 rounded text-center font-medium transition bg-purple-600 text-white shadow-sm touch-manipulation';
            } else {
                btn.className = 'effort-btn py-2 sm:py-1 rounded text-center font-medium transition text-slate-400 hover:text-white touch-manipulation';
            }
        });
    }

    function updateSystemStatsUI(sys, whitelistCount) {
        elements.modalCpuVal.textContent = `${sys.cpu_percent}%`;
        elements.modalRamVal.textContent = `${sys.memory_used_gb} / ${sys.memory_total_gb} GB`;
        elements.modalDiskVal.textContent = `${sys.disk_free_gb} GB (${100 - sys.disk_percent}% boş)`;
        elements.whitelistCountBadge.textContent = `${whitelistCount || 0} Kullanıcı`;
    }

    // ---------------- Mobile Sidebar Helpers ---------------- //

    function openMobileSidebar() {
        if (elements.sidebar) {
            elements.sidebar.classList.remove('-translate-x-full');
        }
        if (elements.sidebarBackdrop) {
            elements.sidebarBackdrop.classList.remove('hidden');
        }
    }

    function closeMobileSidebar() {
        if (elements.sidebar) {
            elements.sidebar.classList.add('-translate-x-full');
        }
        if (elements.sidebarBackdrop) {
            elements.sidebarBackdrop.classList.add('hidden');
        }
    }

    function toggleMobileSidebar() {
        if (elements.sidebar && elements.sidebar.classList.contains('-translate-x-full')) {
            openMobileSidebar();
        } else {
            closeMobileSidebar();
        }
    }

    function maybeCloseMobileSidebar() {
        if (window.innerWidth < 1024) {
            closeMobileSidebar();
        }
    }

    // ---------------- Event Listeners ---------------- //

    function setupEventListeners() {
        // Mobile Sidebar Controls
        if (elements.btnToggleSidebar) {
            elements.btnToggleSidebar.addEventListener('click', toggleMobileSidebar);
        }
        if (elements.btnCloseSidebar) {
            elements.btnCloseSidebar.addEventListener('click', closeMobileSidebar);
        }
        if (elements.sidebarBackdrop) {
            elements.sidebarBackdrop.addEventListener('click', closeMobileSidebar);
        }

        // Keyboard navigation (Esc to close modal or sidebar)
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                closeMobileSidebar();
                if (elements.modalSystem) elements.modalSystem.classList.add('hidden');
            }
        });

        // New Chat
        elements.btnNewChat.addEventListener('click', () => {
            resetChat();
            maybeCloseMobileSidebar();
        });

        // Model Change
        elements.selectModel.addEventListener('change', async (e) => {
            state.model = e.target.value;
            updateBadges();
            await saveSessionSettings();
        });

        // Effort Change
        elements.effortBtns.forEach(btn => {
            btn.addEventListener('click', async () => {
                updateEffortUI(btn.dataset.effort);
                await saveSessionSettings();
            });
        });

        // Workspace Save
        elements.btnSaveWorkspace.addEventListener('click', async () => {
            const ws = elements.inputWorkspace.value.trim();
            if (!ws) return;
            state.workspace = ws;
            updateBadges();
            await saveSessionSettings();
        });

        // Auto Approve Toggle
        elements.toggleAutoApprove.addEventListener('change', async (e) => {
            state.autoApprove = e.target.checked;
            await saveSessionSettings();
        });

        // Clear History
        elements.btnClearHistory.addEventListener('click', async () => {
            if (confirm('Tüm konuşma geçmişini temizlemek istediğinize emin misiniz?')) {
                await fetch('/api/history', { method: 'DELETE' });
                await resetChat();
                await loadConversations();
            }
        });

        // Cancel Task
        elements.btnCancelTask.addEventListener('click', cancelTask);

        // Prompt Input Keydown (Enter to send on desktop, Shift+Enter for newline)
        elements.inputPrompt.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey && window.innerWidth >= 768) {
                e.preventDefault();
                submitPrompt();
            }
        });

        // Send Button Click
        elements.btnSendPrompt.addEventListener('click', submitPrompt);

        // File Upload
        elements.fileUpload.addEventListener('change', handleFileUpload);

        // Modal Controls
        elements.btnOpenSystemModal.addEventListener('click', openSystemModal);
        elements.btnCloseModal.addEventListener('click', () => elements.modalSystem.classList.add('hidden'));
        elements.modalSystem.addEventListener('click', (e) => {
            if (e.target === elements.modalSystem) elements.modalSystem.classList.add('hidden');
        });

        // Whitelist Add
        elements.btnAddWhitelist.addEventListener('click', handleAddWhitelist);

        // Logout Button
        const btnLogout = document.getElementById('btn-logout');
        if (btnLogout) {
            btnLogout.addEventListener('click', async () => {
                await fetch('/api/auth/logout', { method: 'POST' });
                window.location.reload();
            });
        }

        // Quick Action Chips
        elements.quickChips.forEach(chip => {
            chip.addEventListener('click', () => {
                const title = chip.querySelector('.font-semibold').textContent;
                elements.inputPrompt.value = title;
                submitPrompt();
            });
        });
    }

    // ---------------- Session & Chat Functions ---------------- //

    async function saveSessionSettings() {
        try {
            await fetch('/api/session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    user_id: state.userId,
                    model: state.model,
                    effort: state.effort,
                    workspace: state.workspace,
                    auto_approve: state.autoApprove
                })
            });
        } catch (e) {
            console.error('Failed to save session:', e);
        }
    }

    async function resetChat() {
        if (state.isStreaming) {
            cancelTask();
        }
        try {
            await fetch('/api/session/reset', { method: 'POST' });
            state.conversationId = null;
            elements.messagesContainer.innerHTML = '';
            elements.messagesContainer.appendChild(elements.welcomeCard);
            elements.welcomeCard.classList.remove('hidden');
            if (elements.statLatency) elements.statLatency.textContent = '--';
            if (elements.statTokens) elements.statTokens.textContent = '--';
            elements.attachmentsTray.innerHTML = '';
            elements.attachmentsTray.classList.add('hidden');
            state.attachments = [];
            lucide.createIcons();
        } catch (e) {
            console.error('Failed to reset chat:', e);
        }
    }

    async function loadConversations() {
        try {
            const res = await fetch('/api/conversations');
            if (!res.ok) return;
            const data = await res.json();
            elements.conversationsList.innerHTML = '';

            if (!data.conversations || data.conversations.length === 0) {
                elements.conversationsList.innerHTML = '<div class="text-[11px] text-slate-500 text-center py-2">Kayıtlı oturum yok</div>';
                return;
            }

            data.conversations.forEach(c => {
                const item = document.createElement('button');
                item.className = 'w-full text-left p-2.5 sm:p-2 rounded-lg bg-slate-950/50 hover:bg-slate-800/80 active:bg-slate-800 transition text-slate-300 text-xs truncate border border-slate-800/40 flex items-center gap-2 touch-manipulation';
                const snippet = c.title ? c.title.substring(0, 28) + '...' : c.conversation_id.substring(0, 12);
                item.innerHTML = `<i data-lucide="message-square" class="w-3.5 h-3.5 text-purple-400 shrink-0"></i> <span class="truncate">${snippet}</span>`;
                item.addEventListener('click', () => {
                    loadConversationHistory(c.conversation_id);
                    maybeCloseMobileSidebar();
                });
                elements.conversationsList.appendChild(item);
            });
            lucide.createIcons();
        } catch (e) {
            console.error('Failed to load conversations:', e);
        }
    }

    async function loadConversationHistory(convId) {
        try {
            state.conversationId = convId;
            const res = await fetch(`/api/history?conversation_id=${encodeURIComponent(convId)}`);
            if (!res.ok) return;
            const data = await res.json();

            elements.messagesContainer.innerHTML = '';
            elements.welcomeCard.classList.add('hidden');

            data.history.forEach(msg => {
                if (msg.role === 'user') {
                    appendUserMessage(msg.content);
                } else {
                    appendAssistantMessage(msg.content, msg.metadata ? JSON.parse(msg.metadata) : null);
                }
            });
            scrollToBottom();
            lucide.createIcons();
        } catch (e) {
            console.error('Failed to load history:', e);
        }
    }

    // ---------------- Message Sending & SSE Stream ---------------- //

    async function submitPrompt() {
        const text = elements.inputPrompt.value.trim();
        if ((!text && state.attachments.length === 0) || state.isStreaming) return;

        // Build full prompt including attachments if any
        let fullPrompt = text;
        if (state.attachments.length > 0) {
            const attachmentNotes = state.attachments.map(a => `[Ekli Dosya: ${a.saved_path}]`).join('\n');
            fullPrompt = `${attachmentNotes}\n\n${text}`.trim();
        }

        // Hide welcome card
        elements.welcomeCard.classList.add('hidden');

        // Append user bubble
        appendUserMessage(text, state.attachments);

        // Clear input & attachments
        elements.inputPrompt.value = '';
        elements.attachmentsTray.innerHTML = '';
        elements.attachmentsTray.classList.add('hidden');
        state.attachments = [];
        autoResizeTextarea(elements.inputPrompt);

        // Prepare Assistant Streaming Container
        const { messageElement, thinkingContainer, thinkingContent, toolsContainer, responseContent, cursor } = createAssistantStreamingBubble();

        setStreamingState(true);
        const startTime = performance.now();

        state.activeAbortController = new AbortController();

        try {
            const response = await fetch('/api/chat/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                signal: state.activeAbortController.signal,
                body: JSON.stringify({
                    prompt: fullPrompt,
                    user_id: state.userId,
                    conversation_id: state.conversationId,
                    workspace: state.workspace,
                    model: state.model,
                    effort: state.effort,
                    auto_approve: state.autoApprove
                })
            });

            if (!response.ok) {
                const err = await response.text();
                throw new Error(err || 'Stream connection failed');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';
            let accumulatedMarkdown = '';
            let accumulatedThinking = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const chunks = buffer.split('\n\n');
                buffer = chunks.pop(); // keep last incomplete chunk

                for (const chunk of chunks) {
                    if (!chunk.trim()) continue;

                    // Extract all lines in this chunk
                    const chunkLines = chunk.split('\n');
                    let dataStr = '';
                    for (const line of chunkLines) {
                        const trimmed = line.trim();
                        if (trimmed.startsWith('data:')) {
                            dataStr = trimmed.substring(5).trim();
                        }
                    }

                    if (!dataStr) continue;

                    try {
                        const event = JSON.parse(dataStr);
                        const type = event.type;

                        if (type === 'init') {
                            state.conversationId = event.conversation_id;
                        } else if (type === 'step_update') {
                            const stepType = event.step_type;
                            const textDelta = event.text_delta || '';
                            const toolName = event.tool_name;

                            // Handle reasoning / thinking tokens
                            if (stepType === 'thinking' || (event.accumulated_thinking && !toolName)) {
                                accumulatedThinking += textDelta;
                                thinkingContainer.classList.remove('hidden');
                                thinkingContent.textContent = accumulatedThinking;
                            } 
                            // Handle tool execution
                            else if (toolName) {
                                renderToolCard(toolsContainer, toolName, event.tool_info, event.state, event.duration_seconds);
                            } 
                            // Handle text response delta
                            else if (textDelta) {
                                accumulatedMarkdown += textDelta;
                                responseContent.innerHTML = marked.parse(accumulatedMarkdown);
                            }

                            scrollToBottom();
                        } else if (type === 'result') {
                            const finalResp = event.response || accumulatedMarkdown;
                            responseContent.innerHTML = marked.parse(finalResp);
                            if (cursor) cursor.remove();

                            const duration = ((performance.now() - startTime) / 1000).toFixed(1);
                            if (elements.statLatency) elements.statLatency.textContent = `${duration}s`;
                            if (event.usage && event.usage.total_tokens && elements.statTokens) {
                                elements.statTokens.textContent = `${event.usage.total_tokens.toLocaleString()} tok`;
                            }
                            await loadConversations();
                        } else if (type === 'error') {
                            if (cursor) cursor.remove();
                            responseContent.innerHTML += `<div class="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-xs mt-2">❌ Hata: ${escapeHtml(event.error)}</div>`;
                        }
                    } catch (err) {
                        console.error('Error parsing SSE data chunk:', err, dataStr);
                    }
                }
            }

            if (cursor) cursor.remove();
            lucide.createIcons();

        } catch (e) {
            if (e.name !== 'AbortError') {
                if (cursor) cursor.remove();
                responseContent.innerHTML += `<div class="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-xs mt-2">❌ Bağlantı hatası: ${escapeHtml(e.message)}</div>`;
            }
        } finally {
            setStreamingState(false);
            lucide.createIcons();
        }
    }

    function setStreamingState(isStreaming) {
        state.isStreaming = isStreaming;
        if (isStreaming) {
            elements.statusDot.className = 'w-2 h-2 rounded-full bg-purple-400 animate-ping';
            elements.statusText.textContent = 'Çalışıyor...';
            elements.typingIndicator.classList.remove('hidden');
            elements.typingIndicator.classList.add('flex');
            elements.btnCancelTask.classList.remove('hidden');
            elements.btnCancelTask.classList.add('flex');
            elements.btnSendPrompt.disabled = true;
        } else {
            elements.statusDot.className = 'w-2 h-2 rounded-full bg-emerald-400';
            elements.statusText.textContent = 'Hazır';
            elements.typingIndicator.classList.remove('flex');
            elements.typingIndicator.classList.add('hidden');
            elements.btnCancelTask.classList.remove('flex');
            elements.btnCancelTask.classList.add('hidden');
            elements.btnSendPrompt.disabled = false;
        }
    }

    async function cancelTask() {
        if (state.activeAbortController) {
            state.activeAbortController.abort();
        }
        try {
            await fetch('/api/cancel', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: state.userId })
            });
        } catch (e) {
            console.error('Failed to cancel task:', e);
        }
        setStreamingState(false);
    }

    // ---------------- UI Rendering Helpers ---------------- //

    function appendUserMessage(text, attachments = []) {
        const row = document.createElement('div');
        row.className = 'flex justify-end w-full';

        let attachmentsHtml = '';
        if (attachments && attachments.length > 0) {
            attachmentsHtml = `
                <div class="flex flex-wrap gap-1 mb-1.5 justify-end">
                    ${attachments.map(a => `<span class="inline-flex items-center gap-1 text-[10px] bg-purple-900/60 text-purple-200 px-2 py-0.5 rounded border border-purple-500/40"><i data-lucide="paperclip" class="w-3 h-3"></i> ${escapeHtml(a.filename)}</span>`).join('')}
                </div>
            `;
        }

        row.innerHTML = `
            <div class="max-w-[90%] sm:max-w-2xl bg-purple-600 text-white rounded-2xl rounded-tr-sm px-3.5 py-2.5 sm:px-4 sm:py-3 shadow-lg space-y-1">
                ${attachmentsHtml}
                <div class="text-xs sm:text-sm whitespace-pre-wrap leading-relaxed">${escapeHtml(text)}</div>
                <div class="text-[9px] sm:text-[10px] text-purple-200 text-right opacity-70">${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
            </div>
        `;
        elements.messagesContainer.appendChild(row);
        scrollToBottom();
        lucide.createIcons();
    }

    function createAssistantStreamingBubble() {
        const row = document.createElement('div');
        row.className = 'flex items-start gap-2 sm:gap-3 max-w-full sm:max-w-3xl';

        row.innerHTML = `
            <div class="w-7 h-7 sm:w-8 sm:h-8 rounded-xl bg-gradient-to-tr from-purple-600 to-indigo-500 flex items-center justify-center text-white shrink-0 shadow-md mt-1">
                <i data-lucide="bot" class="w-3.5 h-3.5 sm:w-4 sm:h-4"></i>
            </div>
            <div class="flex-1 space-y-2 overflow-hidden min-w-0">
                <!-- Thinking container (collapsible) -->
                <div class="thinking-container hidden bg-slate-900/90 border border-slate-800 rounded-xl overflow-hidden text-xs">
                    <button class="w-full flex items-center justify-between px-3 py-2 text-slate-400 hover:text-purple-300 font-mono text-[10px] sm:text-[11px] bg-slate-950/40 touch-manipulation" onclick="this.nextElementSibling.classList.toggle('hidden')">
                        <span class="flex items-center gap-1.5"><i data-lucide="brain" class="w-3.5 h-3.5 text-purple-400"></i> Düşünme / Akıl Yürütme</span>
                        <i data-lucide="chevron-down" class="w-3 h-3"></i>
                    </button>
                    <div class="thinking-content p-3 text-slate-400 font-mono text-[10px] sm:text-[11px] whitespace-pre-wrap border-t border-slate-800/60 max-h-48 overflow-y-auto"></div>
                </div>

                <!-- Tools container -->
                <div class="tools-container space-y-1.5"></div>

                <!-- Response container -->
                <div class="bg-slate-900 border border-slate-800/80 rounded-2xl rounded-tl-sm p-3.5 sm:p-4 text-slate-100 shadow-md">
                    <div class="response-content markdown-body"></div>
                    <span class="typing-cursor inline-block w-1.5 sm:w-2 h-3.5 sm:h-4 bg-purple-400 animate-pulse ml-0.5 align-middle"></span>
                </div>
            </div>
        `;

        elements.messagesContainer.appendChild(row);
        scrollToBottom();
        lucide.createIcons();

        return {
            messageElement: row,
            thinkingContainer: row.querySelector('.thinking-container'),
            thinkingContent: row.querySelector('.thinking-content'),
            toolsContainer: row.querySelector('.tools-container'),
            responseContent: row.querySelector('.response-content'),
            cursor: row.querySelector('.typing-cursor')
        };
    }

    function appendAssistantMessage(content, metadata) {
        const row = document.createElement('div');
        row.className = 'flex items-start gap-2 sm:gap-3 max-w-full sm:max-w-3xl';
        row.innerHTML = `
            <div class="w-7 h-7 sm:w-8 sm:h-8 rounded-xl bg-gradient-to-tr from-purple-600 to-indigo-500 flex items-center justify-center text-white shrink-0 shadow-md mt-1">
                <i data-lucide="bot" class="w-3.5 h-3.5 sm:w-4 sm:h-4"></i>
            </div>
            <div class="flex-1 bg-slate-900 border border-slate-800/80 rounded-2xl rounded-tl-sm p-3.5 sm:p-4 text-slate-100 shadow-md markdown-body min-w-0">
                ${marked.parse(content || '')}
            </div>
        `;
        elements.messagesContainer.appendChild(row);
        lucide.createIcons();
    }

    function renderToolCard(container, toolName, toolInfo, state, duration) {
        const cardId = `tool-${toolName}-${JSON.stringify(toolInfo || {})}`;
        let card = container.querySelector(`[data-tool-id="${CSS.escape(cardId)}"]`);

        const isRunning = state === 'running';
        const icon = getToolIcon(toolName);
        const argSnippet = getToolArgSnippet(toolName, toolInfo);

        if (!card) {
            card = document.createElement('div');
            card.dataset.toolId = cardId;
            container.appendChild(card);
        }

        card.className = `tool-card ${isRunning ? 'running' : 'completed'}`;
        card.innerHTML = `
            <div class="flex items-center gap-1.5 sm:gap-2 truncate min-w-0">
                <span class="${isRunning ? 'animate-spin text-purple-400' : 'text-emerald-400'} shrink-0">${icon}</span>
                <span class="font-mono font-semibold text-slate-200 text-[11px] sm:text-xs shrink-0">${escapeHtml(toolName)}</span>
                <span class="text-slate-400 truncate text-[10px] sm:text-[11px] font-mono">${escapeHtml(argSnippet)}</span>
            </div>
            <div class="text-[9px] sm:text-[10px] font-mono text-slate-400 shrink-0">
                ${isRunning ? '<span class="text-purple-400 animate-pulse">Çalışıyor</span>' : (duration ? `✅ ${duration.toFixed(1)}s` : '✅')}
            </div>
        `;
        lucide.createIcons();
    }

    function getToolIcon(name) {
        const icons = {
            run_command: '⚡',
            view_file: '📄',
            write_to_file: '📝',
            replace_file_content: '✏️',
            grep_search: '🔍',
            find_by_name: '🔎',
            list_dir: '📁',
            search_web: '🌐'
        };
        return icons[name] || '⚙️';
    }

    function getToolArgSnippet(name, info) {
        if (!info) return '';
        if (name === 'run_command' && info.CommandLine) return info.CommandLine;
        if (info.TargetFile) return info.TargetFile;
        if (info.AbsolutePath) return info.AbsolutePath;
        if (info.query) return info.query;
        return '';
    }

    // ---------------- File Upload Handling ---------------- //

    async function handleFileUpload(e) {
        const files = e.target.files;
        if (!files || files.length === 0) return;

        for (const file of files) {
            const formData = new FormData();
            formData.append('file', file);

            try {
                const res = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });
                if (!res.ok) throw new Error('Upload failed');
                const data = await res.json();

                state.attachments.push({
                    filename: data.filename,
                    saved_path: data.saved_path
                });

                renderAttachmentsTray();
            } catch (err) {
                alert(`Dosya yüklenemedi: ${file.name}`);
            }
        }
        e.target.value = '';
    }

    function renderAttachmentsTray() {
        elements.attachmentsTray.innerHTML = '';
        if (state.attachments.length === 0) {
            elements.attachmentsTray.classList.add('hidden');
            return;
        }

        elements.attachmentsTray.classList.remove('hidden');
        elements.attachmentsTray.classList.add('flex');

        state.attachments.forEach((att, idx) => {
            const pill = document.createElement('div');
            pill.className = 'inline-flex items-center gap-1.5 bg-slate-800 border border-slate-700 text-slate-200 text-xs px-2.5 py-1 rounded-lg shadow-sm';
            pill.innerHTML = `
                <i data-lucide="paperclip" class="w-3 h-3 text-purple-400"></i>
                <span class="truncate max-w-[120px] sm:max-w-[150px] text-[11px]">${escapeHtml(att.filename)}</span>
                <button type="button" class="text-slate-400 hover:text-rose-400 p-0.5 touch-manipulation" onclick="window.removeAttachment(${idx})">
                    <i data-lucide="x" class="w-3 h-3"></i>
                </button>
            `;
            elements.attachmentsTray.appendChild(pill);
        });
        lucide.createIcons();
    }

    window.removeAttachment = function(index) {
        state.attachments.splice(index, 1);
        renderAttachmentsTray();
    };

    // ---------------- Whitelist Management ---------------- //

    async function openSystemModal() {
        maybeCloseMobileSidebar();
        elements.modalSystem.classList.remove('hidden');
        await loadStatus();
        await loadWhitelist();
        lucide.createIcons();
    }

    async function loadWhitelist() {
        try {
            const res = await fetch('/api/whitelist');
            if (!res.ok) return;
            const data = await res.json();
            elements.modalWhitelistList.innerHTML = '';

            if (!data.users || data.users.length === 0) {
                elements.modalWhitelistList.innerHTML = '<div class="text-slate-500 text-center py-2 text-xs">Henüz kullanıcı eklenmedi</div>';
                return;
            }

            data.users.forEach(u => {
                const item = document.createElement('div');
                item.className = 'flex items-center justify-between p-2 rounded-lg bg-slate-900 border border-slate-800 text-xs';
                item.innerHTML = `
                    <div class="flex items-center gap-2 truncate min-w-0">
                        <span class="font-mono text-purple-300 font-semibold shrink-0">${u.user_id}</span>
                        <span class="text-slate-400 truncate">${escapeHtml(u.username || u.full_name || 'İsimsiz')}</span>
                        <span class="px-1.5 py-0.2 rounded bg-slate-800 text-[10px] text-slate-400 shrink-0">${u.role}</span>
                    </div>
                    <button class="text-slate-500 hover:text-rose-400 p-1.5 touch-manipulation" onclick="window.removeWhitelistUser(${u.user_id})">
                        <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
                    </button>
                `;
                elements.modalWhitelistList.appendChild(item);
            });
            lucide.createIcons();
        } catch (e) {
            console.error('Failed to load whitelist:', e);
        }
    }

    async function handleAddWhitelist() {
        const idVal = elements.inputNewWhitelistId.value.trim();
        const nameVal = elements.inputNewWhitelistName.value.trim();
        if (!idVal) return;

        try {
            const res = await fetch('/api/whitelist', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    user_id: parseInt(idVal),
                    username: nameVal,
                    role: 'user'
                })
            });
            if (res.ok) {
                elements.inputNewWhitelistId.value = '';
                elements.inputNewWhitelistName.value = '';
                await loadWhitelist();
            }
        } catch (e) {
            console.error('Failed to add whitelist user:', e);
        }
    }

    window.removeWhitelistUser = async function(userId) {
        if (!confirm(`Kullanıcı ID ${userId} iznini kaldırmak istediğinize emin misiniz?`)) return;
        try {
            await fetch(`/api/whitelist/${userId}`, { method: 'DELETE' });
            await loadWhitelist();
        } catch (e) {
            console.error('Failed to delete whitelist user:', e);
        }
    };

    // ---------------- Utilities ---------------- //

    function autoResizeTextarea(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 140) + 'px';
    }
    elements.inputPrompt.addEventListener('input', () => autoResizeTextarea(elements.inputPrompt));

    function scrollToBottom() {
        elements.messagesContainer.scrollTop = elements.messagesContainer.scrollHeight;
    }

    function escapeHtml(str) {
        if (!str) return '';
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
    }

    // Start App
    init();
});
