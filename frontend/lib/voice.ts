"use client";

import { API, getSession } from "./api";

/** Shared audio engine for talk mode: Lena's natural voice out, the patient's mic level in. */
let ctx: AudioContext | null = null;

export function audio(): AudioContext {
  if (!ctx) ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
  return ctx;
}

/** Call from a click handler so browsers allow audio to play. */
export async function unlockAudio() {
  try { await audio().resume(); } catch {}
}

const wavCache = new Map<string, ArrayBuffer>();

async function fetchVoice(text: string): Promise<ArrayBuffer | null> {
  if (wavCache.has(text)) return wavCache.get(text)!;
  try {
    const r = await fetch(`${API}/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${getSession()?.token || ""}` },
      body: JSON.stringify({ text }),
    });
    if (!r.ok) return null;
    const buf = await r.arrayBuffer();
    wavCache.set(text, buf);
    return buf;
  } catch {
    return null;
  }
}

/** Start fetching the voice for a line before it's needed. */
export function prefetchVoice(text: string) { void fetchVoice(text); }

export type Speech = { done: Promise<void>; stop: () => void; natural: boolean };

/** Speak a line. `level` receives 0..1 loudness every frame so the orb can move with the voice. */
export async function say(text: string, level: (v: number) => void): Promise<Speech> {
  const buf = await fetchVoice(text);
  if (buf) {
    try {
      const ac = audio();
      const decoded = await ac.decodeAudioData(buf.slice(0));
      const src = ac.createBufferSource();
      src.buffer = decoded;
      const an = ac.createAnalyser();
      an.fftSize = 512;
      src.connect(an); an.connect(ac.destination);
      const data = new Uint8Array(an.fftSize);
      let raf = 0, stopped = false;
      const tick = () => {
        an.getByteTimeDomainData(data);
        let sum = 0;
        for (let i = 0; i < data.length; i++) { const v = (data[i] - 128) / 128; sum += v * v; }
        level(Math.min(1, Math.sqrt(sum / data.length) * 4));
        if (!stopped) raf = requestAnimationFrame(tick);
      };
      const done = new Promise<void>((res) => { src.onended = () => { stopped = true; cancelAnimationFrame(raf); level(0); res(); }; });
      src.start();
      tick();
      return { done, natural: true, stop: () => { try { src.stop(); } catch {} } };
    } catch { /* fall through to browser voice */ }
  }
  // Browser voice fallback, with a gentle synthetic level so the orb still breathes.
  const synth = window.speechSynthesis;
  const u = new SpeechSynthesisUtterance(text);
  const voices = synth.getVoices();
  const pick = voices.find((v) => /en-(CA|GB|US)/.test(v.lang) && /(Samantha|Google UK English Female|Karen|Moira|Natural|Aria|Jenny|Ava)/i.test(v.name)) || voices.find((v) => v.lang.startsWith("en"));
  if (pick) u.voice = pick;
  u.rate = 0.98;
  let raf = 0, t = 0, talking = true;
  const tick = () => { t += 0.12; level(talking ? 0.35 + 0.25 * Math.abs(Math.sin(t)) * Math.abs(Math.sin(t * 2.3)) : 0); raf = requestAnimationFrame(tick); };
  u.onboundary = () => { t += 1; };
  const done = new Promise<void>((res) => {
    const finish = () => { talking = false; cancelAnimationFrame(raf); level(0); res(); };
    u.onend = u.onerror = finish;
    // Some browsers never fire onend (no voices installed); don't leave the conversation hanging.
    setTimeout(finish, 1500 + text.split(/\s+/).length * 420);
  });
  synth.cancel(); synth.speak(u); tick();
  return { done, natural: false, stop: () => synth.cancel() };
}

/** Live microphone loudness while the patient talks. Returns a stop function. */
export async function micLevel(level: (v: number) => void): Promise<() => void> {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    const ac = audio();
    const srcNode = ac.createMediaStreamSource(stream);
    const an = ac.createAnalyser();
    an.fftSize = 512;
    srcNode.connect(an);
    const data = new Uint8Array(an.fftSize);
    let raf = 0;
    const tick = () => {
      an.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) { const v = (data[i] - 128) / 128; sum += v * v; }
      level(Math.min(1, Math.sqrt(sum / data.length) * 6));
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => { cancelAnimationFrame(raf); stream.getTracks().forEach((t) => t.stop()); level(0); };
  } catch {
    return () => {};
  }
}

export function speechRecognitionSupported() {
  return typeof window !== "undefined" && !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);
}

/** One listening turn. Resolves with the final words when the patient pauses (or "" if nothing was heard). */
export function listenOnce(onInterim: (t: string) => void): { result: Promise<string>; stop: () => void } {
  const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
  const rec = new SR();
  rec.lang = "en-CA";
  rec.interimResults = true;
  rec.continuous = false;
  rec.maxAlternatives = 1;
  let finalText = "", latest = "";
  const result = new Promise<string>((res, rej) => {
    rec.onresult = (e: any) => {
      let interim = "";
      for (let i = 0; i < e.results.length; i++) {
        if (e.results[i].isFinal) finalText = (finalText + " " + e.results[i][0].transcript).trim();
        else interim += e.results[i][0].transcript;
      }
      latest = (finalText + " " + interim).trim();
      onInterim(latest);
    };
    rec.onerror = (e: any) => {
      if (e.error === "no-speech" || e.error === "aborted") res("");
      else rej(new Error(e.error === "not-allowed" ? "Microphone access is blocked. Allow it in your browser's site settings, or type instead." : "Voice input stopped. Try again or type instead."));
    };
    rec.onend = () => res((finalText || latest).trim());
  });
  try { rec.start(); } catch {}
  return { result, stop: () => { try { rec.stop(); } catch {} } };
}
