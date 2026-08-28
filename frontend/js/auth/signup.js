/**
 * PROVOK — Signup Page Module
 */
import { api, toast } from '../core/app.js';

document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('signup-form');
    const errorEl = document.getElementById('auth-error');
    const googleBtn = document.getElementById('btn-google-signup');

    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('signup-username').value.trim();
            const email = document.getElementById('signup-email').value.trim();
            const password = document.getElementById('signup-password').value;

            if (!username || !email || !password) {
                showError('Please fill in all fields');
                return;
            }
            if (password.length < 8) {
                showError('Password must be at least 8 characters');
                return;
            }

            try {
                await api.post('/auth/register', { username, email, password });
                
                const formData = new URLSearchParams();
                formData.append('username', email);
                formData.append('password', password);
                
                const loginRes = await fetch('/api/v1/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: formData
                });
                if (loginRes.ok) {
                    const loginData = await loginRes.json();
                    localStorage.setItem('provok-token', loginData.access_token);
                }
                
                toast('Account created! Welcome to PROVOK.', 'success');
                window.location.href = `/profile/${username}`;
            } catch (err) {
                showError(err.message || 'Registration failed');
            }
        });
    }

    if (googleBtn) {
        googleBtn.addEventListener('click', () => {
            window.location.href = '/api/v1/auth/google';
        });
    }

    function showError(msg) {
        if (errorEl) {
            errorEl.textContent = msg;
            errorEl.style.display = 'block';
        }
    }
});
