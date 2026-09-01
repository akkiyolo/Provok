/**
 * PROVOK — Live Page Module
 */
import { api } from '../core/app.js';

document.addEventListener('DOMContentLoaded', async () => {
    const liveFeedGrid = document.getElementById('live-feed-grid');
    if (!liveFeedGrid) return;

    try {
        const debates = await api.get('/debates/?status=LIVE');
        if (debates.length > 0) {
            liveFeedGrid.innerHTML = '';
            debates.forEach(debate => {
                const card = document.createElement('a');
                card.className = 'debate-card';
                card.href = `/debate/${debate.id}`;
                
                card.innerHTML = `
                    <div class="debate-card-meta">
                        <span class="badge badge-live">LIVE · R${debate.current_round}</span>
                        <span class="tag" style="margin-left: 8px;">${debate.mode}</span>
                    </div>
                    <div class="debate-card-question">${debate.title}</div>
                    <div class="debate-card-footer">
                        <span>0 watching</span>
                        <span>Watch →</span>
                    </div>
                `;
                liveFeedGrid.appendChild(card);
            });
        } else {
            liveFeedGrid.innerHTML = '<p style="color: var(--text-muted);">No live debates right now.</p>';
        }
    } catch (err) {
        console.error("Failed to fetch live debates", err);
        liveFeedGrid.innerHTML = '<p style="color: red;">Error loading debates.</p>';
    }
});
