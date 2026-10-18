/**
 * Loads the pre-built anatomy meshes (public/models/body-<sex>.bin, made by frontend/scripts/body/make_body.py)
 * and turns them into either a muscle figure (fibre shader, white tendons, baked ambient occlusion)
 * or a point cloud sampled from the same surface ("nodes").
 */
export type BodyData = {
  count: number; pos: Float32Array; st: Float32Array; nor: Float32Array; fib: Float32Array; attr: Uint8Array; index: Uint32Array; regions: string[];
};

const cache: Record<string, Promise<BodyData>> = {};

export function loadBody(sex: string, base = "/models"): Promise<BodyData> {
  const key = sex === "female" ? "female" : "male";
  if (!cache[key]) {
    cache[key] = Promise.all([
      fetch(`${base}/body-${key}.bin`).then((r) => { if (!r.ok) throw new Error("model " + r.status); return r.arrayBuffer(); }),
      fetch(`${base}/body-regions.json`).then((r) => r.json()),
    ]).then(([buf, regions]) => parse(buf, regions));
  }
  return cache[key];
}

function parse(buf: ArrayBuffer, regions: string[]): BodyData {
  const dv = new DataView(buf);
  const V = dv.getUint32(4, true), T = dv.getUint32(8, true);
  const mn = [dv.getFloat32(12, true), dv.getFloat32(16, true), dv.getFloat32(20, true)];
  const mx = [dv.getFloat32(24, true), dv.getFloat32(28, true), dv.getFloat32(32, true)];
  let o = 36;
  const q = new Uint16Array(buf.slice(o, o + V * 6)); o += V * 6;
  const sq = new Int16Array(buf.slice(o, o + V * 4)); o += V * 4;
  const nb = new Int8Array(buf, o, V * 3); o += V * 3;
  const fb = new Int8Array(buf, o, V * 3); o += V * 3;
  const attr = new Uint8Array(buf.slice(o, o + V * 4)); o += V * 4;
  o += (4 - (o % 4)) % 4;
  const index = new Uint32Array(buf.slice(o, o + T * 12));
  const pos = new Float32Array(V * 3), nor = new Float32Array(V * 3), fib = new Float32Array(V * 3), st = new Float32Array(V * 2);
  for (let i = 0; i < V * 2; i++) st[i] = sq[i] / 8000;
  for (let i = 0; i < V; i++) {
    for (let k = 0; k < 3; k++) {
      pos[i * 3 + k] = mn[k] + (q[i * 3 + k] / 65535) * (mx[k] - mn[k]);
      nor[i * 3 + k] = nb[i * 3 + k] / 127;
      fib[i * 3 + k] = fb[i * 3 + k] / 127;
    }
  }
  return { count: V, pos, st, nor, fib, attr, index, regions };
}

const MUSCLE_VERT = `
  attribute vec3 fibre; attribute vec4 attr; attribute vec2 stripe;
  uniform float uAppear;
  varying vec3 vN; varying vec3 vV; varying vec3 vObjN; varying vec3 vFib; varying vec3 vPos; varying vec4 vAttr; varying vec2 vSt;
  void main() {
    vPos = position; vSt = stripe; vObjN = normal; vFib = fibre; vAttr = attr;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vV = -mv.xyz; vN = normalize(normalMatrix * normal);
    gl_Position = projectionMatrix * mv;
  }`;

const MUSCLE_FRAG = `
  uniform vec3 uMuscle; uniform vec3 uMuscleDark; uniform vec3 uTendon; uniform vec3 uTissue; uniform vec3 uRim; uniform vec3 uEye;
  uniform float uHover; uniform float uAppear; uniform float uTissueIdx; uniform float uEyeIdx;
  varying vec3 vN; varying vec3 vV; varying vec3 vObjN; varying vec3 vFib; varying vec3 vPos; varying vec4 vAttr; varying vec2 vSt;
  void main() {
    // build-up: the figure fills in from the feet upward
    if (vPos.y > uAppear) discard;
    float region = floor(vAttr.x * 255.0 + 0.5);
    float tendon = vAttr.y;
    float ao = mix(0.35, 1.0, vAttr.z);
    // striation runs along each muscle; faded where it would alias (far away or at grazing angles)
    float u = vSt.x, v = vSt.y;
    float wob = sin(v * 60.0 + u * 30.0) * 0.6;
    float fb = fwidth(u * 520.0), ff = fwidth(u * 1500.0);
    float bundle = mix(0.5, 0.5 + 0.5 * sin(u * 520.0 + wob), clamp(1.6 - fb, 0.0, 1.0));
    float fine = mix(0.5, 0.5 + 0.5 * sin(u * 1500.0 + wob * 2.0), clamp(1.3 - ff, 0.0, 1.0));
    vec3 col = mix(uMuscleDark, uMuscle, 0.35 + 0.5 * bundle);
    col *= 0.84 + 0.16 * fine;
    vec3 tcol = uTendon * (0.92 + 0.08 * fine);
    col = mix(col, tcol, smoothstep(0.25, 0.8, tendon));
    if (abs(region - uTissueIdx) < 0.5) col = mix(col, uTissue, 0.35);
    if (abs(region - uEyeIdx) < 0.5) col = uEye;
    vec3 N = normalize(vN), V = normalize(vV);
    vec3 L1 = normalize(vec3(-0.45, 0.75, 0.6)), L2 = normalize(vec3(0.8, 0.1, 0.35)), L3 = normalize(vec3(0.0, -0.6, -0.4));
    float diff = max(dot(N, L1), 0.0) * 0.95 + max(dot(N, L2), 0.0) * 0.35 + max(dot(N, L3), 0.0) * 0.12 + 0.2;
    vec3 H = normalize(L1 + V);
    float spec = pow(max(dot(N, H), 0.0), 42.0) * (0.25 + 0.3 * tendon);
    float rim = pow(1.0 - max(dot(N, V), 0.0), 3.0);
    vec3 c = col * diff * ao + vec3(spec) * ao + uRim * rim * 0.18;
    if (abs(region - uHover) < 0.5) c += uRim * 0.32;
    float edge = smoothstep(uAppear - 0.03, uAppear, vPos.y);
    c = mix(c, uRim * 1.6, edge);
    gl_FragColor = vec4(c, 1.0);
  }`;

export function muscleMesh(THREE: any, d: BodyData, colors: { muscle: string; dark: string; tendon: string; tissue: string; rim: string }) {
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(d.pos, 3));
  g.setAttribute("normal", new THREE.BufferAttribute(d.nor, 3));
  g.setAttribute("fibre", new THREE.BufferAttribute(d.fib, 3));
  g.setAttribute("stripe", new THREE.BufferAttribute(d.st, 2));
  g.setAttribute("attr", new THREE.BufferAttribute(d.attr, 4, true));
  g.setIndex(new THREE.BufferAttribute(d.index, 1));
  g.computeBoundingSphere();
  // the shader writes colours straight to the screen, so keep them as authored (no sRGB→linear conversion)
  const col = (h: string) => new THREE.Color().setStyle(h, THREE.LinearSRGBColorSpace);
  const m = new THREE.ShaderMaterial({
    vertexShader: MUSCLE_VERT, fragmentShader: MUSCLE_FRAG,
    uniforms: {
      uMuscle: { value: col(colors.muscle) }, uMuscleDark: { value: col(colors.dark) },
      uTendon: { value: col(colors.tendon) }, uTissue: { value: col(colors.tissue) },
      uRim: { value: col(colors.rim) }, uEye: { value: col("#F6F2EA") },
      uHover: { value: -1 }, uAppear: { value: 10 },
      uTissueIdx: { value: 253 }, uEyeIdx: { value: 254 },
    },
  });
  return new THREE.Mesh(g, m);
}

/** Region name under a raycast hit (uses the first vertex of the hit face). */
export function regionAt(d: BodyData, faceA: number) {
  const id = d.attr[faceA * 4];
  return id === 254 ? "Eye" : id === 253 ? "Breast tissue" : d.regions[id] || null;
}
export const regionId = (d: BodyData, name: string) => (name === "Eye" ? 254 : name === "Breast tissue" ? 253 : d.regions.indexOf(name));

/** Points sampled from the same surface, for the "nodes" look. */
export function nodeSample(d: BodyData, n = 16000, seed = 7) {
  let x = seed;
  const r = () => ((x = (x * 16807) % 2147483647) / 2147483647);
  const pos = new Float32Array(n * 3), nor = new Float32Array(n * 3), rnd = new Float32Array(n);
  // sample uniformly over triangle area
  const T = d.index.length / 3;
  const cum = new Float64Array(T);
  let tot = 0;
  for (let t = 0; t < T; t++) {
    const a = d.index[t * 3] * 3, b = d.index[t * 3 + 1] * 3, c = d.index[t * 3 + 2] * 3;
    const ux = d.pos[b] - d.pos[a], uy = d.pos[b + 1] - d.pos[a + 1], uz = d.pos[b + 2] - d.pos[a + 2];
    const vx = d.pos[c] - d.pos[a], vy = d.pos[c + 1] - d.pos[a + 1], vz = d.pos[c + 2] - d.pos[a + 2];
    const cx = uy * vz - uz * vy, cy = uz * vx - ux * vz, cz = ux * vy - uy * vx;
    tot += Math.sqrt(cx * cx + cy * cy + cz * cz) / 2;
    cum[t] = tot;
  }
  for (let i = 0; i < n; i++) {
    const target = r() * tot;
    let lo = 0, hi = T - 1;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (cum[mid] < target) lo = mid + 1; else hi = mid; }
    let u = r(), v = r(); if (u + v > 1) { u = 1 - u; v = 1 - v; }
    const ids = [d.index[lo * 3] * 3, d.index[lo * 3 + 1] * 3, d.index[lo * 3 + 2] * 3];
    for (let k = 0; k < 3; k++) {
      pos[i * 3 + k] = d.pos[ids[0] + k] * (1 - u - v) + d.pos[ids[1] + k] * u + d.pos[ids[2] + k] * v;
      nor[i * 3 + k] = d.nor[ids[0] + k];
    }
    rnd[i] = r();
  }
  return { pos, nor, rnd };
}
