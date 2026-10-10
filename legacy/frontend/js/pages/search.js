/**
 * PROVOK — Search Page Module
 * Real-time search with keyboard shortcut support.
 */
import { api, toast, timeAgo } from '../core/app.js';

document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('search-input');
    const btn = document.getElementById('search-btn');
    const resultsContainer = document.getElementById('search-results');
    let debounceTimer = null;

    if (!input || !resultsContainer) return;

    // Focus search with Cmd+K / Ctrl+K
    document.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            input.focus();
            input.select();
        }
    });

    async function performSearch(query) {
        if (!query.trim()) {
            resultsContainer.innerHTML = `<div class="empty fade-in">
                <strong>Search PROVOK</strong>
                <span>Find questions and debates worth your attention.</span>
            </div>`;
            return;
        }

        // Show loading skeleton
        resultsContainer.innerHTML = `
            <div class="skeleton skeleton-text" style="width:60%;margin-top:20px"></div>
            <div class="skeleton skeleton-text" style="width:80%"></div>
            <div class="skeleton skeleton-text" style="width:40%"></div>
        `;

        try {
            const data = await api.get(`/search/?q=${encodeURIComponent(query)}&limit=20`);
            
            if (!data.results || data.results.length === 0) {
                resultsContainer.innerHTML = `<div class="empty fade-in">
                    <strong>No results for "${query}"</strong>
                    <span>Try different keywords or start a new debate.</span>
                    <div style="margin-top:16px"><a class="btn btn-red btn-sm" href="/ask">Start a debate →</a></div>
                </div>`;
                return;
            }

            resultsContainer.innerHTML = `<div class="eyebrow" style="margin-bottom:8px">${data.total} RESULT${data.total !== 1 ? 'S' : ''}</div>`;
            
            data.results.forEach((result, i) => {
                const el = document.createElement('div');
                el.className = 'search-result slide-up';
                el.style.animationDelay = `${i * 0.05}s`;
                el.style.cursor = 'pointer';

                if (result.type === 'debate') {
                    const statusClass = result.status === 'LIVE' ? 'badge-live' : 'badge-completed';
                    el.innerHTML = `
                        <div>
                            <div class="search-result-title">${result.title}</div>
                            <div class="search-result-meta">
                                <span class="badge ${statusClass}" style="font-size:8px;padding:2px 5px">${result.status}</span>
                                ${result.mode ? `<span style="margin-left:6px">${result.mode}</span>` : ''}
                                ${result.created_at ? `<span style="margin-left:6px">· ${timeAgo(result.created_at)}</span>` : ''}
                            </div>
                        </div>
                        <span class="search-result-type">Debate</span>
                    `;
                    el.addEventListener('click', () => window.location.href = result.url);
                } else if (result.type === 'user') {
                    el.innerHTML = `
                        <div style="display:flex;align-items:center;gap:10px">
                            <div class="avatar">${(result.username || 'U')[0].toUpperCase()}</div>
                            <div>
                                <div class="search-result-title" style="font-size:15px">${result.display_name}</div>
                                <div class="search-result-meta">@${result.username}</div>
                            </div>
                        </div>
                        <span class="search-result-type">User</span>
                    `;
                    el.addEventListener('click', () => window.location.href = result.url);
                }

                resultsContainer.appendChild(el);
            });
        } catch (err) {
            resultsContainer.innerHTML = `<div class="empty"><strong>Search failed</strong><span>${err.message}</span></div>`;
        }
    }

    // Debounced search on input
    input.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => performSearch(input.value), 300);
    });

    // Search on button click
    if (btn) {
        btn.addEventListener('click', () => performSearch(input.value));
    }

    // Search on Enter
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            clearTimeout(debounceTimer);
            performSearch(input.value);
        }
    });

    // Auto-focus
    input.focus();
});
