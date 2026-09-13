/**
 * PROVOK — Notifications Page Module
 * Real notifications fetching, mark-as-read, empty states.
 */
import { api, store, toast, timeAgo } from '../core/app.js';

document.addEventListener('DOMContentLoaded', () => {
    const listEl = document.getElementById('notifications-list');
    const markAllBtn = document.getElementById('mark-all-read-btn');
    const unreadCountBadge = document.getElementById('unread-count-badge');

    if (!listEl) return;

    // Check if user is logged in
    const token = store.get('token');
    if (!token) {
        listEl.innerHTML = `
            <div class="notification-empty glass" style="border-radius:var(--radius-lg);padding:48px 24px;">
                <strong>Sign in to view notifications</strong>
                <p class="muted" style="margin-bottom:18px;">Stay updated when someone replies or a verdict is reached.</p>
                <a class="btn btn-primary btn-sm" href="/login">Sign in</a>
            </div>
        `;
        if (markAllBtn) markAllBtn.style.display = 'none';
        return;
    }

    async function loadNotifications() {
        listEl.innerHTML = `
            <div class="skeleton-card shimmer" style="height:72px;margin-bottom:12px;border-radius:var(--radius-md);"></div>
            <div class="skeleton-card shimmer" style="height:72px;margin-bottom:12px;border-radius:var(--radius-md);"></div>
            <div class="skeleton-card shimmer" style="height:72px;border-radius:var(--radius-md);"></div>
        `;

        try {
            const data = await api.get('/notifications/');
            const items = data.notifications || [];
            const unreadCount = data.unread_count || 0;

            if (unreadCountBadge) {
                if (unreadCount > 0) {
                    unreadCountBadge.textContent = `${unreadCount} unread`;
                    unreadCountBadge.style.display = 'inline-block';
                } else {
                    unreadCountBadge.style.display = 'none';
                }
            }

            if (items.length === 0) {
                listEl.innerHTML = `
                    <div class="notification-empty glass" style="border-radius:var(--radius-lg);padding:48px 24px;">
                        <strong>All caught up!</strong>
                        <p class="muted">No new notifications right now. Join a debate to get involved.</p>
                        <a class="btn btn-secondary btn-sm" style="margin-top:16px;" href="/explore">Explore debates</a>
                    </div>
                `;
                if (markAllBtn) markAllBtn.style.display = 'none';
                return;
            }

            if (markAllBtn) {
                markAllBtn.style.display = unreadCount > 0 ? 'inline-flex' : 'none';
            }

            listEl.innerHTML = items.map((item, index) => {
                const unreadCls = !item.is_read ? 'unread' : '';
                const timeStr = item.created_at ? timeAgo(item.created_at) : '';
                const linkHref = item.link || '#';
                
                return `
                    <div class="notification-item ${unreadCls} fade-in" style="animation-delay:${index * 40}ms" data-id="${item.id}">
                        <div style="flex:1;">
                            <strong>${item.title || 'Notification'}</strong>
                            <p class="muted">${item.body || ''} ${timeStr ? `· <span style="font-size:11px">${timeStr}</span>` : ''}</p>
                        </div>
                        <div style="display:flex;align-items:center;gap:8px;">
                            ${!item.is_read ? `<button class="btn btn-ghost btn-sm mark-read-btn" data-id="${item.id}" title="Mark as read" style="font-size:11px;">✓ Mark read</button>` : ''}
                            ${item.link ? `<a class="btn btn-secondary btn-sm" href="${linkHref}">View →</a>` : ''}
                        </div>
                    </div>
                `;
            }).join('');

            // Bind single read buttons
            listEl.querySelectorAll('.mark-read-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    const nid = btn.dataset.id;
                    try {
                        await api.post(`/notifications/${nid}/read`, {});
                        toast('Marked as read', 'info');
                        await loadNotifications();
                    } catch (err) {
                        toast('Failed to update notification', 'error');
                    }
                });
            });

        } catch (err) {
            console.error('Failed to load notifications:', err);
            listEl.innerHTML = `
                <div class="notification-empty">
                    <strong style="color:var(--red);">Could not load notifications</strong>
                    <p class="muted">${err.message || 'Please check your connection and try again.'}</p>
                    <button class="btn btn-secondary btn-sm" style="margin-top:12px;" onclick="location.reload()">Retry</button>
                </div>
            `;
        }
    }

    if (markAllBtn) {
        markAllBtn.addEventListener('click', async () => {
            try {
                await api.post('/notifications/read-all', {});
                toast('All notifications marked as read', 'success');
                await loadNotifications();
            } catch (err) {
                toast('Failed to mark all as read', 'error');
            }
        });
    }

    loadNotifications();
});
