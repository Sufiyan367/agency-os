/**
 * OSAI — AI Automation For Modern Businesses
 * Realistic Digital Business Workflow 3D Engine
 * 
 * Flow: Customer Ingress -> AI Reasoning Matrix -> Commercial Outcomes (Calendar, CRM, Dispatch)
 */

declare var THREE: any;
declare var gsap: any;
declare var ScrollTrigger: any;

interface WorkflowDefinition {
  key: string;
  name: string;
  terminals: string[];
  color: number;
  accentHex: string;
}

interface BusinessNode {
  id: string;
  name: string;
  group: any;
  mesh: any;
  beacon: any;
  halo: any;
  baseScale: number;
  targetScale: number;
  pos: [number, number, number];
  color: number;
}

interface ConduitData {
  id: string;
  curve: any;
  mesh: any;
  pulseParticles: any[];
  startPos: any;
  endPos: any;
}

interface Landing3DState {
  initialized: boolean;
  threeLoaded: boolean;
  gsapLoaded: boolean;
  frameCount: number;
  scrollProgress: number;
  activeWorkflow: string;
  camera: any;
  scene: any;
  renderer: any;
  nodes: Record<string, BusinessNode>;
  conduits: ConduitData[];
  triggerPulse: (key: string) => void;
  selectSolution: (key: string) => void;
  dispose: () => void;
}

(function () {
  'use strict';

  const state: Landing3DState = {
    initialized: false,
    threeLoaded: false,
    gsapLoaded: false,
    frameCount: 0,
    scrollProgress: 0,
    activeWorkflow: 'missed_call',
    camera: null,
    scene: null,
    renderer: null,
    nodes: {},
    conduits: [],
    triggerPulse: () => {},
    selectSolution: () => {},
    dispose: () => {}
  };

  (window as any).agencyLanding3D = state;

  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function initDigitalWorkflow3D(): void {
    const canvas = document.getElementById('bg-canvas-3d') as HTMLCanvasElement | null;
    if (!canvas) return;

    if (typeof THREE === 'undefined') {
      console.warn('[OSAI 3D] Three.js library not loaded yet.');
      return;
    }
    state.threeLoaded = true;

    // 1. Scene & Atmosphere Setup
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x05070d, 0.0007);
    state.scene = scene;

    const aspect = window.innerWidth / window.innerHeight;
    const camera = new THREE.PerspectiveCamera(45, aspect, 1, 3000);
    camera.position.set(0, 0, 840);
    camera.lookAt(0, 0, 0);
    state.camera = camera;

    // 2. WebGL Renderer
    let renderer: any;
    try {
      renderer = new THREE.WebGLRenderer({
        canvas: canvas,
        alpha: true,
        antialias: window.devicePixelRatio < 2,
        powerPreference: 'high-performance',
        precision: 'mediump'
      });
      renderer.setSize(window.innerWidth, window.innerHeight);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.2;
      state.renderer = renderer;
    } catch (err) {
      console.error('[OSAI 3D] Failed to create WebGL context:', err);
      return;
    }

    // 3. Dynamic Technical Lighting
    const ambientLight = new THREE.AmbientLight(0x0b1324, 2.4);
    scene.add(ambientLight);

    const primaryLight = new THREE.DirectionalLight(0x00d4ef, 2.2);
    primaryLight.position.set(300, 400, 500);
    scene.add(primaryLight);

    const secondaryLight = new THREE.DirectionalLight(0x10b981, 1.6);
    secondaryLight.position.set(-350, -250, 400);
    scene.add(secondaryLight);

    const coreLight = new THREE.PointLight(0x00d4ef, 3.8, 850);
    coreLight.position.set(0, 20, 40);
    scene.add(coreLight);

    // =========================================================================
    // 4. ENTITY 1: CUSTOMER INGRESS TERMINAL (Inbound Call / Web Message)
    // =========================================================================
    const ingressGroup = new THREE.Group();
    ingressGroup.position.set(-340, 110, -40);
    scene.add(ingressGroup);

    // Ingress Device Slab (Sleek Phone/Terminal tablet)
    const tabletGeo = new THREE.BoxGeometry(46, 68, 8);
    const tabletMat = new THREE.MeshStandardMaterial({
      color: 0x09101d,
      emissive: 0x00d4ef,
      emissiveIntensity: 0.35,
      metalness: 0.9,
      roughness: 0.2,
      wireframe: false
    });
    const tablet = new THREE.Mesh(tabletGeo, tabletMat);
    ingressGroup.add(tablet);

    // Screen Wireframe & Outline
    const screenGeo = new THREE.BoxGeometry(40, 60, 8.5);
    const screenMat = new THREE.MeshBasicMaterial({
      color: 0x00d4ef,
      wireframe: true,
      transparent: true,
      opacity: 0.5
    });
    const screenMesh = new THREE.Mesh(screenGeo, screenMat);
    ingressGroup.add(screenMesh);

    // Expanding Radio / Signal Transmission Rings
    const signalWaveGroup = new THREE.Group();
    ingressGroup.add(signalWaveGroup);

    const signalRings: any[] = [];
    for (let r = 0; r < 3; r++) {
      const ringGeo = new THREE.RingGeometry(25 + r * 14, 26 + r * 14, 32);
      const ringMat = new THREE.MeshBasicMaterial({
        color: 0x00d4ef,
        transparent: true,
        opacity: 0.35 - r * 0.1,
        side: THREE.DoubleSide
      });
      const ring = new THREE.Mesh(ringGeo, ringMat);
      ring.rotation.x = Math.PI / 2;
      signalWaveGroup.add(ring);
      signalRings.push(ring);
    }

    // Ingress Beacon
    const ingressBeaconGeo = new THREE.SphereGeometry(4.5, 16, 16);
    const ingressBeaconMat = new THREE.MeshBasicMaterial({ color: 0x00d4ef, transparent: true, opacity: 0.9 });
    const ingressBeacon = new THREE.Mesh(ingressBeaconGeo, ingressBeaconMat);
    ingressBeacon.position.set(0, 38, 0);
    ingressGroup.add(ingressBeacon);

    // =========================================================================
    // 5. ENTITY 2: CENTRAL AI PROCESSING & QUALIFICATION MATRIX
    // =========================================================================
    const aiMatrixGroup = new THREE.Group();
    aiMatrixGroup.position.set(0, 20, 0);
    scene.add(aiMatrixGroup);

    // Core Processor Prism (Dual Hexagonal Matrix Plate)
    const procGeo = new THREE.CylinderGeometry(44, 44, 14, 6);
    const procMat = new THREE.MeshStandardMaterial({
      color: 0x071120,
      emissive: 0x00d4ef,
      emissiveIntensity: 0.6,
      metalness: 0.95,
      roughness: 0.15,
      flatShading: true
    });
    const procMesh = new THREE.Mesh(procGeo, procMat);
    procMesh.rotation.x = Math.PI / 6;
    aiMatrixGroup.add(procMesh);

    // Outer Diagnostic Scanner Cage
    const procCageGeo = new THREE.CylinderGeometry(54, 54, 18, 6);
    const procCageMat = new THREE.MeshBasicMaterial({
      color: 0x00d4ef,
      wireframe: true,
      transparent: true,
      opacity: 0.45
    });
    const procCage = new THREE.Mesh(procCageGeo, procCageMat);
    procCage.rotation.x = Math.PI / 6;
    aiMatrixGroup.add(procCage);

    // Rotating Neural Reasoning Orbit Rings
    const orbitRing1Geo = new THREE.TorusGeometry(75, 0.8, 12, 64);
    const orbitRing1Mat = new THREE.MeshBasicMaterial({ color: 0x00d4ef, transparent: true, opacity: 0.4 });
    const orbitRing1 = new THREE.Mesh(orbitRing1Geo, orbitRing1Mat);
    orbitRing1.rotation.x = Math.PI / 3;
    aiMatrixGroup.add(orbitRing1);

    const orbitRing2Geo = new THREE.TorusGeometry(98, 0.7, 12, 64);
    const orbitRing2Mat = new THREE.MeshBasicMaterial({ color: 0x10b981, transparent: true, opacity: 0.35 });
    const orbitRing2 = new THREE.Mesh(orbitRing2Geo, orbitRing2Mat);
    orbitRing2.rotation.y = Math.PI / 4;
    orbitRing2.rotation.z = Math.PI / 5;
    aiMatrixGroup.add(orbitRing2);

    // Matrix Central Pulsar
    const pulsarGeo = new THREE.OctahedronGeometry(16, 0);
    const pulsarMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8, wireframe: true });
    const pulsar = new THREE.Mesh(pulsarGeo, pulsarMat);
    aiMatrixGroup.add(pulsar);

    // =========================================================================
    // 6. ENTITY 3: THREE BUSINESS OUTCOME TERMINALS
    // =========================================================================
    const nodesGroup = new THREE.Group();
    scene.add(nodesGroup);

    const businessNodes: Record<string, BusinessNode> = {};

    // 6A. Calendar Appointment Terminal (Green)
    const calGroup = new THREE.Group();
    calGroup.position.set(340, 160, -20);
    nodesGroup.add(calGroup);

    const calSlabGeo = new THREE.BoxGeometry(42, 42, 10);
    const calSlabMat = new THREE.MeshStandardMaterial({
      color: 0x081a14,
      emissive: 0x10b981,
      emissiveIntensity: 0.55,
      metalness: 0.85,
      roughness: 0.25,
      flatShading: true
    });
    const calSlab = new THREE.Mesh(calSlabGeo, calSlabMat);
    calGroup.add(calSlab);

    const calWireGeo = new THREE.BoxGeometry(46, 46, 12);
    const calWireMat = new THREE.MeshBasicMaterial({ color: 0x10b981, wireframe: true, transparent: true, opacity: 0.5 });
    const calWire = new THREE.Mesh(calWireGeo, calWireMat);
    calGroup.add(calWire);

    const calBeaconGeo = new THREE.SphereGeometry(5, 16, 16);
    const calBeaconMat = new THREE.MeshBasicMaterial({ color: 0x10b981, transparent: true, opacity: 0.95 });
    const calBeacon = new THREE.Mesh(calBeaconGeo, calBeaconMat);
    calBeacon.position.set(0, 28, 0);
    calGroup.add(calBeacon);

    businessNodes['CALENDAR'] = {
      id: 'CALENDAR',
      name: 'Calendar Appointment',
      group: calGroup,
      mesh: calSlab,
      beacon: calBeacon,
      halo: calWire,
      baseScale: 1,
      targetScale: 1,
      pos: [340, 160, -20],
      color: 0x10b981
    };

    // 6B. CRM & Lead Record Terminal (Cyan / Violet)
    const crmGroup = new THREE.Group();
    crmGroup.position.set(380, -10, 0);
    nodesGroup.add(crmGroup);

    const crmTowerGeo = new THREE.BoxGeometry(36, 64, 12);
    const crmTowerMat = new THREE.MeshStandardMaterial({
      color: 0x0a1424,
      emissive: 0x00d4ef,
      emissiveIntensity: 0.5,
      metalness: 0.9,
      roughness: 0.2
    });
    const crmTower = new THREE.Mesh(crmTowerGeo, crmTowerMat);
    crmGroup.add(crmTower);

    const crmWireGeo = new THREE.BoxGeometry(40, 68, 14);
    const crmWireMat = new THREE.MeshBasicMaterial({ color: 0x00d4ef, wireframe: true, transparent: true, opacity: 0.45 });
    const crmWire = new THREE.Mesh(crmWireGeo, crmWireMat);
    crmGroup.add(crmWire);

    const crmBeaconGeo = new THREE.SphereGeometry(5, 16, 16);
    const crmBeaconMat = new THREE.MeshBasicMaterial({ color: 0x00d4ef, transparent: true, opacity: 0.95 });
    const crmBeacon = new THREE.Mesh(crmBeaconGeo, crmBeaconMat);
    crmBeacon.position.set(0, 40, 0);
    crmGroup.add(crmBeacon);

    businessNodes['CRM'] = {
      id: 'CRM',
      name: 'CRM Deal Pipeline',
      group: crmGroup,
      mesh: crmTower,
      beacon: crmBeacon,
      halo: crmWire,
      baseScale: 1,
      targetScale: 1,
      pos: [380, -10, 0],
      color: 0x00d4ef
    };

    // 6C. Multi-Channel Dispatch Terminal (Amber / Emerald)
    const dispatchGroup = new THREE.Group();
    dispatchGroup.position.set(330, -180, -30);
    nodesGroup.add(dispatchGroup);

    const dispatchGeo = new THREE.OctahedronGeometry(22, 0);
    const dispatchMat = new THREE.MeshStandardMaterial({
      color: 0x181005,
      emissive: 0xf59e0b,
      emissiveIntensity: 0.6,
      metalness: 0.85,
      roughness: 0.2,
      flatShading: true
    });
    const dispatchMesh = new THREE.Mesh(dispatchGeo, dispatchMat);
    dispatchGroup.add(dispatchMesh);

    const dispatchHaloGeo = new THREE.OctahedronGeometry(28, 0);
    const dispatchHaloMat = new THREE.MeshBasicMaterial({ color: 0xf59e0b, wireframe: true, transparent: true, opacity: 0.45 });
    const dispatchHalo = new THREE.Mesh(dispatchHaloGeo, dispatchHaloMat);
    dispatchGroup.add(dispatchHalo);

    const dispatchBeaconGeo = new THREE.SphereGeometry(5, 16, 16);
    const dispatchBeaconMat = new THREE.MeshBasicMaterial({ color: 0xf59e0b, transparent: true, opacity: 0.95 });
    const dispatchBeacon = new THREE.Mesh(dispatchBeaconGeo, dispatchBeaconMat);
    dispatchBeacon.position.set(0, 30, 0);
    dispatchGroup.add(dispatchBeacon);

    businessNodes['DISPATCH'] = {
      id: 'DISPATCH',
      name: 'Instant Dispatch',
      group: dispatchGroup,
      mesh: dispatchMesh,
      beacon: dispatchBeacon,
      halo: dispatchHalo,
      baseScale: 1,
      targetScale: 1,
      pos: [330, -180, -30],
      color: 0xf59e0b
    };

    state.nodes = businessNodes;

    // =========================================================================
    // 7. CONDUITS & FLOWING PHOTON PACKETS
    // =========================================================================
    const conduitsGroup = new THREE.Group();
    scene.add(conduitsGroup);
    const conduits: ConduitData[] = [];

    const conduitConfigs = [
      // Ingress -> AI Matrix
      { id: 'INGRESS_TO_AI', start: ingressGroup.position, end: aiMatrixGroup.position, color: 0x00d4ef },
      // AI Matrix -> Calendar
      { id: 'AI_TO_CALENDAR', start: aiMatrixGroup.position, end: calGroup.position, color: 0x10b981 },
      // AI Matrix -> CRM
      { id: 'AI_TO_CRM', start: aiMatrixGroup.position, end: crmGroup.position, color: 0x00d4ef },
      // AI Matrix -> Dispatch
      { id: 'AI_TO_DISPATCH', start: aiMatrixGroup.position, end: dispatchGroup.position, color: 0xf59e0b }
    ];

    conduitConfigs.forEach(cfg => {
      const start = new THREE.Vector3().copy(cfg.start);
      const end = new THREE.Vector3().copy(cfg.end);
      const mid = new THREE.Vector3(
        (start.x + end.x) * 0.5 + (Math.random() - 0.5) * 30,
        (start.y + end.y) * 0.5 + 40,
        (start.z + end.z) * 0.5 + 20
      );

      const curve = new THREE.CatmullRomCurve3([start, mid, end]);
      const tubeGeo = new THREE.TubeGeometry(curve, 32, 1.4, 8, false);
      const tubeMat = new THREE.MeshBasicMaterial({
        color: cfg.color,
        transparent: true,
        opacity: 0.28,
        wireframe: true
      });
      const tubeMesh = new THREE.Mesh(tubeGeo, tubeMat);
      conduitsGroup.add(tubeMesh);

      // Traveling Photon Packets
      const pulseParticles: any[] = [];
      const packetCount = 4;
      const packetGeo = new THREE.SphereGeometry(2.6, 8, 8);
      const packetMat = new THREE.MeshBasicMaterial({
        color: cfg.color,
        transparent: true,
        opacity: 0.95
      });

      for (let i = 0; i < packetCount; i++) {
        const pMesh = new THREE.Mesh(packetGeo, packetMat);
        conduitsGroup.add(pMesh);
        pulseParticles.push({
          mesh: pMesh,
          progress: i / packetCount,
          speed: 0.004 + Math.random() * 0.002
        });
      }

      conduits.push({
        id: cfg.id,
        curve,
        mesh: tubeMesh,
        pulseParticles,
        startPos: start,
        endPos: end
      });
    });

    state.conduits = conduits;

    // =========================================================================
    // 8. AMBIENT TELEMETRY PARTICLE GRID
    // =========================================================================
    const particleCount = 420;
    const particleGeo = new THREE.BufferGeometry();
    const particlePositions = new Float32Array(particleCount * 3);
    const particleColors = new Float32Array(particleCount * 3);

    for (let i = 0; i < particleCount; i++) {
      const idx = i * 3;
      particlePositions[idx] = (Math.random() - 0.5) * 1500;
      particlePositions[idx + 1] = (Math.random() - 0.5) * 1400;
      particlePositions[idx + 2] = (Math.random() - 0.5) * 1000 - 80;

      const isCyan = Math.random() > 0.45;
      particleColors[idx] = isCyan ? 0.0 : 0.06;
      particleColors[idx + 1] = isCyan ? 0.83 : 0.72;
      particleColors[idx + 2] = isCyan ? 0.94 : 0.5;
    }

    particleGeo.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3));
    particleGeo.setAttribute('color', new THREE.BufferAttribute(particleColors, 3));

    const particleMat = new THREE.PointsMaterial({
      size: 3.2,
      vertexColors: true,
      transparent: true,
      opacity: 0.5
    });
    const particleField = new THREE.Points(particleGeo, particleMat);
    scene.add(particleField);

    // =========================================================================
    // 9. INTERACTIVE SIMULATOR & SOLUTION SELECTOR
    // =========================================================================
    const workflows: Record<string, WorkflowDefinition> = {
      missed_call: {
        key: 'missed_call',
        name: 'Missed Call Recovery',
        terminals: ['CALENDAR', 'DISPATCH'],
        color: 0x00d4ef,
        accentHex: '#00d4ef'
      },
      web_enquiry: {
        key: 'web_enquiry',
        name: 'Web Enquiry Conversion',
        terminals: ['CRM', 'CALENDAR'],
        color: 0x38bdf8,
        accentHex: '#38bdf8'
      },
      lead_form: {
        key: 'lead_form',
        name: 'Lead Generation & Qualification',
        terminals: ['CRM', 'DISPATCH', 'CALENDAR'],
        color: 0x10b981,
        accentHex: '#10b981'
      },
      support_request: {
        key: 'support_request',
        name: '24/7 Customer Support',
        terminals: ['DISPATCH', 'CRM'],
        color: 0xf59e0b,
        accentHex: '#f59e0b'
      }
    };

    function triggerPulse(workflowKey: string): void {
      state.activeWorkflow = workflowKey;
      const wf = workflows[workflowKey] || workflows.missed_call;

      // Ingress flare
      ingressBeacon.scale.set(2, 2, 2);
      tablet.material.emissiveIntensity = 0.9;

      // Core processor surge
      coreLight.intensity = 6.5;
      procMesh.material.emissiveIntensity = 1.1;

      // Target node highlights
      Object.keys(businessNodes).forEach(k => {
        const node = businessNodes[k];
        const isTarget = wf.terminals.includes(k);
        if (isTarget) {
          node.targetScale = 1.45;
          node.mesh.material.emissiveIntensity = 1.0;
          node.halo.material.opacity = 0.85;
          node.beacon.scale.set(1.8, 1.8, 1.8);
        } else {
          node.targetScale = 0.85;
          node.mesh.material.emissiveIntensity = 0.25;
          node.halo.material.opacity = 0.2;
          node.beacon.scale.set(0.9, 0.9, 0.9);
        }
      });

      // Accelerate conduits
      conduits.forEach(c => {
        c.mesh.material.opacity = 0.75;
        c.pulseParticles.forEach(p => {
          p.speed = 0.016;
        });
      });

      // Settle back to equilibrium
      setTimeout(() => {
        ingressBeacon.scale.set(1, 1, 1);
        tablet.material.emissiveIntensity = 0.35;
        coreLight.intensity = 3.8;
        procMesh.material.emissiveIntensity = 0.6;

        Object.keys(businessNodes).forEach(k => {
          const node = businessNodes[k];
          node.targetScale = 1.0;
          node.mesh.material.emissiveIntensity = 0.55;
          node.halo.material.opacity = 0.45;
          node.beacon.scale.set(1, 1, 1);
        });

        conduits.forEach(c => {
          c.mesh.material.opacity = 0.28;
          c.pulseParticles.forEach(p => {
            p.speed = 0.004 + Math.random() * 0.002;
          });
        });
      }, 1600);
    }

    state.triggerPulse = triggerPulse;
    state.selectSolution = triggerPulse;
    (window as any).triggerLanding3DPulse = triggerPulse;

    // =========================================================================
    // 10. GSAP SCROLL CHOREOGRAPHY
    // =========================================================================
    let camTargetPos = { x: 0, y: 0, z: 840 };
    let camLookTarget = { x: 0, y: 0, z: 0 };

    if (typeof gsap !== 'undefined' && typeof ScrollTrigger !== 'undefined') {
      state.gsapLoaded = true;
      gsap.registerPlugin(ScrollTrigger);

      ScrollTrigger.create({
        start: 'top top',
        end: 'bottom bottom',
        onUpdate: (self: any) => {
          state.scrollProgress = self.progress;
        }
      });

      const sectionPositions = [
        { trigger: '#hero', cam: { x: 0, y: 0, z: 840 }, look: { x: 0, y: 0, z: 0 } },
        { trigger: '#solutions', cam: { x: 40, y: 30, z: 740 }, look: { x: 20, y: 10, z: 0 } },
        { trigger: '#how-it-works', cam: { x: -60, y: -20, z: 720 }, look: { x: -20, y: -10, z: 0 } },
        { trigger: '#services', cam: { x: 80, y: -40, z: 680 }, look: { x: 30, y: -20, z: 0 } },
        { trigger: '#industries', cam: { x: -40, y: -60, z: 660 }, look: { x: -20, y: -30, z: 0 } },
        { trigger: '#contact', cam: { x: 0, y: 0, z: 860 }, look: { x: 0, y: 0, z: 0 } }
      ];

      sectionPositions.forEach(sp => {
        const el = document.querySelector(sp.trigger);
        if (el) {
          ScrollTrigger.create({
            trigger: el,
            start: 'top 75%',
            end: 'bottom 25%',
            onEnter: () => {
              gsap.to(camTargetPos, { ...sp.cam, duration: 1.6, ease: 'power2.out' });
              gsap.to(camLookTarget, { ...sp.look, duration: 1.6, ease: 'power2.out' });
            },
            onEnterBack: () => {
              gsap.to(camTargetPos, { ...sp.cam, duration: 1.6, ease: 'power2.out' });
              gsap.to(camLookTarget, { ...sp.look, duration: 1.6, ease: 'power2.out' });
            }
          });
        }
      });
    }

    // =========================================================================
    // 11. MOUSE PARALLAX & RESIZING
    // =========================================================================
    let mouseX = 0;
    let mouseY = 0;
    let targetMouseX = 0;
    let targetMouseY = 0;

    if (!prefersReducedMotion) {
      window.addEventListener('mousemove', (e: MouseEvent) => {
        targetMouseX = (e.clientX / window.innerWidth - 0.5) * 50;
        targetMouseY = (e.clientY / window.innerHeight - 0.5) * -50;
      }, { passive: true });
    }

    function handleResize(): void {
      if (!camera || !renderer) return;
      const width = window.innerWidth;
      const height = window.innerHeight;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    }

    window.addEventListener('resize', handleResize, { passive: true });

    // =========================================================================
    // 12. 60FPS RAF RENDER LOOP
    // =========================================================================
    let animId: number;
    let isHidden = false;

    document.addEventListener('visibilitychange', () => {
      isHidden = document.hidden;
    });

    const clock = new THREE.Clock();

    function renderLoop(): void {
      animId = requestAnimationFrame(renderLoop);
      state.frameCount++;

      if (isHidden) return;

      const elapsed = clock.getElapsedTime();

      // Mouse lerp
      mouseX += (targetMouseX - mouseX) * 0.05;
      mouseY += (targetMouseY - mouseY) * 0.05;

      // Smooth camera motion
      camera.position.x = camTargetPos.x + mouseX;
      camera.position.y = camTargetPos.y + mouseY;
      camera.position.z += (camTargetPos.z - camera.position.z) * 0.06;
      camera.lookAt(camLookTarget.x, camLookTarget.y, camLookTarget.z);

      // Ingress tablet floating & signal pulses
      ingressGroup.position.y = 110 + Math.sin(elapsed * 1.6) * 6;
      ingressGroup.rotation.y = Math.sin(elapsed * 0.8) * 0.1;

      signalRings.forEach((ring, idx) => {
        const scaleVal = 1 + (Math.sin(elapsed * 2.5 + idx * 0.8) * 0.15);
        ring.scale.set(scaleVal, scaleVal, scaleVal);
      });

      // AI Reasoning Matrix rotation & oscillation
      aiMatrixGroup.rotation.y = elapsed * 0.25;
      aiMatrixGroup.rotation.z = Math.sin(elapsed * 0.3) * 0.08;
      orbitRing1.rotation.z = elapsed * 0.38;
      orbitRing2.rotation.x = -elapsed * 0.25;
      pulsar.rotation.y = -elapsed * 0.5;

      // Business Outcome Nodes bobbing & scale lerp
      Object.keys(businessNodes).forEach((k, idx) => {
        const node = businessNodes[k];
        node.group.position.y = node.pos[1] + Math.sin(elapsed * 1.8 + idx * 1.2) * 6;
        node.mesh.rotation.y = elapsed * 0.35 + idx;
        node.halo.rotation.z = -elapsed * 0.25;

        node.baseScale += (node.targetScale - node.baseScale) * 0.08;
        node.group.scale.set(node.baseScale, node.baseScale, node.baseScale);
      });

      // Flowing conduit photon particles
      conduits.forEach(conduit => {
        conduit.pulseParticles.forEach(p => {
          p.progress += p.speed;
          if (p.progress > 1) p.progress = 0;
          const pos = conduit.curve.getPoint(p.progress);
          p.mesh.position.copy(pos);
        });
      });

      // Ambient dust rotation
      particleField.rotation.y = elapsed * 0.018;

      renderer.render(scene, camera);
    }

    renderLoop();
    state.initialized = true;

    // Cleanup hook
    state.dispose = function () {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', handleResize);
      renderer.dispose();
    };
  }

  // Boot on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDigitalWorkflow3D);
  } else {
    initDigitalWorkflow3D();
  }
})();
