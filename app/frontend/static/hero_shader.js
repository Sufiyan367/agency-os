/**
 * Agency OS — Premium Hero WebGL Shader Engine
 * Architectural Flow: Swirl + ChromaFlow + FlutedGlass + FilmGrain
 *
 * Characteristics:
 * - Native WebGL (Zero external dependencies)
 * - Restrained Obsidian, Deep Navy & Controlled Electric Cyan palette
 * - Architectural fluted glass coordinate distortion & chromatic dispersion
 * - Fractional Brownian motion (FBM) fluid domain warping
 * - Film grain micro-dithering for tactile cinematic depth
 * - Single RAF loop with automatic pause on scroll out / tab hidden
 * - Strict device-pixel-ratio ceiling (1.5 desktop, 1.0 mobile)
 * - Accessible: respects prefers-reduced-motion with elegant static resting state
 */

(function initHeroShader() {
  'use strict';

  if (typeof window === 'undefined') return;

  const canvas = document.getElementById('heroShaderCanvas');
  if (!canvas) return;

  // Check WebGL support
  const gl = canvas.getContext('webgl', {
    alpha: false,
    antialias: false,
    depth: false,
    stencil: false,
    powerPreference: 'high-performance'
  }) || canvas.getContext('experimental-webgl');

  if (!gl) {
    console.warn('[HeroShader] WebGL unavailable. Falling back to CSS ambient depth.');
    canvas.style.display = 'none';
    return;
  }

  // Check user preference for reduced motion
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Vertex Shader: Fullscreen quad
  const vsSource = `
    attribute vec2 position;
    varying vec2 vUv;
    void main() {
      vUv = (position + 1.0) * 0.5;
      gl_Position = vec4(position, 0.0, 1.0);
    }
  `;

  // Fragment Shader: Swirl + ChromaFlow + FlutedGlass + FilmGrain
  const fsSource = `
    precision highp float;

    uniform float u_time;
    uniform vec2 u_resolution;
    uniform vec2 u_mouse;
    uniform float u_intensity;

    varying vec2 vUv;

    // Simplex Noise Hash & Interpolation
    vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
    vec2 mod289(vec2 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
    vec3 permute(vec3 x) { return mod289(((x * 34.0) + 1.0) * x); }

    float snoise(vec2 v) {
      const vec4 C = vec4(0.211324865405187,
                          0.366025403784439,
                         -0.577350269189626,
                          0.024390243902439);
      vec2 i  = floor(v + dot(v, C.yy));
      vec2 x0 = v - i + dot(i, C.xx);
      vec2 i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
      vec4 x12 = x0.xyxy + C.xxzz;
      x12.xy -= i1;
      i = mod289(i);
      vec3 p = permute(permute(i.y + vec3(0.0, i1.y, 1.0))
             + i.x + vec3(0.0, i1.x, 1.0));
      vec3 m = max(0.5 - vec3(dot(x0, x0), dot(x12.xy, x12.xy), dot(x12.zw, x12.zw)), 0.0);
      m = m * m;
      m = m * m;
      vec3 x = 2.0 * fract(p * C.www) - 1.0;
      vec3 h = abs(x) - 0.5;
      vec3 ox = floor(x + 0.5);
      vec3 a0 = x - ox;
      m *= 1.79284291400159 - 0.85373472095314 * (a0 * a0 + h * h);
      vec3 g;
      g.x  = a0.x  * x0.x  + h.x  * x0.y;
      g.yz = a0.yz * x12.xz + h.yz * x12.yw;
      return 130.0 * dot(m, g);
    }

    // Fractional Brownian Motion (4 octaves with rotation to eliminate axial grid bias)
    float fbm(vec2 p) {
      float v = 0.0;
      float a = 0.5;
      vec2 shift = vec2(100.0);
      mat2 rot = mat2(cos(0.5), sin(0.5), -sin(0.5), cos(0.5));
      for (int i = 0; i < 4; ++i) {
        v += a * snoise(p);
        p = rot * p * 2.0 + shift;
        a *= 0.5;
      }
      return v;
    }

    // Procedural Film Grain Hash
    float hash(vec2 p) {
      return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453123);
    }

    void main() {
      vec2 uv = gl_FragCoord.xy / u_resolution.xy;
      vec2 p = (gl_FragCoord.xy * 2.0 - u_resolution.xy) / min(u_resolution.x, u_resolution.y);

      // Smooth mouse influence with wide radius and gentle falloff
      vec2 mouseOffset = (u_mouse - 0.5) * 0.30;
      p += mouseOffset * 0.35;

      // 1. FLUTED GLASS OPTICS (Architectural Ribbed Refraction)
      float flutingFreq = 52.0;
      float fluting = sin(p.x * flutingFreq) * 0.016 * u_intensity;
      p.x += fluting;

      // 2. SWIRL & DOMAIN WARPING (Fluid Organic Motion)
      // Slow, stately time variable (deliberately restrained pace)
      float t = u_time * 0.075;

      // Primary displacement vectors q and r
      vec2 q = vec2(
        fbm(p + vec2(0.0, 0.0) + vec2(t * 0.28, t * 0.08)),
        fbm(p + vec2(5.2, 1.3) + vec2(t * -0.18, t * 0.22))
      );

      vec2 r = vec2(
        fbm(p + 2.8 * q + vec2(1.7, 9.2) + vec2(t * 0.12, t * -0.09)),
        fbm(p + 2.8 * q + vec2(8.3, 2.8) + vec2(t * -0.08, t * 0.15))
      );

      // Final warped flow coordinate
      float f = fbm(p + 2.4 * r + vec2(0.0, t * 0.04));

      // 3. CHROMAFLOW (Spectral Dispersion across Fluid Ridges)
      float chromaticDisp = 0.012 * u_intensity;
      float fR = fbm(p + 2.4 * r + vec2(chromaticDisp, 0.0));
      float fG = f;
      float fB = fbm(p + 2.4 * r - vec2(chromaticDisp, 0.0));

      // Palette: Deep Obsidian, Midnight Navy, Slate Violet, and Controlled Cyan
      vec3 cBg       = vec3(0.027, 0.027, 0.035); // #070709 Base dark obsidian
      vec3 cNavy     = vec3(0.038, 0.068, 0.140); // Deep Midnight Blue
      vec3 cSlate    = vec3(0.065, 0.075, 0.120); // Cool Slate Depth
      vec3 cCyan     = vec3(0.000, 0.720, 0.880); // Restrained Electric Cyan (#00d4ef)
      vec3 cCyanGlow = vec3(0.045, 0.260, 0.380); // Soft Cyan Diffusion

      // Layer 1: Base dark background into Midnight Navy
      vec3 col = mix(cBg, cNavy, clamp((fR * fR) * 2.0, 0.0, 1.0));

      // Layer 2: ChromaFlow Slate & Wavefront Depth
      col = mix(col, cSlate, clamp(length(q), 0.0, 1.0) * 0.55);

      // Layer 3: Cyan Light Crests (Restrained & Soft, never neon-blown)
      float crest = clamp(pow(max(fG, 0.0), 3.0) * 1.6, 0.0, 1.0);
      col = mix(col, cCyanGlow, crest * 0.68 * u_intensity);

      // Specular ridge on chromatic blue channel
      float specular = smoothstep(0.72, 0.94, fB);
      col += cCyan * (specular * 0.28 * u_intensity);

      // 4. SOFT READABILITY VIGNETTE
      // Gentle radial attenuation centered near hero text so typography is 100% crisp
      vec2 center = vec2(0.5, 0.38);
      float dist = length(uv - center);
      float vignette = smoothstep(0.18, 0.92, dist);
      col = mix(col, cBg, vignette * 0.50);

      // Bottom gradient darkening towards solid page content below hero
      float bottomDarken = smoothstep(0.30, 0.95, 1.0 - uv.y);
      col = mix(col, cBg, bottomDarken * 0.65);

      // 5. FILM GRAIN (Micro-dithering that eliminates banding and gives cinematic finish)
      float grain = (hash(gl_FragCoord.xy + fract(u_time * 19.0)) - 0.5) * 0.032;
      col += vec3(grain);

      gl_FragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
    }
  `;

  // Compile shader helper
  function createShader(glContext, type, source) {
    const shader = glContext.createShader(type);
    glContext.shaderSource(shader, source);
    glContext.compileShader(shader);
    if (!glContext.getShaderParameter(shader, glContext.COMPILE_STATUS)) {
      console.error('[HeroShader] Compile error:', glContext.getShaderInfoLog(shader));
      glContext.deleteShader(shader);
      return null;
    }
    return shader;
  }

  const vertexShader = createShader(gl, gl.VERTEX_SHADER, vsSource);
  const fragmentShader = createShader(gl, gl.FRAGMENT_SHADER, fsSource);

  if (!vertexShader || !fragmentShader) {
    canvas.style.display = 'none';
    return;
  }

  const program = gl.createProgram();
  gl.attachShader(program, vertexShader);
  gl.attachShader(program, fragmentShader);
  gl.linkProgram(program);

  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    console.error('[HeroShader] Program link error:', gl.getProgramInfoLog(program));
    canvas.style.display = 'none';
    return;
  }

  gl.useProgram(program);

  // Set up fullscreen geometry (2 triangles covering screen)
  const positionBuffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
  const positions = new Float32Array([
    -1.0, -1.0,
     1.0, -1.0,
    -1.0,  1.0,
    -1.0,  1.0,
     1.0, -1.0,
     1.0,  1.0,
  ]);
  gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW);

  const positionLocation = gl.getAttribLocation(program, 'position');
  gl.enableVertexAttribArray(positionLocation);
  gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0);

  // Uniform locations
  const uTimeLoc = gl.getUniformLocation(program, 'u_time');
  const uResLoc = gl.getUniformLocation(program, 'u_resolution');
  const uMouseLoc = gl.getUniformLocation(program, 'u_mouse');
  const uIntensityLoc = gl.getUniformLocation(program, 'u_intensity');

  // State
  let targetMouseX = 0.5;
  let targetMouseY = 0.5;
  let currentMouseX = 0.5;
  let currentMouseY = 0.5;
  let animFrameId = null;
  let isTabActive = true;
  let isHeroVisible = true;
  let startTime = performance.now();

  // Resize handler
  function resizeCanvas() {
    const isMobile = window.innerWidth <= 768;
    // Cap DPR: 1.5 on desktop, 1.0 on mobile for optimal performance
    const dpr = Math.min(window.devicePixelRatio || 1, isMobile ? 1.0 : 1.5);
    const width = Math.floor(window.innerWidth * dpr);
    const height = Math.floor(window.innerHeight * dpr);

    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
      gl.viewport(0, 0, width, height);
    }
  }

  window.addEventListener('resize', resizeCanvas, { passive: true });
  resizeCanvas();

  // Mouse move handler (desktop only)
  window.addEventListener('mousemove', function (e) {
    if (window.innerWidth <= 768) return;
    targetMouseX = e.clientX / window.innerWidth;
    targetMouseY = 1.0 - (e.clientY / window.innerHeight);
  }, { passive: true });

  // IntersectionObserver: Only render while hero is visible
  const heroSection = document.getElementById('home') || document.querySelector('.hero-section');
  if (heroSection && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        isHeroVisible = entry.isIntersecting;
        if (!isHeroVisible) {
          if (animFrameId) {
            cancelAnimationFrame(animFrameId);
            animFrameId = null;
          }
        } else if (!animFrameId && isTabActive && !prefersReducedMotion) {
          startTime = performance.now();
          animFrameId = requestAnimationFrame(render);
        }
      });
    }, { threshold: 0.0 });
    observer.observe(heroSection);
  }

  // Visibility handler: Pause when tab is inactive
  document.addEventListener('visibilitychange', function () {
    isTabActive = !document.hidden;
    if (isTabActive && isHeroVisible && !animFrameId && !prefersReducedMotion) {
      animFrameId = requestAnimationFrame(render);
    }
  });

  // Render loop
  function render(timestamp) {
    if (!isTabActive || !isHeroVisible) {
      animFrameId = null;
      return;
    }

    // Smooth mouse lerp
    currentMouseX += (targetMouseX - currentMouseX) * 0.04;
    currentMouseY += (targetMouseY - currentMouseY) * 0.04;

    const elapsedTime = (timestamp - startTime) * 0.001;
    const isMobile = window.innerWidth <= 768;
    const intensity = isMobile ? 0.70 : 1.0;

    gl.useProgram(program);
    gl.uniform1f(uTimeLoc, elapsedTime);
    gl.uniform2f(uResLoc, canvas.width, canvas.height);
    gl.uniform2f(uMouseLoc, currentMouseX, currentMouseY);
    gl.uniform1f(uIntensityLoc, intensity);

    gl.drawArrays(gl.TRIANGLES, 0, 6);

    animFrameId = requestAnimationFrame(render);
  }

  // If prefers-reduced-motion is active, render exactly one static elegant frame and stop
  if (prefersReducedMotion) {
    gl.useProgram(program);
    gl.uniform1f(uTimeLoc, 12.5); // Static resting time
    gl.uniform2f(uResLoc, canvas.width, canvas.height);
    gl.uniform2f(uMouseLoc, 0.5, 0.5);
    gl.uniform1f(uIntensityLoc, 0.65);
    gl.drawArrays(gl.TRIANGLES, 0, 6);
  } else {
    animFrameId = requestAnimationFrame(render);
  }

  // Expose engine status for diagnostics & testing
  window.agencyHeroShader = {
    initialized: true,
    glAvailable: true,
    isRunning: function () { return Boolean(animFrameId); },
    pause: function () {
      if (animFrameId) {
        cancelAnimationFrame(animFrameId);
        animFrameId = null;
      }
    },
    resume: function () {
      if (!animFrameId && isTabActive && isHeroVisible) {
        animFrameId = requestAnimationFrame(render);
      }
    }
  };
})();
