/**
 * Agency OS — Production Landing Page Controller
 * Axion Studio Specification — Pure Vanilla JavaScript
 * Zero external animation libraries / Single RAF loop / Leak-free
 */

(function () {
    'use strict';

    // -------------------------------------------------------------------------
    // 1. MOBILE MENU CONTROLLER
    // -------------------------------------------------------------------------
    const burgerBtn = document.getElementById('burgerBtn');
    const mobileMenu = document.getElementById('mobileMenu');
    const mobileOverlay = document.getElementById('mobileOverlay');
    const siteHeaderContainer = document.getElementById('siteHeaderContainer');
    const mobileLinks = document.querySelectorAll('.mobile-menu-link, .mobile-cta-btn');

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

    mobileLinks.forEach(link => {
        link.addEventListener('click', function (e) {
            closeMobileMenu();
            if (link.dataset.action === 'open-consultation-modal') {
                e.preventDefault();
                openModal(consultationModal);
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

    window.addEventListener('resize', function () {
        if (window.innerWidth > 768) {
            closeMobileMenu();
        }
    });

    // Header blur styling on scroll
    function handleHeaderScroll() {
        if (!siteHeaderContainer) return;
        if (window.scrollY > 30) {
            siteHeaderContainer.classList.add('scrolled');
        } else {
            siteHeaderContainer.classList.remove('scrolled');
        }
    }
    window.addEventListener('scroll', handleHeaderScroll, { passive: true });
    handleHeaderScroll();

    // -------------------------------------------------------------------------
    // 2. ACTIVE SECTION HIGHLIGHTING & SMOOTH NAVIGATION
    // -------------------------------------------------------------------------
    const navLinks = document.querySelectorAll('.nav-link');
    const sections = document.querySelectorAll('section[id]');

    function updateActiveNav() {
        const scrollY = window.scrollY + 180;
        let currentSectionId = '';

        sections.forEach(section => {
            const top = section.offsetTop;
            const height = section.offsetHeight;
            if (scrollY >= top && scrollY < top + height) {
                currentSectionId = section.getAttribute('id');
            }
        });

        navLinks.forEach(link => {
            const href = link.getAttribute('href');
            if (href === '#' + currentSectionId || (currentSectionId === 'process' && href === '#how-it-works')) {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });
    }

    window.addEventListener('scroll', updateActiveNav, { passive: true });

    navLinks.forEach(link => {
        link.addEventListener('click', function (e) {
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

    // -------------------------------------------------------------------------
    // 3. MOUSE-REACTIVE ATMOSPHERIC DEPTH & PARALLAX
    // -------------------------------------------------------------------------
    const heroGlow = document.getElementById('heroAtmosphereGlow');
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (heroGlow && !reducedMotion) {
        let mouseX = 0;
        let mouseY = 0;
        let currentShiftX = 0;
        let currentShiftY = 0;
        let animId = null;
        let isTabActive = true;

        function onMouseMove(e) {
            if (window.innerWidth <= 768) return;
            const centerX = window.innerWidth / 2;
            const centerY = window.innerHeight / 2;
            mouseX = (e.clientX - centerX) * 0.08;
            mouseY = (e.clientY - centerY) * 0.08;
        }

        function renderParallax() {
            if (!isTabActive || window.innerWidth <= 768) {
                animId = requestAnimationFrame(renderParallax);
                return;
            }
            currentShiftX += (mouseX - currentShiftX) * 0.05;
            currentShiftY += (mouseY - currentShiftY) * 0.05;

            heroGlow.style.setProperty('--mouse-shift-x', currentShiftX.toFixed(2) + 'px');
            heroGlow.style.setProperty('--mouse-shift-y', currentShiftY.toFixed(2) + 'px');

            animId = requestAnimationFrame(renderParallax);
        }

        window.addEventListener('mousemove', onMouseMove, { passive: true });
        animId = requestAnimationFrame(renderParallax);

        document.addEventListener('visibilitychange', function () {
            isTabActive = !document.hidden;
        });
    }

    // -------------------------------------------------------------------------
    // 4. FLOATING BACK TO TOP BUTTON
    // -------------------------------------------------------------------------
    const backToTopBtn = document.getElementById('backToTop');
    if (backToTopBtn) {
        window.addEventListener('scroll', function () {
            if (window.scrollY > 400) {
                backToTopBtn.classList.add('visible');
            } else {
                backToTopBtn.classList.remove('visible');
            }
        }, { passive: true });

        backToTopBtn.addEventListener('click', function () {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }

    // -------------------------------------------------------------------------
    // 5. MODALS CONTROLLER (CONSULTATION, PRIVACY, TERMS)
    // -------------------------------------------------------------------------
    const consultationModal = document.getElementById('consultationModal');
    const privacyModal = document.getElementById('privacyModal');
    const termsModal = document.getElementById('termsModal');

    function openModal(modalEl) {
        if (!modalEl) return;
        modalEl.classList.add('open');
        modalEl.setAttribute('aria-hidden', 'false');
        document.body.classList.add('menu-open');
    }

    function closeModal(modalEl) {
        if (!modalEl) return;
        modalEl.classList.remove('open');
        modalEl.setAttribute('aria-hidden', 'true');
        const anyModalOpen = document.querySelector('.modal-backdrop.open');
        if (!anyModalOpen) {
            document.body.classList.remove('menu-open');
        }
    }

    // Consultation modal triggers
    document.querySelectorAll('[data-action="open-consultation-modal"]').forEach(btn => {
        btn.addEventListener('click', function (e) {
            e.preventDefault();
            openModal(consultationModal);
        });
    });

    document.getElementById('closeConsultationModal')?.addEventListener('click', function () {
        closeModal(consultationModal);
    });

    // Privacy modal triggers
    document.getElementById('openPrivacyModalLink')?.addEventListener('click', function (e) {
        e.preventDefault();
        openModal(privacyModal);
    });

    document.getElementById('closePrivacyModal')?.addEventListener('click', function () {
        closeModal(privacyModal);
    });

    // Terms modal triggers
    document.getElementById('openTermsModalLink')?.addEventListener('click', function (e) {
        e.preventDefault();
        openModal(termsModal);
    });

    document.getElementById('closeTermsModal')?.addEventListener('click', function () {
        closeModal(termsModal);
    });

    // Close on backdrop click
    [consultationModal, privacyModal, termsModal].forEach(modal => {
        if (modal) {
            modal.addEventListener('click', function (e) {
                if (e.target === modal) {
                    closeModal(modal);
                }
            });
        }
    });

    // Escape key closes modals and menu
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            closeMobileMenu();
            closeModal(consultationModal);
            closeModal(privacyModal);
            closeModal(termsModal);
        }
    });

    // -------------------------------------------------------------------------
    // 6. CONTACT & CONSULTATION SUBMISSIONS
    // -------------------------------------------------------------------------
    async function submitLead(payload, alertEl, submitBtn, originalBtnText, formEl, successCallback) {
        if (alertEl) {
            alertEl.hidden = true;
            alertEl.textContent = '';
        }

        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Submitting Request...';
        }

        try {
            // Primary endpoint: /api/contact
            let res = await fetch('/api/contact', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            // If not found, try fallback /api/v1/onboarding/consultation
            if (res.status === 404) {
                res = await fetch('/api/v1/onboarding/consultation', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: payload.name,
                        email: payload.email,
                        company: payload.company,
                        service_interest: payload.service_interest,
                        notes: payload.message,
                        current_process: payload.message
                    })
                });
            }

            if (res.ok) {
                if (alertEl) {
                    alertEl.hidden = false;
                    alertEl.className = alertEl.classList.contains('form-alert') ? 'form-alert success' : 'modal-alert success';
                    alertEl.textContent = "Thank you — your request has been received. Our engineering team will review your requirements and respond within 24 business hours.";
                }
                if (formEl) formEl.reset();
                if (typeof successCallback === 'function') {
                    successCallback();
                }
            } else {
                let errorMsg = 'Unable to process your request. Please check all fields and try again.';
                try {
                    const data = await res.json();
                    if (data && data.detail) {
                        errorMsg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
                    }
                } catch (_) {}

                if (alertEl) {
                    alertEl.hidden = false;
                    alertEl.className = alertEl.classList.contains('form-alert') ? 'form-alert error' : 'modal-alert error';
                    alertEl.textContent = errorMsg;
                }
            }
        } catch (err) {
            if (alertEl) {
                alertEl.hidden = false;
                alertEl.className = alertEl.classList.contains('form-alert') ? 'form-alert error' : 'modal-alert error';
                alertEl.textContent = 'Network communication error. Please check your connection and try again.';
            }
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = originalBtnText;
            }
        }
    }

    // Inline Contact Form
    const contactForm = document.getElementById('contactForm');
    const inlineAlert = document.getElementById('inlineAlert');
    const contactSubmitBtn = document.getElementById('contactSubmitBtn');

    if (contactForm) {
        contactForm.addEventListener('submit', function (e) {
            e.preventDefault();
            const name = document.getElementById('contactName')?.value.trim() || '';
            const email = document.getElementById('contactEmail')?.value.trim() || '';
            const company = document.getElementById('contactCompany')?.value.trim() || '';
            const service = document.getElementById('contactService')?.value || '';
            const message = document.getElementById('contactMessage')?.value.trim() || '';

            submitLead(
                { name, email, company, service_interest: service, message },
                inlineAlert,
                contactSubmitBtn,
                'Send Consultation Request',
                contactForm
            );
        });
    }

    // Modal Consultation Form
    const consultationForm = document.getElementById('consultationForm');
    const consultationAlert = document.getElementById('consultationAlert');
    const consultationSubmitBtn = document.getElementById('consultationSubmitBtn');

    if (consultationForm) {
        consultationForm.addEventListener('submit', function (e) {
            e.preventDefault();
            const name = consultationForm.querySelector('[name="name"]')?.value.trim() || '';
            const email = consultationForm.querySelector('[name="email"]')?.value.trim() || '';
            const company = consultationForm.querySelector('[name="company"]')?.value.trim() || '';
            const phone = consultationForm.querySelector('[name="phone"]')?.value.trim() || '';
            const service = consultationForm.querySelector('[name="service_interest"]')?.value || 'sales_automation';
            const note = consultationForm.querySelector('[name="message"]')?.value.trim() || '';

            const fullMsg = phone ? `Phone: ${phone} | Note: ${note}` : note;

            submitLead(
                { name, email, company, service_interest: service, message: fullMsg },
                consultationAlert,
                consultationSubmitBtn,
                'Request Assessment',
                consultationForm,
                function () {
                    setTimeout(() => closeModal(consultationModal), 3000);
                }
            );
        });
    }

})();
