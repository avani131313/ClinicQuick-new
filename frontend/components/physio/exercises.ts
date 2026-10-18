/**
 * The exercises the camera coach understands. Each one says how to measure it from body landmarks
 * (MediaPipe Pose, 33 points, normalised image coordinates), when a rep counts, what to tell the person,
 * and two key poses for the guide figure drawn over them.
 */
export type LM = { x: number; y: number; z?: number; visibility?: number };
export type V2 = [number, number];
export type Joint = "head" | "lsh" | "rsh" | "lel" | "rel" | "lwr" | "rwr" | "lhip" | "rhip" | "lkn" | "rkn" | "lan" | "ran";
export type Pose = Record<Joint, V2>;

// MediaPipe landmark indices
export const I = { nose: 0, lsh: 11, rsh: 12, lel: 13, rel: 14, lwr: 15, rwr: 16, lhip: 23, rhip: 24, lkn: 25, rkn: 26, lan: 27, ran: 28 } as const;
export const BONES: [Joint, Joint][] = [
  ["lsh", "rsh"], ["lsh", "lel"], ["lel", "lwr"], ["rsh", "rel"], ["rel", "rwr"], ["lsh", "lhip"], ["rsh", "rhip"], ["lhip", "rhip"],
  ["lhip", "lkn"], ["lkn", "lan"], ["rhip", "rkn"], ["rkn", "ran"],
];

const vis = (p?: LM) => (p ? p.visibility ?? 1 : 0);
/** Angle at b (degrees) between a-b-c. */
export function angle(a: LM, b: LM, c: LM) {
  const v1 = [a.x - b.x, a.y - b.y], v2 = [c.x - b.x, c.y - b.y];
  const d = (v1[0] * v2[0] + v1[1] * v2[1]) / (Math.hypot(v1[0], v1[1]) * Math.hypot(v2[0], v2[1]) || 1);
  return (Math.acos(Math.max(-1, Math.min(1, d))) * 180) / Math.PI;
}
/** Average a measurement over the sides the camera can actually see. */
function sides(lm: LM[], f: (s: "l" | "r") => [number, number] | null) {
  const out = (["l", "r"] as const).map(f).filter(Boolean) as [number, number][];
  const good = out.filter(([, v]) => v > 0.5);
  const use = good.length ? good : out.filter(([, v]) => v > 0.3);
  if (!use.length) return null;
  return use.reduce((a, [x]) => a + x, 0) / use.length;
}
const side = (lm: LM[], s: "l" | "r", j: "sh" | "el" | "wr" | "hip" | "kn" | "an") => lm[I[`${s}${j}` as keyof typeof I]];
export function torsoLean(lm: LM[]) {
  const sh = { x: (lm[I.lsh].x + lm[I.rsh].x) / 2, y: (lm[I.lsh].y + lm[I.rsh].y) / 2 };
  const hp = { x: (lm[I.lhip].x + lm[I.rhip].x) / 2, y: (lm[I.lhip].y + lm[I.rhip].y) / 2 };
  return (Math.atan2(Math.abs(sh.x - hp.x), Math.abs(hp.y - sh.y)) * 180) / Math.PI;
}

// Guide poses, front view, in torso lengths (hip-centre to shoulder-centre = 1), y up, feet at 0.
const STAND: Pose = {
  head: [0, 3.5], lsh: [0.42, 3.05], rsh: [-0.42, 3.05], lel: [0.6, 2.52], rel: [-0.6, 2.52], lwr: [0.68, 2.02], rwr: [-0.68, 2.02],
  lhip: [0.22, 2.05], rhip: [-0.22, 2.05], lkn: [0.24, 1.02], rkn: [-0.24, 1.02], lan: [0.25, 0], ran: [-0.25, 0],
};
const P = (o: Partial<Pose>): Pose => ({ ...STAND, ...o });

export type Exercise = {
  key: string; name: string; cue: string; joint: "knee" | "shoulder" | "hip"; anchor: "feet" | "hips";
  measure: (lm: LM[]) => number | null; low: number; high: number; startsHigh: boolean;
  tips: (lm: LM[], value: number, phase: "rest" | "moving") => string | null;
  repTip: (extreme: number) => string | null;
  guide: [Pose, Pose]; jointFor: (lm: LM[]) => [LM, LM, LM] | null;
};

export const EXERCISES: Record<string, Exercise> = {
  squat: {
    key: "squat", name: "Sit-to-stand squat", cue: "Sit back like there's a chair behind you, then stand tall.", joint: "knee", anchor: "feet",
    measure: (lm) => sides(lm, (s) => [angle(side(lm, s, "hip"), side(lm, s, "kn"), side(lm, s, "an")), Math.min(vis(side(lm, s, "hip")), vis(side(lm, s, "kn")), vis(side(lm, s, "an")))]),
    low: 110, high: 158, startsHigh: true,
    tips: (lm, v, ph) => (ph === "moving" && torsoLean(lm) > 42 ? "Keep your chest up" : null),
    repTip: (min) => (min > 122 ? "Try to sit a little lower" : null),
    guide: [STAND, P({ head: [0, 2.6], lsh: [0.42, 2.18], rsh: [-0.42, 2.18], lel: [0.42, 1.95], rel: [-0.42, 1.95], lwr: [0.36, 1.88], rwr: [-0.36, 1.88],
      lhip: [0.25, 1.28], rhip: [-0.25, 1.28], lkn: [0.36, 0.98], rkn: [-0.36, 0.98] })],
    jointFor: (lm) => { const s = vis(lm[I.lkn]) >= vis(lm[I.rkn]) ? "l" : "r"; return [side(lm, s, "hip"), side(lm, s, "kn"), side(lm, s, "an")]; },
  },
  arm_raise: {
    key: "arm_raise", name: "Front arm raise", cue: "Arms straight, lift them up in front of you to overhead, then lower slowly.", joint: "shoulder", anchor: "hips",
    measure: (lm) => sides(lm, (s) => [angle(side(lm, s, "hip"), side(lm, s, "sh"), side(lm, s, "wr")), Math.min(vis(side(lm, s, "sh")), vis(side(lm, s, "wr")))]),
    low: 40, high: 145, startsHigh: false,
    tips: (lm) => {
      const el = sides(lm, (s) => [angle(side(lm, s, "sh"), side(lm, s, "el"), side(lm, s, "wr")), vis(side(lm, s, "el"))]);
      return el !== null && el < 140 ? "Keep your arms straight" : null;
    },
    repTip: (max) => (max < 155 ? "Lift a little higher if it's comfortable" : null),
    guide: [STAND, P({ lel: [0.46, 3.6], rel: [-0.46, 3.6], lwr: [0.44, 4.12], rwr: [-0.44, 4.12] })],
    jointFor: (lm) => { const s = vis(lm[I.lwr]) >= vis(lm[I.rwr]) ? "l" : "r"; return [side(lm, s, "hip"), side(lm, s, "sh"), side(lm, s, "wr")]; },
  },
  knee_raise: {
    key: "knee_raise", name: "Standing knee raise", cue: "Stand tall. Lift one knee to hip height, lower it, then the other.", joint: "hip", anchor: "hips",
    measure: (lm) => {
      const a = (["l", "r"] as const).map((s) => [angle(side(lm, s, "sh"), side(lm, s, "hip"), side(lm, s, "kn")), vis(side(lm, s, "kn"))] as const).filter(([, v]) => v > 0.4);
      return a.length ? Math.min(...a.map(([x]) => x)) : null;
    },
    low: 118, high: 160, startsHigh: true,
    tips: (lm, v, ph) => (torsoLean(lm) > 18 ? "Stand tall, don't lean back" : null),
    repTip: (min) => (min > 128 ? "Bring your knee up toward hip height" : null),
    guide: [STAND, P({ lkn: [0.26, 1.98], lan: [0.3, 1.05], lel: [0.55, 2.55], rel: [-0.55, 2.55] })],
    jointFor: (lm) => {
      const l = angle(lm[I.lsh], lm[I.lhip], lm[I.lkn]), r = angle(lm[I.rsh], lm[I.rhip], lm[I.rkn]);
      const s = l < r ? "l" : "r"; return [side(lm, s, "sh"), side(lm, s, "hip"), side(lm, s, "kn")];
    },
  },
};

/** Counts reps from a stream of angle values, with hysteresis so jitter doesn't double count. */
export function createRepCounter(ex: Exercise) {
  let phase: "rest" | "moving" = "rest", extreme = ex.startsHigh ? 180 : 0, reps = 0;
  return {
    get reps() { return reps; }, get phase() { return phase; },
    reset() { reps = 0; phase = "rest"; extreme = ex.startsHigh ? 180 : 0; },
    /** Returns the finished rep's extreme angle when a rep completes. */
    push(v: number): number | null {
      if (ex.startsHigh) {
        if (phase === "rest" && v < ex.low) { phase = "moving"; extreme = v; }
        if (phase === "moving") { extreme = Math.min(extreme, v); if (v > ex.high) { phase = "rest"; reps++; return extreme; } }
      } else {
        if (phase === "rest" && v > ex.high) { phase = "moving"; extreme = v; }
        if (phase === "moving") { extreme = Math.max(extreme, v); if (v < ex.low) { phase = "rest"; reps++; return extreme; } }
      }
      return null;
    },
  };
}

export const lerpPose = (a: Pose, b: Pose, t: number) =>
  Object.fromEntries((Object.keys(a) as Joint[]).map((k) => [k, [a[k][0] + (b[k][0] - a[k][0]) * t, a[k][1] + (b[k][1] - a[k][1]) * t]])) as Pose;

/** 0 → 1 → 0 over one rep, with holds at each end. */
export function tempo(t: number, period = 3.4) {
  const p = (t % period) / period;
  const e = (x: number) => (x < 0.5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2);
  if (p < 0.15) return 0;
  if (p < 0.45) return e((p - 0.15) / 0.3);
  if (p < 0.6) return 1;
  if (p < 0.9) return 1 - e((p - 0.6) / 0.3);
  return 0;
}
