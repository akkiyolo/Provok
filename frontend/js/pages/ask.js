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

            // Extract selected options
            const positionBtn = document.querySelector('#position-options .option.selected');
            const opponentBtn = document.querySelector('#opponent-options .option.selected');
            const modeBtn = document.querySelector('#mode-options .option.selected');

            const payload = {
                title: question,
                initial_position: positionBtn ? positionBtn.dataset.value : 'FOR',
                opponent_type: opponentBtn ? opponentBtn.dataset.value : 'AI_SWARM',
                mode: modeBtn ? modeBtn.dataset.value : 'ASYNC',
                is_public: true
            };

            toast('Creating debate...', 'info');
            
            try {
                const res = await api.post('/debates/', payload);
                if (res.id) {
                    toast('Debate created!', 'success');
                    window.location.href = `/debate/${res.id}`;
                }
            } catch (err) {
                toast(err.message || 'Failed to create debate', 'error');
            }
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
