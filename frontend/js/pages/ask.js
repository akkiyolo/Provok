/**
 * PROVOK — Ask Page Module
 * Supports Human vs AI Swarm, Human vs Human, and autonomous Agent vs Agent (LiteLLM Groq vs Gemini).
 */
import { api, toast } from '../core/app.js';

document.addEventListener('DOMContentLoaded', () => {
    const positionField = document.getElementById('position-field');

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
        btn.addEventListener('click', () => {
            document.querySelectorAll('#opponent-options .option').forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
            const opp = btn.dataset.value;
            if (opp === 'AI_VS_AI') {
                if (positionField) positionField.style.display = 'none';
            } else {
                if (positionField) positionField.style.display = 'block';
            }
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
            const titleInput = document.getElementById('ask-title');
            const title = (titleInput && titleInput.value.trim()) || question;

            if (!question) {
                toast('Please enter a question or topic', 'error');
                return;
            }

            // Extract selected options
            const positionBtn = document.querySelector('#position-options .option.selected');
            const opponentBtn = document.querySelector('#opponent-options .option.selected');
            const modeBtn = document.querySelector('#mode-options .option.selected');
            const oppVal = opponentBtn ? opponentBtn.dataset.value : 'AI_SWARM';

            const payload = {
                title: question,
                initial_position: oppVal === 'AI_VS_AI' ? 'FOR' : (positionBtn ? positionBtn.dataset.value : 'FOR'),
                opponent_type: oppVal,
                mode: modeBtn ? modeBtn.dataset.value : 'LIVE',
                is_public: true
            };

            submitBtn.classList.add('loading');
            submitBtn.disabled = true;
            toast(oppVal === 'AI_VS_AI' ? 'Launching Agent vs Agent arena...' : 'Creating debate...', 'info');
            
            try {
                const res = await api.post('/debates/', payload);
                if (res.id) {
                    toast('Debate created!', 'success');
                    window.location.href = `/debate/${res.id}`;
                }
            } catch (err) {
                toast(err.message || 'Failed to create debate', 'error');
                submitBtn.classList.remove('loading');
                submitBtn.disabled = false;
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
