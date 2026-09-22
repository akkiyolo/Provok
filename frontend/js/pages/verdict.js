import { api, toast } from '../core/app.js';

document.addEventListener('DOMContentLoaded', async () => {
    const urlParams = new URLSearchParams(window.location.search);
    let debateId = urlParams.get('debate_id') || urlParams.get('id');
    if (!debateId) {
        const pathParts = window.location.pathname.split('/').filter(Boolean);
        // URL format: /debate/{debate_id}/verdict
        debateId = pathParts.length >= 2 ? pathParts[pathParts.length - 2] : null;
    }
    
    if (!debateId || debateId === 'debate' || debateId === 'setup') {
        return;
    }

    let currentVerdict = null;
    let currentPoll = null;

    try {
        const [verdict, poll] = await Promise.all([
            api.get(`/debates/${debateId}/verdict`),
            api.get(`/debates/${debateId}/poll`).catch(() => null)
        ]);
        currentVerdict = verdict;
        currentPoll = poll;

        if (verdict) {
            renderVerdict(verdict, poll);
            setupComparisonGrid(verdict, poll);
            setupTrophyCard(verdict, poll, debateId);
        }
    } catch (e) {
        console.error("Failed to fetch verdict or poll", e);
        toast('Failed to load verdict details.', 'error');
    }

    function renderVerdict(verdict) {
        // Question / Topic Title
        const questionEl = document.querySelector('.verdict-question');
        if (questionEl && verdict.debate_title) {
            questionEl.textContent = verdict.debate_title;
            document.title = `Verdict: ${verdict.debate_title} — PROVOK`;
        }

        // Judge conclusion headline
        const titleEl = document.getElementById('verdict-title');
        if (titleEl && verdict.judge_conclusion) {
            titleEl.textContent = verdict.judge_conclusion;
        }

        // Winner determination
        let winnerSide = (verdict.details_json && verdict.details_json.winner_side) || 'SPLIT';
        if (winnerSide === 'SPLIT' || !winnerSide) {
            const scoreA = (verdict.evidence_quality_a || 0) + (verdict.reasoning_a || 0) + (verdict.rebuttal_effectiveness_a || 0);
            const scoreB = (verdict.evidence_quality_b || 0) + (verdict.reasoning_b || 0) + (verdict.rebuttal_effectiveness_b || 0);
            if (scoreA > scoreB) winnerSide = 'FOR';
            else if (scoreB > scoreA) winnerSide = 'AGAINST';
            else winnerSide = 'FOR';
        }

        // Result Strip
        const resultStrip = document.querySelector('.result-strip');
        if (resultStrip) {
            const winnerBadgeColor = winnerSide === 'FOR' ? 'var(--yellow)' : 'var(--blue)';
            resultStrip.innerHTML = `
                <div style="background:var(--paper-2);border:1px solid var(--line);border-radius:var(--radius-md);padding:24px;margin-bottom:32px;">
                    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;flex-wrap:wrap;gap:10px;">
                        <span class="badge" style="background:${winnerBadgeColor};color:#fff;font-weight:700;font-size:13px;padding:6px 14px;">
                            ${winnerSide} DECISIVELY WON
                        </span>
                        <span style="font-size:13px;color:var(--muted);font-family:var(--mono);">
                            JUDGE CONFIDENCE: ${(verdict.judge_confidence ? (verdict.judge_confidence * 100).toFixed(0) : 85)}%
                        </span>
                    </div>
                    <div style="font-size:15px;line-height:1.7;color:var(--ink-light);">${verdict.synthesis || ''}</div>
                </div>
            `;
        }

        // Common Ground / Position Shift
        const positionRow = document.querySelector('.position-row');
        if (positionRow && verdict.areas_of_agreement) {
            positionRow.innerHTML = `
                <div style="background:var(--paper-2);border-left:3px solid var(--red);padding:16px 20px;border-radius:var(--radius-sm);font-size:14px;line-height:1.7;color:var(--ink-light);margin-top:12px;">
                    <strong>Common Ground Identified:</strong> ${verdict.areas_of_agreement}
                </div>
            `;
        }

        // Scorecard Grid
        const scoreGrid = document.querySelector('.score-grid');
        if (scoreGrid) {
            const metrics = [
                { label: 'Evidence Quality', a: (verdict.evidence_quality_a || 0.8) * 10, b: (verdict.evidence_quality_b || 0.8) * 10 },
                { label: 'Logical Reasoning', a: (verdict.reasoning_a || 0.85) * 10, b: (verdict.reasoning_b || 0.85) * 10 },
                { label: 'Rebuttal Effectiveness', a: (verdict.rebuttal_effectiveness_a || 0.8) * 10, b: (verdict.rebuttal_effectiveness_b || 0.8) * 10 },
                { label: 'Consistency', a: (verdict.consistency_a || 0.85) * 10, b: (verdict.consistency_b || 0.85) * 10 },
                { label: 'Responsiveness', a: (verdict.responsiveness_a || 0.8) * 10, b: (verdict.responsiveness_b || 0.8) * 10 }
            ];

            scoreGrid.innerHTML = `
                <div style="display:grid;gap:14px;background:var(--paper-2);border:1px solid var(--line);border-radius:var(--radius-md);padding:24px;">
                    <div style="display:flex;justify-content:space-between;font-weight:700;font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;padding-bottom:8px;border-bottom:1px solid var(--line);">
                        <span style="color:var(--yellow)">Side FOR</span>
                        <span>Evaluation Metric</span>
                        <span style="color:var(--blue)">Side AGAINST</span>
                    </div>
                    ${metrics.map(m => `
                        <div style="display:flex;align-items:center;justify-content:space-between;gap:16px;font-size:14px;">
                            <span style="font-weight:700;color:var(--yellow);width:45px;text-align:left;font-family:var(--mono);">${m.a.toFixed(1)}</span>
                            <div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;">
                                <span style="font-weight:500;font-size:13px;">${m.label}</span>
                                <div style="display:flex;width:100%;height:6px;background:rgba(0,0,0,0.2);border-radius:3px;overflow:hidden;">
                                    <div style="width:${(m.a / (m.a + m.b)) * 100}%;background:var(--yellow);"></div>
                                    <div style="width:${(m.b / (m.a + m.b)) * 100}%;background:var(--blue);"></div>
                                </div>
                            </div>
                            <span style="font-weight:700;color:var(--blue);width:45px;text-align:right;font-family:var(--mono);">${m.b.toFixed(1)}</span>
                        </div>
                    `).join('')}
                </div>
            `;
        }
    }

    function setupComparisonGrid(verdict, poll) {
        // AI Winner
        let aiWinner = (verdict.details_json && verdict.details_json.winner_side) || 'FOR';
        const aiWinnerTitle = document.getElementById('ai-winner-title');
        const aiWinnerBadge = document.getElementById('ai-winner-badge');
        const aiSummary = document.getElementById('ai-verdict-summary');
        const aiConf = document.getElementById('ai-confidence-label');

        if (aiWinnerTitle) aiWinnerTitle.textContent = `${aiWinner} Decisively Won`;
        if (aiWinnerBadge) {
            aiWinnerBadge.textContent = `${aiWinner} SIDE`;
            aiWinnerBadge.style.background = aiWinner === 'FOR' ? 'var(--yellow)' : 'var(--blue)';
        }
        if (aiSummary && verdict.judge_conclusion) {
            aiSummary.textContent = verdict.judge_conclusion;
        }
        if (aiConf) {
            const conf = verdict.judge_confidence ? Math.round(verdict.judge_confidence * 100) : 85;
            aiConf.textContent = `${conf}% Confidence`;
        }

        // Community Poll Winner
        const pollWinnerTitle = document.getElementById('poll-winner-title');
        const pollWinnerBadge = document.getElementById('poll-winner-badge');
        const cmpPollFor = document.getElementById('cmp-poll-for');
        const cmpPollAgainst = document.getElementById('cmp-poll-against');
        const cmpBarFor = document.getElementById('cmp-bar-for');
        const cmpBarAgainst = document.getElementById('cmp-bar-against');
        const pollTotal = document.getElementById('poll-total-votes-label');

        if (poll) {
            const pFor = poll.pct_for ?? 50;
            const pAgainst = poll.pct_against ?? 50;
            const total = poll.total_votes || 0;

            if (cmpPollFor) cmpPollFor.textContent = `FOR ${pFor}% (${poll.votes_for || 0})`;
            if (cmpPollAgainst) cmpPollAgainst.textContent = `AGAINST ${pAgainst}% (${poll.votes_against || 0})`;
            if (cmpBarFor) cmpBarFor.style.width = `${pFor}%`;
            if (cmpBarAgainst) cmpBarAgainst.style.width = `${pAgainst}%`;
            if (pollTotal) pollTotal.textContent = `${total} Total Vote${total === 1 ? '' : 's'}`;

            if (total === 0) {
                if (pollWinnerTitle) pollWinnerTitle.textContent = 'Audience Votes Awaiting';
                if (pollWinnerBadge) {
                    pollWinnerBadge.textContent = 'PENDING';
                    pollWinnerBadge.style.background = 'var(--paper-3)';
                }
            } else if (poll.winner_side === 'FOR') {
                if (pollWinnerTitle) pollWinnerTitle.textContent = 'Audience Favors FOR';
                if (pollWinnerBadge) {
                    pollWinnerBadge.textContent = 'COMMUNITY: FOR';
                    pollWinnerBadge.style.background = 'var(--yellow)';
                }
            } else if (poll.winner_side === 'AGAINST') {
                if (pollWinnerTitle) pollWinnerTitle.textContent = 'Audience Favors AGAINST';
                if (pollWinnerBadge) {
                    pollWinnerBadge.textContent = 'COMMUNITY: AGAINST';
                    pollWinnerBadge.style.background = 'var(--blue)';
                }
            } else {
                if (pollWinnerTitle) pollWinnerTitle.textContent = 'Audience Split Evenly';
                if (pollWinnerBadge) {
                    pollWinnerBadge.textContent = 'TIE 50/50';
                    pollWinnerBadge.style.background = 'var(--paper-3)';
                }
            }
        }
    }

    // ── 1200x630 High-Resolution Trophy Card Canvas ──────────────
    function drawTrophyCard(canvas, verdict, poll) {
        const ctx = canvas.getContext('2d');
        const W = 1200;
        const H = 630;
        canvas.width = W;
        canvas.height = H;

        // 1. Sleek Dark Gradient Background
        const bgGrad = ctx.createLinearGradient(0, 0, W, H);
        bgGrad.addColorStop(0, '#090a0f');
        bgGrad.addColorStop(0.5, '#12141d');
        bgGrad.addColorStop(1, '#0c0d14');
        ctx.fillStyle = bgGrad;
        ctx.fillRect(0, 0, W, H);

        // 2. Ambient glows
        const glow1 = ctx.createRadialGradient(160, 100, 10, 160, 100, 380);
        glow1.addColorStop(0, 'rgba(224, 90, 43, 0.18)');
        glow1.addColorStop(1, 'rgba(224, 90, 43, 0)');
        ctx.fillStyle = glow1;
        ctx.fillRect(0, 0, W, H);

        const glow2 = ctx.createRadialGradient(W - 140, H - 100, 10, W - 140, H - 100, 420);
        glow2.addColorStop(0, 'rgba(78, 120, 240, 0.15)');
        glow2.addColorStop(1, 'rgba(78, 120, 240, 0)');
        ctx.fillStyle = glow2;
        ctx.fillRect(0, 0, W, H);

        // 3. Card Border
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
        ctx.lineWidth = 2;
        ctx.strokeRect(30, 30, W - 60, H - 60);

        // 4. Header / Brand
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 26px "Space Grotesk", Inter, sans-serif';
        ctx.fillText('PROVOK', 60, 85);
        ctx.fillStyle = '#e05a2b';
        ctx.font = 'bold 26px "Space Grotesk", Inter, sans-serif';
        ctx.fillText('•', 165, 85);

        ctx.fillStyle = '#8b867d';
        ctx.font = '600 13px "DM Mono", monospace';
        ctx.fillText('OFFICIAL DIALECTICAL VERDICT · 4 ROUNDS CONCLUDED', 190, 84);

        // 5. Debate Title
        ctx.fillStyle = '#f5f5f7';
        ctx.font = 'bold 38px "Space Grotesk", Inter, sans-serif';
        const titleText = verdict.debate_title || 'Structured Debate Arena';
        wrapText(ctx, titleText, 60, 150, W - 120, 48, 2);

        // 6. Winner Banner Box
        let winnerSide = (verdict.details_json && verdict.details_json.winner_side) || 'FOR';
        const winColor = winnerSide === 'FOR' ? '#f59e0b' : '#3b82f6';

        // Banner box background
        ctx.fillStyle = 'rgba(255, 255, 255, 0.04)';
        ctx.beginPath();
        ctx.roundRect(60, 235, W - 120, 160, 16);
        ctx.fill();
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // Winner Chip
        ctx.fillStyle = winColor;
        ctx.beginPath();
        ctx.roundRect(85, 260, 240, 42, 8);
        ctx.fill();

        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 16px Inter, sans-serif';
        ctx.fillText(`🏆 ${winnerSide} DECISIVELY WON`, 105, 287);

        // Judge Confidence
        const confidence = verdict.judge_confidence ? Math.round(verdict.judge_confidence * 100) : 85;
        ctx.fillStyle = '#a1a1aa';
        ctx.font = '600 14px "DM Mono", monospace';
        ctx.fillText(`AI BENCH CONFIDENCE: ${confidence}%`, 345, 287);

        // Judge Conclusion text inside banner
        ctx.fillStyle = '#e4e4e7';
        ctx.font = 'italic 18px Inter, sans-serif';
        const conclusionText = `"${verdict.judge_conclusion || verdict.synthesis || 'A decisive clash of dialectical arguments resolved by multi-round AI synthesis.'}"`;
        wrapText(ctx, conclusionText, 85, 335, W - 170, 26, 2);

        // 7. Dual Consensus Columns (AI Verdict vs Community Poll)
        // AI Col
        ctx.fillStyle = '#71717a';
        ctx.font = '600 12px "DM Mono", monospace';
        ctx.fillText('AI BENCH EVALUATION', 60, 440);

        ctx.fillStyle = '#f4f4f5';
        ctx.font = '600 16px Inter, sans-serif';
        ctx.fillText(`Winner: Side ${winnerSide} · High Consensus`, 60, 468);

        // Audience Col
        ctx.fillStyle = '#71717a';
        ctx.font = '600 12px "DM Mono", monospace';
        ctx.fillText('COMMUNITY AUDIENCE POLL', 600, 440);

        let pollString = 'Poll Votes: Awaiting Audience Consensus';
        if (poll && poll.total_votes > 0) {
            pollString = `FOR ${poll.pct_for}% · AGAINST ${poll.pct_against}% (${poll.total_votes} votes)`;
        }
        ctx.fillStyle = '#f4f4f5';
        ctx.font = '600 16px Inter, sans-serif';
        ctx.fillText(pollString, 600, 468);

        // 8. Bottom Footer
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
        ctx.beginPath();
        ctx.moveTo(60, 520);
        ctx.lineTo(W - 60, 520);
        ctx.stroke();

        ctx.fillStyle = '#e05a2b';
        ctx.font = 'bold 15px "Space Grotesk", Inter, sans-serif';
        ctx.fillText('PROVOK ARENA', 60, 565);

        ctx.fillStyle = '#71717a';
        ctx.font = '13px Inter, sans-serif';
        ctx.fillText('Autonomous AI Swarm & Human Dialectics · provok.onrender.com', 210, 564);

        ctx.fillStyle = '#a1a1aa';
        ctx.font = '600 12px "DM Mono", monospace';
        ctx.fillText(new Date().toISOString().split('T')[0], W - 160, 564);
    }

    function wrapText(ctx, text, x, y, maxWidth, lineHeight, maxLines = 3) {
        const words = (text || '').split(' ');
        let line = '';
        let lineCount = 0;
        for (let n = 0; n < words.length; n++) {
            const testLine = line + words[n] + ' ';
            const metrics = ctx.measureText(testLine);
            if (metrics.width > maxWidth && n > 0) {
                ctx.fillText(line.trim(), x, y);
                line = words[n] + ' ';
                y += lineHeight;
                lineCount++;
                if (lineCount >= maxLines - 1 && n < words.length - 1) {
                    line += '…';
                    break;
                }
            } else {
                line = testLine;
            }
        }
        ctx.fillText(line.trim(), x, y);
        return y + lineHeight;
    }

    function setupTrophyCard(verdict, poll, debateId) {
        const openBtn = document.getElementById('btn-open-trophy');
        const modal = document.getElementById('trophy-modal');
        const closeBtn = document.getElementById('btn-close-trophy');
        const closeXBtn = document.getElementById('btn-close-modal');
        const canvas = document.getElementById('trophy-canvas');
        const downloadBtn = document.getElementById('btn-download-png');
        const twitterBtn = document.getElementById('btn-share-twitter');

        if (!openBtn || !modal || !canvas) return;

        const openModal = () => {
            modal.classList.add('open');
            drawTrophyCard(canvas, verdict, poll);
        };

        const closeModal = () => {
            modal.classList.remove('open');
        };

        openBtn.addEventListener('click', openModal);
        if (closeBtn) closeBtn.addEventListener('click', closeModal);
        if (closeXBtn) closeXBtn.addEventListener('click', closeModal);

        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });

        // Download PNG
        if (downloadBtn) {
            downloadBtn.addEventListener('click', () => {
                const link = document.createElement('a');
                link.download = `provok-verdict-${debateId}.png`;
                link.href = canvas.toDataURL('image/png');
                link.click();
                toast('Trophy card downloaded!', 'success');
            });
        }

        // Share on X (Twitter)
        if (twitterBtn) {
            twitterBtn.addEventListener('click', () => {
                let winner = (verdict.details_json && verdict.details_json.winner_side) || 'FOR';
                const topic = verdict.debate_title || 'Debate';
                const text = encodeURIComponent(`The AI Bench verdict is in on PROVOK!\n\nDebate: "${topic}"\nWinner: Side ${winner}\n\nCheck the transcript, consensus breakdown, and cast your audience vote:`);
                const url = encodeURIComponent(window.location.href);
                window.open(`https://twitter.com/intent/tweet?text=${text}&url=${url}`, '_blank');
            });
        }
    }
});

