/**
 * PROVOK — Ask Page Module
 */
import { api, toast } from '../core/app.js';

document.addEventListener('DOMContentLoaded', () => {
    // Position buttons
    document.querySelectorAll('#position-options .option').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#position-options .option').forEach(b => {
                b.classList.remove('selected', 'for', 'against');
            });
            const pos = btn.dataset.value;
            btn.classList.add('selected');
            if (pos === 'AGAINST') {
                btn.classList.add('against');
            } else {
                btn.classList.add('for');
            }
        });
    });

    // Opponent buttons
    document.querySelectorAll('#opponent-options .option').forEach(btn => {
        if (btn.disabled) return;
        btn.addEventListener('click', () => {
            document.querySelectorAll('#opponent-options .option').forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
        });
    });

    // Mode buttons
    document.querySelectorAll('#mode-options .option').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#mode-options .option').forEach(b => b.classList.remove('selected'));
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
