// ============================================================================
// AUTOMATED AGENCY OS — 3D SPATIAL COMMAND HUD ENGINE
// ============================================================================

declare const THREE: any;
declare const gsap: any;
declare const ScrollTrigger: any;

interface Agency3DState {
  initialized: boolean;
  scene: any;
  camera: any;
  renderer: any;
  nodesGroup: any;
  coreMesh: any;
  ringsGroup: any;
}

(function initAgencyLanding3D() {
  if (typeof window === 'undefined') return;

  const canvas = document.getElementById('bg-canvas-3d') as HTMLCanvasElement;
  if (!canvas || typeof THREE === 'undefined') {
    (window as any).agencyLanding3D = { initialized: false };
    return;
  }

  // Set up Scene, Camera, Renderer
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.1, 1000);
  camera.position.set(0, 0, 45);

  let renderer: any;
  try {
    renderer = new THREE.WebGLRenderer({
      canvas: canvas,
      alpha: true,
      antialias: true,
      powerPreference: 'high-performance'
    });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  } catch (e) {
    console.warn("WebGL initialization failed:", e);
    (window as any).agencyLanding3D = { initialized: false };
    return;
  }

  // 1. Ambient & Directional Lights
  const ambientLight = new THREE.AmbientLight(0x0a1628, 2.5);
  scene.add(ambientLight);

  const cyanPoint = new THREE.PointLight(0x00d4ef, 3.5, 120);
  cyanPoint.position.set(20, 20, 30);
  scene.add(cyanPoint);

  const indigoPoint = new THREE.PointLight(0x38bdf8, 2.8, 100);
  indigoPoint.position.set(-25, -15, 20);
  scene.add(indigoPoint);

  // 2. Spatial Constellation Nodes (Connected Agency Graph)
  const nodesGroup = new THREE.Group();
  scene.add(nodesGroup);

  const particleCount = 200;
  const particleGeometry = new THREE.BufferGeometry();
  const positions = new Float32Array(particleCount * 3);
  const colors = new Float32Array(particleCount * 3);

  const cyanColor = new THREE.Color(0x00d4ef);
  const blueColor = new THREE.Color(0x38bdf8);
  const whiteColor = new THREE.Color(0xffffff);

  for (let i = 0; i < particleCount; i++) {
    const x = (Math.random() - 0.5) * 90;
    const y = (Math.random() - 0.5) * 70;
    const z = (Math.random() - 0.5) * 50;

    positions[i * 3] = x;
    positions[i * 3 + 1] = y;
    positions[i * 3 + 2] = z;

    const chosen = Math.random() > 0.6 ? cyanColor : (Math.random() > 0.4 ? blueColor : whiteColor);
    colors[i * 3] = chosen.r;
    colors[i * 3 + 1] = chosen.g;
    colors[i * 3 + 2] = chosen.b;
  }

  particleGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  particleGeometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

  const particleMaterial = new THREE.PointsMaterial({
    size: 0.6,
    vertexColors: true,
    transparent: true,
    opacity: 0.75,
    blending: THREE.AdditiveBlending
  });

  const particleSystem = new THREE.Points(particleGeometry, particleMaterial);
  nodesGroup.add(particleSystem);

  // 3. Central Autonomous Operating System Core
  const coreGroup = new THREE.Group();
  coreGroup.position.set(16, 2, 0); // Aligns with hero right side
  scene.add(coreGroup);

  // Core Icosahedron Wireframe
  const coreGeo = new THREE.IcosahedronGeometry(7.5, 1);
  const coreWireMat = new THREE.MeshBasicMaterial({
    color: 0x00d4ef,
    wireframe: true,
    transparent: true,
    opacity: 0.35
  });
  const coreWire = new THREE.Mesh(coreGeo, coreWireMat);
  coreGroup.add(coreWire);

  // Core Solid Facet
  const coreSolidMat = new THREE.MeshStandardMaterial({
    color: 0x061426,
    metalness: 0.85,
    roughness: 0.25,
    transparent: true,
    opacity: 0.75
  });
  const coreSolid = new THREE.Mesh(coreGeo, coreSolidMat);
  coreGroup.add(coreSolid);

  // Orbital Energy Rings
  const ringsGroup = new THREE.Group();
  coreGroup.add(ringsGroup);

  const ringGeo1 = new THREE.TorusGeometry(11, 0.08, 16, 100);
  const ringMat1 = new THREE.MeshBasicMaterial({ color: 0x00d4ef, transparent: true, opacity: 0.6 });
  const ring1 = new THREE.Mesh(ringGeo1, ringMat1);
  ring1.rotation.x = Math.PI / 3;
  ringsGroup.add(ring1);

  const ringGeo2 = new THREE.TorusGeometry(13.5, 0.06, 16, 100);
  const ringMat2 = new THREE.MeshBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.4 });
  const ring2 = new THREE.Mesh(ringGeo2, ringMat2);
  ring2.rotation.y = Math.PI / 4;
  ringsGroup.add(ring2);

  // Floating Micro Satellite Nodes
  const satGroup = new THREE.Group();
  coreGroup.add(satGroup);

  const satGeo = new THREE.OctahedronGeometry(1.2, 0);
  const satMat = new THREE.MeshBasicMaterial({ color: 0x10b981, wireframe: true });
  
  const sat1 = new THREE.Mesh(satGeo, satMat);
  sat1.position.set(14, 4, 2);
  satGroup.add(sat1);

  const sat2 = new THREE.Mesh(satGeo, new THREE.MeshBasicMaterial({ color: 0xf59e0b, wireframe: true }));
  sat2.position.set(-13, -5, -4);
  satGroup.add(sat2);

  // Resize handler
  function onWindowResize() {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    // Responsive position adjustments
    if (window.innerWidth < 1024) {
      coreGroup.position.set(0, 10, -10);
    } else {
      coreGroup.position.set(16, 2, 0);
    }
  }
  window.addEventListener('resize', onWindowResize);
  onWindowResize();

  // GSAP ScrollTrigger Camera Path & Stage Transformations
  if (typeof gsap !== 'undefined' && typeof ScrollTrigger !== 'undefined') {
    gsap.registerPlugin(ScrollTrigger);

    // Section 2 Hero -> Section 3 Problem
    gsap.to(coreGroup.position, {
      scrollTrigger: {
        trigger: '#how-it-works',
        start: 'top bottom',
        end: 'center center',
        scrub: 1.2
      },
      x: -18,
      y: -4,
      z: -12
    });

    // Section 4 The Engine
    gsap.to(coreGroup.position, {
      scrollTrigger: {
        trigger: '#engine',
        start: 'top bottom',
        end: 'center center',
        scrub: 1.2
      },
      x: 0,
      y: 0,
      z: -5
    });

    // Section 8 Revenue Loop
    gsap.to(coreGroup.rotation, {
      scrollTrigger: {
        trigger: '#revenue-loop',
        start: 'top bottom',
        end: 'bottom top',
        scrub: 1
      },
      y: Math.PI * 4
    });

    // Section 13 Final CTA
    gsap.to(coreGroup.position, {
      scrollTrigger: {
        trigger: '#contact',
        start: 'top bottom',
        end: 'center center',
        scrub: 1.2
      },
      x: 0,
      y: -12,
      z: 5
    });
  }

  // Animation Loop
  let reqId: number;
  let clock = new THREE.Clock();

  function animate() {
    reqId = requestAnimationFrame(animate);

    const delta = clock.getDelta();
    const elapsed = clock.getElapsedTime();

    // Constant subtle rotations
    coreWire.rotation.x += delta * 0.18;
    coreWire.rotation.y += delta * 0.22;
    coreSolid.rotation.x -= delta * 0.12;
    coreSolid.rotation.y -= delta * 0.15;

    ring1.rotation.z += delta * 0.25;
    ring2.rotation.x += delta * 0.2;

    satGroup.rotation.y += delta * 0.35;

    // Gentle node field drift
    nodesGroup.rotation.y = Math.sin(elapsed * 0.08) * 0.15;
    nodesGroup.rotation.x = Math.cos(elapsed * 0.06) * 0.08;

    renderer.render(scene, camera);
  }
  animate();

  // Export Global State for Tests & Validation
  const state: Agency3DState = {
    initialized: true,
    scene: scene,
    camera: camera,
    renderer: renderer,
    nodesGroup: nodesGroup,
    coreMesh: coreWire,
    ringsGroup: ringsGroup
  };
  (window as any).agencyLanding3D = state;
})();
