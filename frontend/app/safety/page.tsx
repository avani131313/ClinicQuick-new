"use client";

/**
 * Fall alert. While it's on, the phone watches its motion sensors. After a hard fall and no movement:
 * three buzzes asking "Are you okay?", then an alarm and a spoken countdown, then it calls a medical help line.
 * The demo calls Health811 (Ontario's nurse line), never 911.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Footer, TopBar, useRequireRole } from "@/components/ui";
import { askMotionPermission, buzz, createAlarm, createFallDetector, say, type Sample } from "@/lib/fall";
import { cssVar, useTheme } from "@/lib/theme";
import s from "./safety.module.css";

type Stage = "off" | "watching" | "check" | "alarm" | "calling" | "safe";
const DEFAULT_LINE = { name: "Health811", number: "1-866-797-0000" };
const CHECK_SECONDS = 12, COUNTDOWN = 10;

function useHelpLine() {
  const [line, setLine] = useState(DEFAULT_LINE);
  useEffect(() => { try { const v = localStorage.getItem("cq.helpline"); if (v) setLine(JSON.parse(v)); } catch {} }, []);
  const save = (l: typeof DEFAULT_LINE) => { setLine(l); try { localStorage.setItem("cq.helpline", JSON.stringify(l)); } catch {} };
  return [line, save] as const;
}

function Trace({ samples }: { samples: React.MutableRefObject<Sample[]> }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const theme = useTheme();
  useEffect(() => {
    const cv = ref.current!; const ctx = cv.getContext("2d")!;
    let raf = 0;
    const draw = () => {
      const dpr = Math.min(2, devicePixelRatio || 1), w = cv.clientWidth, h = cv.clientHeight;
      if (cv.width !== w * dpr) { cv.width = w * dpr; cv.height = h * dpr; }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
      const now = performance.now(), span = 6000, max = 4;
      const y = (g: number) => h - 8 - (Math.min(g, max) / max) * (h - 16);
      const accent = cssVar("--accent"), line = cssVar("--line-2"), txt = cssVar("--text-3"), red = cssVar("--red");
      ctx.font = "11px " + cssVar("--mono", "monospace");
      ([[1, line, "1 g, still"], [0.5, line, "free fall"], [2.4, red, "impact"]] as const).forEach(([g, c, label]) => {
        ctx.strokeStyle = c; ctx.setLineDash([3, 4]); ctx.beginPath(); ctx.moveTo(0, y(g)); ctx.lineTo(w, y(g)); ctx.stroke();
        ctx.setLineDash([]); ctx.fillStyle = txt; ctx.fillText(label, 6, y(g) - 4);
      });
      const pts = samples.current.filter((p) => now - p.t < span);
      ctx.strokeStyle = accent; ctx.lineWidth = 2; ctx.lineJoin = "round"; ctx.beginPath();
      pts.forEach((p, i) => { const x = w - ((now - p.t) / span) * w; i ? ctx.lineTo(x, y(p.g)) : ctx.moveTo(x, y(p.g)); });
      ctx.stroke();
      const last = pts[pts.length - 1];
      if (last) { ctx.fillStyle = accent; ctx.beginPath(); ctx.arc(w - ((now - last.t) / span) * w, y(last.g), 3.5, 0, 7); ctx.fill(); }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [samples, theme]);
  return <canvas ref={ref} className={s.trace} aria-label="Live motion from the phone's accelerometer" role="img" />;
}

export default function Safety() {
  const ok = useRequireRole(["patient"]);
  const [stage, setStage] = useState<Stage>("off");
  const [sensor, setSensor] = useState<"unknown" | "live" | "none" | "denied">("unknown");
  const [left, setLeft] = useState(0);
  const [buzzes, setBuzzes] = useState(0);
  const [line, setLine] = useHelpLine();
  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState("");
  const samples = useRef<Sample[]>([]);
  const stageRef = useRef<Stage>("off");
  const timers = useRef<number[]>([]);
  const alarm = useRef(createAlarm());
  const wake = useRef<any>(null);
  const lineRef = useRef(line);
  lineRef.current = line;
  stageRef.current = stage;

  const clear = () => { timers.current.forEach(clearTimeout); timers.current = []; window.speechSynthesis?.cancel(); alarm.current.stop(); };
  const later = (fn: () => void, ms: number) => timers.current.push(window.setTimeout(fn, ms));

  const call = useCallback(() => {
    clear(); setStage("calling");
    say(`Calling ${lineRef.current.name} now.`);
    const digits = lineRef.current.number.replace(/[^\d+]/g, "");
    later(() => { window.location.href = `tel:${digits}`; }, 900);
  }, []);

  const startAlarm = useCallback(() => {
    clear(); setStage("alarm"); setLeft(COUNTDOWN);
    alarm.current.start(); alarm.current.duck(true); buzz([800, 300, 800, 300, 800]);
    let started = false;
    const count = () => {
      if (started) return; started = true; alarm.current.duck(false);
      for (let i = 1; i <= COUNTDOWN; i++) later(() => {
        const n = COUNTDOWN - i;
        setLeft(n);
        if (n > 0) { alarm.current.duck(true); say(String(n), () => alarm.current.duck(false)); buzz(250); }
        else call();
      }, i * 1000);
    };
    say(`Person detected unaware. Calling emergency in ${COUNTDOWN}.`, count);
    later(count, 4200); // if speech isn't available, don't wait for it
  }, [call]);

  const onFall = useCallback(() => {
    if (stageRef.current !== "watching") return;
    clear(); setStage("check"); setBuzzes(0); setLeft(CHECK_SECONDS);
    // three buzzes, four seconds apart, each with a beep and the question
    [0, 4000, 8000].forEach((ms, i) => later(() => {
      setBuzzes(i + 1); buzz([500, 180, 500]); alarm.current.beep(2);
      if (i === 0) say("Are you okay? Tap the screen if you are.");
    }, ms));
    for (let i = 1; i <= CHECK_SECONDS; i++) later(() => setLeft(CHECK_SECONDS - i), i * 1000);
    later(startAlarm, CHECK_SECONDS * 1000);
  }, [startAlarm]);

  const detector = useRef<ReturnType<typeof createFallDetector> | null>(null);
  useEffect(() => {
    const d = createFallDetector(() => onFall(), (p) => {
      samples.current.push(p);
      if (samples.current.length > 600) samples.current.splice(0, 200);
      setSensor((v) => (v === "unknown" || v === "none" ? "live" : v));
      // moving the phone during the check counts as a response
      if (stageRef.current === "check" && Math.abs(p.g - 1) > 0.6 && !simulating.current) imOkay("We felt you move. Glad you're okay.");
    });
    detector.current = d;
    return () => { d.stop(); clear(); };
  }, [onFall]); // eslint-disable-line react-hooks/exhaustive-deps

  const simulating = useRef(false);

  async function turnOn() {
    alarm.current.unlock();
    const p = await askMotionPermission();
    if (p === "denied") { setSensor("denied"); return; }
    if (p === "unsupported") setSensor("none");
    detector.current?.start(); detector.current?.rearm();
    setStage("watching"); setNote("");
    try { wake.current = await (navigator as any).wakeLock?.request("screen"); } catch {}
    // no samples after a moment means this device has no motion sensor (most laptops)
    later(() => setSensor((v) => (v === "unknown" ? "none" : v)), 1500);
  }
  function turnOff() { clear(); detector.current?.stop(); setStage("off"); try { wake.current?.release(); } catch {} }
  function imOkay(msg = "Okay. Glad you're alright.") {
    clear(); setStage("safe"); setNote(msg); say(msg);
    later(() => { detector.current?.rearm(); setStage("watching"); }, 2500);
  }
  async function simulate() {
    if (stageRef.current === "off") await turnOn();
    alarm.current.unlock();
    detector.current?.rearm();
    simulating.current = true;
    detector.current?.simulate();
    later(() => { simulating.current = false; }, 6500);
  }

  if (!ok) return null;
  const on = stage !== "off";
  return (
    <>
      <TopBar />
      <main className={`wrap page ${s.page}`}>
        <header className={s.head}>
          <p className="eyebrow">Safety</p>
          <h1>Fall alert</h1>
          <p className="muted">If you fall and don't respond, your phone asks if you're okay, then calls for help.</p>
        </header>

        <section className={s.main}>
          <div className={`panel ${s.status}`} data-on={on || undefined}>
            <div className={s.shield} aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"><path d="M12 3 4.5 6v5.5c0 4.6 3.2 8 7.5 9.5 4.3-1.5 7.5-4.9 7.5-9.5V6L12 3z" />{on && <path d="M9 12l2.2 2.2L15.5 10" strokeLinecap="round" />}</svg>
            </div>
            <div className={s.statusText}>
              <h2>{on ? "Watching for falls" : "Fall alert is off"}</h2>
              <p className="muted">
                {!on ? "Turn it on before you go for a walk, shower, or are home alone." :
                  sensor === "none" ? "This device has no motion sensor. Open ClinicQuick on your phone, or simulate a fall to see what happens." :
                  sensor === "denied" ? "Motion access was blocked. Allow motion and orientation access for this site in your browser settings." :
                  "Keep ClinicQuick open. Your screen stays on while it watches."}
              </p>
            </div>
            <div className={s.actions}>
              {on ? <button className="btn ghost" onClick={turnOff}>Turn off</button> : <button className="btn" onClick={turnOn}>Turn on fall alert</button>}
              <button className="btn ghost" onClick={simulate}>Simulate a fall</button>
            </div>
            {note && <p className={s.note} role="status">{note}</p>}
          </div>

          <div className={`panel ${s.live}`}>
            <div className={s.liveHead}><p className="panel-title">Motion right now</p><span className={s.badge} data-live={sensor === "live" || undefined}>{sensor === "live" ? "Sensor live" : "No sensor"}</span></div>
            <Trace samples={samples} />
            <p className="small">Total acceleration in g. A fall shows a dip, a spike, then a flat line.</p>
          </div>

          <div className={`panel ${s.line}`}>
            <p className="panel-title">If you don't respond, we call</p>
            {editing ? (
              <form className={s.lineForm} onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget); setLine({ name: String(f.get("n") || DEFAULT_LINE.name), number: String(f.get("p") || DEFAULT_LINE.number) }); setEditing(false); }}>
                <label htmlFor="hl-n">Name</label><input id="hl-n" name="n" defaultValue={line.name} />
                <label htmlFor="hl-p">Number</label><input id="hl-p" name="p" defaultValue={line.number} inputMode="tel" />
                <div className={s.formBtns}><button className="btn small">Save</button><button type="button" className="btn ghost small" onClick={() => setEditing(false)}>Cancel</button></div>
              </form>
            ) : (
              <>
                <p className={s.lineName}>{line.name}</p>
                <p className={`num ${s.lineNum}`}>{line.number}</p>
                <button className="linkish small" onClick={() => setEditing(true)}>Change number</button>
              </>
            )}
            <p className="small">Demo setting: a medical help line, not 911. In a real emergency call 911 yourself.</p>
          </div>
        </section>

        <section className={s.how}>
          <h2>What happens after a fall</h2>
          <ol>
            <li><strong>Hard fall, then stillness</strong><span>The phone feels a drop and an impact, then no movement for a few seconds.</span></li>
            <li><strong>Three buzzes</strong><span>It vibrates and asks "Are you okay?" Tap the screen or move to say you're fine.</span></li>
            <li><strong>Alarm and countdown</strong><span>A siren and a spoken countdown from 10, so people nearby hear it too.</span></li>
            <li><strong>Call for help</strong><span>At zero it calls {line.name}. You can cancel at any point.</span></li>
          </ol>
          <p className="small">Vibration works on Android. iPhones don't let websites vibrate, so they beep and flash instead. Motion sensors need the site to open over https on your phone.</p>
        </section>
      </main>
      <Footer />

      {(stage === "check" || stage === "alarm" || stage === "calling" || stage === "safe") && (
        <div className={s.overlay} data-stage={stage} role="alertdialog" aria-modal="true" aria-live="assertive"
          onClick={() => stage === "check" && imOkay()}>
          {stage === "check" && (
            <div className={s.ov}>
              <div className={s.pulse} aria-hidden="true"><span /><span /><span /></div>
              <p className={s.ovEyebrow}>Fall detected · buzz {buzzes} of 3</p>
              <h2 className={s.ovTitle}>Are you okay?</h2>
              <p className={s.ovText}>Tap anywhere if you're alright. Alarm in <span className="num">{left}</span>s.</p>
              <button className={s.okBtn} onClick={(e) => { e.stopPropagation(); imOkay(); }}>I'm okay</button>
              <div className={s.bar}><span style={{ width: `${(left / CHECK_SECONDS) * 100}%` }} /></div>
            </div>
          )}
          {stage === "alarm" && (
            <div className={s.ov}>
              <p className={s.ovEyebrow}>No response</p>
              <h2 className={s.ovTitle}>Person detected unaware</h2>
              <p className={s.ovText}>Calling {line.name} in</p>
              <p className={`num ${s.count}`} key={left}>{left}</p>
              <button className={s.okBtn} onClick={() => imOkay()}>Cancel, I'm okay</button>
            </div>
          )}
          {stage === "calling" && (
            <div className={s.ov}>
              <div className={s.pulse} aria-hidden="true"><span /><span /><span /></div>
              <p className={s.ovEyebrow}>Calling</p>
              <h2 className={s.ovTitle}>{line.name}</h2>
              <p className={`num ${s.ovText}`}>{line.number}</p>
              <a className={s.okBtn} href={`tel:${line.number.replace(/[^\d+]/g, "")}`}>Call again</a>
              <button className="linkish" onClick={() => imOkay("Okay. Fall alert is back on.")}>I'm safe, close this</button>
            </div>
          )}
          {stage === "safe" && (
            <div className={s.ov}><h2 className={s.ovTitle}>You're okay</h2><p className={s.ovText}>{note}</p></div>
          )}
        </div>
      )}
    </>
  );
}
