/**
 * PROVOK — Ask Page Module
 */
import { api, toast } from '../core/app.js';

document.addEventListener('DOMContentLoaded', () => {
    // Position buttons
    document.querySelectorAll('#position-btns .position-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#position-btns .position-btn').forEach(b => {
                b.classList.remove('selected-for', 'selected-against');
            });
            const pos = btn.dataset.position;
            if (pos.includes('AGAINST')) {
                btn.classList.add('selected-against');
            } else {
                btn.classList.add('selected-for');
            }
        });
    });

    // Opponent buttons
    document.querySelectorAll('#opponent-btns .opponent-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#opponent-btns .opponent-btn').forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
        });
    });

    // Mode buttons
    document.querySelectorAll('#mode-btns .mode-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#mode-btns .mode-btn').forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
        });
    });

    // Submit
    const submitBtn = document.getElementById('ask-submit');
    if (submitBtn) {
        submitBtn.addEventListener('click', async () => {
            const question = document.getElementById('ask-question').value.trim();
            if (!question) {
                toast('Please enter a question', 'error');
                return;
            }
            toast('Creating debate...', 'info');
            // Will call API in Phase 3
        });
    }

    // Auto-resize textarea
    const textarea = document.getElementById('ask-question');
    if (textarea) {
        textarea.addEventListener('input', () => {
            textarea.style.height = 'auto';
            textarea.style.height = textarea.scrollHeight + 'px';
        });
    }
});
