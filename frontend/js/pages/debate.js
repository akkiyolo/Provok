/**
 * PROVOK — Debate Room Module
 */
import { api, store, toast } from '../core/app.js';

/**
 * PROVOK — Debate Room Module
 */
import { api, store, toast } from '../core/app.js';

document.addEventListener('DOMContentLoaded', async () => {
    // Extract debate ID from URL path (e.g. /debate/1234-5678-...)
    const pathParts = window.location.pathname.split('/');
    let debateId = pathParts[pathParts.length - 1];
    if (!debateId || debateId === 'debate' || debateId === 'setup') {
        // Fallback for demo if just opening /debate
        debateId = 'demo-debate-id';
    }

    // Connect WebSocket
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/${debateId}`;
    let socket = null;

    function connectWebSocket() {
        socket = new WebSocket(wsUrl);
        
        socket.onopen = () => {
            console.log(`Connected to Debate ${debateId} WS`);
        };
        
        socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.event_type === 'argument_submitted') {
                    appendArgumentToStream(data.payload);
                } else if (data.event_type === 'vote_registered') {
                    // Update vote count UI
                    const argId = data.payload.argument_id;
                    const voteCounter = document.querySelector(`.vote-btn[data-id="${argId}"] .vote-count`);
                    if (voteCounter) {
                        voteCounter.textContent = parseInt(voteCounter.textContent || 0) + 1;
                    }
                } else if (data.event_type === 'new_challenge') {
                    // Prepend to challenge stream
                    toast(`New challenge from ${data.payload.user}: ${data.payload.content.substring(0, 30)}...`, 'info');
                } else if (data.event_type === 'verdict_ready') {
                    toast('Debate concluded! Redirecting to Verdict...', 'success');
                    setTimeout(() => {
                        window.location.href = `/debate/${debateId}/verdict`;
                    }, 3000);
                }
            } catch (e) {
                console.error("Failed to parse WS message", e);
            }
        };

        socket.onclose = () => {
            console.log("WS connection closed. Reconnecting...");
            setTimeout(connectWebSocket, 3000);
        };
    }
    
    // Only connect if it looks like a real UUID debate ID or we want to test WS
    if (debateId !== 'demo-debate-id') {
        connectWebSocket();
    }

    function appendArgumentToStream(argData) {
        const stream = document.querySelector('.argument-stream');
        if (!stream) return;

        const isUserSide = argData.is_ai === false; // Simplified logic

        const argHtml = `
            <div class="argument ${argData.is_ai ? '' : 'user-argument'}">
                <div class="argument-header">
                    <img src="/static/img/avatars/${argData.is_ai ? 'swarm' : 'default'}.webp" alt="Avatar" class="avatar avatar-sm">
                    <span class="argument-author">${argData.is_ai ? 'AI Swarm' : 'You'}</span>
                    <span class="argument-badge badge badge-outline">${argData.type}</span>
                    <span class="argument-time">Just now</span>
                </div>
                <div class="argument-body text-md">
                    ${argData.content}
                </div>
                <div class="argument-footer" style="margin-top: 8px;">
                    <button class="btn btn-sm btn-outline vote-btn" data-id="${argData.id}">
                        <i class="ph ph-thumbs-up"></i> <span class="vote-count">0</span>
                    </button>
                </div>
            </div>
        `;
        stream.insertAdjacentHTML('beforeend', argHtml);
        stream.scrollTop = stream.scrollHeight;
        
        // Re-bind vote buttons
        bindVoteButtons();
    }

    // Submit argument
    const submitBtn = document.getElementById('btn-submit-argument');
    const composeInput = document.getElementById('compose-input');
    
    if (submitBtn && composeInput) {
        submitBtn.addEventListener('click', async () => {
            const content = composeInput.value.trim();
            if (!content) return;
            
            submitBtn.disabled = true;
            toast('Submitting argument...', 'info');
            
            try {
                const response = await api.post(`/debates/${debateId}/turn`, {
                    content: content,
                    argument_type: "OPENING"
                });
                
                if (response) {
                    composeInput.value = '';
                    composeInput.style.height = 'auto';
                }
            } catch (err) {
                console.error("Submit error", err);
            } finally {
                submitBtn.disabled = false;
            }
        });
    }

    // Auto-resize compose textarea
    if (composeInput) {
        composeInput.addEventListener('input', () => {
            composeInput.style.height = 'auto';
            composeInput.style.height = Math.min(composeInput.scrollHeight, 200) + 'px';
        });
    }

    // Timer countdown (display only — server is authoritative)
    let timerSeconds = 154; // 2:34
    const timerDisplay = document.getElementById('timer-display');
    
    setInterval(() => {
        if (timerSeconds > 0) {
            timerSeconds--;
            const mins = Math.floor(timerSeconds / 60);
            const secs = timerSeconds % 60;
            if (timerDisplay) {
                timerDisplay.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
                // Warning states
                const timer = timerDisplay.closest('.timer');
                if (timer) {
                    timer.classList.remove('timer-warning', 'timer-danger');
                    if (timerSeconds <= 30) timer.classList.add('timer-danger');
                    else if (timerSeconds <= 60) timer.classList.add('timer-warning');
                }
            }
        }
    }, 1000);

    // Voting
    function bindVoteButtons() {
        document.querySelectorAll('.vote-btn').forEach(btn => {
            // Remove existing listener to prevent duplicates
            const newBtn = btn.cloneNode(true);
            if(btn.parentNode) btn.parentNode.replaceChild(newBtn, btn);
            
            newBtn.addEventListener('click', async () => {
                const argId = newBtn.getAttribute('data-id');
                if (!argId) return;
                
                try {
                    await api.post(`/debates/${debateId}/vote?argument_id=${argId}`, {});
                    newBtn.classList.add('selected');
                    toast('Vote recorded', 'success');
                } catch (e) {
                    console.error("Vote failed", e);
                }
            });
        });
    }
    bindVoteButtons();

    // Take break
    const breakBtn = document.getElementById('btn-take-break');
    if (breakBtn) {
        breakBtn.addEventListener('click', () => {
            toast('Taking a break — your debate will be saved', 'info');
        });
    }

    // Concede
    const concedeBtn = document.getElementById('btn-concede');
    if (concedeBtn) {
        concedeBtn.addEventListener('click', () => {
            if (confirm('Are you sure you want to concede this debate?')) {
                toast('Concession submitted', 'info');
            }
        });
    }
});
