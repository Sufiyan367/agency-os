/* ==========================================================================
   AGENCY OS — 3D CINEMATIC SCROLL EXPERIENCE SCRIPT
   GPU Kinetic Canvas, Interactive Simulator, Modals & Narrative Telemetry
   ========================================================================== */

(function() {
  'use strict';

  // Check prefers-reduced-motion
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Simulator Scenarios Data Model
  const SIM_SCENARIOS = {
    missed_call: {
      step1: {
        tag: 'TRIGGER // 20:42 EST',
        title: 'Missed After-Hours Call',
        body: 'Homeowner calls with AC breakdown outside office hours. Call rings out and disconnects after 4 rings.',
        status: 'Trigger Received',
        statusType: 'active'
      },
      step2: {
        tag: 'INGEST // 380ms',
        title: 'Caller Intelligence',
        body: 'Ingests caller ID, resolves local service territory, and checks CRM for existing customer history.',
        status: 'Context Grounded',
        statusType: 'active'
      },
      step3: {
        tag: 'REASONING // 620ms',
        title: 'Priority 1 Routing',
        body: 'Classified as urgent emergency repair. Rules engine triggers immediate autonomous follow-up protocol.',
        status: 'Decision Locked',
        statusType: 'active'
      },
      step4: {
        tag: 'ACTION // 1.2s',
        title: 'Conversational SMS',
        body: 'Dispatches instant personalized text with priority slot reservation link. Holds morning 08:30 AM dispatch.',
        status: 'Action Dispatched',
        statusType: 'active'
      },
      step5: {
        tag: 'OUTCOME // Confirmed',
        title: 'Opportunity Saved',
        body: 'Customer books technician slot in 45s before calling competitor. $850 emergency job secured automatically.',
        status: 'Contract Secured',
        statusType: 'complete'
      }
    },
    web_enquiry: {
      step1: {
        tag: 'TRIGGER // 14:15 EST',
        title: 'Commercial Inbound',
        body: 'Clinic group submits website inquiry: "Need multi-clinic patient booking and automated reminder sync."',
        status: 'Trigger Received',
        statusType: 'active'
      },
      step2: {
        tag: 'INGEST // 240ms',
        title: 'Domain & Fit Audit',
        body: 'Parses business registry, verifies 4 operating practice locations, and checks software compatibility.',
        status: 'Profile Enriched',
        statusType: 'active'
      },
      step3: {
        tag: 'REASONING // 510ms',
        title: 'Enterprise Architecture',
        body: 'Identifies high-value enterprise opportunity. Assembles customized multi-location architecture proposal.',
        status: 'Scoping Complete',
        statusType: 'active'
      },
      step4: {
        tag: 'ACTION // 850ms',
        title: 'Interactive Dossier',
        body: 'Emails managing partner an interactive proposal preview with calendar link to speak directly with an architect.',
        status: 'Proposal Sent',
        statusType: 'active'
      },
      step5: {
        tag: 'OUTCOME // Confirmed',
        title: 'Strategy Call Booked',
        body: 'Managing partner reserves consultation call with pre-compiled technical dossier. Zero manual sales legwork.',
        status: 'Pipeline Added',
        statusType: 'complete'
      }
    },
    lead_form: {
      step1: {
        tag: 'TRIGGER // 11:05 EST',
        title: 'Fleet Service Scope',
        body: 'Logistics manager submits 12-vehicle service manifest requesting commercial preventative maintenance quote.',
        status: 'Trigger Received',
        statusType: 'active'
      },
      step2: {
        tag: 'INGEST // 410ms',
        title: 'Fleet VIN Analysis',
        body: 'Extracts VIN numbers, mileage thresholds, and OEM maintenance schedules from attached fleet schedule.',
        status: 'Fleet Grounded',
        statusType: 'active'
      },
      step3: {
        tag: 'REASONING // 780ms',
        title: 'Automated Estimating',
        body: 'Calculates labor hours, parts procurement pricing, and generates tiered multi-tier SLA contract options.',
        status: 'Quote Generated',
        statusType: 'active'
      },
      step4: {
        tag: 'ACTION // 1.4s',
        title: 'Web-Native Proposal',
        body: 'Deploys interactive web proposal with cryptographic e-sign and upfront retainer payment gateway.',
        status: 'Delivered Instantly',
        statusType: 'active'
      },
      step5: {
        tag: 'OUTCOME // Confirmed',
        title: 'Retainer Cleared',
        body: 'Logistics director approves proposal and pays $3,600 initial deposit online within 90 minutes.',
        status: 'Revenue Collected',
        statusType: 'complete'
      }
    },
    support_request: {
      step1: {
        tag: 'TRIGGER // 03:12 EST',
        title: 'Carrier Latency Spike',
        body: 'Automated telemetry watcher detects upstream carrier SIP latency spiking to 420ms on primary trunk.',
        status: 'Anomaly Detected',
        statusType: 'active'
      },
      step2: {
        tag: 'INGEST // 50ms',
        title: 'Health Diagnostics',
        body: 'Health check probe confirms packet loss on primary route. Secondary redundant carrier routes healthy.',
        status: 'Diagnostics Clear',
        statusType: 'active'
      },
      step3: {
        tag: 'REASONING // 90ms',
        title: 'Failover Trigger',
        body: 'Circuit breaker protocol engages. Initiates zero-downtime hot-swap to secondary low-latency SIP carrier.',
        status: 'Failover Armed',
        statusType: 'active'
      },
      step4: {
        tag: 'ACTION // 120ms',
        title: 'Route Redirection',
        body: 'Swaps DNS routes and telephony gateways; dispatches incident summary to CEO notification feed.',
        status: 'Traffic Rerouted',
        statusType: 'active'
      },
      step5: {
        tag: 'OUTCOME // Confirmed',
        title: 'Zero Dropped Calls',
        body: '99.98% platform uptime preserved seamlessly. Zero missed customer calls during carrier outage.',
        status: 'Self-Healed',
        statusType: 'complete'
      }
    }
  };

  // Wait for DOM to be ready
  document.addEventListener('DOMContentLoaded', () => {
    initHeaderScroll();
    initMobileNav();
    initConsultationModals();
    initContactForm();
    initSimulator();
    initSmoothAnchors();
    initNarrativeObserver();

    // 3D Kinetic Canvas Backdrop
    if (!prefersReducedMotion) {
      initKineticCanvas3D();
    }
  });

  /* --------------------------------------------------------------------------
     1. Header Scroll Blur & Sticky Transition
     -------------------------------------------------------------------------- */
  function initHeaderScroll() {
    const header = document.querySelector('.site-header');
    if (!header) return;

    function handleScroll() {
      if (window.scrollY > 40) {
        header.classList.add('scrolled');
      } else {
        header.classList.remove('scrolled');
      }
    }

    window.addEventListener('scroll', handleScroll, { passive: true });
    handleScroll();
  }

  /* --------------------------------------------------------------------------
     2. Mobile Navigation Drawer (Zero Portal Exposure)
     -------------------------------------------------------------------------- */
  function initMobileNav() {
    const toggleBtn = document.getElementById('mobileToggle');
    const drawer = document.getElementById('mobileDrawer');
    const backdrop = document.getElementById('mobileDrawerBackdrop');
    if (!toggleBtn || !drawer) return;

    function openDrawer() {
      drawer.classList.add('open');
      drawer.setAttribute('aria-hidden', 'false');
      toggleBtn.setAttribute('aria-expanded', 'true');
      if (backdrop) backdrop.classList.add('open');
      document.body.style.overflow = 'hidden';
    }

    function closeDrawer() {
      drawer.classList.remove('open');
      drawer.setAttribute('aria-hidden', 'true');
      toggleBtn.setAttribute('aria-expanded', 'false');
      if (backdrop) backdrop.classList.remove('open');
      document.body.style.overflow = '';
    }

    toggleBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (drawer.classList.contains('open')) {
        closeDrawer();
      } else {
        openDrawer();
      }
    });

    if (backdrop) {
      backdrop.addEventListener('click', closeDrawer);
    }

    // Close on any nav link click inside drawer
    const links = drawer.querySelectorAll('a, button');
    links.forEach(link => {
      link.addEventListener('click', closeDrawer);
    });

    // Close on ESC
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && drawer.classList.contains('open')) {
        closeDrawer();
      }
    });
  }

  /* --------------------------------------------------------------------------
     3. Consultation Modal Dialog & Submission
     -------------------------------------------------------------------------- */
  function initConsultationModals() {
    const modal = document.getElementById('consultationModal');
    const closeBtn = document.getElementById('closeConsultationModal');
    const triggerBtns = document.querySelectorAll('[data-action="open-consultation-modal"]');
    const form = document.getElementById('modalForm');
    const alertBox = document.getElementById('modalAlert');
    const submitBtn = document.getElementById('btnSubmitModal');

    if (!modal) return;

    function openModal() {
      modal.classList.add('open');
      modal.setAttribute('aria-hidden', 'false');
      document.body.style.overflow = 'hidden';
      const firstInput = modal.querySelector('input');
      if (firstInput) firstInput.focus();
    }

    function closeModal() {
      modal.classList.remove('open');
      modal.setAttribute('aria-hidden', 'true');
      document.body.style.overflow = '';
      if (alertBox) {
        alertBox.textContent = '';
        alertBox.style.display = 'none';
      }
    }

    triggerBtns.forEach(btn => btn.addEventListener('click', openModal));
    if (closeBtn) closeBtn.addEventListener('click', closeModal);

    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeModal();
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && modal.classList.contains('open')) {
        closeModal();
      }
    });

    if (form) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const name = (document.getElementById('modalName') || {}).value || '';
        const email = (document.getElementById('modalEmail') || {}).value || '';
        const company = (document.getElementById('modalCompany') || {}).value || '';
        const service = (document.getElementById('modalService') || {}).value || '';
        const message = (document.getElementById('modalMessage') || {}).value || '';

        if (!name || !email || !company) {
          showAlert(alertBox, 'Please complete all required fields.', 'error');
          return;
        }

        if (submitBtn) {
          submitBtn.disabled = true;
          submitBtn.textContent = 'Submitting Request...';
        }

        try {
          const resp = await fetch('/api/contact', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, email, company, service, message })
          });

          if (resp.ok) {
            showAlert(alertBox, 'Request received. An automation architect will review your bottlenecks and reach out within 2 hours.', 'success');
            form.reset();
            setTimeout(() => {
              closeModal();
            }, 3500);
          } else {
            showAlert(alertBox, 'Submission error. Please try again or reach out directly at contact@automatedagencyos.tech', 'error');
          }
        } catch (err) {
          showAlert(alertBox, 'Network issue. Please try again in a few moments.', 'error');
        } finally {
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Confirm Consultation Request';
          }
        }
      });
    }
  }

  /* --------------------------------------------------------------------------
     4. Main Contact Consultation Form Submission
     -------------------------------------------------------------------------- */
  function initContactForm() {
    const form = document.getElementById('contactForm');
    const alertBox = document.getElementById('contactAlert');
    const submitBtn = document.getElementById('btnSubmitContact');
    const submitText = document.getElementById('btnSubmitText');

    if (!form) return;

    form.addEventListener('submit', async (e) => {
      e.preventDefault();

      const name = (document.getElementById('contactName') || {}).value || '';
      const email = (document.getElementById('contactEmail') || {}).value || '';
      const company = (document.getElementById('contactCompany') || {}).value || '';
      const service = (document.getElementById('contactService') || {}).value || '';
      const message = (document.getElementById('contactMessage') || {}).value || '';

      if (!name || !email || !company || !message) {
        showAlert(alertBox, 'Please fill in all required fields.', 'error');
        return;
      }

      if (submitBtn) {
        submitBtn.disabled = true;
        if (submitText) submitText.textContent = 'Transmitting Request...';
      }

      try {
        const resp = await fetch('/api/contact', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, email, company, service, message })
        });

        if (resp.ok) {
          showAlert(alertBox, 'Thank you. Your consultation request has been logged. An automation engineer will prepare a tailored audit and reach out shortly.', 'success');
          form.reset();
        } else {
          showAlert(alertBox, 'Unable to submit right now. Please email us at contact@automatedagencyos.tech.', 'error');
        }
      } catch (err) {
        showAlert(alertBox, 'Network failure. Please verify connection and try again.', 'error');
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          if (submitText) submitText.textContent = 'Request Strategy Call';
        }
      }
    });
  }

  function showAlert(alertEl, msg, type) {
    if (!alertEl) return;
    alertEl.textContent = msg;
    alertEl.className = 'contact-alert ' + type;
    alertEl.style.display = 'block';
  }

  /* --------------------------------------------------------------------------
     5. Real Interactive Simulator ("See How The System Works")
     -------------------------------------------------------------------------- */
  function initSimulator() {
    const tabs = document.querySelectorAll('.sim-tab');
    if (!tabs.length) return;

    const colInput = document.getElementById('sim-content-input');
    const colReasoning = document.getElementById('sim-content-reasoning');
    const colDecision = document.getElementById('sim-content-decision');
    const colAction = document.getElementById('sim-content-action');
    const colOutcome = document.getElementById('sim-content-outcome');

    function renderStage(scenarioKey) {
      const data = SIM_SCENARIOS[scenarioKey] || SIM_SCENARIOS.missed_call;

      renderColumn(colInput, data.step1);
      renderColumn(colReasoning, data.step2);
      renderColumn(colDecision, data.step3);
      renderColumn(colAction, data.step4);
      renderColumn(colOutcome, data.step5);

      // Pulse columns sequentially
      const cols = document.querySelectorAll('.sim-stage-col');
      cols.forEach((col, idx) => {
        col.classList.remove('pulsing');
        setTimeout(() => {
          col.classList.add('pulsing');
          setTimeout(() => col.classList.remove('pulsing'), 600);
        }, idx * 120);
      });
    }

    function renderColumn(targetEl, stepData) {
      if (!targetEl || !stepData) return;
      targetEl.innerHTML = `
        <span class="sim-node-tag">${escapeHtml(stepData.tag)}</span>
        <div class="sim-highlight-text">${escapeHtml(stepData.title)}</div>
        <p>${escapeHtml(stepData.body)}</p>
        <span class="sim-status-badge ${stepData.statusType === 'complete' ? 'complete' : 'active'}">
          ● ${escapeHtml(stepData.status)}
        </span>
      `;
    }

    function escapeHtml(str) {
      return String(str || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        tabs.forEach(t => {
          t.classList.remove('active');
          t.setAttribute('aria-selected', 'false');
        });
        tab.classList.add('active');
        tab.setAttribute('aria-selected', 'true');
        const scenario = tab.getAttribute('data-sim');
        renderStage(scenario);
      });
    });

    // Initial render
    renderStage('missed_call');
  }

  /* --------------------------------------------------------------------------
     6. Smooth Anchors with Fixed Header Offset
     -------------------------------------------------------------------------- */
  function initSmoothAnchors() {
    const anchorLinks = document.querySelectorAll('a[href^="#"]');
    const headerHeight = 80;

    anchorLinks.forEach(anchor => {
      anchor.addEventListener('click', function(e) {
        const targetId = this.getAttribute('href');
        if (!targetId || targetId === '#') return;

        const targetEl = document.querySelector(targetId);
        if (targetEl) {
          e.preventDefault();
          const targetPosition = targetEl.getBoundingClientRect().top + window.scrollY - headerHeight;
          window.scrollTo({
            top: targetPosition,
            behavior: 'smooth'
          });
        }
      });
    });
  }

  /* --------------------------------------------------------------------------
     7. Narrative Scroll Observer & Stage Satellite Coordination
     -------------------------------------------------------------------------- */
  function initNarrativeObserver() {
    const steps = document.querySelectorAll('.scroll-step');
    const satellites = document.querySelectorAll('.orbit-satellite');
    const heroWidget = document.getElementById('hero-core-widget');

    if (!steps.length) return;

    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            steps.forEach(s => s.classList.remove('active-step'));
            entry.target.classList.add('active-step');
            const stepNum = entry.target.getAttribute('data-step');
            
            // Coordinate with hero satellite highlight if in view
            satellites.forEach(sat => sat.style.borderColor = '');
            const targetSat = document.querySelector(`.sat-${stepNum}`);
            if (targetSat) {
              targetSat.style.borderColor = '#00d4ef';
            }
          }
        });
      }, { threshold: 0.4 });

      steps.forEach(step => observer.observe(step));
    }

    // Hero Widget Interactive Parallax Tilt
    if (heroWidget && !prefersReducedMotion) {
      window.addEventListener('mousemove', (e) => {
        const { clientX, clientY } = e;
        const cx = window.innerWidth / 2;
        const cy = window.innerHeight / 2;
        const rotY = ((clientX - cx) / cx) * 12;
        const rotX = -((clientY - cy) / cy) * 12;
        heroWidget.style.transform = `perspective(800px) rotateX(${rotX.toFixed(2)}deg) rotateY(${rotY.toFixed(2)}deg)`;
      }, { passive: true });
    }
  }

  /* --------------------------------------------------------------------------
     8. High-Performance 3D Kinetic Automation Engine (Canvas)
     -------------------------------------------------------------------------- */
  function initKineticCanvas3D() {
    const canvas = document.getElementById('bg-canvas-3d');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let width = 0;
    let height = 0;
    let dpr = 1;
    let animFrameId = null;

    // Orbital parameters
    const rings = [
      { radius: 180, tiltX: 1.1, tiltY: 0.3, speed: 0.003, rot: 0, color: 'rgba(0, 212, 239, 0.22)' },
      { radius: 300, tiltX: 0.9, tiltY: -0.4, speed: -0.002, rot: Math.PI / 4, color: 'rgba(99, 102, 241, 0.2)' },
      { radius: 440, tiltX: 0.7, tiltY: 0.5, speed: 0.0015, rot: Math.PI / 2, color: 'rgba(0, 212, 239, 0.15)' }
    ];

    // Starfield / Depth Particles
    const PARTICLE_COUNT = 85;
    const particles = [];

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.scale(dpr, dpr);
    }

    function initParticles() {
      particles.length = 0;
      for (let i = 0; i < PARTICLE_COUNT; i++) {
        particles.push({
          x: (Math.random() - 0.5) * 1600,
          y: (Math.random() - 0.5) * 1200,
          z: Math.random() * 800 + 100,
          radius: Math.random() * 1.5 + 0.8,
          alpha: Math.random() * 0.6 + 0.2,
          speedZ: Math.random() * 0.4 + 0.1
        });
      }
    }

    let scrollYOffset = 0;
    window.addEventListener('scroll', () => {
      scrollYOffset = window.scrollY * 0.0008;
    }, { passive: true });

    let mouseX = 0;
    let mouseY = 0;
    window.addEventListener('mousemove', (e) => {
      mouseX = (e.clientX - width / 2) * 0.0004;
      mouseY = (e.clientY - height / 2) * 0.0004;
    }, { passive: true });

    function render() {
      ctx.clearRect(0, 0, width, height);

      const centerX = width * 0.65; // Positioned behind right-side hero visual on desktop
      const centerY = Math.min(height * 0.45, 420);

      // Draw background 3D particles
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        p.z -= p.speedZ;
        if (p.z <= 20) p.z = 900;

        const fov = 400;
        const scale = fov / (fov + p.z);
        const px = (width / 2) + p.x * scale + mouseX * 200;
        const py = (height / 2) + p.y * scale + mouseY * 200;

        if (px >= 0 && px <= width && py >= 0 && py <= height) {
          ctx.beginPath();
          ctx.arc(px, py, p.radius * scale, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(165, 180, 252, ${p.alpha * scale})`;
          ctx.fill();
        }
      }

      // Draw Concentric Orbital Rings in 3D Perspective
      rings.forEach((ring, rIdx) => {
        ring.rot += ring.speed + scrollYOffset * 0.01;

        ctx.save();
        ctx.beginPath();
        const steps = 64;
        for (let s = 0; s <= steps; s++) {
          const theta = (s / steps) * Math.PI * 2;
          // 3D coordinates on inclined orbital plane
          const rawX = Math.cos(theta + ring.rot) * ring.radius;
          const rawY = Math.sin(theta + ring.rot) * ring.radius * ring.tiltX;
          const rawZ = Math.sin(theta) * ring.radius * ring.tiltY;

          // Projection
          const fov = 600;
          const scale = fov / (fov + rawZ + 150);
          const projX = centerX + rawX * scale + mouseX * 100;
          const projY = centerY + rawY * scale + mouseY * 100;

          if (s === 0) {
            ctx.moveTo(projX, projY);
          } else {
            ctx.lineTo(projX, projY);
          }
        }
        ctx.closePath();
        ctx.strokeStyle = ring.color;
        ctx.lineWidth = 1;
        ctx.stroke();

        // Draw an orbiting data node on each ring
        const nodeAngle = ring.rot * 2 + rIdx;
        const nX = Math.cos(nodeAngle) * ring.radius;
        const nY = Math.sin(nodeAngle) * ring.radius * ring.tiltX;
        const nZ = Math.sin(nodeAngle) * ring.radius * ring.tiltY;
        const nScale = 600 / (600 + nZ + 150);
        const nodePx = centerX + nX * nScale + mouseX * 100;
        const nodePy = centerY + nY * nScale + mouseY * 100;

        // Node Glow
        ctx.beginPath();
        ctx.arc(nodePx, nodePy, 4 * nScale, 0, Math.PI * 2);
        ctx.fillStyle = rIdx % 2 === 0 ? '#00d4ef' : '#818cf8';
        ctx.shadowColor = rIdx % 2 === 0 ? '#00d4ef' : '#818cf8';
        ctx.shadowBlur = 12;
        ctx.fill();
        ctx.shadowBlur = 0;

        ctx.restore();
      });

      animFrameId = requestAnimationFrame(render);
    }

    window.addEventListener('resize', () => {
      resize();
      initParticles();
    });

    resize();
    initParticles();
    render();
  }

})();
