/**
 * PROVOK — Home Page Module
 */
import { api, store, toast } from '../core/app.js';

document.addEventListener('DOMContentLoaded', async () => {
    // Fetch live debates
    try {
        const debates = await api.get('/debates/');
        const liveContainer = document.getElementById('live-debates');
        if (liveContainer && debates.length > 0) {
            liveContainer.innerHTML = '';
            debates.forEach(debate => {
                const card = document.createElement('div');
                card.className = 'debate-card';
                card.style.cursor = 'pointer';
                card.innerHTML = `
                    <div style="font-size: 11px; font-weight: 700; letter-spacing: 0.1em; color: var(--accent); margin-bottom: 8px; text-transform: uppercase;">
                        ${debate.status === 'LIVE' ? '🔴 LIVE' : debate.status}
                    </div>
                    <h3 style="margin-bottom: 8px;">${debate.title}</h3>
                    <div style="font-size: 12px; color: var(--text-muted);">
                        ${debate.mode} • Round ${debate.current_round}
                    </div>
                `;
                card.addEventListener('click', () => {
                    window.location.href = `/debate/${debate.id}`;
                });
                liveContainer.appendChild(card);
            });
        }
    } catch (err) {
        console.error("Failed to fetch debates", err);
    }

    // Topic tags interactive
    document.querySelectorAll('.topic-row .topic').forEach(tag => {
        tag.addEventListener('click', () => {
            document.querySelectorAll('.topic-row .topic').forEach(t => t.classList.remove('active'));
            tag.classList.add('active');
        });
    });
});
