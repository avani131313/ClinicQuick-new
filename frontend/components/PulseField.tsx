"use client";

/**
 * A point cloud that morphs as the page scrolls: a slowly beating 3D heart becomes a
 * single heartbeat trace on a monitor line. Kept deliberately calm.
 * Canvas 2D only, ~1,400 points. Respects prefers-reduced-motion.
 */
import { useEffect, useRef } from "react";
import { HEART_COLOURS, loadHeart, type HeartData } from "./health/heart";

type P = { x: number; y: number; z: number };
const N = 1400;

function rand(seed: number) {
  let s = seed;
  return () => ((s = (s * 16807) % 2147483647) / 2147483647);
}

/** The anatomical heart (public/models/heart-points.json): chambers, aorta and its branches, venae cavae. */
function anatomicalHeart(data: HeartData, r: () => number): { pts: P[]; reg: number[] } {
  const pts: P[] = [], reg: number[] = [];
  for (let i = 0; i < N; i++) {
    const [x, y, z, g] = data.points[i % data.points.length];
    // y is up in the model, down on the canvas; tilt the apex down-left like a real heart in the chest
    pts.push({ x: x * 0.95 + (r() - 0.5) * 0.004, y: -y * 0.95, z: z * 0.95 });
    reg.push(g);
  }
  return { pts, reg };
}

function fromCanvas(draw: (c: CanvasRenderingContext2D, s: number) => void, r: () => number, depth = 0.06): P[] {
  const s = 220;
  const cv = document.createElement("canvas");
  cv.width = s; cv.height = s;
  const c = cv.getContext("2d")!;
  c.fillStyle = "#fff"; c.strokeStyle = "#fff";
  draw(c, s);
  const d = c.getImageData(0, 0, s, s).data;
  const px: [number, number][] = [];
  for (let y = 0; y < s; y += 2) for (let x = 0; x < s; x += 2) if (d[(y * s + x) * 4 + 3] > 120) px.push([x, y]);
  const out: P[] = [];
  for (let i = 0; i < N; i++) {
    const [x, y] = px[Math.floor(r() * px.length)] || [s / 2, s / 2];
    out.push({ x: (x + r() * 2 - s / 2) / (s / 2), y: (y + r() * 2 - s / 2) / (s / 2), z: (r() - 0.5) * depth });
  }
  return out;
}

function buildShapes(data: HeartData): { shapes: P[][]; reg: number[] } {
  const r = rand(7);
  const h = anatomicalHeart(data, r);
  // one heartbeat on a monitor line: flat, P wave, QRS spike, T wave, flat
  const ecg = fromCanvas((c, s) => {
    c.lineWidth = 4; c.lineJoin = "round"; c.lineCap = "round";
    const y0 = s * 0.56;
    const pts: [number, number][] = [
      [0.02, 0], [0.3, 0], [0.34, -0.05], [0.38, 0], [0.44, 0], [0.47, 0.06], [0.52, -0.4], [0.56, 0.16], [0.59, 0],
      [0.66, 0], [0.71, -0.09], [0.77, 0], [0.98, 0],
    ];
    c.beginPath();
    pts.forEach(([x, y], i) => (i ? c.lineTo(x * s, y0 + y * s) : c.moveTo(x * s, y0 + y * s)));
    c.stroke();
  }, r, 0.04);
  return { shapes: [h.pts, ecg], reg: h.reg };
}

// the heart is coloured by anatomy (arteries red, veins blue); the reading it becomes is the cool accent
const ACCENT_DARK = "#8EE3CB", ACCENT_LIGHT = "#0B7A65";

function hexToRgb(h: string) { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

export default function PulseField({ progress }: { progress: React.MutableRefObject<number> }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let alive = true, stop = () => {};
    loadHeart().then((data) => { if (alive) stop = run(data); }).catch(() => {});
    return () => { alive = false; stop(); };
  }, [progress]);

  function run(data: HeartData) {
    const cv = ref.current!;
    const ctx = cv.getContext("2d")!;
    const { shapes, reg } = buildShapes(data);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const jitter = Array.from({ length: N }, (_, i) => ((i * 9301 + 49297) % 233280) / 233280);
    let raf = 0, w = 0, h = 0, dpr = 1, shown = 0;
    const resize = () => {
      dpr = Math.min(2, window.devicePixelRatio || 1);
      w = cv.clientWidth; h = cv.clientHeight;
      cv.width = w * dpr; cv.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);
    const t0 = performance.now();
    const frame = (now: number) => {
      const t = (now - t0) / 1000;
      // smooth toward the scroll target so morphs glide
      const target = Math.max(0, Math.min(shapes.length - 1, progress.current));
      shown += (target - shown) * (reduce ? 1 : 0.06);
      const i0 = Math.floor(shown), i1 = Math.min(shapes.length - 1, i0 + 1);
      const f = reduce ? Math.round(shown - i0) : ease(shown - i0);
      const A = shapes[i0], B = shapes[i1];
      const light = document.documentElement.dataset.theme === "light";
      const accent = hexToRgb(light ? ACCENT_LIGHT : ACCENT_DARK);
      const pal = (light ? HEART_COLOURS.light : HEART_COLOURS.dark).map(hexToRgb);
      const isHeart = (k: number) => k === 0;
      const heartWeight = (isHeart(i0) ? 1 - f : 0) + (isHeart(i1) ? f : 0);
      const beatPhase = (t * 0.9) % 1;
      const beat = reduce ? 1 : 1 + heartWeight * (0.045 * Math.exp(-Math.pow((beatPhase - 0.1) / 0.05, 2)) + 0.025 * Math.exp(-Math.pow((beatPhase - 0.3) / 0.05, 2)));
      // the heart sways rather than spinning, so its outline stays readable
      const rot = reduce ? 0.2 : (Math.sin(t * 0.3) * 0.55 - 0.3) * heartWeight + 0.06 * Math.sin(t * 0.3) * (1 - heartWeight);
      const cos = Math.cos(rot), sin = Math.sin(rot);
      const desktop = w > 860;
      const cx = desktop ? w * 0.71 : w * 0.5;
      const cy = desktop ? h * 0.5 : h * 0.36;
      const scale = Math.min(w * (desktop ? 0.22 : 0.4), h * 0.28) * beat * (1 + (1 - heartWeight) * 0.25);
      ctx.clearRect(0, 0, w, h);
      for (let i = 0; i < N; i++) {
        const a = A[i], b = B[i];
        let x = a.x + (b.x - a.x) * f, y = a.y + (b.y - a.y) * f, z = a.z + (b.z - a.z) * f;
        if (!reduce) { const j = jitter[i]; x += Math.sin(t * 0.6 + j * 40) * 0.003; y += Math.cos(t * 0.5 + j * 31) * 0.003; }
        const rx = x * cos + z * sin, rz = -x * sin + z * cos;
        const persp = 1 / (1.6 - rz * 0.5);
        const sx = cx + rx * scale * persp * 1.6, sy = cy + y * scale * persp * 1.6;
        const sweep = reduce ? 0 : Math.exp(-Math.pow((x + 1) / 2 - ((t * 0.35) % 1.2), 2) / 0.004) * (1 - heartWeight);
        const alpha = Math.min(1, 0.22 + heartWeight * 0.2 + 0.55 * Math.max(0, Math.min(1, (rz + 1) / 2)) + sweep * 0.6);
        const size = (1 + persp * 1.3 + sweep * 1.2) * (desktop ? 1 : 0.9) * (1 + heartWeight * 0.6);
        const hc = pal[reg[i]] || pal[0];
        const col = [0, 1, 2].map((k) => Math.round(accent[k] + (hc[k] - accent[k]) * heartWeight));
        ctx.fillStyle = `rgba(${col[0]},${col[1]},${col[2]},${alpha.toFixed(2)})`;
        ctx.fillRect(sx, sy, size, size);
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", resize); };
  }
  return <canvas ref={ref} aria-hidden="true" style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} />;
}
