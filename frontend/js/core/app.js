/**
 * PROVOK — Core Application Module
 * 
 * Shared utilities, API client, state management, toast system.
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
        if (body && method !== 'GET') {
            config.body = JSON.stringify(body);
        }
        try {
            const res = await fetch(url, config);
            if (res.status === 401) {
                // Try token refresh
                const refreshed = await this.refresh();
                if (refreshed) {
                    return this.request(method, path, body, options);
                }
                window.location.href = '/login';
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
            const res = await fetch(`${API_BASE}/auth/refresh`, {
                method: 'POST',
                credentials: 'include',
            });
            return res.ok;
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

// ── Toast System ──────────────────────────────────────────────
export function toast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const el = document.createElement('div');
    el.className = 'toast';
    if (type === 'error') el.style.borderColor = 'var(--error)';
    if (type === 'success') el.style.borderColor = 'var(--success)';
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => {
        el.style.opacity = '0';
        el.style.transform = 'translateX(100%)';
        el.style.transition = 'all 0.3s ease';
        setTimeout(() => el.remove(), 300);
    }, duration);
}

// ── Navigation Active State ───────────────────────────────────
function setActiveNav() {
    const path = window.location.pathname;
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.toggle('active', link.getAttribute('href') === path);
    });
}

// ── Init ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    setActiveNav();
});

export { ApiError };
