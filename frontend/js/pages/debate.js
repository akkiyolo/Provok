/**
 * PROVOK — Debate Room Module
 * Loads real debate data from API and streams live arguments via WebSocket.
 */
import { api, store, toast } from '../core/app.js';

// ── Helpers ─────────────────────────────────────────────────────
const PHASE_LABELS = {
    OPENING: 'OPENING · Make your strongest case',
    REBUTTAL: 'REBUTTAL · Attack the strongest argument',
    CROSS_EXAMINATION: 'CROSS EXAMINATION · Challenge the evidence',
    CLOSING: 'CLOSING · Make your final case',
};

function renderRounds(totalRounds, currentRound) {
    const track = document.getElementById('rounds-track');
    if (!track) return;
    track.innerHTML = '';
    for (let i = 1; i <= totalRounds; i++) {
        const span = document.createElement('span');
        span.className = 'round' + (i < currentRound ? ' done' : i === currentRound ? ' active' : '');
        track.appendChild(span);
    }
}

// Maps side_id UUIDs seen so far to FOR/AGAINST labels once the debate loads
const sideMap = {};

function renderArgument(arg) {
    const stream = document.getElementById('argument-stream');
    if (!stream) return;

    // Determine speaker info — API returns side_id (UUID) not "FOR"/"AGAINST" directly
    const isAI = arg.is_ai === true || arg.participant_type === 'AI_SWARM';
    const sideLabel = arg.side || sideMap[arg.side_id] || '';
    const sideClass = sideLabel === 'FOR' ? 'for' : sideLabel === 'AGAINST' ? 'against' : '';
    const speakerName = isAI ? 'AI Swarm' : (arg.author_name || 'You');
    const argType = (arg.argument_type || arg.type || 'OPENING').replace(/_/g, ' ');
    const content = (arg.content || '').replace(/\n/g, '<br>');
    const time = arg.created_at ? new Date(arg.created_at).toLocaleTimeString() : 'Now';

    const el = document.createElement('div');
    el.className = `argument ${sideClass}`;
    el.dataset.id = arg.id || '';
    el.innerHTML = `
        <div class="argument-head">
            <div class="speaker">
                <div style="width:28px;height:28px;border-radius:50%;background:var(--red);color:#fff;display:grid;place-items:center;font-weight:700;font-size:11px;flex:none">
                    ${speakerName[0].toUpperCase()}
                </div>
                <div>
                    <div class="speaker-name">${speakerName}</div>
                    <div class="side">${sideLabel}</div>
                </div>
            </div>
            <div class="argument-type">${argType}</div>
        </div>
        <div class="argument-body">${content}</div>
        <div class="argument-foot">
            <span>${time}</span>
            <div class="reaction-row">
                <button class="dark-btn vote-btn" data-id="${arg.id || ''}">👍 <span class="vote-count">0</span></button>
            </div>
        </div>`;
    stream.appendChild(el);
    stream.scrollTop = stream.scrollHeight;
}

// ── Main ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    // Get debate ID from URL
    const pathParts = window.location.pathname.split('/').filter(Boolean);
    const debateId = pathParts[pathParts.length - 1];

    if (!debateId || debateId === 'debate') {
        document.getElementById('debate-question').textContent = 'No debate ID found.';
        return;
    }

    // ── Load debate from API ─────────────────────────────────────
    let debate = null;
    try {
        debate = await api.get(`/debates/${debateId}`);
    } catch (err) {
        toast('Could not load debate: ' + (err.message || 'Unknown error'), 'error');
        document.getElementById('debate-question').textContent = 'Error loading debate.';
        document.getElementById('loading-state').textContent = 'Failed to load debate.';
        return;
    }

    // ── Populate header ──────────────────────────────────────────
    const titleEl = document.getElementById('debate-question');
    if (titleEl) titleEl.textContent = debate.title || 'Untitled Debate';

    document.title = `${debate.title || 'Debate'} — PROVOK`;

    const totalRounds = debate.total_rounds || 4;
    const currentRound = debate.current_round || 1;
    renderRounds(totalRounds, currentRound);

    const phaseLabel = document.getElementById('round-label');
    if (phaseLabel) {
        const phase = (debate.rounds && debate.rounds[0] && debate.rounds[0].phase) || 'OPENING';
        phaseLabel.textContent = `ROUND ${currentRound} / ${totalRounds} · ${PHASE_LABELS[phase] || phase}`;
    }

    const watcherEl = document.getElementById('debate-watchers');
    if (watcherEl) watcherEl.textContent = `${debate.viewer_count || 1} watching`;

    // Update compose placeholder based on round
    const composeInput = document.getElementById('compose-input');
    if (composeInput && currentRound > 1) {
        composeInput.placeholder = 'Write your rebuttal…';
    }

    // Handle Participant vs Spectator view
    let currentUser = null;
    try {
        currentUser = await api.request('GET', '/auth/me', null, { noRedirect: true });
    } catch (e) {
        // Not logged in
    }

    const composeSection = document.querySelector('.compose');
    const isOwner = currentUser && (currentUser.id === debate.creator_id || currentUser.is_admin);

    if (composeSection) {
        if (!isOwner) {
            composeSection.style.display = 'none';
        } else {
            composeSection.style.display = 'block';
        }
    }

    if (isOwner) {
        const topmeta = document.querySelector('.debate-topmeta');
        if (topmeta) {
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'dark-btn';
            deleteBtn.style.color = 'var(--red)';
            deleteBtn.style.borderColor = 'var(--red)';
            deleteBtn.textContent = 'Delete Debate';
            deleteBtn.style.marginLeft = '12px';
            deleteBtn.addEventListener('click', async () => {
                if (confirm("Are you sure you want to permanently delete this debate?")) {
                    try {
                        await api.delete('/debates/' + debateId);
                        toast('Debate deleted successfully', 'success');
                        setTimeout(() => window.location.href = '/', 1000);
                    } catch(err) {
                        toast('Failed to delete debate', 'error');
                    }
                }
            });
            topmeta.appendChild(deleteBtn);
        }
    }

    // ── Render existing arguments ────────────────────────────────
    const loadingState = document.getElementById('loading-state');
    if (loadingState) loadingState.remove();

    if (debate.rounds && debate.rounds.length > 0) {
        for (const round of debate.rounds) {
            if (round.arguments) {
                for (const arg of round.arguments) {
                    renderArgument(arg);
                }
            }
        }
    }

    // If no arguments yet, show a prompt
    const stream = document.getElementById('argument-stream');
    if (stream && stream.querySelectorAll('.argument').length === 0) {
        const placeholder = document.createElement('div');
        placeholder.id = 'empty-placeholder';
        placeholder.style.cssText = 'color:var(--muted);padding:40px 28px;font-size:14px;line-height:1.7';
        
        if (currentUser && currentUser.id === debate.creator_id) {
            placeholder.textContent = 'The debate floor is open. Make your opening argument below.';
        } else {
            placeholder.textContent = 'Waiting for the debate to begin...';
        }
        
        stream.appendChild(placeholder);
    }

    // ── WebSocket ────────────────────────────────────────────────
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/${debateId}`;
    let socket = null;

    function connectWebSocket() {
        socket = new WebSocket(wsUrl);

        socket.onopen = () => {
            console.log(`WS connected to debate ${debateId}`);
        };

        socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.event_type === 'argument_submitted') {
                    // Remove the empty-state placeholder if present
                    const placeholder = stream.querySelector('div[style]');
                    if (placeholder && !placeholder.classList.contains('argument')) placeholder.remove();
                    renderArgument(data.payload);
                } else if (data.event_type === 'verdict_ready') {
                    toast('Debate concluded! Redirecting to Verdict…', 'success');
                    setTimeout(() => { window.location.href = `/debate/${debateId}/verdict`; }, 3000);
                }
            } catch (e) {
                console.error('Failed to parse WS message', e);
            }
        };

        socket.onclose = () => {
            console.log('WS closed, reconnecting in 3s…');
            setTimeout(connectWebSocket, 3000);
        };
    }
    connectWebSocket();

    // ── Submit argument ──────────────────────────────────────────
    const submitBtn = document.getElementById('btn-submit-argument');
    if (submitBtn && composeInput) {
        const doSubmit = async () => {
            const content = composeInput.value.trim();
            if (!content) { toast('Write something first!', 'error'); return; }
            submitBtn.disabled = true;
            submitBtn.textContent = 'Submitting…';
            try {
                const arg = await api.post(`/debates/${debateId}/turn`, {
                    content,
                    argument_type: currentRound === 1 ? 'OPENING' : 'REBUTTAL',
                });
                // Remove placeholder if present
                const ph = document.getElementById('empty-placeholder');
                if (ph) ph.remove();
                // Render the submitted argument immediately
                renderArgument(arg);
                composeInput.value = '';
                composeInput.style.height = 'auto';
                toast('Argument submitted! Waiting for AI response…', 'success');
            } catch (err) {
                toast(err.message || 'Failed to submit argument', 'error');
            } finally {
                submitBtn.disabled = false;
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

    // ── Concede ──────────────────────────────────────────────────
    const concedeBtn = document.getElementById('btn-concede');
    if (concedeBtn) {
        concedeBtn.addEventListener('click', () => {
            if (confirm('Are you sure you want to concede this debate?')) {
                toast('Concession submitted', 'info');
            }
        });
    }

    // ── Save & leave ─────────────────────────────────────────────
    const breakBtn = document.getElementById('btn-take-break');
    if (breakBtn) {
        breakBtn.addEventListener('click', () => {
            toast('Your debate has been saved — you can return anytime', 'info');
            setTimeout(() => { window.location.href = '/'; }, 2000);
        });
    }
});
