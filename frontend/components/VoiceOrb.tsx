"use client";

/**
 * Lena: a human head and shoulders drawn as a low-poly wireframe in the app's green (three.js),
 * from public/models/lena-mesh.json (made by scripts/body/make_lena.py).
 * - Speaking: her jaw moves with her voice and a soft wave of light runs out over the mesh from her mouth.
 * - Listening: her eyes and edges brighten and pulse gently.
 * - Thinking: a scan line sweeps up through her and she glances side to side.
 * - She turns her head a little toward your cursor, breathes when idle, and blinks.
 * Props: levelRef 0..1 loudness, modeRef current mode, size in px.
 */
import { useEffect, useRef } from "react";
import { cssVar, useTheme } from "@/lib/theme";

export type OrbMode = "speaking" | "listening" | "thinking" | "idle";
type LenaMesh = { v: number[]; t: number[]; jaw: number[]; eyes: [number, number, number][] };

let cache: Promise<LenaMesh> | null = null;
const loadLena = (): Promise<LenaMesh> => (cache ??= fetch("/models/lena-mesh.json").then((r) => r.json() as Promise<LenaMesh>));

const NECK = 0.12; // the head turns above this height (model units)
const POSE = `
  uniform float uYaw; uniform float uPitch; uniform float uJaw; uniform float uBreath;
  mat3 headRot(float w) {
    float cy = cos(uYaw * w), sy = sin(uYaw * w), cp = cos(uPitch * w), sp = sin(uPitch * w);
    return mat3(cy, 0.0, -sy, 0.0, 1.0, 0.0, sy, 0.0, cy) * mat3(1.0, 0.0, 0.0, 0.0, cp, sp, 0.0, -sp, cp);
  }
  float headW(float y) { return smoothstep(${(NECK - 0.12).toFixed(2)}, ${NECK.toFixed(2)}, y); }
  vec3 pose(vec3 p, float jaw) {
    p.y -= jaw * uJaw * 0.022;
    p.y += uBreath * 0.006 * (1.0 - headW(p.y));
    vec3 o = vec3(0.0, ${NECK.toFixed(2)}, 0.0);
    return headRot(headW(p.y)) * (p - o) + o;
  }`;
const SHARED = `
  uniform float uScan; uniform float uWave; uniform float uTalk; uniform vec3 uMouth; uniform float uGlow;
  float extra(vec3 p) {
    float scan = exp(-pow((p.y - uScan) / 0.05, 2.0));
    float d = distance(p, uMouth);
    float wave = uTalk * exp(-pow((d - uWave) / 0.08, 2.0)) * smoothstep(1.2, 0.2, d);
    return scan * 1.1 + wave * 0.9 + uGlow;
  }`;

const FILL_V = POSE + SHARED + `
  attribute vec3 aN; attribute float aJaw;
  uniform vec3 uLight;
  varying float vL; varying float vFade; varying float vX;
  void main() {
    vec3 p = pose(position, aJaw);
    vec3 n = normalize(headRot(headW(position.y)) * aN);
    vec3 nv = normalize(normalMatrix * n);
    vL = 0.1 + 0.55 * pow(max(dot(nv, uLight), 0.0), 1.4) + 0.25 * pow(1.0 - abs(nv.z), 3.0);
    vX = extra(position);
    vFade = smoothstep(-0.62, -0.3, position.y);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
  }`;
const FILL_F = `
  uniform vec3 uColor; uniform vec3 uBase; uniform float uFill; varying float vL; varying float vFade; varying float vX;
  void main() { gl_FragColor = vec4(mix(uBase, uColor, clamp(vL + vX * 0.25, 0.0, 1.0)), (uFill + vX * 0.08) * vFade); }`;

const LINE_V = POSE + SHARED + `
  attribute float aJaw; varying float vA;
  void main() {
    vec3 p = pose(position, aJaw);
    vA = (0.55 + extra(position)) * smoothstep(-0.62, -0.3, position.y);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
  }`;
const LINE_F = `uniform vec3 uColor; uniform vec3 uHi; uniform float uLine; varying float vA;
  void main() { gl_FragColor = vec4(mix(uColor, uHi, clamp(vA - 0.9, 0.0, 1.0)), min(1.0, vA) * uLine); }`;

const DOT_V = POSE + SHARED + `
  attribute float aJaw; uniform float uPix; varying float vA;
  void main() {
    vec3 p = pose(position, aJaw);
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    float x = extra(position);
    vA = (0.6 + x) * smoothstep(-0.62, -0.3, position.y);
    gl_PointSize = uPix * (2.4 + x * 2.5) * (3.6 / -mv.z);
    gl_Position = projectionMatrix * mv;
  }`;
const DOT_F = `uniform vec3 uColor; uniform vec3 uHi; varying float vA;
  void main() { float d = length(gl_PointCoord - 0.5); if (d > 0.5) discard; gl_FragColor = vec4(mix(uColor, uHi, clamp(vA - 0.8, 0.0, 1.0)), min(1.0, vA) * smoothstep(0.5, 0.1, d)); }`;

const EYE_V = POSE + `
  uniform float uPix; uniform float uEye; uniform float uBlink; uniform float uLook;
  void main() {
    vec3 p = pose(position + vec3(uLook * 0.012, 0.0, 0.0), 0.0);
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_PointSize = uPix * (5.0 + uEye * 5.0) * uBlink * (3.6 / -mv.z);
    gl_Position = projectionMatrix * mv;
  }`;
const EYE_F = `uniform vec3 uHi; uniform float uEye;
  void main() { float d = length(gl_PointCoord - 0.5); if (d > 0.5) discard; gl_FragColor = vec4(uHi, (0.75 + uEye * 0.25) * smoothstep(0.5, 0.0, d)); }`;

export default function VoiceOrb({ levelRef, modeRef, size = 420 }: { levelRef: React.MutableRefObject<number>; modeRef: React.MutableRefObject<OrbMode>; size?: number }) {
  const host = useRef<HTMLDivElement>(null);
  const theme = useTheme();

  useEffect(() => {
    let dispose = () => {};
    let dead = false;
    (async () => {
      const [THREE, m] = await Promise.all([import("three"), loadLena()]);
      const el = host.current;
      if (!el || dead) return;
      let renderer: any;
      try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true }); } catch { return; }
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      renderer.setPixelRatio(dpr); renderer.setSize(size, size); renderer.setClearColor(0, 0);
      el.appendChild(renderer.domElement);
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const light = theme === "light";
      const blending = light ? THREE.NormalBlending : THREE.AdditiveBlending;
      // colours are used as authored (the shaders write them straight to the screen)
      const C = (h: string) => new THREE.Color().setStyle(h, THREE.LinearSRGBColorSpace);
      const accent = C(cssVar("--accent", light ? "#0B7A65" : "#8EE3CB"));
      const hi = C(light ? "#04392F" : "#F0FFFA");

      const V = new Float32Array(m.v), T = m.t;
      const nV = V.length / 3;
      const jaw = new Float32Array(nV); m.jaw.forEach((i) => (jaw[i] = 1));
      let mouth = [0, 0, 0], mk = 0;
      m.jaw.forEach((i) => { if (V[i * 3 + 2] > 0.15) { mouth[0] += V[i * 3]; mouth[1] += V[i * 3 + 1]; mouth[2] += V[i * 3 + 2]; mk++; } });
      mouth = mk ? mouth.map((x) => x / mk) : [0, 0.28, 0.24];
      mouth[1] += 0.06;

      const U = {
        uYaw: { value: 0 }, uPitch: { value: 0 }, uJaw: { value: 0 }, uBreath: { value: 0 },
        uScan: { value: -5 }, uWave: { value: 0 }, uTalk: { value: 0 }, uGlow: { value: 0 }, uMouth: { value: new THREE.Vector3(...mouth) },
        uColor: { value: accent }, uHi: { value: hi }, uPix: { value: dpr }, uLight: { value: new THREE.Vector3(-0.45, 0.55, 0.7).normalize() },
        uFill: { value: light ? 0.16 : 0.3 }, uBase: { value: light ? C("#E4F3EE") : C("#000000") }, uLine: { value: light ? 0.75 : 0.62 },
        uEye: { value: 0 }, uBlink: { value: 1 }, uLook: { value: 0 },
      };

      // faces: flat normals, drawn first so they hide the edges behind
      const fp = new Float32Array(T.length * 3), fn = new Float32Array(T.length * 3), fj = new Float32Array(T.length);
      const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3(), n = new THREE.Vector3();
      for (let t = 0; t < T.length; t += 3) {
        a.fromArray(V, T[t] * 3); b.fromArray(V, T[t + 1] * 3); c.fromArray(V, T[t + 2] * 3);
        n.subVectors(b, a).cross(c.clone().sub(a)).normalize();
        for (let k = 0; k < 3; k++) { fp.set([V[T[t + k] * 3], V[T[t + k] * 3 + 1], V[T[t + k] * 3 + 2]], (t + k) * 3); fn.set([n.x, n.y, n.z], (t + k) * 3); fj[t + k] = jaw[T[t + k]]; }
      }
      const fg = new THREE.BufferGeometry();
      fg.setAttribute("position", new THREE.BufferAttribute(fp, 3)); fg.setAttribute("aN", new THREE.BufferAttribute(fn, 3)); fg.setAttribute("aJaw", new THREE.BufferAttribute(fj, 1));
      const fm = new THREE.ShaderMaterial({ vertexShader: FILL_V, fragmentShader: FILL_F, uniforms: U, transparent: true, blending,
        polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
      const faces = new THREE.Mesh(fg, fm); faces.renderOrder = 0;

      // edges: each shared edge once
      const seen = new Set<string>(); const ep: number[] = [], ej: number[] = [];
      for (let t = 0; t < T.length; t += 3) for (const [i, j] of [[T[t], T[t + 1]], [T[t + 1], T[t + 2]], [T[t + 2], T[t]]]) {
        const key = i < j ? `${i}-${j}` : `${j}-${i}`; if (seen.has(key)) continue; seen.add(key);
        ep.push(V[i * 3], V[i * 3 + 1], V[i * 3 + 2], V[j * 3], V[j * 3 + 1], V[j * 3 + 2]); ej.push(jaw[i], jaw[j]);
      }
      const lg = new THREE.BufferGeometry();
      lg.setAttribute("position", new THREE.Float32BufferAttribute(ep, 3)); lg.setAttribute("aJaw", new THREE.Float32BufferAttribute(ej, 1));
      const lm = new THREE.ShaderMaterial({ vertexShader: LINE_V, fragmentShader: LINE_F, uniforms: U, transparent: true, blending, depthWrite: false });
      const edges = new THREE.LineSegments(lg, lm); edges.renderOrder = 1;

      const dg = new THREE.BufferGeometry();
      dg.setAttribute("position", new THREE.BufferAttribute(V, 3)); dg.setAttribute("aJaw", new THREE.BufferAttribute(jaw, 1));
      const dm = new THREE.ShaderMaterial({ vertexShader: DOT_V, fragmentShader: DOT_F, uniforms: U, transparent: true, blending, depthWrite: false });
      const dots = new THREE.Points(dg, dm); dots.renderOrder = 2;

      const eg = new THREE.BufferGeometry(); eg.setAttribute("position", new THREE.Float32BufferAttribute(m.eyes.flat(), 3));
      const em = new THREE.ShaderMaterial({ vertexShader: EYE_V, fragmentShader: EYE_F, uniforms: U, transparent: true, blending, depthTest: false, depthWrite: false });
      const eyes = new THREE.Points(eg, em); eyes.renderOrder = 3;

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 50);
      camera.position.set(0, 0.17, 2.85); camera.lookAt(0, 0.15, 0);
      const bust = new THREE.Group(); bust.add(faces, edges, dots, eyes); scene.add(bust);

      let mx = 0, my = 0;
      const onMove = (e: PointerEvent) => {
        const r = el.getBoundingClientRect();
        mx = Math.max(-1, Math.min(1, (e.clientX - (r.left + r.width / 2)) / 500));
        my = Math.max(-1, Math.min(1, (e.clientY - (r.top + r.height / 2)) / 500));
      };
      window.addEventListener("pointermove", onMove);

      const t0 = performance.now();
      let raf = 0, L = 0, yaw = 0, pitch = 0, eye = 0, talk = 0, glow = 0, nextBlink = 2, blinkAt = -1;
      const frame = (now: number) => {
        const t = (now - t0) / 1000;
        const mode = modeRef.current;
        L += ((levelRef.current || 0) - L) * 0.35;
        if (t > nextBlink) { blinkAt = t; nextBlink = t + 2.5 + Math.random() * 3; }
        U.uBlink.value = reduce ? 1 : Math.max(0.05, blinkAt > 0 ? Math.min(1, Math.abs(t - blinkAt - 0.07) / 0.07) : 1);
        const speaking = mode === "speaking";
        U.uJaw.value += ((speaking ? Math.min(1, L * 1.8) : 0) - U.uJaw.value) * 0.4;
        talk += ((speaking ? 0.35 + L * 0.9 : 0) - talk) * 0.15; U.uTalk.value = reduce ? 0 : talk;
        U.uWave.value = (t * 0.9) % 1.1;
        eye += ((mode === "listening" ? 0.7 + 0.3 * Math.sin(t * 4) : speaking ? 0.3 + L * 0.5 : 0.15) - eye) * 0.12; U.uEye.value = eye;
        glow += ((mode === "listening" ? 0.18 + 0.1 * Math.sin(t * 3) : 0) - glow) * 0.08; U.uGlow.value = glow;
        U.uScan.value = mode === "thinking" && !reduce ? ((t * 0.5) % 1.5) * 1.9 - 0.85 : -5;
        U.uLook.value += ((mode === "thinking" && !reduce ? Math.sin(t * 2.2) : mx * 0.5) - U.uLook.value) * 0.1;
        U.uBreath.value = reduce ? 0 : Math.sin(t * 1.3);
        const ty = reduce ? 0 : mode === "thinking" ? Math.sin(t * 1.4) * 0.3 : mx * 0.45 + Math.sin(t * 0.45) * 0.06;
        const tp = reduce ? 0 : mode === "listening" ? -0.07 : my * 0.15 + Math.sin(t * 0.6) * 0.02;
        yaw += (ty - yaw) * 0.05; pitch += (tp - pitch) * 0.05;
        U.uYaw.value = yaw; U.uPitch.value = pitch;
        bust.rotation.y = reduce ? 0 : Math.sin(t * 0.25) * 0.08;
        renderer.render(scene, camera);
        raf = requestAnimationFrame(frame);
      };
      raf = requestAnimationFrame(frame);
      dispose = () => {
        cancelAnimationFrame(raf); window.removeEventListener("pointermove", onMove);
        [fg, fm, lg, lm, dg, dm, eg, em].forEach((d) => d.dispose()); renderer.dispose(); renderer.domElement.remove();
      };
    })();
    return () => { dead = true; dispose(); };
  }, [size, theme]); // eslint-disable-line react-hooks/exhaustive-deps

  return <div ref={host} style={{ width: size, height: size, maxWidth: "100%" }} aria-hidden="true" />;
}
