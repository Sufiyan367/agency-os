/* ==========================================================================
   AGENCY OS — CEO COMMAND CENTER 3D SCRIPT
   Dynamic Greeting, 3D Core Reactivity & Perspective Microinteractions
   ========================================================================== */

(function() {
  'use strict';

  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  document.addEventListener('DOMContentLoaded', () => {
    initCeoGreeting();
    initPerspectiveCardTilts();
    initCoreEventBridge();
  });

  /* --------------------------------------------------------------------------
     1. Dynamic Greeting
     -------------------------------------------------------------------------- */
  function initCeoGreeting() {
    const greetingEl = document.getElementById('ceo-dynamic-greeting');
    if (!greetingEl) return;

    const hour = new Date().getHours();
    let timeOfDay = 'evening';
    if (hour >= 5 && hour < 12) {
      timeOfDay = 'morning';
    } else if (hour >= 12 && hour < 17) {
      timeOfDay = 'afternoon';
    } else {
      timeOfDay = 'evening';
    }

    greetingEl.textContent = `Good ${timeOfDay}, CEO.`;
  }

  /* --------------------------------------------------------------------------
     2. 3D Perspective Card Tilt Microinteractions
     -------------------------------------------------------------------------- */
  function initPerspectiveCardTilts() {
    if (prefersReducedMotion || window.innerWidth < 1024) return;

    const tiltCards = document.querySelectorAll('.agency-kpi-block, .agency-panel-card');

    tiltCards.forEach(card => {
      let isHovered = false;

      card.addEventListener('mouseenter', () => {
        isHovered = true;
      });

      card.addEventListener('mousemove', (e) => {
        if (!isHovered) return;
        const rect = card.getBoundingClientRect();
        const x = (e.clientX - rect.left) / rect.width - 0.5;
        const y = (e.clientY - rect.top) / rect.height - 0.5;

        // Subtle controlled rotation: max 3.5 degrees
        const rotX = -y * 7;
        const rotY = x * 7;

        card.style.transform = `perspective(800px) rotateX(${rotX.toFixed(2)}deg) rotateY(${rotY.toFixed(2)}deg) translateY(-2px)`;
      });

      card.addEventListener('mouseleave', () => {
        isHovered = false;
        card.style.transform = '';
      });
    });
  }

  /* --------------------------------------------------------------------------
     3. 3D Autonomous Operating Core Reactivity
     -------------------------------------------------------------------------- */
  function initCoreEventBridge() {
    // Listen for custom agency events or update intervals
    window.addEventListener('agency:event', (e) => {
      const eventType = e.detail?.type || '';
      highlightCoreDomain(eventType);
    });
  }

  function highlightCoreDomain(type) {
    const nucleus = document.querySelector('.core-center-nucleus');
    if (!nucleus) return;

    nucleus.style.boxShadow = '0 0 36px rgba(0, 212, 239, 0.9), inset 0 0 12px #ffffff';
    setTimeout(() => {
      if (nucleus) nucleus.style.boxShadow = '';
    }, 1200);
  }

  window.agencyHighlightCore = highlightCoreDomain;
})();
