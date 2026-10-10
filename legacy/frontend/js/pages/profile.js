/**
 * PROVOK — Profile Page Module
 * User profile, debates history, follow/unfollow, avatar upload, tabs.
 */
import { api, toast, store, timeAgo } from '../core/app.js';

document.addEventListener('DOMContentLoaded', async () => {
    // Extract username from /profile/{username}
    const pathParts = window.location.pathname.split('/').filter(Boolean);
    const username = pathParts[pathParts.length - 1];

    if (!username || username === 'profile') {
        window.location.href = '/';
        return;
    }

    try {
        const [profileUser, currentUser] = await Promise.all([
            api.get(`/users/${username}`),
            api.request('GET', '/auth/me', null, { noRedirect: true }).catch(() => null)
        ]);

        renderProfile(profileUser);
        loadUserDebates(username);

        const isOwner = currentUser && currentUser.username.toLowerCase() === profileUser.username.toLowerCase();
        const btnFollow = document.getElementById('btn-follow');
        const btnEditAvatar = document.getElementById('btn-edit-avatar');
        const fileInput = document.getElementById('avatar-upload');

        if (isOwner) {
            if (btnFollow) btnFollow.style.display = 'none';
            if (btnEditAvatar) {
                btnEditAvatar.style.display = 'block';
                btnEditAvatar.addEventListener('click', () => {
                    fileInput.click();
                });
            }

            if (fileInput) {
                fileInput.addEventListener('change', async (e) => {
                    const file = e.target.files[0];
                    if (!file) return;

                    const formData = new FormData();
                    formData.append('file', file);

                    try {
                        const data = await api.post('/users/me/avatar', formData);
                        toast('Profile picture updated!', 'success');
                        
                        const avatarEl = document.getElementById('profile-avatar');
                        avatarEl.style.backgroundImage = `url(${data.avatar_url})`;
                        avatarEl.style.backgroundSize = 'cover';
                        avatarEl.style.backgroundPosition = 'center';
                        avatarEl.innerHTML = '';
                        
                        setTimeout(() => window.location.reload(), 1000);
                    } catch (err) {
                        toast('Failed to upload image.', 'error');
                    }
                });
            }
        } else {
            if (btnFollow) {
                btnFollow.addEventListener('click', async () => {
                    if (!currentUser) {
                        window.location.href = '/login';
                        return;
                    }
                    try {
                        const res = await api.post(`/users/${username}/follow`);
                        if (res.status === 'followed') {
                            btnFollow.textContent = 'Unfollow';
                            btnFollow.classList.replace('btn-secondary', 'btn-ghost');
                            toast(`You are now following ${username}`, 'success');
                            const followersEl = document.getElementById('stat-followers');
                            followersEl.textContent = parseInt(followersEl.textContent || '0') + 1;
                        } else {
                            btnFollow.textContent = 'Follow';
                            btnFollow.classList.replace('btn-ghost', 'btn-secondary');
                            toast(`Unfollowed ${username}`, 'info');
                            const followersEl = document.getElementById('stat-followers');
                            followersEl.textContent = Math.max(0, parseInt(followersEl.textContent || '0') - 1);
                        }
                    } catch (err) {
                        toast(err.message, 'error');
                    }
                });
            }
        }

        // Tab switching
        const tabs = document.querySelectorAll('.profile-tab');
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                tabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                const tabText = tab.textContent.trim().toLowerCase();
                if (tabText === 'debates') {
                    loadUserDebates(username);
                } else {
                    const feedEl = document.getElementById('profile-feed');
                    if (feedEl) {
                        feedEl.innerHTML = `
                            <div class="empty glass" style="grid-column:1/-1;padding:48px;border-radius:var(--radius-lg);text-align:center;">
                                <strong style="display:block;font-size:16px;color:var(--ink);margin-bottom:6px;">No ${tabText} to display</strong>
                                <span class="muted">Check back later or join a live debate.</span>
                            </div>
                        `;
                    }
                }
            });
        });

    } catch (err) {
        console.error('Profile error:', err);
        toast('User not found', 'error');
    }
});

function animateCounter(el, target) {
    if (!el) return;
    const duration = 600;
    const start = 0;
    const startTime = performance.now();
    function step(now) {
        const progress = Math.min((now - startTime) / duration, 1);
        el.textContent = Math.floor(progress * target);
        if (progress < 1) requestAnimationFrame(step);
        else el.textContent = target;
    }
    requestAnimationFrame(step);
}

function renderProfile(user) {
    const nameEl = document.getElementById('profile-name');
    const eyebrowEl = document.getElementById('profile-eyebrow');
    const bioEl = document.getElementById('profile-bio');

    if (nameEl) nameEl.textContent = user.display_name || user.username;
    if (eyebrowEl) eyebrowEl.textContent = `@${user.username}`;
    if (bioEl) bioEl.textContent = user.bio || 'No bio provided.';
    
    animateCounter(document.getElementById('stat-debates'), user.stats.debates_participated || 0);
    animateCounter(document.getElementById('stat-wins'), user.stats.debates_won || 0);
    animateCounter(document.getElementById('stat-followers'), user.stats.followers || 0);
    animateCounter(document.getElementById('stat-following'), user.stats.following || 0);

    const avatarEl = document.getElementById('profile-avatar');
    if (avatarEl) {
        if (user.avatar_url) {
            avatarEl.style.backgroundImage = `url(${user.avatar_url})`;
            avatarEl.style.backgroundSize = 'cover';
            avatarEl.style.backgroundPosition = 'center';
            avatarEl.innerHTML = '';
        } else {
            avatarEl.innerHTML = (user.username || 'U')[0].toUpperCase();
        }
    }
}

async function loadUserDebates(username) {
    const feedEl = document.getElementById('profile-feed');
    if (!feedEl) return;

    feedEl.innerHTML = `
        <div class="skeleton-card shimmer" style="height:140px;border-radius:var(--radius-md);"></div>
        <div class="skeleton-card shimmer" style="height:140px;border-radius:var(--radius-md);"></div>
    `;

    try {
        const debates = await api.get(`/users/${username}/debates`);
        if (!debates || debates.length === 0) {
            feedEl.innerHTML = `
                <div class="empty glass" style="grid-column:1/-1;padding:48px;border-radius:var(--radius-lg);text-align:center;">
                    <strong style="display:block;font-size:16px;color:var(--ink);margin-bottom:6px;">No debates yet</strong>
                    <span class="muted">This user hasn't participated in any public debates.</span>
                </div>
            `;
            return;
        }

        feedEl.innerHTML = debates.map((d, index) => {
            const statusBadge = d.status === 'COMPLETED' 
                ? `<span class="badge" style="background:var(--paper-2);color:var(--ink-light);font-size:10px;">COMPLETED</span>`
                : `<span class="badge" style="background:rgba(224,90,43,0.15);color:var(--red);font-size:10px;">LIVE</span>`;
            const timeStr = d.created_at ? timeAgo(d.created_at) : '';
            return `
                <div class="debate-card glass fade-in" style="animation-delay:${index * 60}ms;padding:22px;border-radius:var(--radius-md);border:1px solid var(--line);transition:transform var(--duration-fast),box-shadow var(--duration-fast);cursor:pointer;" onclick="location.href='/debate/${d.id}'">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                        ${statusBadge}
                        <span class="muted" style="font-size:11px;">${timeStr}</span>
                    </div>
                    <h3 style="font-family:var(--display);font-size:17px;font-weight:600;line-height:1.3;margin-bottom:12px;color:var(--ink);">${d.title}</h3>
                    <div style="display:flex;justify-content:space-between;align-items:center;font-size:12px;color:var(--muted);">
                        <span>Round ${d.current_round || 1} · ${d.mode || 'Swarm'}</span>
                        <span style="color:var(--red);font-weight:500;">Enter debate →</span>
                    </div>
                </div>
            `;
        }).join('');

    } catch (err) {
        console.error('Failed to load user debates:', err);
        feedEl.innerHTML = `
            <div class="empty" style="grid-column:1/-1;text-align:center;padding:32px;">
                <span class="muted">Could not load debates for this user.</span>
            </div>
        `;
    }
}
