/* ==========================================================================
   AGENCY OS — CEO COMMAND CENTER THREE.JS 3D ENGINE
   Tactical WebGL Agency OS Core, Live Subsystem Conduits & Module Focus
   ========================================================================== */

(function() {
  'use strict';

  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Global Engine Reference for Diagnostics & Automated Tests
  window.agencyDashboard3D = {
    initialized: false,
    threeLoaded: false,
    frameCount: 0,
    activeSubsystem: null,
    subsystems: {},
    highlightSubsystem: null,
    triggerEventAnimation: null
  };

  document.addEventListener('DOMContentLoaded', () => {
    initCeoGreeting();
    initPerspectiveCardTilts();
    initThreeJsDashboardCore();
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
     2. Perspective Microinteractions for Cards
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

        const rotX = -y * 6;
        const rotY = x * 6;
        card.style.transform = `perspective(800px) rotateX(${rotX.toFixed(2)}deg) rotateY(${rotY.toFixed(2)}deg) translateY(-2px)`;
      });

      card.addEventListener('mouseleave', () => {
        isHovered = false;
        card.style.transform = '';
      });
    });
  }

  /* --------------------------------------------------------------------------
     3. THREE.JS TACTICAL AGENCY OS CORE (WEBGL)
     -------------------------------------------------------------------------- */
  function initThreeJsDashboardCore() {
    const canvas = document.getElementById('dashboard-3d-canvas');
    const stage = document.getElementById('ceo-core-stage');
    if (!canvas || !stage) return;

    if (typeof THREE === 'undefined') {
      console.warn('[Dashboard3D] Three.js not loaded, showing CSS fallback.');
      const fallback = document.getElementById('agency-os-core-fallback');
      if (fallback) fallback.style.display = 'flex';
      return;
    }

    window.agencyDashboard3D.threeLoaded = true;

    // Stage dimensions
    let width = stage.clientWidth || 320;
    let height = stage.clientHeight || 140;
    const isMobile = window.innerWidth <= 768;

    // 1. WebGL Renderer
    const renderer = new THREE.WebGLRenderer({
      canvas: canvas,
      alpha: true,
      antialias: !isMobile,
      powerPreference: 'high-performance'
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, isMobile ? 1.5 : 2));
    renderer.setSize(width, height);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;

    // 2. Scene & Camera
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, width / height, 1, 1000);
    const defaultCamPos = new THREE.Vector3(0, 10, 155);
    const targetCamPos = defaultCamPos.clone();
    camera.position.copy(defaultCamPos);

    const defaultLookTarget = new THREE.Vector3(0, 0, 0);
    const targetLookTarget = defaultLookTarget.clone();
    const currentLookTarget = defaultLookTarget.clone();

    window.agencyDashboard3D.renderer = renderer;
    window.agencyDashboard3D.scene = scene;
    window.agencyDashboard3D.camera = camera;

    // 3. Lighting
    const ambientLight = new THREE.AmbientLight(0x0f172a, 3.0);
    scene.add(ambientLight);

    const coreLight = new THREE.PointLight(0x00d4ef, 3.5, 300);
    coreLight.position.set(0, 0, 0);
    scene.add(coreLight);

    const dirLight = new THREE.DirectionalLight(0x38bdf8, 1.8);
    dirLight.position.set(50, 80, 70);
    scene.add(dirLight);

    // 4. Central Group
    const coreGroup = new THREE.Group();
    scene.add(coreGroup);

    // Faceted Dodecahedron Nucleus
    const nucleusGeo = new THREE.DodecahedronGeometry(15, 0);
    const nucleusMat = new THREE.MeshStandardMaterial({
      color: 0x075985,
      emissive: 0x00d4ef,
      emissiveIntensity: 0.65,
      roughness: 0.25,
      metalness: 0.8
    });
    const nucleusMesh = new THREE.Mesh(nucleusGeo, nucleusMat);
    coreGroup.add(nucleusMesh);

    // Luminous Edges for Nucleus
    const edgesGeo = new THREE.EdgesGeometry(nucleusGeo);
    const edgesMat = new THREE.LineBasicMaterial({ color: 0x38bdf8, linewidth: 1.5 });
    const edgesMesh = new THREE.LineSegments(edgesGeo, edgesMat);
    nucleusMesh.add(edgesMesh);

    // Gyro Rings
    const ring1Geo = new THREE.TorusGeometry(26, 0.65, 8, 48);
    const ring1Mat = new THREE.MeshBasicMaterial({ color: 0x00d4ef, transparent: true, opacity: 0.45 });
    const ring1 = new THREE.Mesh(ring1Geo, ring1Mat);
    ring1.rotation.x = Math.PI / 3;
    coreGroup.add(ring1);

    const ring2Geo = new THREE.TorusGeometry(36, 0.55, 8, 48);
    const ring2Mat = new THREE.MeshBasicMaterial({ color: 0x8b5cf6, transparent: true, opacity: 0.35 });
    const ring2 = new THREE.Mesh(ring2Geo, ring2Mat);
    ring2.rotation.x = -Math.PI / 4;
    ring2.rotation.y = Math.PI / 6;
    coreGroup.add(ring2);

    // 5. 7 Operational Subsystem Nodes
    // Architectural Topology:
    //              ACQUISITION (0, 44, 0)
    //                   │
    // COMMUNICATION ── AI CORE ── SALES
    // (-48, 10, -8)     │       (48, 10, 8)
    //               PAYMENT
    //            (-34, -32, 10)
    //                   │
    //               DELIVERY
    //             (34, -32, -10)
    //                   │
    //                SUPPORT
    //              (0, -44, 0)
    // INTELLIGENCE Orbit: (0, 22, 34)
    const subsystemDefs = [
      { id: 'ACQUISITION', name: 'Acquisition', pos: [0, 44, 0], color: 0x00d4ef, views: ['global-acquisition', 'leads'] },
      { id: 'COMMUNICATION', name: 'Communication', pos: [-48, 10, -8], color: 0x38bdf8, views: ['queue', 'replies'] },
      { id: 'SALES', name: 'Sales', pos: [48, 10, 8], color: 0x10b981, views: ['proposals'] },
      { id: 'PAYMENT', name: 'Payment', pos: [-34, -32, 10], color: 0x8b5cf6, views: ['payments'] },
      { id: 'DELIVERY', name: 'Delivery', pos: [34, -32, -10], color: 0x6366f1, views: ['client-intelligence'] },
      { id: 'SUPPORT', name: 'Support', pos: [0, -44, 0], color: 0xf59e0b, views: ['support-ops', 'runs'] },
      { id: 'INTELLIGENCE', name: 'Intelligence', pos: [0, 22, 34], color: 0xf43f5e, views: ['intelligence', 'decision-analytics'] }
    ];

    const subsystems = {};

    subsystemDefs.forEach(def => {
      const nodeGroup = new THREE.Group();
      nodeGroup.position.set(def.pos[0], def.pos[1], def.pos[2]);

      // Micro faceted sphere
      const sGeo = new THREE.SphereGeometry(5.2, 12, 12);
      const sMat = new THREE.MeshStandardMaterial({
        color: def.color,
        emissive: def.color,
        emissiveIntensity: 0.5,
        roughness: 0.3,
        metalness: 0.7
      });
      const sMesh = new THREE.Mesh(sGeo, sMat);
      nodeGroup.add(sMesh);

      // Status Beacon Ring
      const beaconGeo = new THREE.RingGeometry(6.8, 8.5, 16);
      const beaconMat = new THREE.MeshBasicMaterial({
        color: def.color,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.4
      });
      const beaconMesh = new THREE.Mesh(beaconGeo, beaconMat);
      beaconMesh.rotation.x = Math.PI / 2;
      nodeGroup.add(beaconMesh);

      coreGroup.add(nodeGroup);

      // Cybernetic Conduit to Core Center
      const lineGeo = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(0, 0, 0),
        new THREE.Vector3(...def.pos)
      ]);
      const lineMat = new THREE.LineBasicMaterial({
        color: def.color,
        transparent: true,
        opacity: 0.3
      });
      const conduitLine = new THREE.Line(lineGeo, lineMat);
      coreGroup.add(conduitLine);

      subsystems[def.id] = {
        def,
        group: nodeGroup,
        mesh: sMesh,
        material: sMat,
        beacon: beaconMesh,
        conduit: conduitLine,
        basePos: new THREE.Vector3(...def.pos),
        active: false,
        pulseVal: 0
      };
    });

    window.agencyDashboard3D.subsystems = subsystems;

    // 6. Subtle Floating Particle Field
    const particleTotal = 45;
    const pGeo = new THREE.BufferGeometry();
    const pCoords = new Float32Array(particleTotal * 3);
    for (let i = 0; i < particleTotal * 3; i += 3) {
      pCoords[i] = (Math.random() - 0.5) * 200;
      pCoords[i + 1] = (Math.random() - 0.5) * 160;
      pCoords[i + 2] = (Math.random() - 0.5) * 120;
    }
    pGeo.setAttribute('position', new THREE.BufferAttribute(pCoords, 3));
    const pMat = new THREE.PointsMaterial({ color: 0x38bdf8, size: 1.8, transparent: true, opacity: 0.4 });
    const particleCloud = new THREE.Points(pGeo, pMat);
    coreGroup.add(particleCloud);

    // 7. Real Data Binding (NO Fabricated Operational Metrics)
    function bindRealSystemTelemetry() {
      // Check Real Prospects in DOM
      const leadsEl = document.getElementById('ceo-val-total-prospects') || document.getElementById('val-leads');
      const leadsVal = leadsEl ? parseInt(leadsEl.textContent.replace(/[^0-9]/g, '') || '0', 10) : 0;
      if (subsystems.ACQUISITION) {
        if (leadsVal > 0) {
          subsystems.ACQUISITION.material.emissiveIntensity = 0.8;
          subsystems.ACQUISITION.beacon.material.opacity = 0.7;
        } else {
          // Neutral idle state
          subsystems.ACQUISITION.material.emissiveIntensity = 0.25;
          subsystems.ACQUISITION.beacon.material.opacity = 0.2;
        }
      }

      // Check Real Sales Pipeline in DOM
      const salesEl = document.getElementById('ceo-val-interested-leads') || document.getElementById('ceo-val-qualified-prospects');
      const salesVal = salesEl ? parseInt(salesEl.textContent.replace(/[^0-9]/g, '') || '0', 10) : 0;
      if (subsystems.SALES) {
        if (salesVal > 0) {
          subsystems.SALES.material.emissiveIntensity = 0.85;
          subsystems.SALES.beacon.material.opacity = 0.75;
        } else {
          subsystems.SALES.material.emissiveIntensity = 0.25;
          subsystems.SALES.beacon.material.opacity = 0.2;
        }
      }

      // Check Real Backend Health Status in DOM
      const healthEl = document.getElementById('ceo-backend-health-text');
      const isConnected = healthEl && healthEl.textContent.trim().toUpperCase() === 'CONNECTED';
      if (isConnected) {
        nucleusMat.emissive.setHex(0x00d4ef);
        coreLight.color.setHex(0x00d4ef);
      } else {
        nucleusMat.emissive.setHex(0xf59e0b);
        coreLight.color.setHex(0xf59e0b);
      }
    }

    // Run data binding check periodically
    setInterval(bindRealSystemTelemetry, 4000);
    bindRealSystemTelemetry();

    // 8. Module Interaction: Highlight Subsystem on View Switch
    function highlightSubsystem(subsystemId) {
      window.agencyDashboard3D.activeSubsystem = subsystemId;

      Object.keys(subsystems).forEach(id => {
        const sub = subsystems[id];
        const isTarget = id === subsystemId;

        if (isTarget) {
          sub.group.scale.set(1.4, 1.4, 1.4);
          sub.material.emissiveIntensity = 1.0;
          sub.beacon.material.opacity = 0.9;
          sub.conduit.material.opacity = 0.85;

          // Smoothly bias camera toward selected subsystem
          targetCamPos.set(sub.basePos.x * 0.4, sub.basePos.y * 0.4 + 5, 130);
          targetLookTarget.copy(sub.basePos).multiplyScalar(0.5);
        } else if (subsystemId) {
          sub.group.scale.set(0.9, 0.9, 0.9);
          sub.material.emissiveIntensity = 0.2;
          sub.beacon.material.opacity = 0.15;
          sub.conduit.material.opacity = 0.15;
        } else {
          // Reset all
          sub.group.scale.set(1, 1, 1);
          sub.material.emissiveIntensity = 0.45;
          sub.beacon.material.opacity = 0.35;
          sub.conduit.material.opacity = 0.3;
          targetCamPos.copy(defaultCamPos);
          targetLookTarget.copy(defaultLookTarget);
        }
      });
    }

    window.agencyDashboard3D.highlightSubsystem = highlightSubsystem;

    // Hook cleanly into window.navToView
    const origNavToView = window.navToView;
    window.navToView = function(viewName) {
      if (typeof origNavToView === 'function') {
        origNavToView(viewName);
      }

      // Map view name to 3D subsystem
      let matchedId = null;
      subsystemDefs.forEach(def => {
        if (def.views.includes(viewName)) {
          matchedId = def.id;
        }
      });

      highlightSubsystem(matchedId);
    };

    // 9. Meaningful Event Animation Bridge (Payment, Incidents, Deliveries)
    window.agencyDashboard3D.triggerEventAnimation = function(eventType) {
      let targetSubId = null;
      if (eventType.includes('PAYMENT')) targetSubId = 'PAYMENT';
      else if (eventType.includes('SEV') || eventType.includes('SUPPORT')) targetSubId = 'SUPPORT';
      else if (eventType.includes('REPLY') || eventType.includes('OUTREACH')) targetSubId = 'COMMUNICATION';
      else if (eventType.includes('DELIVERY')) targetSubId = 'DELIVERY';

      if (targetSubId && subsystems[targetSubId]) {
        const targetNode = subsystems[targetSubId];
        targetNode.group.scale.set(1.8, 1.8, 1.8);
        coreLight.intensity = 6.0;

        setTimeout(() => {
          targetNode.group.scale.set(1, 1, 1);
          coreLight.intensity = 3.5;
        }, 1200);
      }
    };

    // Listen for internal test buttons
    document.querySelectorAll('.btn-trigger-test-alert').forEach(btn => {
      btn.addEventListener('click', () => {
        const evType = btn.getAttribute('data-event-type') || '';
        window.agencyDashboard3D.triggerEventAnimation(evType);
      });
    });

    // 10. Interactive Raycasting on Hover
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2(-999, -999);
    let hoveredMesh = null;

    canvas.addEventListener('mousemove', (e) => {
      const rect = canvas.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    }, { passive: true });

    canvas.addEventListener('mouseleave', () => {
      mouse.x = -999;
      mouse.y = -999;
    });

    // 11. Animation Loop with Visibility Pause
    let isVisible = true;
    let animId = null;

    function render() {
      animId = requestAnimationFrame(render);
      window.agencyDashboard3D.frameCount++;

      if (!isVisible) return;

      const time = performance.now() * 0.001;

      // Smooth Camera & Target Lerp
      camera.position.lerp(targetCamPos, 0.06);
      currentLookTarget.lerp(targetLookTarget, 0.06);
      camera.lookAt(currentLookTarget);

      // Controlled Core Rotation
      if (!prefersReducedMotion) {
        nucleusMesh.rotation.y += 0.008;
        nucleusMesh.rotation.x += 0.004;

        ring1.rotation.z += 0.006;
        ring2.rotation.z -= 0.005;

        // Gentle floating oscillation
        coreGroup.position.y = Math.sin(time * 1.8) * 2.2;

        // Conduits pulse breathing
        Object.keys(subsystems).forEach((id, idx) => {
          const sub = subsystems[id];
          const pulse = (Math.sin(time * 3 + idx) + 1) * 0.5;
          sub.beacon.rotation.z += 0.015;
          if (!window.agencyDashboard3D.activeSubsystem) {
            sub.beacon.scale.setScalar(1 + pulse * 0.15);
          }
        });
      }

      // Raycasting
      if (mouse.x > -100) {
        raycaster.setFromCamera(mouse, camera);
        const meshesToTest = Object.values(subsystems).map(s => s.mesh);
        const intersects = raycaster.intersectObjects(meshesToTest);

        if (intersects.length > 0) {
          const hit = intersects[0].object;
          if (hoveredMesh !== hit) {
            canvas.style.cursor = 'pointer';
            hoveredMesh = hit;
          }
        } else {
          if (hoveredMesh) {
            canvas.style.cursor = 'default';
            hoveredMesh = null;
          }
        }
      }

      renderer.render(scene, camera);
    }

    // Visibility management
    document.addEventListener('visibilitychange', () => {
      isVisible = !document.hidden;
    });

    if ('IntersectionObserver' in window) {
      const obs = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          isVisible = entry.isIntersecting;
        });
      }, { threshold: 0.1 });
      obs.observe(canvas);
    }

    // Resize Handler
    window.addEventListener('resize', () => {
      width = stage.clientWidth || 320;
      height = stage.clientHeight || 140;
      const mob = window.innerWidth <= 768;

      camera.aspect = width / height;
      camera.updateProjectionMatrix();

      renderer.setSize(width, height);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, mob ? 1.5 : 2));
    }, { passive: true });

    render();
    window.agencyDashboard3D.initialized = true;
    console.log('[Dashboard3D] Tactical Three.js WebGL Core initialized.');
  }

})();
