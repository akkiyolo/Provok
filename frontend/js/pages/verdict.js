import { api, toast } from '../core/app.js';

document.addEventListener('DOMContentLoaded', async () => {
    // Extract debate ID from URL path (e.g. /debate/1234-5678-.../verdict)
    const pathParts = window.location.pathname.split('/');
    let debateId = pathParts[pathParts.length - 2];
    
    if (!debateId || debateId === 'debate' || debateId === 'setup') {
        debateId = 'demo-debate-id'; // Fallback
    }

    try {
        if (debateId !== 'demo-debate-id') {
            const verdict = await api.get(`/debates/${debateId}/verdict`);
            if (verdict) {
                renderScorecard(verdict);
            }
        }
    } catch (e) {
        console.error("Failed to fetch verdict", e);
        toast('Failed to load verdict details.', 'error');
    }

    function renderScorecard(verdict) {
        // AI Synthesis
        const verdictSynthesis = document.querySelector('.verdict-text');
        if (verdictSynthesis && verdict.synthesis) {
            verdictSynthesis.innerHTML = `<p>${verdict.synthesis}</p>`;
        }

        // Common Ground
        const commonGround = document.querySelector('.common-ground ul');
        if (commonGround && verdict.areas_of_agreement) {
            commonGround.innerHTML = `<li>${verdict.areas_of_agreement}</li>`;
        }
        
        // Update winner badge if applicable
        if (verdict.details_json && verdict.details_json.winner_side) {
            const winnerBadge = document.querySelector('.verdict-header .badge');
            if (winnerBadge) {
                winnerBadge.textContent = `${verdict.details_json.winner_side} WINS`;
                if (verdict.details_json.winner_side === 'AGAINST') {
                    winnerBadge.classList.replace('badge-accent', 'badge-danger');
                }
            }
        }
    }
});
