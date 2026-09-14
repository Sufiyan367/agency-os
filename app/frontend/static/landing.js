/**
 * Agency OS — Production Landing Page Controller
 * Pure Vanilla JavaScript — Zero Frameworks / Zero External Dependencies
 */

(function() {
    'use strict';

    // -------------------------------------------------------------------------
    // 1. MOBILE MENU & HEADER SCROLL CONTROLLER
    // -------------------------------------------------------------------------
    const burgerBtn = document.getElementById('burgerBtn');
    const mobileMenu = document.getElementById('mobileMenu');
    const mobileOverlay = document.getElementById('mobileOverlay');
    const siteHeaderContainer = document.getElementById('siteHeaderContainer');
    const menuLinks = document.querySelectorAll('.mobile-menu-link, .mobile-signin-btn, .mobile-cta-btn');

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

    // Close on link click and scroll
    menuLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            closeMobileMenu();
            if (link.classList.contains('mobile-cta-btn')) {
                e.preventDefault();
                openConsultationModal(link);
                return;
            }
            const href = link.getAttribute('href');
            if (href && href.startsWith('#')) {
                e.preventDefault();
                const target = document.querySelector(href);
                if (target) {
                    target.scrollIntoView({ behavior: 'smooth' });
                }
            }
        });
    });

    // Window resize reset
    window.addEventListener('resize', function() {
        if (window.innerWidth > 720) {
            closeMobileMenu();
        }
    });

    // Header blur styling on scroll
    function handleHeaderScroll() {
        if (!siteHeaderContainer) return;
        if (window.scrollY > 40) {
            siteHeaderContainer.classList.add('scrolled');
        } else {
            siteHeaderContainer.classList.remove('scrolled');
        }
    }
    window.addEventListener('scroll', handleHeaderScroll, { passive: true });
    handleHeaderScroll();

    // -------------------------------------------------------------------------
    // 2. SMOOTH NAVIGATION & ACTIVE SECTION HIGHLIGHTING
    // -------------------------------------------------------------------------
    const navLinks = document.querySelectorAll('.nav-link');
    const mobileNavLinks = document.querySelectorAll('.mobile-menu-link');

    function setActiveNav(targetHref) {
        navLinks.forEach(link => {
            if (link.getAttribute('href') === targetHref) {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });
        mobileNavLinks.forEach(link => {
            if (link.getAttribute('href') === targetHref) {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });
    }

    // Smooth scroll on desktop nav clicks
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            const href = link.getAttribute('href');
            if (href && href.startsWith('#')) {
                e.preventDefault();
                const targetEl = document.querySelector(href);
                if (targetEl) {
                    targetEl.scrollIntoView({ behavior: 'smooth' });
                    setActiveNav(href);
                }
            }
        });
    });

    // Track active sections on scroll
    const observedSections = [
        { id: 'home', nav: '#home' },
        { id: 'product', nav: '#product' },
        { id: 'capabilities', nav: '#capabilities' },
        { id: 'channels', nav: '#capabilities' },
        { id: 'how-it-works', nav: '#how-it-works' },
        { id: 'industries', nav: '#industries' },
        { id: 'case-studies', nav: '#case-studies' },
        { id: 'architecture', nav: '#case-studies' },
        { id: 'security', nav: '#case-studies' },
        { id: 'contact', nav: '#contact' }
    ];

    const intersectingSectionIds = new Set();

    function updateActiveNavFromScroll() {
        const scrollY = window.pageYOffset || window.scrollY || 0;
        const viewportHeight = window.innerHeight || 800;
        const totalHeight = document.documentElement.scrollHeight || document.body.scrollHeight || 10000;

        // Force #home when near the top
        if (scrollY < 120) {
            setActiveNav('#home');
            return;
        }

        // Force #contact when scrolled to bottom of document
        if (scrollY + viewportHeight >= totalHeight - 120) {
            setActiveNav('#contact');
            return;
        }

        // Find the first intersecting section in document order
        for (let i = 0; i < observedSections.length; i++) {
            const sec = observedSections[i];
            if (intersectingSectionIds.has(sec.id)) {
                setActiveNav(sec.nav);
                return;
            }
        }
    }

    if ('IntersectionObserver' in window) {
        const sectionObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    intersectingSectionIds.add(entry.target.id);
                } else {
                    intersectingSectionIds.delete(entry.target.id);
                }
            });
            updateActiveNavFromScroll();
        }, {
            rootMargin: '-15% 0px -55% 0px'
        });

        observedSections.forEach(item => {
            const el = document.getElementById(item.id);
            if (el) sectionObserver.observe(el);
        });
    }

    window.addEventListener('scroll', updateActiveNavFromScroll, { passive: true });

    // -------------------------------------------------------------------------
    // 3. SCROLL REVEAL ANIMATIONS
    // -------------------------------------------------------------------------
    const revealElements = document.querySelectorAll('.scroll-reveal');
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (prefersReducedMotion) {
        revealElements.forEach(el => el.classList.add('revealed'));
    } else if ('IntersectionObserver' in window && revealElements.length > 0) {
        const revealObserver = new IntersectionObserver((entries, obs) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('revealed');
                    obs.unobserve(entry.target);
                }
            });
        }, { threshold: 0.12 });

        revealElements.forEach(el => revealObserver.observe(el));
    } else {
        revealElements.forEach(el => el.classList.add('revealed'));
    }

    // -------------------------------------------------------------------------
    // 4. STATS COUNT-UP CONTROLLER
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

    if (prefersReducedMotion) {
        statElements.forEach(el => {
            const target = parseFloat(el.getAttribute('data-target') || '0');
            const decimals = parseInt(el.getAttribute('data-decimals') || '0', 10);
            el.textContent = target.toFixed(decimals);
        });
    } else if ('IntersectionObserver' in window && statItems.length > 0) {
        const statsObserver = new IntersectionObserver((entries, obs) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const item = entry.target;
                    obs.unobserve(item);
                    const el = item.querySelector('[data-target]');
                    if (el && !el.dataset.animated) {
                        el.dataset.animated = 'true';
                        const index = Array.from(statItems).indexOf(item);
                        const target = parseFloat(el.getAttribute('data-target') || '0');
                        const decimals = parseInt(el.getAttribute('data-decimals') || '0', 10);
                        const duration = 1400 + index * 80;
                        const delay = 350 + index * 90;
                        animateCountUp(el, target, decimals, duration, delay);
                    }
                }
            });
        }, { threshold: 0.25 });

        statItems.forEach(item => statsObserver.observe(item));
    } else {
        statElements.forEach((el, i) => {
            const target = parseFloat(el.getAttribute('data-target') || '0');
            const decimals = parseInt(el.getAttribute('data-decimals') || '0', 10);
            animateCountUp(el, target, decimals, 1400 + i * 80, 350 + i * 90);
        });
    }

    // -------------------------------------------------------------------------
    // 5. BACK TO TOP BUTTON
    // -------------------------------------------------------------------------
    const backToTopBtn = document.getElementById('backToTop');

    if (backToTopBtn) {
        function updateBackToTop() {
            const y = window.pageYOffset || window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
            if (y > 500) {
                backToTopBtn.classList.add('visible');
            } else {
                backToTopBtn.classList.remove('visible');
            }
        }
        window.addEventListener('scroll', updateBackToTop, { passive: true });
        document.addEventListener('scroll', updateBackToTop, { passive: true });
        updateBackToTop();

        backToTopBtn.addEventListener('click', function() {
            const homeSection = document.getElementById('home');
            if (homeSection) {
                homeSection.scrollIntoView({ behavior: 'smooth' });
            } else {
                window.scrollTo({ top: 0, behavior: 'smooth' });
            }
        });
    }

    // -------------------------------------------------------------------------
    // 6. CONSULTATION MODAL CONTROLLER
    // -------------------------------------------------------------------------
    const consultationModal = document.getElementById('consultationModal');
    const closeConsultationBtn = document.getElementById('closeConsultationModal');
    const openConsultationTriggers = document.querySelectorAll('[data-action="open-consultation-modal"]');
    const consultationForm = document.getElementById('consultationForm');
    const consultationAlert = document.getElementById('consultationAlert');
    let lastFocusedTrigger = null;

    function openConsultationModal(triggerElement) {
        if (!consultationModal) return;
        lastFocusedTrigger = triggerElement || document.activeElement;
        consultationModal.classList.add('active');
        consultationModal.setAttribute('aria-hidden', 'false');
        if (consultationAlert) {
            consultationAlert.hidden = true;
            consultationAlert.className = 'modal-alert';
            consultationAlert.textContent = '';
        }
        const firstInput = consultationModal.querySelector('input');
        if (firstInput) setTimeout(() => firstInput.focus(), 80);
    }

    function closeConsultationModal() {
        if (!consultationModal) return;
        consultationModal.classList.remove('active');
        consultationModal.setAttribute('aria-hidden', 'true');
        if (lastFocusedTrigger && typeof lastFocusedTrigger.focus === 'function') {
            try { lastFocusedTrigger.focus(); } catch (_) {}
        }
    }

    openConsultationTriggers.forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            openConsultationModal(btn);
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

    window.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeMobileMenu();
            closeConsultationModal();
        }
    });

    // -------------------------------------------------------------------------
    // 7. FORM SUBMISSIONS: MODAL & INLINE FORMS
    // -------------------------------------------------------------------------
    async function submitConsultationRequest({ name, email, company, note, submitBtn, alertEl, onSuccess }) {
        if (!name || !email) {
            if (alertEl) {
                alertEl.hidden = false;
                alertEl.className = alertEl.classList.contains('form-alert') ? 'form-alert error' : 'modal-alert error';
                alertEl.textContent = 'Please provide both your name and work email address.';
            }
            return;
        }

        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.dataset.originalText = submitBtn.textContent;
            submitBtn.textContent = 'Submitting Request...';
        }

        if (alertEl) {
            alertEl.hidden = true;
            alertEl.textContent = '';
        }

        try {
            const res = await fetch('/api/v1/onboarding/consultation', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name,
                    email: email,
                    phone: '',
                    agency_name: company || '',
                    company: company || '',
                    niche: 'enterprise',
                    current_process: note || 'Agency OS Architecture Consultation Request'
                })
            });

            if (res.ok) {
                const data = await res.json();
                if (alertEl) {
                    alertEl.hidden = false;
                    alertEl.className = alertEl.classList.contains('form-alert') ? 'form-alert success' : 'modal-alert success';
                    alertEl.textContent = data.message || 'Request received. A systems architect will reach out shortly.';
                }
                if (typeof onSuccess === 'function') {
                    onSuccess();
                }
            } else {
                let errorDetail = 'Unable to submit your consultation request. Please try again.';
                try {
                    const errData = await res.json();
                    if (errData && errData.detail) {
                        if (typeof errData.detail === 'string') {
                            errorDetail = errData.detail;
                        } else if (Array.isArray(errData.detail)) {
                            errorDetail = errData.detail.map(d => d.msg || d.message || JSON.stringify(d)).join(', ');
                        } else {
                            errorDetail = JSON.stringify(errData.detail);
                        }
                    } else if (errData && errData.message) {
                        errorDetail = errData.message;
                    }
                } catch (_) {}

                if (alertEl) {
                    alertEl.hidden = false;
                    alertEl.className = alertEl.classList.contains('form-alert') ? 'form-alert error' : 'modal-alert error';
                    alertEl.textContent = errorDetail;
                }
            }
        } catch (networkError) {
            if (alertEl) {
                alertEl.hidden = false;
                alertEl.className = alertEl.classList.contains('form-alert') ? 'form-alert error' : 'modal-alert error';
                alertEl.textContent = 'Network communication error. Please check your connection and try again.';
            }
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = submitBtn.dataset.originalText || 'Request Consultation';
            }
        }
    }

    // Modal Form Handler
    if (consultationForm) {
        consultationForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const nameInput = document.getElementById('consultationName');
            const emailInput = document.getElementById('consultationEmail');
            const companyInput = document.getElementById('consultationCompany');
            const noteInput = document.getElementById('consultationNote');
            const submitBtn = document.getElementById('consultationSubmitBtn');

            submitConsultationRequest({
                name: nameInput?.value?.trim() || '',
                email: emailInput?.value?.trim() || '',
                company: companyInput?.value?.trim() || '',
                note: noteInput?.value?.trim() || '',
                submitBtn: submitBtn,
                alertEl: consultationAlert,
                onSuccess: function() {
                    consultationForm.reset();
                    setTimeout(closeConsultationModal, 2500);
                }
            });
        });
    }

    // Inline Contact Form Handler
    const inlineForm = document.getElementById('inlineContactForm');
    const inlineAlert = document.getElementById('inlineAlert');
    const inlineSubmitBtn = document.getElementById('inlineSubmitBtn');

    if (inlineForm) {
        inlineForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const nameInput = document.getElementById('inlineName');
            const emailInput = document.getElementById('inlineEmail');
            const companyInput = document.getElementById('inlineCompany');
            const noteInput = document.getElementById('inlineNote');

            submitConsultationRequest({
                name: nameInput?.value?.trim() || '',
                email: emailInput?.value?.trim() || '',
                company: companyInput?.value?.trim() || '',
                note: noteInput?.value?.trim() || '',
                submitBtn: inlineSubmitBtn,
                alertEl: inlineAlert,
                onSuccess: function() {
                    inlineForm.reset();
                }
            });
        });
    }

})();
