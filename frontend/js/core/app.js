/**
 * PROVOK — Core Application Module
 * 
 * Shared utilities, API client, state management, toast system, nav effects.
 */

// ── API Client ────────────────────────────────────────────────
const API_BASE = '/api/v1';

export const api = {
    async request(method, path, body = null, options = {}) {
        const url = `${API_BASE}${path}`;
        const config = {
            method,
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            ...options,
        };
        const token = localStorage.getItem('provok-token');
        if (token) {
            config.headers['Authorization'] = `Bearer ${token}`;
        }
        if (body && method !== 'GET') {
            if (body instanceof FormData) {
                delete config.headers['Content-Type'];
                config.body = body;
            } else {
                config.body = JSON.stringify(body);
            }
        }
        try {
            const res = await fetch(url, config);
            if (res.status === 401) {
                const refreshed = await this.refresh();
                if (refreshed) {
                    return this.request(method, path, body, options);
                }
                if (!options.noRedirect) {
                    window.location.href = '/login';
                }
                throw new ApiError('Unauthorized', 401, null);
            }
            if (res.status === 204) {
                return null;
            }
            const data = await res.json();
            if (!res.ok) {
                throw new ApiError(data.detail || 'Request failed', res.status, data);
            }
            return data;
        } catch (err) {
            if (err instanceof ApiError) throw err;
            throw new ApiError('Network error', 0, null);
        }
    },

    get(path) { return this.request('GET', path); },
    post(path, body) { return this.request('POST', path, body); },
    put(path, body) { return this.request('PUT', path, body); },
    delete(path) { return this.request('DELETE', path); },

    async refresh() {
        try {
            const token = localStorage.getItem('provok-token');
            if (!token) return false;
            const res = await fetch(`${API_BASE}/auth/refresh`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                },
                credentials: 'include',
            });
            if (res.ok) {
                const data = await res.json();
                if (data.access_token) {
                    localStorage.setItem('provok-token', data.access_token);
                }
                return true;
            }
            return false;
        } catch {
            return false;
        }
    },
};

class ApiError extends Error {
    constructor(message, status, data) {
        super(message);
        this.status = status;
        this.data = data;
    }
}

// ── State Management ──────────────────────────────────────────
class Store {
    constructor() {
        this._state = {};
        this._listeners = new Map();
    }

    get(key) { return this._state[key]; }

    set(key, value) {
        const old = this._state[key];
        this._state[key] = value;
        if (old !== value && this._listeners.has(key)) {
            this._listeners.get(key).forEach(fn => fn(value, old));
        }
    }

    subscribe(key, fn) {
        if (!this._listeners.has(key)) this._listeners.set(key, new Set());
        this._listeners.get(key).add(fn);
        return () => this._listeners.get(key).delete(fn);
    }
}

export const store = new Store();

// ── Toast System — premium notifications ──────────────────────
const TOAST_ICONS = {
    success: '✓',
    error: '✕',
    warning: '⚠',
    info: 'ℹ',
};

export function toast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    
    const icon = TOAST_ICONS[type] || TOAST_ICONS.info;
    el.innerHTML = `<span class="toast-icon">${icon}</span><span>${message}</span>`;
    
    container.appendChild(el);
    setTimeout(() => {
        el.style.opacity = '0';
        el.style.transform = 'translateX(100%)';
        el.style.transition = 'all 0.3s ease';
        setTimeout(() => el.remove(), 300);
    }, duration);
}

// ── Time Formatting ───────────────────────────────────────────
export function timeAgo(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);
    
    if (seconds < 60) return 'just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
    return date.toLocaleDateString();
}

// ── Skeleton Loader ───────────────────────────────────────────
export function createSkeletonCards(count = 3) {
    let html = '';
    for (let i = 0; i < count; i++) {
        html += `<div class="debate-card" style="border-top:1px solid var(--line);padding:23px 0">
            <div class="skeleton skeleton-text" style="width:80px;height:10px;margin-bottom:13px"></div>
            <div class="skeleton skeleton-title"></div>
            <div class="skeleton skeleton-text" style="width:40%"></div>
        </div>`;
    }
    return html;
}

// ── Navigation Effects ────────────────────────────────────────
function initNavEffects() {
    const nav = document.querySelector('.nav');
    if (!nav) return;

    // Scroll shadow
    let lastScroll = 0;
    window.addEventListener('scroll', () => {
        const y = window.scrollY;
        nav.classList.toggle('scrolled', y > 10);
        lastScroll = y;
    }, { passive: true });

    // Active state
    const path = window.location.pathname;
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.toggle('active', link.getAttribute('href') === path);
    });

    // Mobile menu toggle
    const mobileToggle = document.querySelector('.mobile-toggle');
    const navLinks = document.querySelector('.nav-links');
    if (mobileToggle && navLinks) {
        mobileToggle.addEventListener('click', () => {
            navLinks.classList.toggle('open');
        });
        // Close on link click
        navLinks.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', () => navLinks.classList.remove('open'));
        });
    }
}

// ── Theme Management ──────────────────────────────────────────
function initTheme() {
    const savedTheme = localStorage.getItem('provok-theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
        document.documentElement.classList.add('dark');
    } else {
        document.documentElement.classList.remove('dark');
    }
}

export function toggleTheme() {
    const isDark = document.documentElement.classList.toggle('dark');
    localStorage.setItem('provok-theme', isDark ? 'dark' : 'light');
}

// ── Auth Init ───────────────────────────────────────────────────
async function initAuth() {
    try {
        const user = await api.request('GET', '/auth/me', null, { noRedirect: true });
        if (user) {
            store.set('user', user);
            const loginBtns = document.querySelectorAll('a[href="/login"]');
            loginBtns.forEach(btn => {
                if (btn.classList.contains('desktop-only') || btn.closest('.nav-actions')) {
                    const avatar = document.createElement('a');
                    avatar.href = '/profile/' + user.username;
                    avatar.className = 'nav-avatar';
                    avatar.style.cssText = 'width: 32px; height: 32px; border-radius: 50%; background: var(--ink); color: var(--paper); display: grid; place-items: center; font-weight: bold; text-decoration: none; font-size: 12px; transition: transform 0.15s;';
                    
                    if (user.avatar_url) {
                        avatar.style.backgroundImage = `url(${user.avatar_url})`;
                        avatar.style.backgroundSize = 'cover';
                        avatar.style.backgroundPosition = 'center';
                        avatar.innerHTML = '';
                    } else {
                        avatar.innerHTML = (user.username || 'U')[0].toUpperCase();
                    }
                    avatar.addEventListener('mouseenter', () => avatar.style.transform = 'scale(1.1)');
                    avatar.addEventListener('mouseleave', () => avatar.style.transform = '');
                    
                    btn.parentNode.replaceChild(avatar, btn);
                }
            });

            // Fetch notification count
            try {
                const notifData = await api.request('GET', '/notifications/?unread_only=true&limit=1', null, { noRedirect: true });
                if (notifData && notifData.unread_count > 0) {
                    const notifLink = document.querySelector('a[href="/notifications"]');
                    if (notifLink) {
                        const wrapper = document.createElement('span');
                        wrapper.className = 'nav-notif-wrapper';
                        wrapper.innerHTML = `Notifications<span class="notif-badge">${notifData.unread_count}</span>`;
                        notifLink.innerHTML = '';
                        notifLink.appendChild(wrapper);
                    }
                }
            } catch(e) { /* notifications unavailable */ }
        }
    } catch (e) {
        // Not logged in
    }
}

// ── Init ──────────────────────────────────────────────────────
initTheme();
document.addEventListener('DOMContentLoaded', () => {
    initNavEffects();
    const themeBtn = document.getElementById('theme-toggle');
    if (themeBtn) {
        themeBtn.addEventListener('click', toggleTheme);
    }
    initAuth();
});

export { ApiError };
