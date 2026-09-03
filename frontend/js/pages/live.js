/**
 * PROVOK — Live Page Module
 */
import { api, store, toast } from '../core/app.js';

document.addEventListener('DOMContentLoaded', async () => {
    const liveFeedGrid = document.getElementById('live-feed-grid');
    if (!liveFeedGrid) return;

    try {
        const debates = await api.get('/debates/?status=LIVE');
        if (debates.length > 0) {
            liveFeedGrid.innerHTML = '';
            debates.forEach(debate => {
                const card = document.createElement('div');
                card.className = 'debate-card';
                card.style.position = 'relative';
                card.style.cursor = 'pointer';
                
                const isOwner = store.currentUser && (store.currentUser.id === debate.creator_id || store.currentUser.is_admin);
                const deleteBtnHtml = isOwner ? `<button class="delete-btn" data-id="${debate.id}" style="position: absolute; right: 16px; top: 16px; border: none; background: transparent; color: var(--text-muted); cursor: pointer; padding: 4px; font-size: 16px; z-index: 10;">&times;</button>` : '';

                card.innerHTML = `
                    ${deleteBtnHtml}
                    <div class="debate-card-meta">
                        <span class="badge badge-live">LIVE · R${debate.current_round}</span>
                        <span class="tag" style="margin-left: 8px;">${debate.mode}</span>
                    </div>
                    <div class="debate-card-question" style="padding-right: 24px;">${debate.title}</div>
                    <div class="debate-card-footer">
                        <span>0 watching</span>
                        <span>Watch →</span>
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
