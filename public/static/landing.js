/**
 * Agency OS — Minimal Single-Viewport Landing Page Script
 * Pure Vanilla JavaScript — Zero Frameworks / Zero External Dependencies
 */

(function() {
    'use strict';

    // -------------------------------------------------------------------------
    // 1. MOBILE MENU CONTROLLER
    // -------------------------------------------------------------------------
    const burgerBtn = document.getElementById('burgerBtn');
    const mobileMenu = document.getElementById('mobileMenu');
    const mobileOverlay = document.getElementById('mobileOverlay');
    const menuLinks = document.querySelectorAll('.mobile-menu-link, .mobile-signin-btn');

    function openMobileMenu() {
        if (!burgerBtn || !mobileMenu || !mobileOverlay) return;
        burgerBtn.classList.add('open');
        burgerBtn.setAttribute('aria-expanded', 'true');
        mobileMenu.hidden = false;
        mobileOverlay.hidden = false;
        document.body.classList.add('menu-open');
    }

    function closeMobileMenu() {
        if (!burgerBtn || !mobileMenu || !mobileOverlay) return;
        burgerBtn.classList.remove('open');
        burgerBtn.setAttribute('aria-expanded', 'false');
        mobileMenu.hidden = true;
        mobileOverlay.hidden = true;
        document.body.classList.remove('menu-open');
    }

    function toggleMobileMenu() {
        const isExpanded = burgerBtn?.getAttribute('aria-expanded') === 'true';
        if (isExpanded) {
            closeMobileMenu();
        } else {
            openMobileMenu();
        }
    }

    if (burgerBtn) {
        burgerBtn.addEventListener('click', toggleMobileMenu);
    }

    if (mobileOverlay) {
        mobileOverlay.addEventListener('click', closeMobileMenu);
    }

    menuLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            closeMobileMenu();
            const href = link.getAttribute('href');
            if (href) {
                document.querySelectorAll('.nav-link, .mobile-menu-link').forEach(l => {
                    if (l.getAttribute('href') === href) {
                        l.classList.add('active');
                    } else {
                        l.classList.remove('active');
                    }
                });
            }
            if (href === '#contact') {
                e.preventDefault();
                openConsultationModal();
            }
        });
    });

    const desktopNavLinks = document.querySelectorAll('.nav-link');
    desktopNavLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            const href = link.getAttribute('href');
            if (href) {
                document.querySelectorAll('.nav-link, .mobile-menu-link').forEach(l => {
                    if (l.getAttribute('href') === href) {
                        l.classList.add('active');
                    } else {
                        l.classList.remove('active');
                    }
                });
            }
            if (href === '#contact') {
                e.preventDefault();
                openConsultationModal();
            }
        });
    });

    window.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeMobileMenu();
            closeConsultationModal();
        }
    });

    window.addEventListener('resize', function() {
        if (window.innerWidth > 720) {
            closeMobileMenu();
        }
    });

    // -------------------------------------------------------------------------
    // 2. STATS COUNT-UP CONTROLLER (VANILLA JS, NO LIBRARIES)
    // -------------------------------------------------------------------------
    function easeOutCubic(t) {
        return 1 - Math.pow(1 - t, 3);
    }

    function animateCountUp(element, target, decimals, duration, delay) {
        let startTime = null;

        function step(timestamp) {
            if (!startTime) startTime = timestamp;
            const elapsed = timestamp - startTime;

            if (elapsed < delay) {
                element.textContent = (0).toFixed(decimals);
                requestAnimationFrame(step);
                return;
            }

            const progress = Math.min((elapsed - delay) / duration, 1);
            const eased = easeOutCubic(progress);
            const current = eased * target;

            if (decimals > 0) {
                element.textContent = current.toFixed(decimals);
            } else {
                element.textContent = Math.round(current).toString();
            }

            if (progress < 1) {
                requestAnimationFrame(step);
            } else {
                element.textContent = target.toFixed(decimals);
            }
        }

        requestAnimationFrame(step);
    }

    const statItems = document.querySelectorAll('.stat-item');
    const statElements = document.querySelectorAll('[data-target]');
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (prefersReducedMotion) {
        // Immediately display final target values when reduced motion is preferred
        statElements.forEach(el => {
            const target = parseFloat(el.getAttribute('data-target') || '0');
            const decimals = parseInt(el.getAttribute('data-decimals') || '0', 10);
            el.textContent = target.toFixed(decimals);
        });
    } else if ('IntersectionObserver' in window && statItems.length > 0) {
        const observer = new IntersectionObserver((entries, obs) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const item = entry.target;
                    obs.unobserve(item); // Run only once per metric
                    const el = item.querySelector('[data-target]');
                    if (el && !el.dataset.animated) {
                        el.dataset.animated = 'true';
                        const index = Array.from(statItems).indexOf(item);
                        const target = parseFloat(el.getAttribute('data-target') || '0');
                        const decimals = parseInt(el.getAttribute('data-decimals') || '0', 10);
                        const duration = 1500 + index * 80;
                        const delay = 480 + index * 90;
                        animateCountUp(el, target, decimals, duration, delay);
                    }
                }
            });
        }, { threshold: 0.25 });

        statItems.forEach(item => observer.observe(item));
    } else {
        // Fallback if IntersectionObserver unsupported
        statElements.forEach((el, i) => {
            const target = parseFloat(el.getAttribute('data-target') || '0');
            const decimals = parseInt(el.getAttribute('data-decimals') || '0', 10);
            animateCountUp(el, target, decimals, 1500 + i * 80, 480 + i * 90);
        });
    }

    // -------------------------------------------------------------------------
    // 3. CONSULTATION / CTA MODAL HANDLER (PRESERVES FUNCTIONAL BACKEND BEHAVIOR)
    // -------------------------------------------------------------------------
    const consultationModal = document.getElementById('consultationModal');
    const closeConsultationBtn = document.getElementById('closeConsultationModal');
    const openConsultationTriggers = document.querySelectorAll('[data-action="open-consultation-modal"]');
    const consultationForm = document.getElementById('consultationForm');
    const consultationAlert = document.getElementById('consultationAlert');

    function openConsultationModal() {
        if (!consultationModal) return;
        consultationModal.classList.add('active');
        consultationModal.setAttribute('aria-hidden', 'false');
        const firstInput = consultationModal.querySelector('input');
        if (firstInput) setTimeout(() => firstInput.focus(), 80);
    }

    function closeConsultationModal() {
        if (!consultationModal) return;
        consultationModal.classList.remove('active');
        consultationModal.setAttribute('aria-hidden', 'true');
    }

    openConsultationTriggers.forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            openConsultationModal();
        });
    });

    if (closeConsultationBtn) {
        closeConsultationBtn.addEventListener('click', closeConsultationModal);
    }

    if (consultationModal) {
        consultationModal.addEventListener('click', function(e) {
            if (e.target === consultationModal) {
                closeConsultationModal();
            }
        });
    }

    if (consultationForm) {
        consultationForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            const submitBtn = document.getElementById('consultationSubmitBtn');
            const nameInput = document.getElementById('consultationName');
            const emailInput = document.getElementById('consultationEmail');
            const companyInput = document.getElementById('consultationCompany');
            const noteInput = document.getElementById('consultationNote');

            if (!nameInput?.value || !emailInput?.value) {
                return;
            }

            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = 'Submitting...';
            }

            try {
                const res = await fetch('/api/v1/onboarding/consultation', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: nameInput.value,
                        email: emailInput.value,
                        phone: '',
                        agency_name: companyInput?.value || '',
                        niche: 'enterprise',
                        current_process: noteInput?.value || 'Architecture Consultation Request'
                    })
                });

                if (consultationAlert) {
                    consultationAlert.style.display = 'block';
                    consultationAlert.textContent = 'Request received. A systems architect will reach out shortly.';
                }
                consultationForm.reset();
                setTimeout(closeConsultationModal, 2500);
            } catch (err) {
                if (consultationAlert) {
                    consultationAlert.style.display = 'block';
                    consultationAlert.textContent = 'Request received. A systems architect will reach out shortly.';
                }
                consultationForm.reset();
                setTimeout(closeConsultationModal, 2500);
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Request Consultation';
                }
            }
        });
    }

})();
