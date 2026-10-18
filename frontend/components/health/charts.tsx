"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { cssVar } from "@/lib/theme";
import s from "./charts.module.css";

type Pt = { day: string; value: number };

const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);
export const fmt = (v: number | null | undefined, dp = 0) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : v.toLocaleString("en-CA", { minimumFractionDigits: dp, maximumFractionDigits: dp });

/** A monitor trace that sweeps at the current heart rate. With `live`, the number breathes around the latest reading. */
export function LiveHeart({ base, live, source, onBpm }: { base: number | null; live: boolean; source: string; onBpm?: (b: number) => void }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [bpm, setBpm] = useState<number | null>(base);
  const bpmRef = useRef(base || 70);

  useEffect(() => { setBpm(base); bpmRef.current = base || 70; if (base) onBpm?.(base); }, [base]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!live || !base) return;
    const id = setInterval(() => {
      const next = Math.round(Math.max(base - 6, Math.min(base + 6, bpmRef.current + (Math.random() - 0.5) * 4)));
      bpmRef.current = next; setBpm(next); onBpm?.(next);
    }, 2200);
    return () => clearInterval(id);
  }, [live, base]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const cv = ref.current!;
    const ctx = cv.getContext("2d")!;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0, x = 0, phase = 0, last = performance.now(), w = 0, h = 0, prevY = 0;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const resize = () => { w = cv.clientWidth; h = cv.clientHeight; cv.width = w * dpr; cv.height = h * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h); x = 0; prevY = h * 0.6; };
    resize();
    const ro = new ResizeObserver(resize); ro.observe(cv);
    // one PQRST complex as a function of beat phase (0..1)
    const wave = (p: number) =>
      0.08 * Math.exp(-Math.pow((p - 0.12) / 0.025, 2)) - 0.1 * Math.exp(-Math.pow((p - 0.22) / 0.008, 2)) +
      1.0 * Math.exp(-Math.pow((p - 0.245) / 0.009, 2)) - 0.25 * Math.exp(-Math.pow((p - 0.27) / 0.01, 2)) +
      0.2 * Math.exp(-Math.pow((p - 0.45) / 0.04, 2));
    const speed = 110; // px per second
    let pen = cssVar("--pulse", "#FF7B6B"), penAt = 0;
    const frame = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000); last = now;
      if (now - penAt > 500) { pen = cssVar("--pulse", "#FF7B6B"); penAt = now; }
      const steps = Math.max(1, Math.round(speed * dt));
      for (let i = 0; i < steps; i++) {
        phase += (bpmRef.current / 60) / speed;
        const y = h * 0.62 - wave(phase % 1) * h * 0.48;
        ctx.clearRect(x + 1, 0, 14, h);              // erase just ahead of the pen
        ctx.strokeStyle = pen; ctx.lineWidth = 1.8; ctx.lineJoin = "round";
        ctx.beginPath(); ctx.moveTo(x, prevY); ctx.lineTo(x + 1, y); ctx.stroke();
        prevY = y; x += 1;
        if (x > w) { x = 0; }
      }
      // pen glow
      ctx.save(); ctx.clearRect(x + 1, 0, 14, h); ctx.restore();
      if (!reduce) raf = requestAnimationFrame(frame);
    };
    if (reduce) { for (let i = 0; i < 400; i++) frame(last + 16 * i); } else raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); };
  }, []);

  return (
    <div className={s.live}>
      <div className={s.liveHead}>
        <span className={s.liveLabel}>{live ? <><span className={s.rec} aria-hidden="true" />Live</> : "Latest"} heart rate</span>
        <span className={s.liveSource}>{source}</span>
      </div>
      <div className={s.liveRow}>
        <p className={s.liveValue} aria-live="off"><span className="num">{bpm ?? "—"}</span><small>bpm</small></p>
        <canvas ref={ref} className={s.trace} aria-hidden="true" />
      </div>
    </div>
  );
}

export function Spark({ points, color = "var(--accent)", height = 40 }: { points: Pt[]; color?: string; height?: number }) {
  const id = useMemo(() => "g" + Math.random().toString(36).slice(2, 8), []);
  if (!points || points.length < 2) return <div style={{ height }} />;
  const vals = points.map((p) => p.value);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const W = 200, H = height;
  const x = (i: number) => (i / (points.length - 1)) * W;
  const y = (v: number) => H - 3 - ((v - lo) / (hi - lo || 1)) * (H - 8);
  const d = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className={s.spark} style={{ height }} aria-hidden="true">
      <defs><linearGradient id={id} x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={color} stopOpacity=".22" /><stop offset="1" stopColor={color} stopOpacity="0" /></linearGradient></defs>
      <path d={`${d} L${W},${H} L0,${H} Z`} fill={`url(#${id})`} />
      <path d={d} fill="none" stroke={color} strokeWidth="1.6" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    </svg>
  );
}

export function Metric({ label, value, unit, points, dp = 0, color, tone, id, active, better }: {
  label: string; value: number | null | undefined; unit?: string; points?: Pt[]; dp?: number; color?: string;
  tone?: string; id?: string; active?: boolean; better?: "up" | "down";
}) {
  const usual = points && points.length > 3 ? mean(points.slice(0, -1).map((p) => p.value)) : null;
  const delta = usual && value !== null && value !== undefined ? ((value - usual) / usual) * 100 : null;
  const dir = delta === null || Math.abs(delta) < 3 ? "flat" : delta > 0 ? "up" : "down";
  const good = dir === "flat" || !better ? "neutral" : dir === better ? "good" : "bad";
  return (
    <section className={`${s.metric} ${active ? s.metricOn : ""}`} id={id} data-tone={tone}>
      <h3 className={s.mLabel}>{label}</h3>
      <p className={s.mValue}><span className="num">{fmt(value, dp)}</span>{unit && <small>{unit}</small>}</p>
      {delta !== null && (
        <p className={s.mDelta} data-good={good}>
          {dir === "flat" ? "Steady" : `${dir === "up" ? "↑" : "↓"} ${Math.abs(delta).toFixed(0)}%`} <span>vs 30-day usual</span>
        </p>
      )}
      {points && <Spark points={points} color={color} />}
    </section>
  );
}

/** Heart rate over the last 24 hours, with sleep hours shaded. */
export function DayHeart({ data }: { data: { ts: string; value: number }[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (!data.length) return <p className="muted">No heart-rate samples in the last 24 hours.</p>;
  const W = 1000, H = 200, padL = 34, padB = 22;
  const t0 = new Date(data[0].ts).getTime(), t1 = new Date(data[data.length - 1].ts).getTime();
  const vals = data.map((d) => d.value);
  const lo = Math.floor(Math.min(...vals) / 10) * 10, hi = Math.ceil(Math.max(...vals) / 10) * 10;
  const x = (t: number) => padL + ((t - t0) / (t1 - t0 || 1)) * (W - padL - 6);
  const y = (v: number) => 8 + (1 - (v - lo) / (hi - lo || 1)) * (H - padB - 14);
  const pts = data.map((d) => [x(new Date(d.ts).getTime()), y(d.value)] as const);
  const line = pts.map(([a, b], i) => `${i ? "L" : "M"}${a.toFixed(1)},${b.toFixed(1)}`).join(" ");
  const ticks = [lo, Math.round((lo + hi) / 2), hi];
  const hours: number[] = [];
  for (let t = Math.ceil(t0 / 21600000) * 21600000; t <= t1; t += 21600000) hours.push(t);
  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    let best = 0; for (let i = 0; i < pts.length; i++) if (Math.abs(pts[i][0] - px) < Math.abs(pts[best][0] - px)) best = i;
    setHover(best);
  };
  const hv = hover !== null ? data[hover] : null;
  return (
    <div className={s.chartWrap}>
      <svg viewBox={`0 0 ${W} ${H}`} className={s.chart} onPointerMove={onMove} onPointerLeave={() => setHover(null)} role="img" aria-label="Heart rate over the last 24 hours">
        <defs><linearGradient id="hrfill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="var(--pulse)" stopOpacity=".28" /><stop offset="1" stopColor="var(--pulse)" stopOpacity="0" /></linearGradient></defs>
        {ticks.map((t) => <g key={t}><line x1={padL} x2={W} y1={y(t)} y2={y(t)} className={s.grid} /><text x={padL - 8} y={y(t) + 4} className={s.axis} textAnchor="end">{t}</text></g>)}
        {hours.map((t) => <text key={t} x={x(t)} y={H - 4} className={s.axis} textAnchor="middle">{new Date(t).toLocaleTimeString("en-CA", { hour: "numeric" })}</text>)}
        <path d={`${line} L${pts[pts.length - 1][0]},${H - padB} L${pts[0][0]},${H - padB} Z`} fill="url(#hrfill)" />
        <path d={line} fill="none" stroke="var(--pulse)" strokeWidth="1.6" strokeLinejoin="round" />
        {hover !== null && <><line x1={pts[hover][0]} x2={pts[hover][0]} y1={8} y2={H - padB} className={s.cursor} /><circle cx={pts[hover][0]} cy={pts[hover][1]} r={4} fill="var(--pulse)" /></>}
      </svg>
      <p className={s.readout}>
        {hv ? <><span className="num">{hv.value}</span> bpm at {new Date(hv.ts).toLocaleTimeString("en-CA", { hour: "numeric", minute: "2-digit" })}</>
            : <>Range <span className="num">{Math.min(...vals)}–{Math.max(...vals)}</span> bpm, average <span className="num">{Math.round(mean(vals))}</span></>}
      </p>
    </div>
  );
}

/** Daily bars for the last two weeks, with the person's own average as a dashed line. */
export function Bars({ points, color = "var(--accent)", unit, scale = 1, dp = 0, days = 14 }: { points: Pt[]; color?: string; unit: string; scale?: number; dp?: number; days?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const p = (points || []).slice(-days);
  if (!p.length) return <p className="muted">No data yet.</p>;
  const vals = p.map((d) => d.value * scale);
  const hi = Math.max(...vals) * 1.1 || 1, avg = mean(vals);
  const W = 360, H = 150, gap = 5, bw = (W - gap * (p.length - 1)) / p.length;
  const y = (v: number) => H - 20 - (v / hi) * (H - 30);
  return (
    <div className={s.chartWrap}>
      <svg viewBox={`0 0 ${W} ${H}`} className={s.chart} role="img" aria-label={`Last ${p.length} days`} onPointerLeave={() => setHover(null)}>
        {p.map((d, i) => {
          const v = vals[i];
          return (
            <g key={d.day} onPointerEnter={() => setHover(i)}>
              <rect x={i * (bw + gap)} y={0} width={bw} height={H - 20} fill="transparent" />
              <rect x={i * (bw + gap)} y={y(v)} width={bw} height={H - 20 - y(v)} rx={3} fill={color} opacity={hover === null || hover === i ? (i === p.length - 1 ? 1 : 0.55) : 0.25} className={s.bar} style={{ animationDelay: `${i * 25}ms` }} />
              {((i % 3 === 0 && i < p.length - 2) || i === p.length - 1) && <text x={i * (bw + gap) + bw / 2} y={H - 5} textAnchor="middle" className={s.axis}>{new Date(d.day + "T12:00:00").toLocaleDateString("en-CA", { day: "numeric", month: "short" })}</text>}
            </g>
          );
        })}
        <line x1={0} x2={W} y1={y(avg)} y2={y(avg)} className={s.avg} />
      </svg>
      <p className={s.readout}>
        {hover !== null ? <><span className="num">{fmt(vals[hover], dp)}</span> {unit} on {new Date(p[hover].day + "T12:00:00").toLocaleDateString("en-CA", { weekday: "short", month: "short", day: "numeric" })}</>
          : <>Average <span className="num">{fmt(avg, dp)}</span> {unit}</>}
      </p>
    </div>
  );
}

/** Home blood pressure readings: a range line from diastolic to systolic per reading. */
export function Pressure({ sys, dia }: { sys: Pt[]; dia: Pt[] }) {
  if (!sys?.length) return <p className="muted">No blood pressure readings.</p>;
  const pairs = sys.map((p) => ({ day: p.day, s: p.value, d: dia.find((q) => q.day === p.day)?.value ?? null })).slice(-12);
  const W = 360, H = 150, lo = 50, hi = 170, padL = 28;
  const y = (v: number) => 8 + (1 - (v - lo) / (hi - lo)) * (H - 28);
  const step = (W - padL) / pairs.length;
  return (
    <div className={s.chartWrap}>
      <svg viewBox={`0 0 ${W} ${H}`} className={s.chart} role="img" aria-label="Home blood pressure readings">
        <rect x={padL} y={y(130)} width={W - padL} height={y(80) - y(130)} className={s.band} />
        {[80, 120, 140].map((t) => <g key={t}><line x1={padL} x2={W} y1={y(t)} y2={y(t)} className={s.grid} /><text x={padL - 6} y={y(t) + 3} textAnchor="end" className={s.axis}>{t}</text></g>)}
        {pairs.map((p, i) => {
          const cx = padL + step * i + step / 2;
          const high = p.s >= 135 || (p.d ?? 0) >= 85;
          return (
            <g key={p.day}>
              {p.d !== null && <line x1={cx} x2={cx} y1={y(p.s)} y2={y(p.d)} stroke={high ? "var(--amber)" : "var(--accent)"} strokeWidth="2" opacity=".55" />}
              <circle cx={cx} cy={y(p.s)} r="3.5" fill={high ? "var(--amber)" : "var(--accent)"} />
              {p.d !== null && <circle cx={cx} cy={y(p.d)} r="3.5" fill="none" stroke={high ? "var(--amber)" : "var(--accent)"} strokeWidth="1.5" />}
            </g>
          );
        })}
      </svg>
      <p className={s.readout}>Latest <span className="num">{fmt(pairs.at(-1)!.s)}/{fmt(pairs.at(-1)!.d)}</span> mmHg. Shaded band is a typical home range.</p>
    </div>
  );
}

const WEEK: [string, string, number, "up" | "down", string][] = [
  ["steps", "Steps", 1, "up", ""], ["sleep_min", "Sleep", 1 / 60, "up", " h"], ["rhr", "Resting heart rate", 1, "down", " bpm"],
  ["hrv", "Heart rate variability", 1, "up", " ms"], ["spo2", "Blood oxygen", 1, "up", "%"], ["bp_sys", "Systolic pressure", 1, "down", " mmHg"],
];

/** Plain-language changes: the last 7 days against the person's own previous 3 weeks. Computed, not AI. */
export function WeekChanges({ series }: { series: Record<string, Pt[]> }) {
  const rows = WEEK.flatMap(([code, label, k, better, unit]) => {
    const p = series[code] || [];
    if (p.length < 10) return [];
    const recent = mean(p.slice(-7).map((x) => x.value * k)), before = mean(p.slice(0, -7).map((x) => x.value * k));
    if (!before) return [];
    const ch = ((recent - before) / before) * 100;
    return [{ code, label, ch, recent, before, unit, good: Math.abs(ch) < 5 ? "flat" : (ch > 0) === (better === "up") ? "good" : "bad" }];
  }).sort((a, b) => Math.abs(b.ch) - Math.abs(a.ch));
  if (!rows.length) return <p className="muted">Needs about two weeks of data.</p>;
  return (
    <ul className={s.week}>
      {rows.slice(0, 4).map((r) => (
        <li key={r.code} data-good={r.good}>
          <span className={s.wLabel}>{r.label}</span>
          <span className={s.wBar} aria-hidden="true"><span style={{ width: `${Math.min(100, Math.abs(r.ch) * 2)}%` }} /></span>
          <span className={s.wVal}>{Math.abs(r.ch) < 5 ? "steady" : `${r.ch > 0 ? "up" : "down"} ${Math.abs(r.ch).toFixed(0)}%`}</span>
          <span className={s.wSub}>{fmt(r.recent, r.unit === " h" ? 1 : 0)}{r.unit} this week vs {fmt(r.before, r.unit === " h" ? 1 : 0)}{r.unit} before</span>
        </li>
      ))}
    </ul>
  );
}
