/* ==========================================================================
   AGENCY OS — THREE.JS 3D CINEMATIC MOTION & SCROLL ENGINE
   WebGL Perspective Scene, GSAP ScrollTrigger Choreography & Live Workflows
   ========================================================================== */

(function() {
  'use strict';

  // Check prefers-reduced-motion
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Global Engine Reference for diagnostics and tests
  window.agencyLanding3D = {
    initialized: false,
    threeLoaded: false,
    gsapLoaded: false,
    frameCount: 0,
    activeWorkflow: 'missed_call',
    nodes: {},
    sceneState: 'HERO',
    scrollProgress: 0
  };

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

  // Wait for DOM
  document.addEventListener('DOMContentLoaded', () => {
    initHeaderScroll();
    initMobileNav();
    initConsultationModals();
    initContactForm();
    initSimulator();
    initSmoothAnchors();

    // Initialize Real Three.js WebGL 3D Motion Engine
    initThreeJsLandingScene();
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
     2. Mobile Navigation Drawer
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

    const links = drawer.querySelectorAll('a, button');
    links.forEach(link => {
      link.addEventListener('click', closeDrawer);
    });

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
        const service = (document.getElementById('modalGoal') || {}).value || '';

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
            body: JSON.stringify({ name, email, company, service, message: `Consultation Modal: ${service}` })
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
            submitBtn.textContent = 'Confirm Strategy Call Request';
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
      window.agencyLanding3D.activeWorkflow = scenarioKey;

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

      // Trigger Three.js WebGL reactive pulse across the 3D scene
      if (typeof window.triggerLanding3DPulse === 'function') {
        window.triggerLanding3DPulse(scenarioKey);
      }
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
     7. THREE.JS 3D CINEMATIC WEBGL MOTION ENGINE
     -------------------------------------------------------------------------- */
  function initThreeJsLandingScene() {
    const canvas = document.getElementById('bg-canvas-3d');
    if (!canvas) return;

    if (typeof THREE === 'undefined') {
      console.warn('[Landing3D] Three.js not loaded, deferring initialization.');
      return;
    }

    window.agencyLanding3D.threeLoaded = true;

    // 1. Renderer Setup
    let width = window.innerWidth;
    let height = window.innerHeight;
    const isMobile = width <= 768;

    const renderer = new THREE.WebGLRenderer({
      canvas: canvas,
      alpha: true,
      antialias: !isMobile,
      powerPreference: 'high-performance'
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, isMobile ? 1.5 : 2));
    renderer.setSize(width, height);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;

    // 2. Scene & Camera Setup
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, width / height, 1, 2500);
    camera.position.set(0, 0, 850);

    window.agencyLanding3D.renderer = renderer;
    window.agencyLanding3D.scene = scene;
    window.agencyLanding3D.camera = camera;

    // 3. Controlled Lighting
    const ambientLight = new THREE.AmbientLight(0x0a101d, 2.5);
    scene.add(ambientLight);

    const keyLight = new THREE.DirectionalLight(0x00d4ef, 2.2);
    keyLight.position.set(300, 400, 500);
    scene.add(keyLight);

    const rimLight = new THREE.DirectionalLight(0x6366f1, 2.8);
    rimLight.position.set(-300, -200, 300);
    scene.add(rimLight);

    const pointLight = new THREE.PointLight(0x00d4ef, 3.0, 600);
    pointLight.position.set(0, 0, 0);
    scene.add(pointLight);

    // 4. Main 3D System Hierarchy Group
    const systemGroup = new THREE.Group();
    scene.add(systemGroup);

    // Initial desktop placement offset towards right side of hero text
    const targetBaseX = isMobile ? 0 : 200;
    systemGroup.position.set(targetBaseX, 0, 0);

    // 5. Central Nucleus (AI AUTOMATION CORE)
    const nucleusGeo = new THREE.IcosahedronGeometry(isMobile ? 38 : 50, 1);
    const nucleusMat = new THREE.MeshStandardMaterial({
      color: 0x0284c7,
      emissive: 0x00d4ef,
      emissiveIntensity: 0.6,
      roughness: 0.2,
      metalness: 0.8,
      wireframe: false
    });
    const nucleusMesh = new THREE.Mesh(nucleusGeo, nucleusMat);
    systemGroup.add(nucleusMesh);

    // Wireframe Outer Cage for Nucleus
    const cageGeo = new THREE.IcosahedronGeometry(isMobile ? 46 : 60, 1);
    const cageMat = new THREE.MeshBasicMaterial({
      color: 0x38bdf8,
      wireframe: true,
      transparent: true,
      opacity: 0.45
    });
    const cageMesh = new THREE.Mesh(cageGeo, cageMat);
    systemGroup.add(cageMesh);

    // 6. Orbital Concentric Rings
    const orbitalRings = [];
    const ringSpecs = [
      { r: isMobile ? 100 : 135, tube: 0.8, tiltX: Math.PI / 3, tiltY: 0.2, color: 0x00d4ef, speed: 0.004 },
      { r: isMobile ? 160 : 210, tube: 0.7, tiltX: Math.PI / 4, tiltY: -0.3, color: 0x6366f1, speed: -0.003 },
      { r: isMobile ? 220 : 290, tube: 0.6, tiltX: Math.PI / 2.5, tiltY: 0.4, color: 0x00d4ef, speed: 0.002 }
    ];

    ringSpecs.forEach(spec => {
      const ringGeo = new THREE.TorusGeometry(spec.r, spec.tube, 8, isMobile ? 48 : 80);
      const ringMat = new THREE.MeshBasicMaterial({
        color: spec.color,
        transparent: true,
        opacity: 0.35
      });
      const ringMesh = new THREE.Mesh(ringGeo, ringMat);
      ringMesh.rotation.x = spec.tiltX;
      ringMesh.rotation.y = spec.tiltY;
      systemGroup.add(ringMesh);
      orbitalRings.push({ mesh: ringMesh, speed: spec.speed });
    });

    // 7. Core Conceptual 3D Nodes
    // Concept:
    //         AI AUTOMATION CORE (Center 0,0,0)
    //         /        |         \
    //      LEADS      AI      WORKFLOWS
    //         \        |         /
    //            SELL / BUILD
    //                 |
    //               DEPLOY
    //                 |
    //               GROW
    const nodeDefs = [
      { id: 'leads', name: 'LEADS', pos: [-130, 80, 40], color: 0x00d4ef, size: 14 },
      { id: 'ai', name: 'AI', pos: [0, 110, -20], color: 0x38bdf8, size: 16 },
      { id: 'workflows', name: 'WORKFLOWS', pos: [130, 80, 30], color: 0x6366f1, size: 14 },
      { id: 'sell_build', name: 'SELL / BUILD', pos: [85, -70, 50], color: 0x10b981, size: 15 },
      { id: 'deploy', name: 'DEPLOY', pos: [-85, -80, -30], color: 0x8b5cf6, size: 13 },
      { id: 'grow', name: 'GROW', pos: [0, -145, 20], color: 0x00d4ef, size: 16 }
    ];

    const nodesMap = {};
    const nodeMaterials = [];

    nodeDefs.forEach(def => {
      const nGroup = new THREE.Group();
      nGroup.position.set(def.pos[0], def.pos[1], def.pos[2]);

      const nGeo = new THREE.SphereGeometry(def.size, 16, 16);
      const nMat = new THREE.MeshStandardMaterial({
        color: def.color,
        emissive: def.color,
        emissiveIntensity: 0.55,
        roughness: 0.3,
        metalness: 0.7
      });
      const nMesh = new THREE.Mesh(nGeo, nMat);
      nGroup.add(nMesh);

      // Halo ring around node
      const haloGeo = new THREE.RingGeometry(def.size * 1.3, def.size * 1.6, 24);
      const haloMat = new THREE.MeshBasicMaterial({
        color: def.color,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.4
      });
      const haloMesh = new THREE.Mesh(haloGeo, haloMat);
      nGroup.add(haloMesh);

      systemGroup.add(nGroup);

      nodesMap[def.id] = {
        group: nGroup,
        mesh: nMesh,
        material: nMat,
        halo: haloMesh,
        basePos: new THREE.Vector3(...def.pos),
        baseScale: 1
      };
      nodeMaterials.push(nMat);
    });

    window.agencyLanding3D.nodes = nodesMap;

    // 8. 3D Cybernetic Connector Lines
    const connections = [
      ['leads', 'ai'],
      ['ai', 'workflows'],
      ['workflows', 'sell_build'],
      ['sell_build', 'deploy'],
      ['deploy', 'grow'],
      ['leads', 'sell_build'],
      ['grow', 'leads']
    ];

    const lineObjects = [];
    connections.forEach(([fromId, toId]) => {
      const fromNode = nodesMap[fromId];
      const toNode = nodesMap[toId];
      if (!fromNode || !toNode) return;

      const curve = new THREE.CatmullRomCurve3([
        fromNode.basePos,
        new THREE.Vector3().addVectors(fromNode.basePos, toNode.basePos).multiplyScalar(0.5).add(new THREE.Vector3(0, 15, 20)),
        toNode.basePos
      ]);

      const points = curve.getPoints(32);
      const lineGeo = new THREE.BufferGeometry().setFromPoints(points);
      const lineMat = new THREE.LineBasicMaterial({
        color: 0x38bdf8,
        transparent: true,
        opacity: 0.25,
        linewidth: 1
      });
      const lineMesh = new THREE.Line(lineGeo, lineMat);
      systemGroup.add(lineMesh);

      lineObjects.push({ line: lineMesh, curve, material: lineMat });
    });

    // 9. Floating 3D Spline Pulse Particles (Data Flow)
    const pulseCount = 12;
    const pulseGeo = new THREE.SphereGeometry(3, 8, 8);
    const pulseMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.85 });
    const pulses = [];

    for (let i = 0; i < pulseCount; i++) {
      const pMesh = new THREE.Mesh(pulseGeo, pulseMat);
      systemGroup.add(pMesh);
      pulses.push({
        mesh: pMesh,
        connIndex: i % lineObjects.length,
        progress: (i / pulseCount)
      });
    }

    // 10. Ambient 3D Particle Constellation (Telemetry Dust)
    const particleTotal = isMobile ? 80 : 200;
    const partGeo = new THREE.BufferGeometry();
    const partPositions = new Float32Array(particleTotal * 3);

    for (let i = 0; i < particleTotal * 3; i += 3) {
      partPositions[i] = (Math.random() - 0.5) * 1600;
      partPositions[i + 1] = (Math.random() - 0.5) * 1200;
      partPositions[i + 2] = (Math.random() - 0.5) * 900;
    }

    partGeo.setAttribute('position', new THREE.BufferAttribute(partPositions, 3));
    const partMat = new THREE.PointsMaterial({
      color: 0xa5b4fc,
      size: 2.2,
      transparent: true,
      opacity: 0.45
    });
    const particleCloud = new THREE.Points(partGeo, partMat);
    scene.add(particleCloud);

    // 11. Mouse Parallax (Smooth Lerp)
    let targetMouseX = 0;
    let targetMouseY = 0;
    let currentMouseX = 0;
    let currentMouseY = 0;

    if (!prefersReducedMotion && !isMobile) {
      window.addEventListener('mousemove', (e) => {
        targetMouseX = (e.clientX - width / 2) * 0.15;
        targetMouseY = (e.clientY - height / 2) * 0.15;
      }, { passive: true });
    }

    // 12. Interactive Pulse Wave Trigger from Simulator
    window.triggerLanding3DPulse = function(workflowKey) {
      const targetColors = {
        missed_call: 0x00d4ef,
        web_enquiry: 0x38bdf8,
        lead_form: 0x10b981,
        support_request: 0xf59e0b
      };
      const activeColor = targetColors[workflowKey] || 0x00d4ef;

      // Pulse nucleus
      pointLight.color.setHex(activeColor);
      pointLight.intensity = 5.0;

      // Animate nucleus expansion
      if (typeof gsap !== 'undefined') {
        gsap.to(nucleusMesh.scale, { x: 1.25, y: 1.25, z: 1.25, duration: 0.35, yoyo: true, repeat: 1, ease: 'power2.out' });
        gsap.to(cageMesh.scale, { x: 1.2, y: 1.2, z: 1.2, duration: 0.45, yoyo: true, repeat: 1, ease: 'power2.out' });
        
        // Highlight active node
        const keyNode = nodesMap.leads;
        if (keyNode) {
          gsap.to(keyNode.group.scale, { x: 1.6, y: 1.6, z: 1.6, duration: 0.4, yoyo: true, repeat: 1 });
        }
      } else {
        nucleusMesh.scale.set(1.2, 1.2, 1.2);
        setTimeout(() => nucleusMesh.scale.set(1, 1, 1), 500);
      }
    };

    // 13. GSAP ScrollTrigger 3D Choreography
    function initScrollTriggerChoreography() {
      if (typeof gsap === 'undefined' || typeof ScrollTrigger === 'undefined' || prefersReducedMotion) {
        // Fallback: standard scroll handler
        window.addEventListener('scroll', () => {
          const scrollY = window.scrollY;
          const maxScroll = document.documentElement.scrollHeight - window.innerHeight || 1;
          const p = Math.min(Math.max(scrollY / maxScroll, 0), 1);
          window.agencyLanding3D.scrollProgress = p;

          camera.position.z = 850 - p * 300;
          camera.position.y = -p * 150;
          systemGroup.rotation.y = p * Math.PI * 1.5;
        }, { passive: true });
        return;
      }

      window.agencyLanding3D.gsapLoaded = true;
      gsap.registerPlugin(ScrollTrigger);

      // Section 1: Hero to Discover
      ScrollTrigger.create({
        trigger: '#hero',
        start: 'top top',
        end: 'bottom top',
        scrub: 1,
        onUpdate: (self) => {
          const p = self.progress;
          window.agencyLanding3D.scrollProgress = p * 0.2;
          camera.position.z = 850 - p * 120;
          systemGroup.rotation.y = p * 0.8;
          systemGroup.position.x = targetBaseX - p * (isMobile ? 0 : 80);
        }
      });

      // Section 2: Operating Lifecycle (Discover -> Audit -> Persuade -> Sell -> Build -> Deploy -> Maintain -> Grow)
      ScrollTrigger.create({
        trigger: '#how-it-works',
        start: 'top center',
        end: 'bottom center',
        scrub: 1.2,
        onUpdate: (self) => {
          const p = self.progress;
          window.agencyLanding3D.scrollProgress = 0.2 + p * 0.4;
          camera.position.z = 730 - p * 80;
          camera.position.y = -p * 100;
          systemGroup.rotation.y = 0.8 + p * 1.4;
          systemGroup.rotation.x = p * 0.2;

          // Sequential node scaling highlights based on scroll milestone
          if (nodesMap.leads) nodesMap.leads.group.scale.setScalar(1 + (p < 0.2 ? 0.3 : 0));
          if (nodesMap.ai) nodesMap.ai.group.scale.setScalar(1 + (p >= 0.2 && p < 0.4 ? 0.35 : 0));
          if (nodesMap.workflows) nodesMap.workflows.group.scale.setScalar(1 + (p >= 0.4 && p < 0.6 ? 0.35 : 0));
          if (nodesMap.sell_build) nodesMap.sell_build.group.scale.setScalar(1 + (p >= 0.6 && p < 0.8 ? 0.35 : 0));
          if (nodesMap.deploy) nodesMap.deploy.group.scale.setScalar(1 + (p >= 0.8 && p < 0.95 ? 0.35 : 0));
          if (nodesMap.grow) nodesMap.grow.group.scale.setScalar(1 + (p >= 0.95 ? 0.4 : 0));
        }
      });

      // Section 3: Interactive Demo & Services
      ScrollTrigger.create({
        trigger: '#interactive-demo',
        start: 'top bottom',
        end: 'bottom top',
        scrub: 1,
        onUpdate: (self) => {
          const p = self.progress;
          window.agencyLanding3D.scrollProgress = 0.6 + p * 0.2;
          camera.position.z = 650 + Math.sin(p * Math.PI) * 50;
          systemGroup.position.x = (isMobile ? 0 : 120);
        }
      });

      // Section 4: Final CTA
      ScrollTrigger.create({
        trigger: '#contact',
        start: 'top bottom',
        end: 'bottom bottom',
        scrub: 1,
        onUpdate: (self) => {
          const p = self.progress;
          window.agencyLanding3D.scrollProgress = 0.8 + p * 0.2;
          camera.position.z = 700 - p * 100;
          systemGroup.position.x = 0; // Center behind CTA card
          systemGroup.position.y = -60;
        }
      });
    }

    initScrollTriggerChoreography();

    // 14. Main Animation Loop (Optimized RAF)
    let isVisible = true;
    let animId = null;

    function renderLoop() {
      animId = requestAnimationFrame(renderLoop);
      window.agencyLanding3D.frameCount++;

      if (!isVisible) return;

      const time = performance.now() * 0.001;

      // Mouse Parallax Lerp
      currentMouseX += (targetMouseX - currentMouseX) * 0.05;
      currentMouseY += (targetMouseY - currentMouseY) * 0.05;

      camera.position.x = currentMouseX;
      camera.position.y = -currentMouseY + (window.agencyLanding3D.scrollProgress ? -window.agencyLanding3D.scrollProgress * 80 : 0);
      camera.lookAt(systemGroup.position.x * 0.3, systemGroup.position.y * 0.3, 0);

      // Controlled Continuous Rotations
      if (!prefersReducedMotion) {
        nucleusMesh.rotation.y += 0.006;
        nucleusMesh.rotation.x += 0.003;
        cageMesh.rotation.y -= 0.004;
        cageMesh.rotation.z += 0.002;

        orbitalRings.forEach(r => {
          r.mesh.rotation.z += r.speed;
        });

        // Orbit satellite nodes gently
        nodeDefs.forEach((def, idx) => {
          const node = nodesMap[def.id];
          if (!node) return;
          const wobble = Math.sin(time * 1.5 + idx) * 3.5;
          node.group.position.y = node.basePos.y + wobble;
          node.halo.rotation.z += 0.01;
        });

        // Pulse Particles moving along curves
        pulses.forEach(p => {
          p.progress = (p.progress + 0.004) % 1.0;
          const conn = lineObjects[p.connIndex];
          if (conn && conn.curve) {
            const pt = conn.curve.getPoint(p.progress);
            p.mesh.position.copy(pt);
          }
        });

        // Subtle particle cloud drift
        particleCloud.rotation.y = time * 0.015;
        particleCloud.rotation.x = Math.sin(time * 0.01) * 0.05;

        // Point light breathing
        pointLight.intensity = 2.4 + Math.sin(time * 2.0) * 0.5;
      }

      renderer.render(scene, camera);
    }

    // Pause rendering when tab is hidden or canvas is not visible
    document.addEventListener('visibilitychange', () => {
      isVisible = !document.hidden;
    });

    if ('IntersectionObserver' in window) {
      const obs = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          isVisible = entry.isIntersecting;
        });
      }, { threshold: 0.05 });
      obs.observe(canvas);
    }

    // Responsive Resize Handler
    window.addEventListener('resize', () => {
      width = window.innerWidth;
      height = window.innerHeight;
      const mob = width <= 768;

      camera.aspect = width / height;
      camera.updateProjectionMatrix();

      renderer.setSize(width, height);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, mob ? 1.5 : 2));

      systemGroup.position.x = mob ? 0 : 200;
    }, { passive: true });

    renderLoop();
    window.agencyLanding3D.initialized = true;
    console.log('[Landing3D] Real Three.js WebGL Motion Engine active.');
  }

})();
