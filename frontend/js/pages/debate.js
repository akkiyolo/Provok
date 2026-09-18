/**
 * PROVOK — Debate Room Module
 * Multi-round progression (all 4 rounds), autonomous Agent-vs-Agent spectator mode,
 * AI thinking indicators, dynamic rounds track, and real-time WebSockets.
 */
import { api, store, toast, timeAgo } from '../core/app.js';

// ── Helpers ─────────────────────────────────────────────────────
const PHASE_LABELS = {
    OPENING: 'OPENING · Make your strongest case',
    REBUTTAL: 'REBUTTAL · Attack the strongest argument',
    CROSS_EXAMINATION: 'CROSS EXAMINATION · Challenge the evidence',
    CLOSING: 'CLOSING · Make your final case',
};

const PHASE_PLACEHOLDERS = {
    OPENING: 'Write your opening statement (Round 1)…',
    REBUTTAL: 'Write your rebuttal countering the opponent (Round 2)…',
    CROSS_EXAMINATION: 'Ask a pointed question or cross-examine claims (Round 3)…',
    CLOSING: 'Write your decisive closing statement (Round 4)…',
};

function renderRounds(totalRounds, currentRound, isCompleted = false) {
    const track = document.getElementById('rounds-track');
    if (!track) return;
    track.innerHTML = '';
    for (let i = 1; i <= totalRounds; i++) {
        const span = document.createElement('span');
        if (isCompleted || i < currentRound) {
            span.className = 'round done';
        } else if (i === currentRound) {
            span.className = 'round active';
        } else {
            span.className = 'round';
        }
        track.appendChild(span);
    }
}

let isCurrentDebateAiVsAi = false;
const sideMap = {};

function renderArgument(arg, animate = true) {
    const stream = document.getElementById('argument-stream');
    if (!stream) return;

    // Deduplicate by ID
    if (arg.id && stream.querySelector(`[data-id="${arg.id}"]`)) {
        return;
    }

    // Remove empty placeholder and loading states
    const ph = document.getElementById('empty-placeholder');
    if (ph) ph.remove();
    const loadingState = document.getElementById('loading-state');
    if (loadingState) loadingState.remove();

    // Remove any thinking indicator
    const thinking = stream.querySelector('.ai-thinking');
    if (thinking) thinking.remove();

    const isAI = isCurrentDebateAiVsAi || arg.is_ai === true || arg.participant_type === 'AI_SWARM' || arg.participant_type === 'AI_AGENT';
    const sideLabel = (arg.side || sideMap[arg.side_id] || 'FOR').toUpperCase();
    const sideClass = sideLabel === 'FOR' ? 'for' : 'against';
    
    let speakerName = arg.agent_name;
    if (!speakerName) {
        if (isAI || isCurrentDebateAiVsAi) {
            speakerName = sideLabel === 'AGAINST' ? 'Agent AGAINST' : 'Agent FOR';
        } else {
            speakerName = arg.author_name || 'You';
        }
    }

    const argType = (arg.argument_type || arg.type || 'OPENING').replace(/_/g, ' ');
    
    // Clean any scratchpad/thinking tokens
    let rawContent = arg.content || '';
    if (rawContent.includes('</think>')) {
        rawContent = rawContent.split('</think>').pop().trim();
    } else {
        rawContent = rawContent.replace(/<think>[\s\S]*?<\/think>/gi, '').trim();
        if (rawContent.startsWith('<think>')) {
            rawContent = rawContent.replace(/<think>/g, '').trim();
        }
    }
    const content = rawContent.replace(/\n/g, '<br>');
    const time = arg.created_at ? timeAgo(arg.created_at) : 'Now';

    const avatarBg = sideClass === 'for' ? 'var(--yellow)' : 'var(--blue)';
    const avatarColor = '#fff';

    const el = document.createElement('div');
    el.className = `argument ${sideClass} fade-in`;
    if (animate) el.style.animationDelay = '0.05s';
    el.dataset.id = arg.id || '';
    el.innerHTML = `
        <div class="argument-head">
            <div class="speaker">
                <div style="width:32px;height:32px;border-radius:50%;background:${avatarBg};color:${avatarColor};display:grid;place-items:center;font-weight:700;font-size:11px;flex:none">
                    ${isAI ? '⚡' : speakerName[0].toUpperCase()}
                </div>
                <div>
                    <div class="speaker-name" style="font-weight:600;">${speakerName}</div>
                    <div class="side" style="font-size:11px;color:var(--muted);">${sideLabel}</div>
                </div>
            </div>
            <div class="argument-type" style="font-size:10px;text-transform:uppercase;letter-spacing:.05em;background:var(--paper-2);padding:3px 8px;border-radius:var(--radius-sm);">${argType}</div>
        </div>
        <div class="argument-body" style="margin-top:12px;line-height:1.65;font-size:15px;">${content}</div>
        <div class="argument-foot" style="margin-top:14px;display:flex;justify-content:space-between;align-items:center;font-size:11px;color:var(--muted);">
            <span>${time}</span>
            <div class="reaction-row">
                <button class="dark-btn vote-btn" data-id="${arg.id || ''}" style="padding:2px 8px;font-size:11px;">👍 <span class="vote-count">0</span></button>
            </div>
        </div>`;
    stream.appendChild(el);
    stream.scrollTo({ top: stream.scrollHeight, behavior: 'smooth' });
}

function showAgentThinking(label = 'AI is preparing an argument…') {
    const stream = document.getElementById('argument-stream');
    if (!stream) return;
    
    // Remove existing
    const existing = stream.querySelector('.ai-thinking');
    if (existing) existing.remove();

    const el = document.createElement('div');
    el.className = 'ai-thinking fade-in';
    el.innerHTML = `
        <div style="width:32px;height:32px;border-radius:50%;background:var(--ink);color:var(--paper);display:grid;place-items:center;font-size:13px;flex:none">⚡</div>
        <div>
            <div class="ai-thinking-label" style="font-size:13px;font-weight:500;">${label}</div>
            <div class="thinking-dots"><span></span><span></span><span></span></div>
        </div>
    `;
    stream.appendChild(el);
    stream.scrollTo({ top: stream.scrollHeight, behavior: 'smooth' });
}

function renderParticipants(debate) {
    const list = document.getElementById('participants-list');
    if (!list) return;

    const isAgentVsAgent = debate.opponent_type === 'AI_VS_AI';

    if (isAgentVsAgent) {
        list.innerHTML = `
            <div class="participant">
                <div class="avatar avatar-ai" style="width:32px;height:32px;font-size:12px;background:var(--yellow);color:#fff">⚡</div>
                <div>
                    <div style="font-weight:700;font-size:13px">Agent FOR</div>
                    <small class="side" style="color:var(--yellow);font-weight:600;">FOR Side</small>
                </div>
            </div>
            <div class="participant" style="margin-top:8px;">
                <div class="avatar avatar-ai" style="width:32px;height:32px;font-size:12px;background:var(--blue);color:#fff">⚡</div>
                <div>
                    <div style="font-weight:700;font-size:13px">Agent AGAINST</div>
                    <small class="side" style="color:var(--blue);font-weight:600;">AGAINST Side</small>
                </div>
            </div>
        `;
        return;
    }

    const seen = new Set();
    const participants = [];
    
    if (debate.rounds) {
        for (const round of debate.rounds) {
            if (round.arguments) {
                for (const arg of round.arguments) {
                    const key = arg.participant_id || arg.side;
                    if (!seen.has(key)) {
                        seen.add(key);
                        const isAI = arg.is_ai || arg.participant_type === 'AI_SWARM';
                        participants.push({
                            name: isAI ? 'AI Swarm' : (arg.author_name || 'You'),
                            side: arg.side || '',
                            isAI,
                        });
                    }
                }
            }
        }
    }

    if (participants.length === 0) {
        const user = store.get('user');
        participants.push({ name: user ? user.username : 'You', side: 'FOR', isAI: false });
        participants.push({ name: 'AI Swarm', side: 'AGAINST', isAI: true });
    }

    list.innerHTML = participants.map(p => `
        <div class="participant">
            <div class="avatar${p.isAI ? ' avatar-ai' : ''}" style="width:32px;height:32px;font-size:12px">
                ${p.isAI ? '⚡' : p.name[0].toUpperCase()}
            </div>
            <div>
                <div style="font-weight:700;font-size:13px">${p.name}</div>
                <small class="side">${p.side}</small>
            </div>
        </div>
    `).join('');
}

function renderVoteButtons() {
    const voteButtons = document.getElementById('vote-buttons');
    if (!voteButtons) return;
    voteButtons.innerHTML = `
        <button class="dark-btn" style="border-color:var(--yellow);color:var(--yellow);font-weight:600;">VOTE FOR</button>
        <button class="dark-btn" style="border-color:var(--blue);color:var(--blue);font-weight:600;">VOTE AGAINST</button>
    `;
    voteButtons.querySelectorAll('button').forEach(btn => {
        btn.addEventListener('click', () => toast('Vote recorded for this round!', 'success'));
    });
}

// ── Main ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    const pathParts = window.location.pathname.split('/').filter(Boolean);
    const debateId = pathParts[pathParts.length - 1];

    if (!debateId || debateId === 'debate') {
        const qEl = document.getElementById('debate-question');
        if (qEl) qEl.textContent = 'No debate ID found.';
        return;
    }

    // ── Load debate from API ─────────────────────────────────────
    let debate = null;
    try {
        debate = await api.get(`/debates/${debateId}`);
    } catch (err) {
        toast('Could not load debate: ' + (err.message || 'Unknown error'), 'error');
        return;
    }

    const isAgentVsAgent = debate.opponent_type === 'AI_VS_AI';
    isCurrentDebateAiVsAi = isAgentVsAgent;
    const isCompleted = debate.status === 'COMPLETED' || debate.status === 'DebateStatus.COMPLETED';

    // ── Populate header ──────────────────────────────────────────
    const titleEl = document.getElementById('debate-question');
    if (titleEl) titleEl.textContent = debate.title || 'Untitled Debate';
    document.title = `${debate.title || 'Debate'} — PROVOK`;

    const totalRounds = 4;
    let currentRound = debate.current_round || 1;
    renderRounds(totalRounds, currentRound, isCompleted);

    const updateRoundUI = (rnd, phaseName) => {
        currentRound = rnd;
        const phaseLabel = document.getElementById('round-label');
        if (phaseLabel) {
            if (isCompleted) {
                phaseLabel.textContent = `DEBATE COMPLETED · ALL 4 ROUNDS CONCLUDED`;
            } else {
                phaseLabel.textContent = `ROUND ${rnd} / ${totalRounds} · ${PHASE_LABELS[phaseName] || phaseName}`;
            }
        }
        renderRounds(totalRounds, rnd, isCompleted);

        const composeInput = document.getElementById('compose-input');
        if (composeInput && !isAgentVsAgent) {
            composeInput.placeholder = PHASE_PLACEHOLDERS[phaseName] || 'Write your argument…';
        }
    };

    const initialPhase = (debate.rounds && debate.rounds[0] && debate.rounds[0].phase) || 'OPENING';
    updateRoundUI(currentRound, initialPhase);

    const watcherEl = document.getElementById('debate-watchers');
    if (watcherEl) watcherEl.textContent = `${debate.viewer_count || 1} watching`;

    // Status badge
    const statusBadge = document.getElementById('debate-status-badge');
    if (statusBadge) {
        if (isCompleted) {
            statusBadge.className = 'badge badge-completed';
            statusBadge.textContent = 'COMPLETED';
        } else if (isAgentVsAgent) {
            statusBadge.className = 'badge';
            statusBadge.style.background = 'rgba(224,90,43,0.2)';
            statusBadge.style.color = 'var(--red)';
            statusBadge.textContent = 'AGENT VS AGENT';
        }
    }

    // ── UI Controls & Spectator Mode ─────────────────────────────
    const composeSection = document.querySelector('.compose');
    const spectatorBanner = document.getElementById('spectator-mode-banner');
    const finishedBanner = document.getElementById('debate-finished-banner');
    const verdictLinkBtn = document.getElementById('verdict-link-btn');

    if (verdictLinkBtn) {
        verdictLinkBtn.href = `/debate/${debateId}/verdict`;
    }

    const showCompletedState = () => {
        if (composeSection) composeSection.style.display = 'none';
        if (spectatorBanner) spectatorBanner.style.display = 'none';
        if (finishedBanner) finishedBanner.style.display = 'block';
        if (statusBadge) {
            statusBadge.className = 'badge badge-completed';
            statusBadge.textContent = 'COMPLETED';
        }
        renderRounds(totalRounds, 4, true);
        const phaseLabel = document.getElementById('round-label');
        if (phaseLabel) phaseLabel.textContent = `DEBATE COMPLETED · ALL 4 ROUNDS CONCLUDED`;
    };

    if (isCompleted) {
        showCompletedState();
    } else if (isAgentVsAgent) {
        // Hide human compose box, show spectator banner
        if (composeSection) composeSection.style.display = 'none';
        if (spectatorBanner) spectatorBanner.style.display = 'flex';
    } else {
        // Human vs AI or Human vs Human
        let currentUser = store.get('user');
        if (!currentUser) {
            try {
                currentUser = await api.request('GET', '/auth/me', null, { noRedirect: true });
            } catch (e) {}
        }
        const isOwner = !debate.creator_id || !currentUser || (currentUser.id === debate.creator_id || currentUser.is_admin);
        if (composeSection) {
            composeSection.style.display = isOwner ? 'block' : 'none';
        }
    }

    // ── Populate sidebar ─────────────────────────────────────────
    renderParticipants(debate);
    renderVoteButtons();

    // ── Render existing arguments ────────────────────────────────
    const loadingState = document.getElementById('loading-state');
    if (loadingState) loadingState.remove();

    if (debate.rounds && debate.rounds.length > 0) {
        for (const round of debate.rounds) {
            if (round.arguments) {
                for (const arg of round.arguments) {
                    renderArgument(arg, false);
                }
            }
        }
    }

    // Empty state
    const stream = document.getElementById('argument-stream');
    if (stream && stream.querySelectorAll('.argument').length === 0) {
        if (isCompleted) {
            // Completed, banner handles it
        } else {
            const placeholder = document.createElement('div');
            placeholder.id = 'empty-placeholder';
            placeholder.className = 'fade-in';
            placeholder.style.cssText = 'color:var(--muted);padding:40px 28px;font-size:14px;line-height:1.7';
            
            if (isAgentVsAgent) {
                placeholder.textContent = 'Autonomous debate in progress. Agents are preparing arguments…';
                showAgentThinking('Agent FOR is preparing opening statement…');
            } else {
                placeholder.textContent = 'The debate floor is open. Make your opening argument below.';
            }
            stream.appendChild(placeholder);
        }
    }

    // ── WebSocket Real-time updates ──────────────────────────────
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/${debateId}`;
    let socket = null;
    let pingInterval = null;

    function connectWebSocket() {
        socket = new WebSocket(wsUrl);
        socket.onopen = () => {
            console.log(`WS connected to debate ${debateId}`);
            if (pingInterval) clearInterval(pingInterval);
            pingInterval = setInterval(() => {
                if (socket && socket.readyState === WebSocket.OPEN) {
                    socket.send('ping');
                }
            }, 20000);
        };

        socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                const eventType = data.event_type;
                const payload = data.payload || {};

                if (eventType === 'agent_debate_started') {
                    const ph = document.getElementById('empty-placeholder');
                    if (ph) ph.remove();
                    showAgentThinking('Agent FOR is preparing opening statement…');
                } else if (eventType === 'argument_submitted') {
                    const ph = document.getElementById('empty-placeholder');
                    if (ph) ph.remove();
                    renderArgument(payload);
                } else if (eventType === 'agent_thinking') {
                    const agentName = payload.agent || 'AI Agent';
                    const phase = (payload.phase || 'argument').replace(/_/g, ' ');
                    showAgentThinking(`${agentName} is preparing ${phase}…`);
                    const spectatorStatus = document.getElementById('spectator-status-text');
                    if (spectatorStatus) {
                        spectatorStatus.textContent = `${agentName} is preparing ${phase}…`;
                    }
                } else if (eventType === 'round_advanced') {
                    const nextRnd = payload.round_number || (currentRound + 1);
                    const nextPhase = payload.phase || 'REBUTTAL';
                    updateRoundUI(nextRnd, nextPhase);
                    toast(`Advanced to Round ${nextRnd}: ${nextPhase}`, 'info');
                } else if (eventType === 'debate_completed') {
                    showCompletedState();
                    toast('Debate concluded! Read the final verdict.', 'success');
                } else if (eventType === 'verdict_ready') {
                    showCompletedState();
                    toast('Verdict ready! Redirecting in 3s…', 'success');
                    setTimeout(() => { window.location.href = `/debate/${debateId}/verdict`; }, 3000);
                }
            } catch (e) {
                console.error('Failed to parse WS message', e);
            }
        };

        socket.onclose = () => {
            if (pingInterval) clearInterval(pingInterval);
            console.log('WS closed, reconnecting in 2s…');
            setTimeout(connectWebSocket, 2000);
        };
    }
    connectWebSocket();

    // ── Submit argument (Human mode) ─────────────────────────────
    const submitBtn = document.getElementById('btn-submit-argument');
    const composeInput = document.getElementById('compose-input');
    if (submitBtn && composeInput) {
        const doSubmit = async () => {
            const content = composeInput.value.trim();
            if (!content) { toast('Write something first!', 'error'); return; }
            submitBtn.disabled = true;
            submitBtn.classList.add('loading');
            try {
                const arg = await api.post(`/debates/${debateId}/turn`, {
                    content,
                    argument_type: 'OPENING', // Backend automatically adjusts by round
                });
                const ph = document.getElementById('empty-placeholder');
                if (ph) ph.remove();
                renderArgument(arg);
                composeInput.value = '';
                composeInput.style.height = 'auto';
                toast('Argument submitted!', 'success');
                
                showAgentThinking('AI Swarm is analyzing and preparing rebuttal…');
            } catch (err) {
                toast(err.message || 'Failed to submit argument', 'error');
            } finally {
                submitBtn.disabled = false;
                submitBtn.classList.remove('loading');
                submitBtn.textContent = 'Submit';
            }
        };

        submitBtn.addEventListener('click', doSubmit);
        composeInput.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') doSubmit();
        });
        composeInput.addEventListener('input', () => {
            composeInput.style.height = 'auto';
            composeInput.style.height = Math.min(composeInput.scrollHeight, 200) + 'px';
        });
    }

    // ── Save & leave ─────────────────────────────────────────────
    const breakBtn = document.getElementById('btn-take-break');
    if (breakBtn) {
        breakBtn.addEventListener('click', () => {
            toast('Progress saved — you can return anytime', 'info');
            setTimeout(() => { window.location.href = '/'; }, 1500);
        });
    }
});
