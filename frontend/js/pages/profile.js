import { api, toast, store } from '../core/app.js';

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

        const isOwner = currentUser && currentUser.username === profileUser.username;
        const btnFollow = document.getElementById('btn-follow');
        const btnEditAvatar = document.getElementById('btn-edit-avatar');
        const fileInput = document.getElementById('avatar-upload');

        if (isOwner) {
            btnFollow.style.display = 'none';
            btnEditAvatar.style.display = 'block';

            btnEditAvatar.addEventListener('click', () => {
                fileInput.click();
            });

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
                    
                    // Trigger a reload to update the nav avatar
                    setTimeout(() => window.location.reload(), 1000);
                } catch (err) {
                    toast('Failed to upload image.', 'error');
                }
            });
        } else {
            // Handle follow logic
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
                    } else {
                        btnFollow.textContent = 'Follow';
                        btnFollow.classList.replace('btn-ghost', 'btn-secondary');
                        toast(`Unfollowed ${username}`, 'info');
                    }
                } catch (err) {
                    toast(err.message, 'error');
                }
            });
        }
    } catch (err) {
        toast('User not found', 'error');
        // setTimeout(() => window.location.href = '/', 2000);
    }
});

function renderProfile(user) {
    document.getElementById('profile-name').textContent = user.display_name;
    document.getElementById('profile-eyebrow').textContent = `@${user.username}`;
    document.getElementById('profile-bio').textContent = user.bio || 'No bio provided.';
    
    document.getElementById('stat-debates').textContent = user.stats.debates_participated;
    document.getElementById('stat-wins').textContent = user.stats.debates_won;
    document.getElementById('stat-followers').textContent = user.stats.followers;
    document.getElementById('stat-following').textContent = user.stats.following;

    const avatarEl = document.getElementById('profile-avatar');
    if (user.avatar_url) {
        avatarEl.style.backgroundImage = `url(${user.avatar_url})`;
        avatarEl.style.backgroundSize = 'cover';
        avatarEl.style.backgroundPosition = 'center';
        avatarEl.innerHTML = '';
    } else {
        avatarEl.innerHTML = user.username[0].toUpperCase();
    }
}
