/**
 * PROVOK — Home Page Module
 */
import { api, store, toast } from '../core/app.js';

document.addEventListener('DOMContentLoaded', () => {
    // Debate cards are clickable
    document.querySelectorAll('.debate-card').forEach(card => {
        card.addEventListener('click', () => {
            // In production, navigate to actual debate
            window.location.href = '/debate/demo';
        });
    });

    // Topic tags interactive
    document.querySelectorAll('#topic-tags .tag').forEach(tag => {
        tag.addEventListener('click', () => {
            document.querySelectorAll('#topic-tags .tag').forEach(t => t.classList.remove('active'));
            tag.classList.add('active');
        });
    });
});
