/**
 * PROVOK — Login Page Module
 */
import { api, toast } from '../core/app.js';

document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('login-form');
    const errorEl = document.getElementById('auth-error');
    const googleBtn = document.getElementById('btn-google-login');

    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('login-email').value.trim();
            const password = document.getElementById('login-password').value;
            
            if (!email || !password) {
                showError('Please fill in all fields');
                return;
            }

            try {
                const formData = new URLSearchParams();
                formData.append('username', email);
                formData.append('password', password);
                
                const res = await fetch('/api/v1/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: formData
                });
                if (!res.ok) {
                    const errorData = await res.json();
                    throw new Error(errorData.detail || 'Login failed');
                }
                const data = await res.json();
                localStorage.setItem('provok-token', data.access_token);
                toast('Welcome back!', 'success');
                window.location.href = '/';
            } catch (err) {
                showError(err.message || 'Invalid credentials');
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
