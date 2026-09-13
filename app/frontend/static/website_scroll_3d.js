/* ==========================================================================
   AGENCY OS — 3D CINEMATIC SCROLL EXPERIENCE SCRIPT
   GSAP 3 + ScrollTrigger 3D Choreography, Interactive Controls & Modals
   ========================================================================== */

(function() {
  'use strict';

  // Check prefers-reduced-motion
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Wait for DOM to be ready
  document.addEventListener('DOMContentLoaded', () => {
    initHeaderScroll();
    initMobileNav();
    initAuditModal();
    initSmoothAnchors();

    if (typeof gsap !== 'undefined' && typeof ScrollTrigger !== 'undefined' && !prefersReducedMotion) {
      gsap.registerPlugin(ScrollTrigger);
      initCinematicScroll3D();
    } else {
      initFallbackAnimations();
    }
  });

  /* --------------------------------------------------------------------------
     1. Header Scroll Blur & Sticky Transition
     -------------------------------------------------------------------------- */
  function initHeaderScroll() {
    const header = document.querySelector('.site-header');
    if (!header) return;

    window.addEventListener('scroll', () => {
      if (window.scrollY > 40) {
        header.classList.add('scrolled');
      } else {
        header.classList.remove('scrolled');
      }
    }, { passive: true });
  }

  /* --------------------------------------------------------------------------
     2. Mobile Navigation Drawer
     -------------------------------------------------------------------------- */
  function initMobileNav() {
    const toggleBtn = document.getElementById('mobileToggle');
    const drawer = document.getElementById('mobileDrawer');
    if (!toggleBtn || !drawer) return;

    toggleBtn.addEventListener('click', () => {
      const isOpen = drawer.classList.toggle('open');
      toggleBtn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      drawer.setAttribute('aria-hidden', isOpen ? 'false' : 'true');
      document.body.style.overflow = isOpen ? 'hidden' : '';
    });

    // Close on navigation link click
    const drawerLinks = drawer.querySelectorAll('.nav-link, .btn-primary, .btn-portal-link');
    drawerLinks.forEach(link => {
      link.addEventListener('click', () => {
        drawer.classList.remove('open');
        toggleBtn.setAttribute('aria-expanded', 'false');
        drawer.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = '';
      });
    });
  }

  /* --------------------------------------------------------------------------
     3. Free Audit Modal Dialog
     -------------------------------------------------------------------------- */
  function initAuditModal() {
    const modalBackdrop = document.getElementById('auditModal');
    const closeBtn = document.getElementById('closeAuditModal');
    const triggerBtns = document.querySelectorAll('[data-action="open-audit-modal"]');
    const form = document.getElementById('auditForm');
    const alertBox = document.getElementById('auditModalAlert');
    const submitBtn = document.getElementById('btnSubmitAudit');

    if (!modalBackdrop) return;

    function openModal() {
      modalBackdrop.classList.add('open');
      modalBackdrop.setAttribute('aria-hidden', 'false');
      document.body.style.overflow = 'hidden';
      const firstInput = modalBackdrop.querySelector('input');
      if (firstInput) firstInput.focus();
    }

    function closeModal() {
      modalBackdrop.classList.remove('open');
      modalBackdrop.setAttribute('aria-hidden', 'true');
      document.body.style.overflow = '';
      if (alertBox) {
        alertBox.className = 'modal-alert';
        alertBox.textContent = '';
        alertBox.style.display = 'none';
      }
    }

    triggerBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        openModal();
      });
    });

    if (closeBtn) {
      closeBtn.addEventListener('click', closeModal);
    }

    modalBackdrop.addEventListener('click', (e) => {
      if (e.target === modalBackdrop) {
        closeModal();
      }
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && modalBackdrop.classList.contains('open')) {
        closeModal();
      }
    });

    // Handle Form Submit
    if (form) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!alertBox || !submitBtn) return;

        const name = (document.getElementById('auditName')?.value || '').trim();
        const email = (document.getElementById('auditEmail')?.value || '').trim();
        const company = (document.getElementById('auditCompany')?.value || '').trim();
        const goal = (document.getElementById('auditGoal')?.value || '').trim();

        if (!name || !email) {
          alertBox.className = 'modal-alert error';
          alertBox.textContent = 'Please provide your full name and work email address.';
          alertBox.style.display = 'block';
          return;
        }

        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
          alertBox.className = 'modal-alert error';
          alertBox.textContent = 'Please enter a valid work email address.';
          alertBox.style.display = 'block';
          return;
        }

        submitBtn.disabled = true;
        const originalText = submitBtn.textContent;
        submitBtn.textContent = 'Analyzing Systems...';

        try {
          const payload = {
            name: name,
            email: email,
            company: company || 'Not specified',
            service_interest: goal || 'Autonomous Systems Audit',
            message: `Free Systems Audit Request: Target company domain: ${company || 'N/A'}. Primary automation objective: ${goal || 'End-to-end agency automation'}.`
          };

          const res = await fetch('/api/contact', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Accept': 'application/json'
            },
            body: JSON.stringify(payload)
          });

          const data = await res.json().catch(() => ({}));

          if (res.ok && data.success) {
            alertBox.className = 'modal-alert success';
            alertBox.textContent = data.message || 'Audit request registered successfully. Our engineering team will review your systems and contact you shortly.';
            alertBox.style.display = 'block';
            form.reset();
            setTimeout(() => {
              closeModal();
            }, 3000);
          } else {
            alertBox.className = 'modal-alert error';
            alertBox.textContent = data.detail || 'Unable to submit request at this moment. Please email us directly or try again.';
            alertBox.style.display = 'block';
          }
        } catch (err) {
          alertBox.className = 'modal-alert error';
          alertBox.textContent = 'Network connectivity error. Please check your connection and try again.';
          alertBox.style.display = 'block';
        } finally {
          submitBtn.disabled = false;
          submitBtn.textContent = originalText;
        }
      });
    }
  }

  /* --------------------------------------------------------------------------
     4. Smooth Scroll for Anchor Links
     -------------------------------------------------------------------------- */
  function initSmoothAnchors() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
      anchor.addEventListener('click', function(e) {
        const targetId = this.getAttribute('href');
        if (targetId === '#' || targetId === '') return;
        const targetElem = document.querySelector(targetId);
        if (targetElem) {
          e.preventDefault();
          targetElem.scrollIntoView({
            behavior: 'smooth',
            block: 'start'
          });
        }
      });
    });
  }

  /* --------------------------------------------------------------------------
     5. Cinematic GSAP 3 + ScrollTrigger 3D Choreography
     -------------------------------------------------------------------------- */
  function initCinematicScroll3D() {
    // 5.1 Hero Core 3D Scroll Zoom & Rotation
    const heroVisual = document.querySelector('.core-system-visual');
    const heroContent = document.querySelector('.scene-hero .scene-content');

    if (heroVisual) {
      gsap.to(heroVisual, {
        scrollTrigger: {
          trigger: '.scene-hero',
          start: 'top top',
          end: 'bottom top',
          scrub: 1.2
        },
        scale: 1.18,
        rotateX: 18,
        rotateY: -15,
        z: 80,
        opacity: 0.25,
        ease: 'power2.out'
      });
    }

    if (heroContent) {
      gsap.to(heroContent, {
        scrollTrigger: {
          trigger: '.scene-hero',
          start: 'top top',
          end: '80% top',
          scrub: 1
        },
        y: -40,
        opacity: 0.3,
        ease: 'power1.out'
      });
    }

    // 5.2 Scene 2: Find — Signal Convergence in Z-Space
    const signalCards = gsap.utils.toArray('.signal-card');
    if (signalCards.length > 0) {
      gsap.from(signalCards, {
        scrollTrigger: {
          trigger: '#scene-find',
          start: 'top 75%',
          end: 'top 30%',
          scrub: 1
        },
        z: (i) => -180 + i * 60,
        rotateY: (i) => (i % 2 === 0 ? -25 : 25),
        rotateX: (i) => (i % 2 === 0 ? 15 : -15),
        opacity: 0.2,
        stagger: 0.15,
        ease: 'power2.out'
      });
    }

    // 5.3 Scene 3: Audit — Device Perspective Sweep
    const auditDevice = document.querySelector('.audit-device-tilt');
    if (auditDevice) {
      gsap.fromTo(auditDevice, 
        {
          rotateX: 25,
          rotateY: -20,
          scale: 0.88,
          opacity: 0.4
        },
        {
          scrollTrigger: {
            trigger: '#scene-audit',
            start: 'top 75%',
            end: 'top 25%',
            scrub: 1.2
          },
          rotateX: 8,
          rotateY: -6,
          scale: 1,
          opacity: 1,
          ease: 'power2.out'
        }
      );
    }

    // 5.4 Scene 4: Persuade — Contextual Chat Bubbles
    const chatBubbles = gsap.utils.toArray('.chat-bubble');
    if (chatBubbles.length > 0) {
      gsap.from(chatBubbles, {
        scrollTrigger: {
          trigger: '#scene-persuade',
          start: 'top 70%',
          toggleActions: 'play none none reverse'
        },
        y: 30,
        z: -60,
        opacity: 0,
        stagger: 0.25,
        duration: 0.8,
        ease: 'back.out(1.4)'
      });
    }

    // 5.5 Scene 5: Sell — Proposal Projection
    const proposalCard = document.querySelector('.proposal-projection-card');
    if (proposalCard) {
      gsap.fromTo(proposalCard,
        {
          rotateX: 18,
          rotateY: 15,
          z: -100,
          opacity: 0.4
        },
        {
          scrollTrigger: {
            trigger: '#scene-sell',
            start: 'top 75%',
            end: 'top 25%',
            scrub: 1
          },
          rotateX: 4,
          rotateY: -4,
          z: 20,
          opacity: 1,
          ease: 'power2.out'
        }
      );
    }

    // 5.6 Scene 6: Build & Deliver — Conveyor Pipeline Steps
    const pipelineSteps = gsap.utils.toArray('.pipeline-step');
    if (pipelineSteps.length > 0) {
      gsap.from(pipelineSteps, {
        scrollTrigger: {
          trigger: '#scene-build',
          start: 'top 70%',
          toggleActions: 'play none none reverse'
        },
        x: 40,
        opacity: 0,
        stagger: 0.15,
        duration: 0.6,
        ease: 'power2.out'
      });
    }

    // 5.7 Scene 7: Maintain — Reliability Mesh Pulse
    const healthMesh = document.querySelector('.health-mesh-display');
    if (healthMesh) {
      gsap.from(healthMesh, {
        scrollTrigger: {
          trigger: '#scene-maintain',
          start: 'top 75%',
          end: 'top 30%',
          scrub: 1
        },
        rotateX: -15,
        rotateY: 12,
        scale: 0.92,
        opacity: 0.5,
        ease: 'power2.out'
      });
    }

    // 5.8 Scene 8: CTA Box 3D Layer Elevation
    const ctaBox = document.querySelector('.cta-box-3d');
    if (ctaBox) {
      gsap.from(ctaBox, {
        scrollTrigger: {
          trigger: '#scene-cta',
          start: 'top 80%',
          end: 'top 40%',
          scrub: 1
        },
        scale: 0.9,
        y: 40,
        opacity: 0.6,
        ease: 'power2.out'
      });
    }
  }

  /* --------------------------------------------------------------------------
     6. Fallback Animations (if GSAP unavailable or prefers-reduced-motion)
     -------------------------------------------------------------------------- */
  function initFallbackAnimations() {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.style.opacity = '1';
          entry.target.style.transform = 'none';
        }
      });
    }, { threshold: 0.15 });

    document.querySelectorAll('.scene-content, .stage-3d, .cta-box-3d').forEach(el => {
      observer.observe(el);
    });
  }

})();
