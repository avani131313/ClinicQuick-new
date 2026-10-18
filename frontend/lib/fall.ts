/**
 * Fall detection from the phone's accelerometer.
 * A fall looks like: a moment of near free-fall (total acceleration well under 1 g), a hard impact
 * (a spike well over 1 g) within a second, then the phone lying still. Stillness after the impact is what
 * separates a fall from dropping the phone into a bag or sitting down hard.
 */
export type FallInfo = { peakG: number; at: number };
export type Sample = { t: number; g: number };

const FREEFALL_G = 0.5, IMPACT_G = 2.4, WINDOW_MS = 1200, STILL_MS = 2500, STILL_SD = 0.14;

export function createFallDetector(onFall: (f: FallInfo) => void, onSample?: (s: Sample) => void) {
  let freefallAt = 0, impactAt = 0, peak = 0;
  let still: number[] = [];
  let armed = true;

  function push(g: number, t = performance.now()) {
    onSample?.({ t, g });
    if (!armed) return;
    if (g < FREEFALL_G) freefallAt = t;
    if (!impactAt && g > IMPACT_G && t - freefallAt < WINDOW_MS) { impactAt = t; peak = g; still = []; return; }
    if (impactAt) {
      peak = Math.max(peak, g);
      if (t - impactAt < 400) return;                 // let the bounce settle
      still.push(g);
      if (t - impactAt > 400 + STILL_MS) {
        const m = still.reduce((a, b) => a + b, 0) / still.length;
        const sd = Math.sqrt(still.reduce((a, b) => a + (b - m) ** 2, 0) / still.length);
        if (sd < STILL_SD) { armed = false; onFall({ peakG: peak, at: t }); }
        impactAt = 0; still = [];
      }
    }
  }

  function onMotion(e: DeviceMotionEvent) {
    const a = e.accelerationIncludingGravity;
    if (!a || a.x == null || a.y == null || a.z == null) return;
    push(Math.hypot(a.x, a.y, a.z) / 9.81);
  }

  return {
    start() { window.addEventListener("devicemotion", onMotion); },
    stop() { window.removeEventListener("devicemotion", onMotion); },
    rearm() { armed = true; impactAt = 0; still = []; },
    push,
    /** Play a scripted fall through the detector (for demos on a laptop). */
    simulate() {
      const t0 = performance.now();
      const script: [number, number][] = [];
      for (let i = 0; i < 25; i++) script.push([i * 40, 1 + Math.sin(i) * 0.08]);           // walking
      for (let i = 0; i < 8; i++) script.push([1000 + i * 40, 0.25 + Math.random() * 0.1]);   // falling
      script.push([1330, 3.6], [1370, 1.9], [1410, 2.7], [1450, 0.6], [1490, 1.3]);         // impact and bounce
      for (let i = 0; i < 90; i++) script.push([1530 + i * 40, 1 + (Math.random() - 0.5) * 0.04]); // lying still
      script.forEach(([dt, g]) => setTimeout(() => push(g, t0 + dt), dt));
    },
  };
}

/** iOS asks permission for motion sensors, and only from a tap. */
export async function askMotionPermission(): Promise<"granted" | "denied" | "unsupported"> {
  if (typeof window === "undefined" || !("DeviceMotionEvent" in window)) return "unsupported";
  const DM = DeviceMotionEvent as unknown as { requestPermission?: () => Promise<string> };
  if (typeof DM.requestPermission === "function") {
    try { return (await DM.requestPermission()) === "granted" ? "granted" : "denied"; } catch { return "denied"; }
  }
  return "granted";
}

/** A siren from the speakers (Web Audio), plus spoken words over it. */
export function createAlarm() {
  let ctx: AudioContext | null = null, osc: OscillatorNode | null = null, gain: GainNode | null = null, timer = 0;
  return {
    unlock() {
      if (!ctx) { const AC = window.AudioContext || (window as any).webkitAudioContext; if (AC) ctx = new AC(); }
      ctx?.resume();
    },
    beep(times = 3) {
      if (!ctx) return;
      for (let i = 0; i < times; i++) {
        const o = ctx.createOscillator(), g = ctx.createGain(), t = ctx.currentTime + i * 0.7;
        o.frequency.value = 880; o.type = "sine";
        g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(0.35, t + 0.02); g.gain.linearRampToValueAtTime(0, t + 0.4);
        o.connect(g).connect(ctx.destination); o.start(t); o.stop(t + 0.45);
      }
    },
    start() {
      if (!ctx || osc) return;
      osc = ctx.createOscillator(); gain = ctx.createGain();
      osc.type = "sawtooth"; gain.gain.value = 0.12;
      osc.connect(gain).connect(ctx.destination); osc.start();
      let up = true;
      const sweep = () => { if (!osc || !ctx) return; osc.frequency.linearRampToValueAtTime(up ? 1250 : 650, ctx.currentTime + 0.5); up = !up; };
      sweep(); timer = window.setInterval(sweep, 500);
    },
    duck(on: boolean) { if (gain && ctx) gain.gain.linearRampToValueAtTime(on ? 0.03 : 0.12, ctx.currentTime + 0.1); },
    stop() { clearInterval(timer); try { osc?.stop(); } catch {} osc = null; gain = null; },
  };
}

export function say(text: string, onEnd?: () => void) {
  if (typeof window === "undefined" || !window.speechSynthesis) { onEnd?.(); return; }
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 1.02; u.pitch = 1; u.volume = 1;
  if (onEnd) u.onend = onEnd;
  window.speechSynthesis.speak(u);
}

export function buzz(pattern: number | number[]) {
  try { return navigator.vibrate?.(pattern) ?? false; } catch { return false; }
}
