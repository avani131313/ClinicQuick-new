"use client";

/**
 * Camera coach. Tracks the person with MediaPipe Pose (runs in the browser, nothing is uploaded),
 * draws their skeleton over the live camera, overlays a guide figure doing the exercise at the right tempo,
 * counts reps from joint angles and gives form tips out loud.
 * "Practice with the guide" runs the same overlay on a demo figure when there's no camera.
 */
import { useEffect, useRef, useState } from "react";
import { cssVar } from "@/lib/theme";
import { BONES, EXERCISES, I, type Joint, type LM, type Pose, angle, createRepCounter, lerpPose, tempo } from "./exercises";
import s from "./coach.module.css";

const MP = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";
const MODEL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task";
const REST_S = 20;

type Mode = "idle" | "loading" | "camera" | "demo" | "error";
type Hud = { reps: number; set: number; angle: number | null; tip: string | null; inView: boolean; rest: number; done: boolean };

let landmarkerPromise: Promise<any> | null = null;
async function getLandmarker() {
  if (!landmarkerPromise) landmarkerPromise = (async () => {
    const url = `${MP}/vision_bundle.mjs`;
    const vision: any = await import(/* webpackIgnore: true */ url);
    const files = await vision.FilesetResolver.forVisionTasks(`${MP}/wasm`);
    const make = (delegate: "GPU" | "CPU") => vision.PoseLandmarker.createFromOptions(files, {
      baseOptions: { modelAssetPath: MODEL, delegate }, runningMode: "VIDEO", numPoses: 1,
    });
    try { return await make("GPU"); } catch { return await make("CPU"); }
  })().catch((e) => { landmarkerPromise = null; throw e; });
  return landmarkerPromise;
}

function speak(text: string) {
  try { const u = new SpeechSynthesisUtterance(text); u.rate = 1.05; window.speechSynthesis.cancel(); window.speechSynthesis.speak(u); } catch {}
}

/** Demo figure: follows the guide a beat behind, and every third rep is a bit shallow so the coach has something to say. */
function demoLandmarks(guide: [Pose, Pose], t: number, aspect: number): LM[] {
  const rep = Math.floor((t - 0.35) / 3.4);
  const depth = rep % 3 === 2 ? 0.55 : 1;
  const p = lerpPose(guide[0], guide[1], tempo(Math.max(0, t - 0.35)) * depth);
  const sc = 0.22, fx = 0.5, fy = 0.93;
  const lm: LM[] = Array.from({ length: 33 }, () => ({ x: 0.5, y: 0.5, visibility: 0 }));
  const put = (i: number, j: Joint) => {
    const n = Math.sin(t * 7 + i) * 0.002;
    lm[i] = { x: fx + (p[j][0] * sc) / aspect + n, y: fy - p[j][1] * sc + n, visibility: 0.98 };
  };
  (Object.keys(I) as (keyof typeof I)[]).forEach((k) => put(I[k], (k === "nose" ? "head" : k) as Joint));
  return lm;
}

export default function PoseCoach({ exerciseKey, reps, sets, voice, onComplete }: {
  exerciseKey: string; reps: number; sets: number; voice: boolean; onComplete?: () => void;
}) {
  const ex = EXERCISES[exerciseKey];
  const canvas = useRef<HTMLCanvasElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const [mode, setMode] = useState<Mode>("idle");
  const [err, setErr] = useState("");
  const [hud, setHud] = useState<Hud>({ reps: 0, set: 1, angle: null, tip: null, inView: true, rest: 0, done: false });
  const voiceRef = useRef(voice); voiceRef.current = voice;
  const doneRef = useRef(onComplete); doneRef.current = onComplete;

  function stopCamera() { stream.current?.getTracks().forEach((t) => t.stop()); stream.current = null; }
  useEffect(() => () => stopCamera(), []);
  useEffect(() => { setHud({ reps: 0, set: 1, angle: null, tip: null, inView: true, rest: 0, done: false }); }, [exerciseKey]);

  async function startCamera() {
    setErr(""); setMode("loading");
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
      const v = video.current!; v.srcObject = stream.current; await v.play();
      await getLandmarker();
      setMode("camera");
      if (voiceRef.current) speak(`${ex.name}. ${ex.cue}`);
    } catch (e: any) {
      stopCamera();
      setErr(e?.name === "NotAllowedError" ? "Camera access was blocked. Allow the camera for this site, or practise with the guide."
        : !navigator.mediaDevices ? "The camera needs a secure (https) connection on this device. You can still practise with the guide."
        : "Couldn't start the camera coach. Check your connection, or practise with the guide.");
      setMode("error");
    }
  }
  function startDemo() { stopCamera(); setErr(""); setMode("demo"); if (voiceRef.current) speak(`${ex.name}. ${ex.cue}`); }
  function stop() { stopCamera(); setMode("idle"); }

  useEffect(() => {
    if (mode !== "camera" && mode !== "demo") return;
    const cv = canvas.current!; const ctx = cv.getContext("2d")!;
    const counter = createRepCounter(ex);
    let raf = 0, set = 1, restUntil = 0, done = false, lastTip = "", lastTipAt = 0, lastHud = 0, lastTs = -1;
    let tip: string | null = null, tipUntil = 0, inView = true, ang: number | null = null;
    const t0 = performance.now();
    let landmarker: any = null;
    if (mode === "camera") getLandmarker().then((l) => (landmarker = l));
    const say = (txt: string) => { if (voiceRef.current) speak(txt); };
    const showTip = (txt: string, now: number) => {
      tip = txt; tipUntil = now + 2600;
      if (txt !== lastTip || now - lastTipAt > 6000) { say(txt); lastTip = txt; lastTipAt = now; }
    };

    const frame = (now: number) => {
      const t = (now - t0) / 1000;
      const dpr = Math.min(2, devicePixelRatio || 1), w = cv.clientWidth, h = cv.clientHeight;
      if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const accent = cssVar("--accent", "#8EE3CB"), text = "#FFFFFF";

      // ---- background + landmarks in canvas pixels
      let pts: { x: number; y: number; v: number }[] | null = null;
      let raw: LM[] | null = null;
      if (mode === "camera") {
        const v = video.current!;
        const vw = v.videoWidth || 1280, vh = v.videoHeight || 720;
        const k = Math.max(w / vw, h / vh), dx = (w - vw * k) / 2, dy = (h - vh * k) / 2;
        ctx.save(); ctx.translate(w, 0); ctx.scale(-1, 1); ctx.drawImage(v, dx, dy, vw * k, vh * k); ctx.restore();
        ctx.fillStyle = "rgba(4,12,12,.28)"; ctx.fillRect(0, 0, w, h);
        if (landmarker && v.readyState >= 2 && v.currentTime !== lastTs) {
          lastTs = v.currentTime;
          const res = landmarker.detectForVideo(v, now);
          raw = res?.landmarks?.[0] || null;
        }
        if (raw) pts = raw.map((p) => ({ x: w - (p.x * vw * k + dx), y: p.y * vh * k + dy, v: p.visibility ?? 1 }));
      } else {
        const g = ctx.createRadialGradient(w / 2, h * 0.45, 10, w / 2, h * 0.45, Math.max(w, h) * 0.7);
        g.addColorStop(0, "#0E2422"); g.addColorStop(1, "#050B0C");
        ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
        ctx.strokeStyle = "rgba(142,227,203,.06)"; ctx.lineWidth = 1;
        for (let x = (w % 40) / 2; x < w; x += 40) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke(); }
        for (let y = (h % 40) / 2; y < h; y += 40) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke(); }
        raw = demoLandmarks(ex.guide, t, w / h);
        pts = raw.map((p) => ({ x: p.x * w, y: p.y * h, v: p.visibility ?? 1 }));
      }

      const J = (j: Joint) => pts![I[j === "head" ? "nose" : j]];
      inView = !!pts && ["lsh", "rsh", "lhip", "rhip", "lkn", "rkn", "lan", "ran"].some((j) => J(j as Joint).v > 0.5) &&
        (ex.anchor === "hips" || (J("lan").v > 0.4 || J("ran").v > 0.4));

      // ---- guide figure, anchored to the person's feet or hips and scaled to their torso
      if (pts && inView) {
        const mid = (a: Joint, b: Joint) => ({ x: (J(a).x + J(b).x) / 2, y: (J(a).y + J(b).y) / 2 });
        const sh = mid("lsh", "rsh"), hp = mid("lhip", "rhip");
        const torso = Math.max(30, Math.hypot(sh.x - hp.x, sh.y - hp.y));
        const anchor = ex.anchor === "feet" ? mid("lan", "ran") : hp;
        const ref = ex.anchor === "feet" ? [0, 0] : [0, ex.guide[0].lhip[1]];
        const gp = lerpPose(ex.guide[0], ex.guide[1], tempo(t));
        const G = (j: Joint) => ({ x: anchor.x + (gp[j][0] - ref[0]) * torso, y: anchor.y - (gp[j][1] - ref[1]) * torso });
        ctx.save();
        ctx.setLineDash([7, 7]); ctx.lineWidth = 3; ctx.lineCap = "round"; ctx.strokeStyle = "rgba(255,255,255,.42)";
        BONES.forEach(([a, b]) => { const A = G(a), B = G(b); ctx.beginPath(); ctx.moveTo(A.x, A.y); ctx.lineTo(B.x, B.y); ctx.stroke(); });
        ctx.setLineDash([]);
        const hd = G("head"); ctx.beginPath(); ctx.arc(hd.x, hd.y, torso * 0.2, 0, 7); ctx.stroke();
        ctx.fillStyle = "rgba(255,255,255,.75)"; ctx.font = "600 12px " + cssVar("--mono", "monospace");
        ctx.fillText("GUIDE", hd.x + torso * 0.26, hd.y - 4);
        ctx.restore();
      }

      // ---- the person's skeleton
      if (pts && inView) {
        ctx.save();
        ctx.lineCap = "round"; ctx.shadowColor = accent; ctx.shadowBlur = 14;
        BONES.forEach(([a, b]) => {
          const A = J(a), B = J(b); if (A.v < 0.35 || B.v < 0.35) return;
          ctx.strokeStyle = accent; ctx.lineWidth = 5; ctx.beginPath(); ctx.moveTo(A.x, A.y); ctx.lineTo(B.x, B.y); ctx.stroke();
        });
        // head and neck, sized from the shoulders
        {
          const ls = J("lsh"), rs = J("rsh"), nose = J("head");
          if (nose.v > 0.4 && ls.v > 0.35 && rs.v > 0.35) {
            const shw = Math.hypot(ls.x - rs.x, ls.y - rs.y);
            const nk = { x: (ls.x + rs.x) / 2, y: (ls.y + rs.y) / 2 };
            ctx.strokeStyle = accent; ctx.lineWidth = 5;
            ctx.beginPath(); ctx.moveTo(nk.x, nk.y); ctx.lineTo(nose.x + (nk.x - nose.x) * 0.45, nose.y + (nk.y - nose.y) * 0.45); ctx.stroke();
            ctx.lineWidth = 3.5; ctx.beginPath(); ctx.arc(nose.x, nose.y, Math.max(12, shw * 0.32), 0, 7); ctx.stroke();
          }
        }
        ctx.shadowBlur = 0;
        (["lsh", "rsh", "lel", "rel", "lwr", "rwr", "lhip", "rhip", "lkn", "rkn", "lan", "ran"] as Joint[]).forEach((j) => {
          const p = J(j); if (p.v < 0.35) return;
          ctx.fillStyle = "#06201B"; ctx.beginPath(); ctx.arc(p.x, p.y, 7, 0, 7); ctx.fill();
          ctx.strokeStyle = accent; ctx.lineWidth = 2.5; ctx.stroke();
        });
        // the joint being measured: an arc and the live angle
        const tri = raw && ex.jointFor(raw);
        if (tri) {
          const toPx = (p: LM) => pts![raw!.indexOf(p)];
          const [a, b, c] = tri.map(toPx);
          if (a && b && c) {
            const a1 = Math.atan2(a.y - b.y, a.x - b.x), a2 = Math.atan2(c.y - b.y, c.x - b.x);
            let d = a2 - a1; while (d > Math.PI) d -= 2 * Math.PI; while (d < -Math.PI) d += 2 * Math.PI;
            ctx.strokeStyle = text; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(b.x, b.y, 30, a1, a1 + d, d < 0); ctx.stroke();
            const deg = Math.round(angle(tri[0], tri[1], tri[2]));
            ctx.font = "600 15px " + cssVar("--mono", "monospace"); ctx.fillStyle = text;
            ctx.fillText(`${deg}°`, b.x + 38, b.y + 5);
          }
        }
        ctx.restore();
      }

      // ---- counting, sets, tips
      if (!done && now >= restUntil && pts && inView && raw) {
        const v = ex.measure(raw);
        ang = v;
        if (v !== null) {
          const ext = counter.push(v);
          if (ext !== null) {
            const n = counter.reps;
            const rt = ex.repTip(ext);
            if (rt) showTip(rt, now); else { tip = "Good rep"; tipUntil = now + 1200; }
            if (n >= reps) {
              if (set >= sets) { done = true; say("All done. Great work."); doneRef.current?.(); }
              else { say(`Set ${set} done. Rest for ${REST_S} seconds.`); restUntil = now + REST_S * 1000; set++; counter.reset(); }
            } else say(String(n));
          } else {
            const ft = ex.tips(raw, v, counter.phase);
            if (ft && now > tipUntil) showTip(ft, now);
          }
        }
      } else if (!inView && now > tipUntil) { tip = null; }
      if (now > tipUntil && tip) tip = null;

      if (now - lastHud > 100) {
        lastHud = now;
        setHud({ reps: counter.reps, set, angle: ang === null ? null : Math.round(ang), tip, inView, rest: Math.max(0, Math.ceil((restUntil - now) / 1000)), done });
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [mode, exerciseKey, reps, sets]); // eslint-disable-line react-hooks/exhaustive-deps

  const live = mode === "camera" || mode === "demo";
  return (
    <div className={s.stage}>
      <video ref={video} playsInline muted className={s.video} />
      <canvas ref={canvas} className={s.canvas} aria-label={`Camera coach for ${ex.name}`} role="img" />
      {!live && (
        <div className={s.start}>
          <p className="eyebrow">Camera coach</p>
          <h2>{ex.name}</h2>
          <p className={s.cue}>{ex.cue}</p>
          <p className="small">Stand 2 to 3 metres from the camera so your whole body is in view. Video stays on your device.</p>
          <div className={s.startBtns}>
            <button className="btn" onClick={startCamera} disabled={mode === "loading"}>{mode === "loading" ? "Starting camera…" : "Start camera"}</button>
            <button className="btn ghost" onClick={startDemo}>Practice with the guide</button>
          </div>
          {err && <p className="error" role="alert">{err}</p>}
        </div>
      )}
      {live && (
        <>
          <div className={s.hudTop}>
            <div className={s.hudName}><span className={s.rec} data-demo={mode === "demo" || undefined}>{mode === "demo" ? "Guide demo" : "Live"}</span><strong>{ex.name}</strong></div>
            <button className={s.stop} onClick={stop}>Stop</button>
          </div>
          <div className={s.counter}>
            <span className={`num ${s.reps}`}>{hud.reps}<small>/{reps}</small></span>
            <span className={s.setLbl}>Set {hud.set} of {sets}</span>
          </div>
          {hud.angle !== null && (
            <div className={s.gauge} aria-label={`${ex.joint} angle ${hud.angle} degrees`}>
              <span>{ex.joint} angle</span><strong className="num">{hud.angle}°</strong>
              <i style={{ height: `${Math.min(100, (hud.angle / 180) * 100)}%` }} />
            </div>
          )}
          {(!hud.inView || hud.tip || hud.rest > 0 || hud.done) && (
            <div className={s.tip} data-kind={hud.done ? "done" : hud.rest ? "rest" : !hud.inView ? "warn" : hud.tip === "Good rep" ? "good" : "tip"} role="status">
              {hud.done ? "All sets done. Great work." : hud.rest ? `Rest · next set in ${hud.rest}s` : !hud.inView ? "Step back so your whole body is in view" : hud.tip}
            </div>
          )}
          <p className={s.legend}><span className={s.lYou} /> You <span className={s.lGuide} /> Guide</p>
        </>
      )}
    </div>
  );
}
