/**
 * PROVOK — Explore Page Module
 * Topic filtering, feed exploration, interactive chips, skeleton loading.
 */
import { api, toast, timeAgo } from '../core/app.js';

const TOPICS = [
    { id: 'all', label: 'All Topics' },
    { id: 'ai', label: 'AI & Autonomy' },
    { id: 'tech', label: 'Technology' },
    { id: 'philosophy', label: 'Philosophy' },
    { id: 'policy', label: 'Public Policy' },
    { id: 'science', label: 'Science' },
    { id: 'culture', label: 'Culture' }
];

document.addEventListener('DOMContentLoaded', () => {
    const topicRow = document.querySelector('.topic-row');
    const feedGrid = document.querySelector('.feed-grid');

    if (!feedGrid) return;

    let activeTopic = 'all';
    let allDebates = [];

    // Render topic chips
    if (topicRow) {
        topicRow.innerHTML = TOPICS.map(t => `
            <button class="topic-chip ${t.id === 'all' ? 'active' : ''}" data-topic="${t.id}" style="
                padding: 6px 14px;
                border-radius: var(--radius-full);
                border: 1px solid var(--line);
                background: ${t.id === 'all' ? 'var(--ink)' : 'var(--paper)'};
                color: ${t.id === 'all' ? 'var(--white)' : 'var(--ink)'};
                font-family: var(--display);
                font-size: 13px;
                font-weight: 500;
                cursor: pointer;
                transition: all var(--duration-fast);
                white-space: nowrap;
            ">
                ${t.label}
            </button>
        `).join('');

        topicRow.querySelectorAll('.topic-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                topicRow.querySelectorAll('.topic-chip').forEach(c => {
                    c.style.background = 'var(--paper)';
                    c.style.color = 'var(--ink)';
                    c.classList.remove('active');
                });
                chip.style.background = 'var(--ink)';
                chip.style.color = 'var(--white)';
                chip.classList.add('active');

                activeTopic = chip.dataset.topic;
                filterAndRender();
            });
        });
    }

    async function loadExploreDebates() {
        feedGrid.innerHTML = `
            <div class="skeleton-card shimmer" style="height:160px;border-radius:var(--radius-md);"></div>
            <div class="skeleton-card shimmer" style="height:160px;border-radius:var(--radius-md);"></div>
            <div class="skeleton-card shimmer" style="height:160px;border-radius:var(--radius-md);"></div>
        `;

        try {
            let res = null;
            try {
                res = await api.get('/explore?limit=30');
            } catch (e) {
                res = await api.get('/feed/explore?limit=30');
            }
            allDebates = (res && res.debates) ? res.debates : [];
            
            // If explore feed returns empty, fallback to debates list
            if (allDebates.length === 0) {
                const fallback = await api.get('/debates/?limit=20');
                allDebates = (fallback || []).map(d => ({
                    id: d.id,
                    title: d.title,
                    status: d.status,
                    mode: d.mode,
                    current_round: d.current_round,
                    viewer_count: 0,
                    created_at: d.created_at
                }));
            }

            filterAndRender();
        } catch (err) {
            console.warn('Explore feed fallback to public debates due to:', err);
            try {
                const fallback = await api.get('/debates/?limit=20');
                allDebates = (fallback || []).map(d => ({
                    id: d.id,
                    title: d.title,
                    status: d.status,
                    mode: d.mode,
                    current_round: d.current_round,
                    viewer_count: 0,
                    created_at: d.created_at
                }));
                filterAndRender();
            } catch (finalErr) {
                console.error('Explore fatal error:', finalErr);
                feedGrid.innerHTML = `
                    <div class="empty glass" style="grid-column:1/-1;text-align:center;padding:48px;border-radius:var(--radius-lg);">
                        <strong style="display:block;font-size:16px;color:var(--red);margin-bottom:6px;">Unable to load feed</strong>
                        <span class="muted">${finalErr.message || 'Please check your connection and try again.'}</span>
                        <button class="btn btn-secondary btn-sm" style="margin-top:14px;" onclick="location.reload()">Retry</button>
                    </div>
                `;
            }
        }
    }

    function filterAndRender() {
        let filtered = allDebates;
        if (activeTopic !== 'all') {
            const query = activeTopic.toLowerCase();
            filtered = allDebates.filter(d => 
                (d.title && d.title.toLowerCase().includes(query)) ||
                (d.mode && d.mode.toLowerCase().includes(query))
            );
        }

        if (filtered.length === 0) {
            feedGrid.innerHTML = `
                <div class="empty glass" style="grid-column:1/-1;text-align:center;padding:56px 20px;border-radius:var(--radius-lg);">
                    <strong style="display:block;font-family:var(--display);font-size:18px;color:var(--ink);margin-bottom:6px;">No debates found</strong>
                    <span class="muted">No discussions under this topic yet. Be the first to start one!</span>
                    <div style="margin-top:16px;">
                        <a class="btn btn-red btn-sm" href="/ask">Start this debate →</a>
                    </div>
                </div>
            `;
            return;
        }

        feedGrid.innerHTML = filtered.map((d, index) => {
            const isLive = d.status === 'LIVE' || d.status === 'WAITING';
            const statusBadge = isLive
                ? `<span class="badge" style="background:rgba(224,90,43,0.15);color:var(--red);font-size:10px;font-weight:600;">LIVE · R${d.current_round || 1}</span>`
                : `<span class="badge" style="background:var(--paper-2);color:var(--ink-light);font-size:10px;">${d.status || 'DEBATE'}</span>`;
            
            const timeStr = d.created_at ? timeAgo(d.created_at) : '';

            return `
                <div class="debate-card glass fade-in" style="
                    animation-delay: ${index * 45}ms;
                    padding: 22px;
                    border-radius: var(--radius-md);
                    border: 1px solid var(--line);
                    cursor: pointer;
                    display: flex;
                    flex-direction: column;
                    justify-content: space-between;
                    min-height: 160px;
                    transition: all var(--duration-fast) var(--ease);
                " onclick="location.href='/debate/${d.id}'">
                    <div>
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                            ${statusBadge}
                            <span class="muted" style="font-size:11px;">${timeStr}</span>
                        </div>
                        <h3 style="
                            font-family: var(--display);
                            font-size: 17px;
                            font-weight: 600;
                            line-height: 1.35;
                            color: var(--ink);
                            margin-bottom: 12px;
                            letter-spacing: -0.01em;
                        ">${d.title}</h3>
                    </div>
                    <div style="display:flex;justify-content:space-between;align-items:center;padding-top:12px;border-top:1px solid var(--line-light);font-size:12px;">
                        <span class="tag" style="background:var(--paper-2);">${d.mode || 'Swarm'}</span>
                        <span style="color:var(--red);font-weight:500;font-family:var(--display);">Enter debate →</span>
                    </div>
                </div>
            `;
        }).join('');
    }

    loadExploreDebates();
});
