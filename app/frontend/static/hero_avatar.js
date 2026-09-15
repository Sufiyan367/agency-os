/**
 * Agency OS — Interactive AI Hero Avatar & Directive Engine
 *
 * Reference interaction: bible-strong-avatar-lab (organic floating, spring/lerp tracking, proximity reaction)
 * Reference visual atmosphere: limora.ai/mcp (dark obsidian, luminous radial glow, glass command pill)
 *
 * Engineering invariants:
 * - Single requestAnimationFrame loop
 * - Zero external animation dependencies
 * - Automatically pauses on hidden tab
 * - Respects prefers-reduced-motion
 * - Fully responsive (disables mouse tracking on mobile touchscreens)
 * - Zero memory leaks or duplicated listeners
 */

(function () {
    'use strict';

    let animFrameId = null;
    let isRunning = false;

    // State
    const state = {
        targetX: 0,
        targetY: 0,
        currentX: 0,
        currentY: 0,
        proximity: 0,
        currentProximity: 0,
        energy: 0,
        isFocused: false,
        isMobile: false,
        reducedMotion: false
    };

    function initHeroAvatar() {
        const container = document.getElementById('hero-command-container');
        const wrapper = document.getElementById('hero-avatar-wrapper');
        const mantle = document.getElementById('hero-avatar-mantle');
        const globalSearch = document.getElementById('global-search-input');

        if (!container || !wrapper || !mantle) {
            return;
        }

        // Check reduced motion
        state.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        state.isMobile = window.innerWidth < 768;

        window.addEventListener('resize', () => {
            state.isMobile = window.innerWidth < 768;
        }, { passive: true });

        // 1. Mouse / Pointer Interaction with Parallax
        function onPointerMove(e) {
            if (state.reducedMotion || state.isMobile) return;

            const rect = container.getBoundingClientRect();
            const wrapperRect = wrapper.getBoundingClientRect();

            // Normalized coordinates [-1, 1] relative to hero container
            const normX = ((e.clientX - rect.left) / rect.width - 0.5) * 2;
            const normY = ((e.clientY - rect.top) / rect.height - 0.5) * 2;

            state.targetX = Math.max(-1, Math.min(1, normX));
            state.targetY = Math.max(-1, Math.min(1, normY));

            // Proximity to avatar center
            const avatarCenterX = wrapperRect.left + wrapperRect.width / 2;
            const avatarCenterY = wrapperRect.top + wrapperRect.height / 2;
            const dist = Math.hypot(e.clientX - avatarCenterX, e.clientY - avatarCenterY);

            // Proximity range 240px
            state.proximity = Math.max(0, 1 - dist / 240);
        }

        function onPointerLeave() {
            state.targetX = 0;
            state.targetY = 0;
            state.proximity = 0;
        }

        container.addEventListener('pointermove', onPointerMove, { passive: true });
        container.addEventListener('pointerleave', onPointerLeave, { passive: true });

        // 2. Input / Typing Reactivity
        function addEnergy(amount) {
            state.energy = Math.min(1.0, state.energy + amount);
        }

        function triggerPulse() {
            addEnergy(0.85);
            const ripple = document.createElement('div');
            ripple.className = 'avatar-ripple-active';
            wrapper.appendChild(ripple);
            setTimeout(() => {
                if (ripple.parentNode) ripple.parentNode.removeChild(ripple);
            }, 680);
        }

        function bindInputEvents(inputEl) {
            if (!inputEl) return;
            inputEl.addEventListener('input', () => {
                addEnergy(0.24);
            }, { passive: true });

            inputEl.addEventListener('keydown', (e) => {
                addEnergy(0.18);
                if (e.key === 'Enter') {
                    triggerPulse();
                }
            }, { passive: true });

            inputEl.addEventListener('focus', () => {
                state.isFocused = true;
                addEnergy(0.35);
            }, { passive: true });

            inputEl.addEventListener('blur', () => {
                state.isFocused = false;
            }, { passive: true });
        }

        bindInputEvents(globalSearch);

        // Avatar click triggers affirmative energy ripple pulse
        wrapper.addEventListener('click', () => {
            triggerPulse();
        });

        // 3. Animation Loop (requestAnimationFrame)
        const maxOffset = 22; // max pixels avatar travels from center
        let startTime = performance.now();

        function render(time) {
            if (!isRunning) return;

            const t = (time - startTime) * 0.0018;

            if (state.reducedMotion) {
                // Static, minimal mode
                container.style.setProperty('--avatar-energy', state.isFocused ? '0.35' : '0.05');
                animFrameId = requestAnimationFrame(render);
                return;
            }

            // Spring / Lerp interpolation for mouse follow
            const lerpRate = 0.07;
            const targetX = state.isMobile ? 0 : state.targetX * maxOffset;
            const targetY = state.isMobile ? 0 : state.targetY * maxOffset;

            state.currentX += (targetX - state.currentX) * lerpRate;
            state.currentY += (targetY - state.currentY) * lerpRate;
            state.currentProximity += (state.proximity - state.currentProximity) * lerpRate;

            // Decay typing energy smoothly back to baseline
            state.energy = Math.max(0, state.energy * 0.94 - 0.0025);
            const effectiveEnergy = Math.max(state.energy, state.isFocused ? 0.32 : 0.0);

            // Dynamic morphing border-radius based on harmonic trigonometric curves
            const r1 = Math.round(50 + 12 * Math.sin(t) + 6 * Math.cos(t * 1.3) + effectiveEnergy * 6 * Math.sin(t * 3));
            const r2 = Math.round(50 + 13 * Math.cos(t * 0.9) - 7 * Math.sin(t * 1.5));
            const r3 = Math.round(50 + 11 * Math.sin(t * 1.2) - 6 * Math.cos(t * 1.8));
            const r4 = Math.round(50 + 14 * Math.cos(t * 1.4) + 6 * Math.sin(t * 1.1));

            mantle.style.borderRadius = `${r1}% ${100 - r1}% ${r2}% ${100 - r2}% / ${r3}% ${r4}% ${100 - r4}% ${100 - r3}%`;

            // 3D Tilt and scale
            const tiltX = -state.currentY * 0.35;
            const tiltY = state.currentX * 0.35;
            const scale = 1 + state.currentProximity * 0.07 + effectiveEnergy * 0.08;

            wrapper.style.transform = `translate3d(${state.currentX.toFixed(2)}px, ${state.currentY.toFixed(2)}px, 0) rotateX(${tiltX.toFixed(2)}deg) rotateY(${tiltY.toFixed(2)}deg) scale(${scale.toFixed(3)})`;

            // Parallax on background atmospheric glow & nucleus
            container.style.setProperty('--bg-shift-x', `${(state.currentX * 0.22).toFixed(1)}px`);
            container.style.setProperty('--bg-shift-y', `${(state.currentY * 0.22).toFixed(1)}px`);
            container.style.setProperty('--avatar-energy', effectiveEnergy.toFixed(3));
            container.style.setProperty('--avatar-proximity', state.currentProximity.toFixed(3));
            container.style.setProperty('--nucleus-x', `${(state.currentX * 0.18).toFixed(1)}px`);
            container.style.setProperty('--nucleus-y', `${(state.currentY * 0.18).toFixed(1)}px`);

            animFrameId = requestAnimationFrame(render);
        }

        // Visibility handler: pause loop when tab is in background
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                stopLoop();
            } else {
                startLoop();
            }
        });

        function startLoop() {
            if (!isRunning) {
                isRunning = true;
                startTime = performance.now();
                animFrameId = requestAnimationFrame(render);
            }
        }

        function stopLoop() {
            isRunning = false;
            if (animFrameId) {
                cancelAnimationFrame(animFrameId);
                animFrameId = null;
            }
        }

        startLoop();

        // Export controller cleanly
        window.agencyHeroAvatar = {
            addEnergy,
            triggerPulse,
            start: startLoop,
            stop: stopLoop
        };
    }

    function escapeHtml(str) {
        if (!str) return '';
        return str
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initHeroAvatar);
    } else {
        initHeroAvatar();
    }
})();
