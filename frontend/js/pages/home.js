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
                card.style.position = 'relative';
                
                const token = localStorage.getItem('provok-token');
                let currentUserId = null;
                try {
                    if (token) currentUserId = JSON.parse(atob(token.split('.')[1])).sub;
                } catch(e) {}
                
                const currentUser = store.get('user');
                const isOwner = (currentUserId && currentUserId === debate.creator_id) || (currentUser && currentUser.is_admin);
                const deleteBtnHtml = isOwner ? `<button class="delete-btn" data-id="${debate.id}" style="position: absolute; right: 16px; top: 16px; border: none; background: transparent; color: var(--text-muted); cursor: pointer; padding: 4px; font-size: 16px; z-index: 10;">&times;</button>` : '';

                card.innerHTML = `
                    ${deleteBtnHtml}
                    <div style="font-size: 11px; font-weight: 700; letter-spacing: 0.1em; color: var(--accent); margin-bottom: 8px; text-transform: uppercase;">
                        ${debate.status === 'LIVE' ? '🔴 LIVE' : debate.status}
                    </div>
                    <h3 style="margin-bottom: 8px; padding-right: 24px;">${debate.title}</h3>
                    <div style="font-size: 12px; color: var(--text-muted);">
                        ${debate.mode} • Round ${debate.current_round}
                    </div>
                `;
                
                card.addEventListener('click', (e) => {
                    if (e.target.classList.contains('delete-btn')) {
                        e.stopPropagation();
                        if (confirm("Are you sure you want to delete this debate?")) {
                            api.delete('/debates/' + debate.id).then(() => {
                                card.remove();
                                toast('Debate deleted', 'success');
                            }).catch(() => {
                                toast('Failed to delete debate', 'error');
                            });
                        }
                        return;
                    }
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
