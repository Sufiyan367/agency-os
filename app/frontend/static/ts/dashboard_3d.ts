/**
 * Agency OS: Mission Control CEO Dashboard — 3D Tactical Core Engine
 * Language: TypeScript
 * Description: Real Three.js WebGL tactical core representing live operational state,
 *              dynamic module focus, and zero fabricated telemetry.
 */

declare const THREE: any;

export interface SubsystemNodeDef {
  id: string;
  name: string;
  pos: [number, number, number];
  color: number;
  views: string[];
}

export interface DashboardConduitData {
  id: string;
  curve: any;
  mesh: any;
  pulseParticles: any[];
}

export interface Dashboard3DState {
  initialized: boolean;
  threeLoaded: boolean;
  frameCount: number;
  activeSubsystem: string | null;
  camera: any;
  scene: any;
  renderer: any;
  subsystems: Record<string, any>;
  conduits: DashboardConduitData[];
  highlightSubsystem: (subsystemId: string | null) => void;
  triggerEventAnimation: (eventType: string) => void;
  dispose: () => void;
}

declare global {
  interface Window {
    agencyDashboard3D: Dashboard3DState;
    navToView?: (viewName: string) => void;
  }
}

(function () {
  'use strict';

  const state: Dashboard3DState = {
    initialized: false,
    threeLoaded: false,
    frameCount: 0,
    activeSubsystem: null,
    camera: null,
    scene: null,
    renderer: null,
    subsystems: {},
    conduits: [],
    highlightSubsystem: () => {},
    triggerEventAnimation: () => {},
    dispose: () => {}
  };

  window.agencyDashboard3D = state;

  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function initDashboard3DCore(): void {
    const canvas = document.getElementById('dashboard-3d-canvas') as HTMLCanvasElement | null;
    const stage = document.getElementById('ceo-core-stage');
    if (!canvas || !stage) return;

    if (typeof THREE === 'undefined') {
      console.warn('[AgencyOS Dashboard 3D] Three.js vendor library not ready.');
      return;
    }
    state.threeLoaded = true;

    // 1. Scene & Camera Setup
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x06090e, 0.003);
    state.scene = scene;

    const width = stage.clientWidth || 320;
    const height = stage.clientHeight || 240;
    const camera = new THREE.PerspectiveCamera(45, width / height, 1, 1000);
    const defaultCamPos = new THREE.Vector3(0, 8, 140);
    const defaultLookTarget = new THREE.Vector3(0, 0, 0);

    camera.position.copy(defaultCamPos);
    camera.lookAt(defaultLookTarget);
    state.camera = camera;

    // 2. WebGL Renderer
    let renderer: any;
    try {
      renderer = new THREE.WebGLRenderer({
        canvas: canvas,
        alpha: true,
        antialias: window.devicePixelRatio < 2,
        powerPreference: 'high-performance'
      });
      renderer.setSize(width, height);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.35;
      state.renderer = renderer;
    } catch (err) {
      console.error('[AgencyOS Dashboard 3D] Failed to acquire WebGL context:', err);
      return;
    }

    // 3. Command Lighting
    const ambientLight = new THREE.AmbientLight(0x0f172a, 2.5);
    scene.add(ambientLight);

    const keyLight = new THREE.DirectionalLight(0x00d4ef, 2.4);
    keyLight.position.set(60, 90, 80);
    scene.add(keyLight);

    const rimLight = new THREE.DirectionalLight(0x8b5cf6, 1.8);
    rimLight.position.set(-70, -60, 60);
    scene.add(rimLight);

    const corePointLight = new THREE.PointLight(0x00d4ef, 3.2, 200);
    corePointLight.position.set(0, 0, 0);
    scene.add(corePointLight);

    // 4. Central Faceted Dodecahedron Nucleus
    const coreGroup = new THREE.Group();
    scene.add(coreGroup);

    const nucleusGeo = new THREE.DodecahedronGeometry(13, 0);
    const nucleusMat = new THREE.MeshStandardMaterial({
      color: 0x070d18,
      emissive: 0x00d4ef,
      emissiveIntensity: 0.65,
      metalness: 0.9,
      roughness: 0.15,
      flatShading: true
    });
    const nucleusMesh = new THREE.Mesh(nucleusGeo, nucleusMat);
    coreGroup.add(nucleusMesh);

    // Inner wireframe highlights
    const edgesGeo = new THREE.EdgesGeometry(nucleusGeo);
    const edgesMat = new THREE.LineBasicMaterial({ color: 0x00d4ef, transparent: true, opacity: 0.75 });
    const edgesMesh = new THREE.LineSegments(edgesGeo, edgesMat);
    nucleusMesh.add(edgesMesh);

    // Dual Concentric Gyro Rings
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

    // 5. Seven Operational Subsystems Topology
    const subsystemDefs: SubsystemNodeDef[] = [
      { id: 'ACQUISITION', name: 'Acquisition', pos: [0, 44, 0], color: 0x00d4ef, views: ['global-acquisition', 'leads', 'prospects'] },
      { id: 'COMMUNICATION', name: 'Communication', pos: [-48, 10, -8], color: 0x38bdf8, views: ['queue', 'replies', 'campaigns'] },
      { id: 'SALES', name: 'Sales', pos: [48, 10, 8], color: 0x10b981, views: ['proposals', 'pipeline', 'deals'] },
      { id: 'PAYMENTS', name: 'Payment', pos: [-34, -32, 10], color: 0x8b5cf6, views: ['payments', 'billing', 'invoices'] },
      { id: 'DELIVERY', name: 'Delivery', pos: [34, -32, -10], color: 0x6366f1, views: ['client-intelligence', 'delivery', 'projects'] },
      { id: 'SUPPORT', name: 'Support', pos: [0, -44, 0], color: 0xf59e0b, views: ['support-ops', 'runs', 'logs'] },
      { id: 'INTELLIGENCE', name: 'Intelligence', pos: [0, 22, 34], color: 0xf43f5e, views: ['intelligence', 'decision-analytics', 'analytics', 'overview'] }
    ];

    const subsystems: Record<string, any> = {};
    const conduits: DashboardConduitData[] = [];

    const nodesGroup = new THREE.Group();
    scene.add(nodesGroup);

    const conduitsGroup = new THREE.Group();
    scene.add(conduitsGroup);

    subsystemDefs.forEach(def => {
      const subGroup = new THREE.Group();
      subGroup.position.set(def.pos[0], def.pos[1], def.pos[2]);

      // Subsystem Faceted Mesh
      const geo = new THREE.OctahedronGeometry(6.5, 0);
      const mat = new THREE.MeshStandardMaterial({
        color: 0x090f1d,
        emissive: def.color,
        emissiveIntensity: 0.45,
        metalness: 0.85,
        roughness: 0.25,
        flatShading: true
      });
      const mesh = new THREE.Mesh(geo, mat);
      subGroup.add(mesh);

      // Outer Ring Frame
      const ringGeo = new THREE.TorusGeometry(9, 0.4, 6, 24);
      const ringMat = new THREE.MeshBasicMaterial({ color: def.color, transparent: true, opacity: 0.35 });
      const ring = new THREE.Mesh(ringGeo, ringMat);
      subGroup.add(ring);

      // Pulsing Beacon
      const beaconGeo = new THREE.SphereGeometry(2, 8, 8);
      const beaconMat = new THREE.MeshBasicMaterial({ color: def.color, transparent: true, opacity: 0.8 });
      const beacon = new THREE.Mesh(beaconGeo, beaconMat);
      subGroup.add(beacon);

      nodesGroup.add(subGroup);

      // 3D Spline Conduit to Center
      const start = new THREE.Vector3(0, 0, 0);
      const end = new THREE.Vector3(def.pos[0], def.pos[1], def.pos[2]);
      const mid = new THREE.Vector3(
        (start.x + end.x) * 0.5,
        (start.y + end.y) * 0.5,
        (start.z + end.z) * 0.5 + 10
      );

      const curve = new THREE.CatmullRomCurve3([start, mid, end]);
      const tubeGeo = new THREE.TubeGeometry(curve, 20, 0.6, 6, false);
      const tubeMat = new THREE.MeshBasicMaterial({
        color: def.color,
        transparent: true,
        opacity: 0.3,
        wireframe: true
      });
      const tubeMesh = new THREE.Mesh(tubeGeo, tubeMat);
      conduitsGroup.add(tubeMesh);

      // Fast-moving photon packets
      const pulseParticles: any[] = [];
      const packetGeo = new THREE.SphereGeometry(1.2, 6, 6);
      const packetMat = new THREE.MeshBasicMaterial({ color: def.color, transparent: true, opacity: 0.95 });

      for (let p = 0; p < 2; p++) {
        const packet = new THREE.Mesh(packetGeo, packetMat);
        conduitsGroup.add(packet);
        pulseParticles.push({
          mesh: packet,
          progress: p * 0.5,
          speed: 0.006 + Math.random() * 0.003
        });
      }

      subsystems[def.id] = {
        def,
        group: subGroup,
        mesh,
        material: mat,
        ring,
        beacon,
        conduit: tubeMesh,
        pulseParticles,
        basePos: new THREE.Vector3(def.pos[0], def.pos[1], def.pos[2])
      };

      conduits.push({
        id: def.id,
        curve,
        mesh: tubeMesh,
        pulseParticles
      });
    });

    state.subsystems = subsystems;
    state.conduits = conduits;

    // 6. Camera Glide Target Coordinates
    const targetCamPos = new THREE.Vector3().copy(defaultCamPos);
    const targetLookTarget = new THREE.Vector3().copy(defaultLookTarget);

    // 7. Dynamic Module Focus Hook
    function highlightSubsystem(subsystemId: string | null): void {
      state.activeSubsystem = subsystemId;

      Object.keys(subsystems).forEach(id => {
        const sub = subsystems[id];
        const isTarget = id === subsystemId;

        if (isTarget) {
          sub.group.scale.set(1.4, 1.4, 1.4);
          sub.material.emissiveIntensity = 1.0;
          sub.beacon.material.opacity = 0.9;
          sub.conduit.material.opacity = 0.85;

          // Camera glide toward subsystem
          targetCamPos.set(sub.basePos.x * 0.45, sub.basePos.y * 0.45 + 5, 125);
          targetLookTarget.copy(sub.basePos).multiplyScalar(0.5);
        } else if (subsystemId) {
          sub.group.scale.set(0.9, 0.9, 0.9);
          sub.material.emissiveIntensity = 0.2;
          sub.beacon.material.opacity = 0.15;
          sub.conduit.material.opacity = 0.15;
        } else {
          sub.group.scale.set(1, 1, 1);
          sub.material.emissiveIntensity = 0.45;
          sub.beacon.material.opacity = 0.35;
          sub.conduit.material.opacity = 0.3;
          targetCamPos.copy(defaultCamPos);
          targetLookTarget.copy(defaultLookTarget);
        }
      });
    }

    state.highlightSubsystem = highlightSubsystem;

    // Hook cleanly into window.navToView
    const origNavToView = window.navToView;
    window.navToView = function (viewName: string) {
      if (typeof origNavToView === 'function') {
        origNavToView(viewName);
      }

      let matchedId: string | null = null;
      subsystemDefs.forEach(def => {
        if (def.views.includes(viewName)) {
          matchedId = def.id;
        }
      });

      highlightSubsystem(matchedId);
    };

    // 8. Event Animation Bridge
    state.triggerEventAnimation = function (eventType: string) {
      let targetId = 'INTELLIGENCE';
      if (eventType.includes('prospect') || eventType.includes('lead')) targetId = 'ACQUISITION';
      else if (eventType.includes('email') || eventType.includes('message')) targetId = 'COMMUNICATION';
      else if (eventType.includes('proposal') || eventType.includes('deal')) targetId = 'SALES';
      else if (eventType.includes('payment') || eventType.includes('invoice')) targetId = 'PAYMENTS';
      else if (eventType.includes('task') || eventType.includes('delivery')) targetId = 'DELIVERY';
      else if (eventType.includes('error') || eventType.includes('alert')) targetId = 'SUPPORT';

      const sub = subsystems[targetId];
      if (sub) {
        sub.pulseParticles.forEach((p: any) => { p.speed = 0.025; });
        setTimeout(() => {
          sub.pulseParticles.forEach((p: any) => { p.speed = 0.007; });
        }, 1200);
      }
    };

    // 9. Window Resize
    function handleResize(): void {
      if (!stage || !camera || !renderer) return;
      const w = stage.clientWidth || 320;
      const h = stage.clientHeight || 240;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    }

    window.addEventListener('resize', handleResize, { passive: true });

    // 10. RAF Loop with Smooth Damped Camera
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

      // Camera lerp
      camera.position.lerp(targetCamPos, 0.05);
      camera.lookAt(targetLookTarget);

      // Core rotation
      coreGroup.rotation.y = elapsed * 0.3;
      coreGroup.rotation.x = Math.sin(elapsed * 0.2) * 0.12;
      ring1.rotation.z = elapsed * 0.4;
      ring2.rotation.y = -elapsed * 0.3;

      // Animate subsystems
      subsystemDefs.forEach((def, idx) => {
        const sub = subsystems[def.id];
        if (sub) {
          sub.mesh.rotation.y = elapsed * 0.6 + idx;
          sub.mesh.rotation.x = elapsed * 0.4 + idx;
          sub.ring.rotation.z = -elapsed * 0.5;

          // Gentle bob
          if (!state.activeSubsystem) {
            sub.group.position.y = def.pos[1] + Math.sin(elapsed * 2 + idx) * 2;
          }
        }
      });

      // Animate photon pulses
      conduits.forEach(conduit => {
        conduit.pulseParticles.forEach(p => {
          p.progress += p.speed;
          if (p.progress > 1) p.progress = 0;
          const pos = conduit.curve.getPoint(p.progress);
          p.mesh.position.copy(pos);
        });
      });

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

  // Auto-boot
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDashboard3DCore);
  } else {
    initDashboard3DCore();
  }
})();
