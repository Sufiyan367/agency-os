"use strict";
/**
 * Agency OS: Autonomous Business Operating System — Cinematic 3D Engine
 * Language: TypeScript
 * Description: Real Three.js WebGL scene and GSAP ScrollTrigger narrative
 *              choreography for the public marketing experience.
 */
(function () {
    'use strict';
    // System State
    const state = {
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
        triggerPulse: () => { },
        dispose: () => { }
    };
    window.agencyLanding3D = state;
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    function initLanding3DEngine() {
        const canvas = document.getElementById('bg-canvas-3d');
        if (!canvas)
            return;
        if (typeof THREE === 'undefined') {
            console.warn('[AgencyOS 3D] Three.js vendor library not ready.');
            return;
        }
        state.threeLoaded = true;
        // 1. Scene & Camera Setup
        const scene = new THREE.Scene();
        scene.fog = new THREE.FogExp2(0x05070d, 0.00065);
        state.scene = scene;
        const aspect = window.innerWidth / window.innerHeight;
        const camera = new THREE.PerspectiveCamera(45, aspect, 1, 3000);
        camera.position.set(0, 0, 850);
        camera.lookAt(0, 0, 0);
        state.camera = camera;
        // 2. WebGL Renderer with High Precision & Smooth Shading
        let renderer;
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
            renderer.toneMappingExposure = 1.25;
            state.renderer = renderer;
        }
        catch (err) {
            console.error('[AgencyOS 3D] Failed to acquire WebGL context:', err);
            return;
        }
        // 3. Dynamic Lighting Architecture
        const ambientLight = new THREE.AmbientLight(0x0d1527, 2.2);
        scene.add(ambientLight);
        const primaryLight = new THREE.DirectionalLight(0x00d4ef, 2.0);
        primaryLight.position.set(300, 400, 500);
        scene.add(primaryLight);
        const secondaryLight = new THREE.DirectionalLight(0x8b5cf6, 1.4);
        secondaryLight.position.set(-400, -200, 300);
        scene.add(secondaryLight);
        const coreLight = new THREE.PointLight(0x00d4ef, 3.5, 900);
        coreLight.position.set(0, 0, 0);
        scene.add(coreLight);
        // 4. Central Kinetic Entity: AUTONOMOUS CORE
        const coreGroup = new THREE.Group();
        scene.add(coreGroup);
        // Faceted Geodesic Nucleus
        const nucleusGeo = new THREE.IcosahedronGeometry(36, 1);
        const nucleusMat = new THREE.MeshStandardMaterial({
            color: 0x050a14,
            emissive: 0x00d4ef,
            emissiveIntensity: 0.55,
            metalness: 0.9,
            roughness: 0.15,
            wireframe: false,
            flatShading: true
        });
        const nucleus = new THREE.Mesh(nucleusGeo, nucleusMat);
        coreGroup.add(nucleus);
        // Outer Armor Wireframe Cage
        const cageGeo = new THREE.IcosahedronGeometry(48, 1);
        const cageMat = new THREE.MeshBasicMaterial({
            color: 0x00d4ef,
            wireframe: true,
            transparent: true,
            opacity: 0.4
        });
        const cage = new THREE.Mesh(cageGeo, cageMat);
        coreGroup.add(cage);
        // 3 Concentric Gyro Rings
        const ring1Geo = new THREE.TorusGeometry(72, 0.75, 12, 64);
        const ring1Mat = new THREE.MeshBasicMaterial({ color: 0x00d4ef, transparent: true, opacity: 0.35 });
        const ring1 = new THREE.Mesh(ring1Geo, ring1Mat);
        ring1.rotation.x = Math.PI / 3;
        coreGroup.add(ring1);
        const ring2Geo = new THREE.TorusGeometry(95, 0.65, 12, 64);
        const ring2Mat = new THREE.MeshBasicMaterial({ color: 0x8b5cf6, transparent: true, opacity: 0.28 });
        const ring2 = new THREE.Mesh(ring2Geo, ring2Mat);
        ring2.rotation.y = Math.PI / 4;
        ring2.rotation.z = Math.PI / 6;
        coreGroup.add(ring2);
        const ring3Geo = new THREE.TorusGeometry(120, 0.55, 12, 64);
        const ring3Mat = new THREE.MeshBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.22 });
        const ring3 = new THREE.Mesh(ring3Geo, ring3Mat);
        ring3.rotation.x = -Math.PI / 4;
        coreGroup.add(ring3);
        // 5. Nine Conceptual System Nodes (Operating Constellation)
        const nodeDefs = [
            { id: 'DISCOVER', name: 'Discover', pos: [-340, 180, -60], color: 0x00d4ef, emissive: 0x00d4ef, description: 'Signal convergence & opportunity detection' },
            { id: 'AUDIT', name: 'Audit', pos: [340, 180, -60], color: 0x8b5cf6, emissive: 0x8b5cf6, description: 'Empirical multi-layer diagnostics' },
            { id: 'PERSUADE', name: 'Persuade', pos: [-400, 30, -30], color: 0x38bdf8, emissive: 0x38bdf8, description: 'Email, Chat, & Voice synthesis' },
            { id: 'SELL', name: 'Sell', pos: [400, 30, -30], color: 0x10b981, emissive: 0x10b981, description: 'Proposal generation & commercial close' },
            { id: 'PAY', name: 'Pay', pos: [-240, -140, 30], color: 0xa855f7, emissive: 0xa855f7, description: 'Automated invoice & settlement conduits' },
            { id: 'BUILD', name: 'Build', pos: [240, -140, 30], color: 0x2563eb, emissive: 0x2563eb, description: 'Production architecture assembly' },
            { id: 'DEPLOY', name: 'Deploy', pos: [-320, -280, 50], color: 0x6366f1, emissive: 0x6366f1, description: 'Edge containers & automated deployment' },
            { id: 'MAINTAIN', name: 'Maintain', pos: [0, -320, 60], color: 0xf59e0b, emissive: 0xf59e0b, description: 'Self-healing mesh & telemetry monitoring' },
            { id: 'LEARN', name: 'Learn', pos: [320, -280, 50], color: 0xf43f5e, emissive: 0xf43f5e, description: 'Outcome feedback loop to neural core' }
        ];
        const nodesGroup = new THREE.Group();
        scene.add(nodesGroup);
        const nodes = {};
        nodeDefs.forEach(def => {
            const nodeGroup = new THREE.Group();
            nodeGroup.position.set(def.pos[0], def.pos[1], def.pos[2]);
            // Faceted Node Geometry
            const geom = new THREE.OctahedronGeometry(15, 0);
            const mat = new THREE.MeshStandardMaterial({
                color: 0x0b1329,
                emissive: def.emissive,
                emissiveIntensity: 0.6,
                metalness: 0.85,
                roughness: 0.25,
                flatShading: true
            });
            const mesh = new THREE.Mesh(geom, mat);
            nodeGroup.add(mesh);
            // Node Wireframe Halo
            const haloGeo = new THREE.OctahedronGeometry(20, 0);
            const haloMat = new THREE.MeshBasicMaterial({
                color: def.color,
                wireframe: true,
                transparent: true,
                opacity: 0.4
            });
            const halo = new THREE.Mesh(haloGeo, haloMat);
            nodeGroup.add(halo);
            // Node Glow Beacon
            const beaconGeo = new THREE.SphereGeometry(4, 16, 16);
            const beaconMat = new THREE.MeshBasicMaterial({
                color: def.color,
                transparent: true,
                opacity: 0.85
            });
            const beacon = new THREE.Mesh(beaconGeo, beaconMat);
            nodeGroup.add(beacon);
            nodesGroup.add(nodeGroup);
            nodes[def.id] = {
                def,
                group: nodeGroup,
                mesh,
                halo,
                beacon,
                baseScale: 1,
                targetScale: 1
            };
        });
        state.nodes = nodes;
        // 6. 3D Spline Conduits with Data Flow Packets
        const conduitsGroup = new THREE.Group();
        scene.add(conduitsGroup);
        const conduits = [];
        nodeDefs.forEach(def => {
            const start = new THREE.Vector3(0, 0, 0);
            const end = new THREE.Vector3(def.pos[0], def.pos[1], def.pos[2]);
            // Create an organic curved spline
            const mid = new THREE.Vector3((start.x + end.x) * 0.5 + (Math.random() - 0.5) * 40, (start.y + end.y) * 0.5 + (Math.random() - 0.5) * 40, (start.z + end.z) * 0.5 + 40);
            const curve = new THREE.CatmullRomCurve3([start, mid, end]);
            const tubeGeo = new THREE.TubeGeometry(curve, 32, 1.2, 8, false);
            const tubeMat = new THREE.MeshBasicMaterial({
                color: def.color,
                transparent: true,
                opacity: 0.22,
                wireframe: true
            });
            const tubeMesh = new THREE.Mesh(tubeGeo, tubeMat);
            conduitsGroup.add(tubeMesh);
            // Animated Photon Packets traversing the conduit
            const pulseParticles = [];
            const packetCount = 4;
            const packetGeo = new THREE.SphereGeometry(2.5, 8, 8);
            const packetMat = new THREE.MeshBasicMaterial({
                color: def.color,
                transparent: true,
                opacity: 0.95
            });
            for (let i = 0; i < packetCount; i++) {
                const packetMesh = new THREE.Mesh(packetGeo, packetMat);
                conduitsGroup.add(packetMesh);
                pulseParticles.push({
                    mesh: packetMesh,
                    progress: (i / packetCount),
                    speed: 0.0035 + Math.random() * 0.002
                });
            }
            conduits.push({
                id: def.id,
                curve,
                mesh: tubeMesh,
                pulseParticles,
                startPos: start,
                endPos: end
            });
        });
        state.conduits = conduits;
        // 7. Starfield Ambient Particle Constellation
        const particleCount = 450;
        const particleGeo = new THREE.BufferGeometry();
        const particlePositions = new Float32Array(particleCount * 3);
        const particleColors = new Float32Array(particleCount * 3);
        for (let i = 0; i < particleCount; i++) {
            const idx = i * 3;
            particlePositions[idx] = (Math.random() - 0.5) * 1600;
            particlePositions[idx + 1] = (Math.random() - 0.5) * 1600;
            particlePositions[idx + 2] = (Math.random() - 0.5) * 1200 - 100;
            // Electric cyan / cool muted slate gradient
            const isCyan = Math.random() > 0.4;
            particleColors[idx] = isCyan ? 0.0 : 0.4;
            particleColors[idx + 1] = isCyan ? 0.83 : 0.55;
            particleColors[idx + 2] = isCyan ? 0.94 : 0.85;
        }
        particleGeo.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3));
        particleGeo.setAttribute('color', new THREE.BufferAttribute(particleColors, 3));
        const particleMat = new THREE.PointsMaterial({
            size: 3.5,
            vertexColors: true,
            transparent: true,
            opacity: 0.55
        });
        const particleField = new THREE.Points(particleGeo, particleMat);
        scene.add(particleField);
        // 8. Interactive Simulator Pulse Trigger
        const simulatorWorkflows = {
            missed_call: {
                key: 'missed_call',
                nodeIds: ['DISCOVER', 'AUDIT', 'PERSUADE', 'SELL'],
                color: 0x00d4ef,
                accentHex: '#00d4ef'
            },
            web_enquiry: {
                key: 'web_enquiry',
                nodeIds: ['AUDIT', 'PERSUADE', 'SELL', 'PAY'],
                color: 0x38bdf8,
                accentHex: '#38bdf8'
            },
            lead_form: {
                key: 'lead_form',
                nodeIds: ['DISCOVER', 'PERSUADE', 'SELL', 'BUILD', 'PAY'],
                color: 0x10b981,
                accentHex: '#10b981'
            },
            customer_question: {
                key: 'customer_question',
                nodeIds: ['AUDIT', 'PERSUADE', 'MAINTAIN', 'LEARN'],
                color: 0xf59e0b,
                accentHex: '#f59e0b'
            }
        };
        function triggerPulse(workflowKey) {
            state.activeWorkflow = workflowKey;
            const wf = simulatorWorkflows[workflowKey] || simulatorWorkflows.missed_call;
            // Animate core flare
            coreLight.intensity = 7.0;
            nucleus.material.emissiveIntensity = 1.2;
            // Surge particles and scale targeted nodes
            nodeDefs.forEach(def => {
                const node = nodes[def.id];
                const isTarget = wf.nodeIds.includes(def.id);
                if (isTarget) {
                    node.targetScale = 1.45;
                    node.mesh.material.emissiveIntensity = 1.0;
                    node.halo.material.opacity = 0.85;
                }
                else {
                    node.targetScale = 0.85;
                    node.mesh.material.emissiveIntensity = 0.25;
                    node.halo.material.opacity = 0.2;
                }
            });
            // Accelerate conduit pulse particles
            conduits.forEach(c => {
                const isTarget = wf.nodeIds.includes(c.id);
                c.mesh.material.opacity = isTarget ? 0.75 : 0.15;
                c.pulseParticles.forEach(p => {
                    p.speed = isTarget ? 0.015 : 0.002;
                });
            });
            // Decay back to equilibrium after pulse
            setTimeout(() => {
                coreLight.intensity = 3.5;
                nucleus.material.emissiveIntensity = 0.55;
                nodeDefs.forEach(def => {
                    const node = nodes[def.id];
                    node.targetScale = 1.0;
                    node.mesh.material.emissiveIntensity = 0.6;
                    node.halo.material.opacity = 0.4;
                });
                conduits.forEach(c => {
                    c.mesh.material.opacity = 0.22;
                    c.pulseParticles.forEach(p => {
                        p.speed = 0.0035 + Math.random() * 0.002;
                    });
                });
            }, 1600);
        }
        state.triggerPulse = triggerPulse;
        window.triggerLanding3DPulse = triggerPulse;
        // 9. GSAP ScrollTrigger Narrative Choreography (9 Chapters)
        let camTargetPos = { x: 0, y: 0, z: 850 };
        let camLookTarget = { x: 0, y: 0, z: 0 };
        if (typeof gsap !== 'undefined' && typeof ScrollTrigger !== 'undefined') {
            state.gsapLoaded = true;
            gsap.registerPlugin(ScrollTrigger);
            // Global Scroll Progress Mapping
            ScrollTrigger.create({
                start: 'top top',
                end: 'bottom bottom',
                onUpdate: (self) => {
                    state.scrollProgress = self.progress;
                }
            });
            // Chapter-specific camera choreography
            const chapters = [
                { trigger: '#hero', cam: { x: 0, y: 0, z: 850 }, look: { x: 0, y: 0, z: 0 } },
                { trigger: '#discover', cam: { x: -80, y: 40, z: 780 }, look: { x: -40, y: 20, z: 0 } },
                { trigger: '#audit', cam: { x: 90, y: 30, z: 750 }, look: { x: 40, y: 15, z: 0 } },
                { trigger: '#persuade', cam: { x: -110, y: -20, z: 720 }, look: { x: -50, y: -10, z: 0 } },
                { trigger: '#sell', cam: { x: 100, y: -40, z: 690 }, look: { x: 50, y: -20, z: 0 } },
                { trigger: '#build', cam: { x: 60, y: -70, z: 670 }, look: { x: 30, y: -30, z: 0 } },
                { trigger: '#deploy', cam: { x: -80, y: -90, z: 650 }, look: { x: -40, y: -40, z: 0 } },
                { trigger: '#maintain', cam: { x: 0, y: -110, z: 640 }, look: { x: 0, y: -50, z: 0 } },
                { trigger: '#grow', cam: { x: 0, y: 0, z: 890 }, look: { x: 0, y: 0, z: 0 } }
            ];
            chapters.forEach(ch => {
                const el = document.querySelector(ch.trigger);
                if (el) {
                    ScrollTrigger.create({
                        trigger: el,
                        start: 'top 70%',
                        end: 'bottom 30%',
                        onEnter: () => {
                            gsap.to(camTargetPos, { ...ch.cam, duration: 1.6, ease: 'power2.out' });
                            gsap.to(camLookTarget, { ...ch.look, duration: 1.6, ease: 'power2.out' });
                        },
                        onEnterBack: () => {
                            gsap.to(camTargetPos, { ...ch.cam, duration: 1.6, ease: 'power2.out' });
                            gsap.to(camLookTarget, { ...ch.look, duration: 1.6, ease: 'power2.out' });
                        }
                    });
                }
            });
        }
        // 10. Mouse Pointer Parallax with Spring Damping
        let mouseX = 0;
        let mouseY = 0;
        let targetMouseX = 0;
        let targetMouseY = 0;
        if (!prefersReducedMotion) {
            window.addEventListener('mousemove', (e) => {
                targetMouseX = (e.clientX / window.innerWidth - 0.5) * 55;
                targetMouseY = (e.clientY / window.innerHeight - 0.5) * -55;
            }, { passive: true });
        }
        // 11. Window Resize Handling
        function handleResize() {
            if (!camera || !renderer)
                return;
            const width = window.innerWidth;
            const height = window.innerHeight;
            camera.aspect = width / height;
            camera.updateProjectionMatrix();
            renderer.setSize(width, height);
            renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        }
        window.addEventListener('resize', handleResize, { passive: true });
        // 12. Main 60FPS RAF Render Loop
        let animId;
        let isHidden = false;
        document.addEventListener('visibilitychange', () => {
            isHidden = document.hidden;
        });
        const clock = new THREE.Clock();
        function renderLoop() {
            animId = requestAnimationFrame(renderLoop);
            state.frameCount++;
            if (isHidden)
                return;
            const delta = clock.getDelta();
            const elapsed = clock.getElapsedTime();
            // Smooth mouse parallax lerp
            mouseX += (targetMouseX - mouseX) * 0.05;
            mouseY += (targetMouseY - mouseY) * 0.05;
            // Update camera position
            camera.position.x = camTargetPos.x + mouseX;
            camera.position.y = camTargetPos.y + mouseY;
            camera.position.z += (camTargetPos.z - camera.position.z) * 0.06;
            camera.lookAt(camLookTarget.x, camLookTarget.y, camLookTarget.z);
            // Rotate kinetic core
            coreGroup.rotation.y = elapsed * 0.22;
            coreGroup.rotation.x = Math.sin(elapsed * 0.15) * 0.1;
            ring1.rotation.z = elapsed * 0.35;
            ring2.rotation.x = -elapsed * 0.28;
            ring3.rotation.y = elapsed * 0.18;
            // Animate constellation nodes
            nodeDefs.forEach((def, i) => {
                const node = nodes[def.id];
                if (node) {
                    // Bobbing wave
                    node.group.position.y = def.pos[1] + Math.sin(elapsed * 1.5 + i * 0.7) * 8;
                    node.mesh.rotation.x = elapsed * 0.4 + i;
                    node.mesh.rotation.y = elapsed * 0.5 + i;
                    node.halo.rotation.z = -elapsed * 0.3;
                    // Scale lerp
                    node.baseScale += (node.targetScale - node.baseScale) * 0.08;
                    node.group.scale.set(node.baseScale, node.baseScale, node.baseScale);
                }
            });
            // Animate conduit photon particles
            conduits.forEach(conduit => {
                conduit.pulseParticles.forEach(p => {
                    p.progress += p.speed;
                    if (p.progress > 1)
                        p.progress = 0;
                    const pos = conduit.curve.getPoint(p.progress);
                    p.mesh.position.copy(pos);
                });
            });
            // Ambient particle field slow rotation
            particleField.rotation.y = elapsed * 0.02;
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
    // Auto-boot on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initLanding3DEngine);
    }
    else {
        initLanding3DEngine();
    }
})();
