/**
 * Agency OS: Operations Command Center Core Engine
 * Professional, high-density AI operations platform client
 * Palantir x Linear x Vercel command center
 */
(function () {
    'use strict';

    let lastMetricsUpdateTime = Date.now();
    let kpiCountUpExecuted = false;

    const state = {
        initialized: true,
        activeSubsystem: null,
        highlightSubsystem: function (subsystemId) {
            state.activeSubsystem = subsystemId;
        },
        triggerEventAnimation: function (eventType) {
            initCoreEventBridge(eventType);
        },
        recordMetricsUpdated: function () {
            lastMetricsUpdateTime = Date.now();
            updateLastUpdatedDisplay();
        },
        dispose: function () {}
    };

    window.agencyDashboard3D = state;

    /**
     * Dynamic Operator Greeting based on local time
     */
    function initCeoGreeting() {
        const greetingEl = document.getElementById('ceo-dynamic-greeting');
        if (!greetingEl) return;

        const hour = new Date().getHours();
        let greeting = 'Good evening, Operator';
        if (hour >= 5 && hour < 12) {
            greeting = 'Good morning, Operator';
        } else if (hour >= 12 && hour < 17) {
            greeting = 'Good afternoon, Operator';
        } else {
            greeting = 'Good evening, Operator';
        }

        const currentText = greetingEl.innerText || '';
        if (currentText.includes('CEO')) {
            greeting = greeting.replace('Operator', 'CEO');
        }
        greetingEl.innerText = greeting;
    }

    /**
     * Subtle, professional card microinteractions without decorative 3D tilt
     */
    function initPerspectiveCardTilts() {
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            return;
        }

        const cards = document.querySelectorAll('.agency-panel-card, .agency-kpi-block, .core-satellite-card');
        cards.forEach(card => {
            card.addEventListener('mouseenter', () => {
                card.classList.add('is-hovered');
            });
            card.addEventListener('mouseleave', () => {
                card.classList.remove('is-hovered');
            });
        });
    }

    /**
     * Core Event Bridge: Animates new real-time operational events cleanly
     */
    function initCoreEventBridge(eventType) {
        const liveOpsList = document.getElementById('ceo-recent-activity-list');
        if (!liveOpsList) return;

        const firstItem = liveOpsList.firstElementChild;
        if (firstItem && !firstItem.classList.contains('event-animated')) {
            firstItem.classList.add('event-animated');
            firstItem.style.opacity = '0';
            firstItem.style.transform = 'translateY(-4px)';
            requestAnimationFrame(() => {
                firstItem.style.transition = 'opacity 0.3s cubic-bezier(0.16, 1, 0.3, 1), transform 0.3s cubic-bezier(0.16, 1, 0.3, 1)';
                firstItem.style.opacity = '1';
                firstItem.style.transform = 'translateY(0)';
            });
        }
    }

    /**
     * Subtle KPI number count-up animation on first load
     * Adheres strictly to: numbers count from 0 to actual value over 500-600ms
     */
    function initKpiNumberCountUp() {
        if (kpiCountUpExecuted) return;
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            kpiCountUpExecuted = true;
            return;
        }

        const kpiElements = document.querySelectorAll('.agency-kpi-big-val, .satellite-big-val, .ceo-kpi-value');
        if (!kpiElements.length) return;

        kpiCountUpExecuted = true;
        kpiElements.forEach((el) => {
            const rawText = el.innerText.trim();
            const isCurrency = rawText.startsWith('$');
            const cleanNum = parseFloat(rawText.replace(/[^0-9.]/g, ''));

            if (isNaN(cleanNum) || cleanNum <= 0) return;

            const duration = 600;
            const startTime = performance.now();

            function updateCount(currentTime) {
                const elapsed = currentTime - startTime;
                const progress = Math.min(elapsed / duration, 1);
                // Ease-out cubic
                const easeOut = 1 - Math.pow(1 - progress, 3);
                const currentVal = Math.round(cleanNum * easeOut);

                if (isCurrency) {
                    el.innerText = '$' + currentVal.toLocaleString();
                } else {
                    el.innerText = currentVal.toLocaleString();
                }

                if (progress < 1) {
                    requestAnimationFrame(updateCount);
                } else {
                    el.innerText = rawText;
                }
            }

            requestAnimationFrame(updateCount);
        });
    }

    /**
     * Progressive reveal for the 9-stage Revenue Pipeline funnel
     */
    function initPipelineProgressiveReveal() {
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

        const steps = document.querySelectorAll('.ceo-funnel-step');
        steps.forEach((step, idx) => {
            step.style.opacity = '0';
            step.style.transform = 'translateY(4px)';
            step.style.transition = `opacity 0.35s cubic-bezier(0.16, 1, 0.3, 1) ${idx * 35}ms, transform 0.35s cubic-bezier(0.16, 1, 0.3, 1) ${idx * 35}ms`;
            requestAnimationFrame(() => {
                step.style.opacity = '1';
                step.style.transform = 'translateY(0)';
            });
        });
    }

    /**
     * Topbar "Last updated: X seconds ago" tracker
     */
    function updateLastUpdatedDisplay() {
        const timerContainer = document.getElementById('top-last-updated');
        const timerVal = document.getElementById('top-last-updated-val');
        if (!timerVal) return;

        if (timerContainer) {
            timerContainer.style.display = 'inline-flex';
        }

        const secAgo = Math.floor((Date.now() - lastMetricsUpdateTime) / 1000);
        if (secAgo < 5) {
            timerVal.innerText = 'just now';
        } else if (secAgo < 60) {
            timerVal.innerText = `${secAgo}s ago`;
        } else {
            const minAgo = Math.floor(secAgo / 60);
            timerVal.innerText = `${minAgo}m ago`;
        }
    }

    /**
     * Initialize Command Center core controllers
     */
    function initDashboard3DCore() {
        initCeoGreeting();
        initPerspectiveCardTilts();

        const feed = document.getElementById('ceo-recent-activity-list');
        if (feed && window.MutationObserver) {
            const observer = new MutationObserver((mutations) => {
                mutations.forEach(m => {
                    if (m.addedNodes.length > 0) {
                        initCoreEventBridge();
                    }
                });
            });
            observer.observe(feed, { childList: true });
        }

        // Initialize relative timer ticker
        updateLastUpdatedDisplay();
        setInterval(updateLastUpdatedDisplay, 10000);

        // Staggered section entrances
        setTimeout(initPipelineProgressiveReveal, 80);
        setTimeout(initKpiNumberCountUp, 250);

        const origNav = window.navToView;
        if (typeof origNav === 'function') {
            window.navToView = function (viewName) {
                origNav(viewName);
                if (state.highlightSubsystem) {
                    state.highlightSubsystem(viewName);
                }
            };
        }
    }

    window.initCeoGreeting = initCeoGreeting;
    window.initPerspectiveCardTilts = initPerspectiveCardTilts;
    window.initCoreEventBridge = initCoreEventBridge;
    window.initKpiNumberCountUp = initKpiNumberCountUp;
    window.initPipelineProgressiveReveal = initPipelineProgressiveReveal;
    window.initDashboard3DCore = initDashboard3DCore;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initDashboard3DCore);
    } else {
        initDashboard3DCore();
    }
})();
