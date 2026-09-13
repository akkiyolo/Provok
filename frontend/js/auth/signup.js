/**
 * PROVOK — Signup Page Module
 * Form submission with button loading states, input validation, and auto-login.
 */
import { api, toast } from '../core/app.js';

document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('signup-form');
    const submitBtn = document.getElementById('signup-submit');
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

            hideError();
            if (submitBtn) {
                submitBtn.classList.add('loading');
                submitBtn.disabled = true;
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
                if (submitBtn) {
                    submitBtn.classList.remove('loading');
                    submitBtn.disabled = false;
                }
            }
        });

        form.querySelectorAll('input').forEach(input => {
            input.addEventListener('input', hideError);
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

    function hideError() {
        if (errorEl) {
            errorEl.style.display = 'none';
        }
    }
});
