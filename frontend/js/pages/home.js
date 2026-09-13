/**
 * PROVOK — Home Page Module
 * Premium home page with skeleton loading, staggered animations, relative time.
 */
import { api, store, toast, timeAgo, createSkeletonCards } from '../core/app.js';

document.addEventListener('DOMContentLoaded', async () => {
    const liveContainer = document.getElementById('live-debates');

    // Show skeleton loading state
    if (liveContainer) {
        liveContainer.innerHTML = createSkeletonCards(3);
    }

    // Fetch live debates
    try {
        const debates = await api.get('/debates/');
        if (liveContainer) {
            if (debates.length > 0) {
                liveContainer.innerHTML = '';
                debates.forEach((debate, index) => {
                    const card = document.createElement('div');
                    card.className = 'debate-card slide-up';
                    card.style.cursor = 'pointer';
                    card.style.position = 'relative';
                    card.style.animationDelay = `${index * 0.08}s`;

                    const token = localStorage.getItem('provok-token');
                    let currentUserId = null;
                    try {
                        if (token) currentUserId = JSON.parse(atob(token.split('.')[1])).sub;
                    } catch(e) {}
                    
                    const currentUser = store.get('user');
                    const isOwner = (currentUserId && currentUserId === debate.creator_id) || (currentUser && currentUser.is_admin);
                    const deleteBtnHtml = isOwner ? `<button class="delete-btn" data-id="${debate.id}">&times;</button>` : '';
                    const statusBadge = debate.status === 'LIVE' 
                        ? '<span class="badge badge-live">LIVE</span>' 
                        : `<span class="badge badge-completed">${debate.status}</span>`;
                    const time = timeAgo(debate.created_at);

                    card.innerHTML = `
                        ${deleteBtnHtml}
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:13px">
                            ${statusBadge}
                            <span class="tag">${debate.mode || 'LIVE'}</span>
                        </div>
                        <h3 style="font-size:19px;letter-spacing:-.02em;margin-bottom:8px;padding-right:24px">${debate.title}</h3>
                        <div style="font-size:11px;color:var(--muted);display:flex;gap:12px">
                            <span>Round ${debate.current_round || 1}</span>
                            ${time ? `<span>${time}</span>` : ''}
                        </div>
                    `;
                    
                    card.addEventListener('click', (e) => {
                        if (e.target.classList.contains('delete-btn')) {
                            e.stopPropagation();
                            if (confirm("Are you sure you want to delete this debate?")) {
                                api.delete('/debates/' + debate.id).then(() => {
                                    card.style.opacity = '0';
                                    card.style.transform = 'translateX(-20px)';
                                    card.style.transition = 'all 0.3s ease';
                                    setTimeout(() => card.remove(), 300);
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
            } else {
                liveContainer.innerHTML = `
                    <div class="empty fade-in">
                        <strong>No debates yet</strong>
                        <span>Be the first to start a debate and put your beliefs under pressure.</span>
                        <div style="margin-top:16px">
                            <a class="btn btn-red btn-sm" href="/ask">Start a debate →</a>
                        </div>
                    </div>
                `;
            }
        }
    } catch (err) {
        console.error("Failed to fetch debates", err);
        if (liveContainer) {
            liveContainer.innerHTML = `
                <div class="empty">
                    <strong>Could not load debates</strong>
                    <span>Check your connection and try again.</span>
                </div>
            `;
        }
    }

    // Topic tags interactive
    document.querySelectorAll('.topic-row .topic').forEach(tag => {
        tag.addEventListener('click', () => {
            document.querySelectorAll('.topic-row .topic').forEach(t => t.classList.remove('active'));
            tag.classList.add('active');
        });
    });
});
