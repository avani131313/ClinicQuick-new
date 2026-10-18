"use client";

/**
 * The patient's body, rendered with three.js from a pre-built anatomy mesh (public/models), in two looks:
 * - "anatomy": an écorché-style muscle figure; hover a muscle to see its name.
 * - "nodes": points sampled from the same surface, glowing at the silhouette.
 * The heart is an anatomical heart (chambers, aorta, venae cavae) that beats at `bpm`.
 * Drag to turn; the +/- buttons or a trackpad pinch zoom. Hotspots are HTML labels pinned to the body.
 */
import { useEffect, useRef, useState } from "react";
import { cssVar, useTheme } from "@/lib/theme";
import { loadBody, muscleMesh, nodeSample, regionAt, regionId } from "./anatomy";
import { HEART_COLOURS, loadHeart } from "./heart";
import s from "./body.module.css";

export type Anchor = "head" | "heart" | "lungs" | "wrist" | "abdomen" | "legs" | "arm";
export type Hotspot = { id: string; anchor: Anchor; label: string; value: string; tone?: "ok" | "watch" | "alert" | "pulse" };
type V3 = [number, number, number];

const ANCHORS = (sex: string): Record<Anchor, V3> => {
  const sh = sex === "female" ? 0.168 : 0.19;
  return {
    head: [0.02, 1.7, 0.08], heart: [0.03, 1.31, 0.075], lungs: [-0.075, 1.345, 0.085], abdomen: [0, 1.1, 0.1],
    wrist: [-(sh + 0.075), 0.905, 0.03], arm: [sh + 0.05, 1.12, 0.02], legs: [0.1, 0.62, 0.075],
  };
};

const NODE_VERT = `
  uniform float uTime; uniform float uScan; uniform float uSize; uniform float uPix;
  attribute vec3 normal2; attribute float rnd;
  varying float vAlpha; varying float vScan;
  void main() {
    vec3 p = position + normal2 * (sin(uTime * 0.9 + rnd * 40.0) * 0.0012);
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    vec3 n = normalize(normalMatrix * normal2);
    float rim = pow(1.0 - abs(dot(n, normalize(-mv.xyz))), 1.6);
    vScan = exp(-pow((position.y - uScan) / 0.035, 2.0));
    vAlpha = 0.38 + rim * 0.8 + vScan * 0.6;
    gl_PointSize = uSize * uPix * (0.6 + rim * 0.8 + vScan) / -mv.z;
    gl_Position = projectionMatrix * mv;
  }`;
const NODE_FRAG = `
  uniform vec3 uColor; uniform vec3 uScanColor; varying float vAlpha; varying float vScan;
  void main() {
    float d = length(gl_PointCoord - 0.5); if (d > 0.5) discard;
    gl_FragColor = vec4(mix(uColor, uScanColor, vScan), vAlpha * smoothstep(0.5, 0.0, d));
  }`;
const HEART_VERT = `
  uniform float uBeat; uniform float uSize; uniform float uPix; attribute float rnd; attribute vec3 aColor;
  varying float vA; varying vec3 vC;
  void main() {
    vec3 p = position * (1.0 + uBeat * vec3(0.1, 0.13, 0.1) * (position.y < 0.1 ? 1.0 : 0.45));
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    vA = 0.55 + 0.45 * uBeat; vC = aColor;
    gl_PointSize = uSize * uPix * (0.75 + rnd * 0.6) / -mv.z;
    gl_Position = projectionMatrix * mv;
  }`;
const HEART_FRAG = `
  varying float vA; varying vec3 vC;
  void main() { float d = length(gl_PointCoord - 0.5); if (d > 0.5) discard; gl_FragColor = vec4(vC, vA * smoothstep(0.5, 0.05, d)); }`;

export default function BodyScene({
  sex, bpm = 68, hotspots = [], active, onSelect, height = 620,
}: { sex: string; bpm?: number; hotspots?: Hotspot[]; active?: string | null; onSelect?: (id: string) => void; height?: number }) {
  const host = useRef<HTMLDivElement>(null);
  const labels = useRef<Record<string, HTMLButtonElement | null>>({});
  const control = useRef<{ zoom: (k: number) => void; reset: () => void } | null>(null);
  const bpmRef = useRef(bpm);
  const spotsRef = useRef(hotspots);
  const [mode, setMode] = useState<"anatomy" | "nodes">("anatomy");
  const [muscle, setMuscle] = useState<{ name: string; x: number; y: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const theme = useTheme();
  bpmRef.current = bpm;
  spotsRef.current = hotspots;

  useEffect(() => { try { const m = localStorage.getItem("cq.body"); if (m === "nodes" || m === "anatomy") setMode(m); } catch {} }, []);
  const pickMode = (m: "anatomy" | "nodes") => { setMode(m); try { localStorage.setItem("cq.body", m); } catch {} };

  useEffect(() => {
    let disposed = false;
    let cleanup = () => {};
    setLoading(true);
    (async () => {
      const [THREE, body, heartData] = await Promise.all([import("three"), loadBody(sex), loadHeart()]);
      const el = host.current;
      if (!el || disposed) return;
      let renderer: any;
      try {
        renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
      } catch {
        el.dataset.nogl = "1";
        return;
      }
      setLoading(false);
      const light = theme === "light";
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      renderer.setPixelRatio(dpr);
      renderer.setClearColor(0x000000, 0);
      el.prepend(renderer.domElement);
      renderer.domElement.className = s.canvas;

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(30, 1, 0.05, 50);
      let dist = 3.6;
      const target = new THREE.Vector3(0, 0.9, 0);
      const figure = new THREE.Group();
      if (sex === "female") figure.scale.setScalar(0.965);
      scene.add(figure);
      const disposables: any[] = [];

      // --- body ---------------------------------------------------------------------
      let mesh: any = null, nodeMat: any = null;
      if (mode === "anatomy") {
        mesh = muscleMesh(THREE, body, {
          muscle: cssVar("--muscle", "#C4533F"), dark: cssVar("--muscle-dark", "#7E2A22"), tendon: cssVar("--tendon", "#EFE6D8"),
          tissue: "#E3A58C", rim: cssVar("--accent", "#8EE3CB"),
        });
        figure.add(mesh);
        disposables.push(mesh.geometry, mesh.material);
      } else {
        const smp = nodeSample(body, 20000, sex === "female" ? 5 : 3);
        const g = new THREE.BufferGeometry();
        g.setAttribute("position", new THREE.BufferAttribute(smp.pos, 3));
        g.setAttribute("normal2", new THREE.BufferAttribute(smp.nor, 3));
        g.setAttribute("rnd", new THREE.BufferAttribute(smp.rnd, 1));
        nodeMat = new THREE.ShaderMaterial({
          vertexShader: NODE_VERT, fragmentShader: NODE_FRAG, transparent: true, depthWrite: false,
          blending: light ? THREE.NormalBlending : THREE.AdditiveBlending,
          uniforms: { uTime: { value: 0 }, uScan: { value: -1 }, uSize: { value: 2.8 }, uPix: { value: dpr },
            uColor: { value: new THREE.Color(cssVar("--accent", "#86E6CC")) }, uScanColor: { value: new THREE.Color(light ? "#063F33" : "#E9FFF8") } },
        });
        figure.add(new THREE.Points(g, nodeMat));
        disposables.push(g, nodeMat);
      }

      // --- anatomical heart -----------------------------------------------------------
      const pal = (light ? HEART_COLOURS.light : HEART_COLOURS.dark).map((h) => new THREE.Color(h));
      const hp = new Float32Array(heartData.points.length * 3), hc = new Float32Array(heartData.points.length * 3), hr = new Float32Array(heartData.points.length);
      heartData.points.forEach(([x, y, z, reg], i) => {
        hp.set([x, y, z], i * 3); hc.set([pal[reg].r, pal[reg].g, pal[reg].b], i * 3); hr[i] = (i * 7919 % 1000) / 1000;
      });
      const hg = new THREE.BufferGeometry();
      hg.setAttribute("position", new THREE.BufferAttribute(hp, 3));
      hg.setAttribute("aColor", new THREE.BufferAttribute(hc, 3));
      hg.setAttribute("rnd", new THREE.BufferAttribute(hr, 1));
      const hmat = new THREE.ShaderMaterial({
        vertexShader: HEART_VERT, fragmentShader: HEART_FRAG, transparent: true, depthWrite: false, depthTest: mode !== "anatomy",
        blending: light ? THREE.NormalBlending : THREE.AdditiveBlending,
        uniforms: { uBeat: { value: 0 }, uSize: { value: 2.6 }, uPix: { value: dpr } },
      });
      const heart = new THREE.Points(hg, hmat);
      heart.renderOrder = 10;
      heart.scale.setScalar(0.06);
      heart.position.set(0.028, 1.31, 0.03);
      heart.rotation.set(0.1, -0.35, -0.35);
      figure.add(heart);
      disposables.push(hg, hmat);

      // floor ring
      const fp: number[] = [];
      for (let i = 0; i < 700; i++) { const a = (i / 700) * Math.PI * 2, rr = i % 3 === 0 ? 0.55 : 0.38; fp.push(Math.cos(a) * rr, 0, Math.sin(a) * rr); }
      const fg = new THREE.BufferGeometry(); fg.setAttribute("position", new THREE.Float32BufferAttribute(fp, 3));
      const fm = new THREE.PointsMaterial({ color: new THREE.Color(cssVar("--accent", "#3E8C7C")), size: 1.6 * dpr, sizeAttenuation: false, transparent: true, opacity: 0.35 });
      const floor = new THREE.Points(fg, fm);
      scene.add(floor);
      disposables.push(fg, fm);

      // --- interaction ------------------------------------------------------------------
      let yaw = -0.3, pitch = 0.04, vYaw = 0, dragging = false, lastX = 0, lastY = 0, idleAt = 0, distGoal = dist;
      const zoomTo = (d: number) => { distGoal = Math.max(1.4, Math.min(5, d)); idleAt = performance.now(); };
      control.current = { zoom: (k: number) => zoomTo(distGoal + k), reset: () => { distGoal = 3.6; pitch = 0.04; yaw = -0.3; vYaw = 0; idleAt = performance.now(); } };
      const cv = renderer.domElement as HTMLCanvasElement;
      const down = (e: PointerEvent) => { dragging = true; lastX = e.clientX; lastY = e.clientY; (e.target as Element).setPointerCapture?.(e.pointerId); };
      const move = (e: PointerEvent) => {
        if (!dragging) return;
        const dx = e.clientX - lastX, dy = e.clientY - lastY; lastX = e.clientX; lastY = e.clientY;
        vYaw = dx * 0.008; yaw += vYaw; pitch = Math.max(-0.35, Math.min(0.45, pitch + dy * 0.004)); idleAt = performance.now();
      };
      const up = () => { dragging = false; idleAt = performance.now(); };
      const wheel = (e: WheelEvent) => { if (!e.ctrlKey) return; e.preventDefault(); zoomTo(dist + e.deltaY * 0.01); };
      const ray = new THREE.Raycaster(); const ndc = new THREE.Vector2();
      let hoverName: string | null = null;
      const hover = (e: PointerEvent) => {
        if (!mesh || dragging) return;
        const r = cv.getBoundingClientRect();
        ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
        ray.setFromCamera(ndc, camera);
        const hit = ray.intersectObject(mesh, false)[0];
        const name = hit ? regionAt(body, hit.face.a) : null;
        if (name !== hoverName) { hoverName = name; mesh.material.uniforms.uHover.value = name ? regionId(body, name) : -1; }
        setMuscle(name ? { name, x: e.clientX - r.left, y: e.clientY - r.top } : null);
      };
      const out = () => { hoverName = null; if (mesh) mesh.material.uniforms.uHover.value = -1; setMuscle(null); };
      cv.addEventListener("pointerdown", down); window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
      cv.addEventListener("wheel", wheel, { passive: false });
      cv.addEventListener("pointermove", hover); cv.addEventListener("pointerleave", out);

      const resize = () => {
        const w = el.clientWidth, h = el.clientHeight;
        renderer.setSize(w, h, false);
        camera.aspect = w / h; camera.updateProjectionMatrix();
      };
      resize();
      const ro = new ResizeObserver(resize); ro.observe(el);

      const anchors = ANCHORS(sex);
      const v = new THREE.Vector3();
      const t0 = performance.now();
      let raf = 0, beatT = 0, last = t0;
      const frame = (now: number) => {
        const t = (now - t0) / 1000, dt = Math.min(0.05, (now - last) / 1000); last = now;
        if (!dragging) { vYaw *= 0.94; yaw += vYaw; if (!reduce && now - idleAt > 2500) yaw += dt * 0.12; }
        dist += (distGoal - dist) * 0.12;
        // zooming in also lifts the view toward the chest, so close-ups show the torso, not the knees
        const lift = Math.max(0, Math.min(1, (3.6 - dist) / 2.2));
        target.y = 0.9 + lift * 0.42;
        figure.rotation.y = yaw; floor.rotation.y = -t * 0.05;
        camera.position.set(0, target.y + Math.sin(pitch) * dist, Math.cos(pitch) * dist);
        camera.lookAt(target);
        if (mesh) mesh.material.uniforms.uAppear.value = reduce ? 9 : -0.05 + Math.min(1, t / 1.6) * 1.95 + (t > 1.6 ? 8 : 0);
        if (nodeMat) { nodeMat.uniforms.uTime.value = t; nodeMat.uniforms.uScan.value = reduce ? -1 : ((t * 0.16) % 1.3) * 1.9 - 0.1; }
        beatT += dt * (bpmRef.current || 68) / 60;
        const ph = beatT % 1;
        hmat.uniforms.uBeat.value = reduce ? 0.3 : Math.exp(-Math.pow((ph - 0.08) / 0.05, 2)) + 0.55 * Math.exp(-Math.pow((ph - 0.26) / 0.05, 2));
        renderer.render(scene, camera);

        const w = el.clientWidth, h = el.clientHeight;
        figure.updateMatrixWorld();
        for (const spot of spotsRef.current) {
          const node = labels.current[spot.id];
          if (!node) continue;
          const a = anchors[spot.anchor];
          v.set(a[0], a[1], a[2]).applyMatrix4(figure.matrixWorld);
          const depth = v.distanceTo(camera.position);
          v.project(camera);
          const x = (v.x * 0.5 + 0.5) * w, y = (-v.y * 0.5 + 0.5) * h;
          node.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0)`;
          node.style.opacity = depth > dist + 0.02 ? "0.35" : "1";
          node.dataset.side = x > w / 2 ? "r" : "l";
        }
        raf = requestAnimationFrame(frame);
      };
      raf = requestAnimationFrame(frame);

      cleanup = () => {
        cancelAnimationFrame(raf); ro.disconnect();
        window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
        cv.removeEventListener("pointermove", hover); cv.removeEventListener("pointerleave", out);
        disposables.forEach((d) => d.dispose()); renderer.dispose(); cv.remove();
      };
    })().catch(() => { if (host.current) host.current.dataset.nogl = "1"; setLoading(false); });
    return () => { disposed = true; cleanup(); };
  }, [sex, mode, theme]);

  return (
    <div ref={host} className={s.host} style={{ height }} aria-label={`3D body figure, ${sex === "female" ? "female" : "male"}. Drag to turn.`} role="img">
      {loading && <p className={s.loading}>Loading body model…</p>}
      {hotspots.map((h) => (
        <button key={h.id} ref={(n) => { labels.current[h.id] = n; }} className={`${s.spot} ${active === h.id ? s.on : ""}`}
          data-tone={h.tone || "ok"} onClick={() => onSelect?.(h.id)} aria-pressed={active === h.id}>
          <span className={s.pin} aria-hidden="true" />
          <span className={s.tag}><span className={s.tagLabel}>{h.label}</span><span className={s.tagValue}>{h.value}</span></span>
        </button>
      ))}
      {muscle && <span className={s.muscleTip} style={{ transform: `translate(${muscle.x + 14}px, ${muscle.y - 10}px)` }}>{muscle.name}</span>}
      <div className={s.modes} role="radiogroup" aria-label="Body view">
        <button role="radio" aria-checked={mode === "anatomy"} onClick={() => pickMode("anatomy")}>Muscles</button>
        <button role="radio" aria-checked={mode === "nodes"} onClick={() => pickMode("nodes")}>Nodes</button>
      </div>
      <div className={s.controls}>
        <button type="button" onClick={() => control.current?.zoom(-0.5)} aria-label="Zoom in">+</button>
        <button type="button" onClick={() => control.current?.zoom(0.5)} aria-label="Zoom out">−</button>
        <button type="button" onClick={() => control.current?.reset()} aria-label="Reset view">⟲</button>
      </div>
      <p className={s.hint} aria-hidden="true">{mode === "anatomy" ? "Drag to turn · hover a muscle" : "Drag to turn"}</p>
    </div>
  );
}
