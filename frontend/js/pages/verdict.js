import { api, toast } from '../core/app.js';

document.addEventListener('DOMContentLoaded', async () => {
    const pathParts = window.location.pathname.split('/').filter(Boolean);
    // URL format: /debate/{debate_id}/verdict
    let debateId = pathParts.length >= 2 ? pathParts[pathParts.length - 2] : null;
    
    if (!debateId || debateId === 'debate' || debateId === 'setup') {
        return;
    }

    try {
        const verdict = await api.get(`/debates/${debateId}/verdict`);
        if (verdict) {
            renderVerdict(verdict);
        }
    } catch (e) {
        console.error("Failed to fetch verdict", e);
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
});
