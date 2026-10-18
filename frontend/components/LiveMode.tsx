"use client";

/**
 * Live voice with Lena (Gemini Live API): continuous two-way audio, no push-to-talk.
 * Mic → 16 kHz PCM over a WebSocket; Lena's 24 kHz audio streams back and plays gaplessly.
 * You can interrupt her; she stops mid-sentence. Safety stops come from the server.
 */
import { useEffect, useRef, useState } from "react";
import VoiceOrb, { OrbMode } from "./VoiceOrb";
import { API, getSession } from "@/lib/api";
import { audio } from "@/lib/voice";
import s from "./talk.module.css";

type Cov = { slot: string; label: string; done: boolean }[];

async function toJpegBase64(f: File): Promise<string | null> {
  if (!f.type.startsWith("image/")) return null;
  const url = URL.createObjectURL(f);
  try {
    const img = await new Promise<HTMLImageElement>((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = url; });
    const scale = Math.min(1, 768 / Math.max(img.width, img.height));
    const c = document.createElement("canvas");
    c.width = Math.round(img.width * scale); c.height = Math.round(img.height * scale);
    c.getContext("2d")!.drawImage(img, 0, 0, c.width, c.height);
    return c.toDataURL("image/jpeg", 0.85).split(",")[1];
  } catch { return null; } finally { URL.revokeObjectURL(url); }
}

export default function LiveMode({ encounterId, onRedFlag, onDone, onFallback, onType, onAttach }: {
  encounterId: string; onRedFlag: (rf: any) => void; onDone: () => void; onFallback: (why: string) => void; onType: () => void; onAttach: (f: File) => void;
}) {
  const level = useRef(0);
  const mode = useRef<OrbMode>("thinking");
  const [ui, setUi] = useState<OrbMode>("thinking");
  const [status, setStatus] = useState("Connecting to Lena…");
  const [cov, setCov] = useState<Cov | null>(null);
  const [answers, setAnswers] = useState(0);
  const [muted, setMuted] = useState(false);
  const mutedRef = useRef(false);
  const wsRef = useRef<WebSocket | null>(null);
  const ended = useRef(false);
  const file = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let stream: MediaStream | null = null, node: AudioWorkletNode | null = null, raf = 0;
    let nextTime = 0, micPeak = 0;
    const sources: AudioBufferSourceNode[] = [];
    const ac = audio();
    const out = ac.createGain();
    const an = ac.createAnalyser(); an.fftSize = 512;
    out.connect(an); an.connect(ac.destination);
    const td = new Uint8Array(an.fftSize);

    const stopPlayback = () => { sources.splice(0).forEach((x) => { try { x.stop(); } catch {} }); nextTime = ac.currentTime; };
    const play = (buf: ArrayBuffer) => {
      const i16 = new Int16Array(buf);
      if (!i16.length) return;
      const ab = ac.createBuffer(1, i16.length, 24000);
      const ch = ab.getChannelData(0);
      for (let i = 0; i < i16.length; i++) ch[i] = i16[i] / 32768;
      const src = ac.createBufferSource();
      src.buffer = ab; src.connect(out);
      const at = Math.max(nextTime, ac.currentTime + 0.05);
      src.start(at); nextTime = at + ab.duration;
      sources.push(src);
      src.onended = () => { const k = sources.indexOf(src); if (k >= 0) sources.splice(k, 1); };
    };

    const startMic = async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
        await ac.audioWorklet.addModule("/pcm-capture.js");
        const src = ac.createMediaStreamSource(stream);
        node = new AudioWorkletNode(ac, "pcm-capture");
        const sink = ac.createGain(); sink.gain.value = 0;
        src.connect(node); node.connect(sink); sink.connect(ac.destination);
        node.port.onmessage = (e) => {
          micPeak = mutedRef.current ? 0 : e.data.peak;
          const ws = wsRef.current;
          if (!mutedRef.current && ws && ws.readyState === 1) ws.send(e.data.pcm);
        };
      } catch {
        onFallback("Microphone access is blocked. Allow it in your browser's site settings, then try again.");
      }
    };

    (async () => {
      await ac.resume();
      const token = getSession()?.token || "";
      const ws = new WebSocket(`${API.replace(/^http/, "ws")}/live/${encounterId}?t=${encodeURIComponent(token)}`);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;
      ws.onmessage = (ev) => {
        if (typeof ev.data !== "string") { play(ev.data as ArrayBuffer); return; }
        const m = JSON.parse(ev.data);
        if (m.type === "ready") { setStatus("Connected"); startMic(); }
        else if (m.type === "turn_complete") { if (typeof m.answers === "number") setAnswers(m.answers); }
        else if (m.type === "interrupted") stopPlayback();
        else if (m.type === "coverage") setCov(m.coverage);
        else if (m.type === "red_flag") { ended.current = true; stopPlayback(); onRedFlag(m.red_flag); }
        else if (m.type === "done") { ended.current = true; setTimeout(onDone, Math.max(300, (nextTime - ac.currentTime) * 1000)); }
        else if (m.type === "error") { ended.current = true; onFallback(m.message); }
      };
      ws.onclose = (e) => {
        if (ended.current) return;
        ended.current = true;
        onFallback(e.code === 4409 ? "Live voice needs the Gemini API key on the server." : "The live connection closed. Switching to the standard voice mode.");
      };
    })();

    const tick = () => {
      const speaking = nextTime > ac.currentTime + 0.02;
      let m: OrbMode, lv = 0;
      if (speaking) {
        an.getByteTimeDomainData(td);
        let sum = 0; for (let i = 0; i < td.length; i++) { const v = (td[i] - 128) / 128; sum += v * v; }
        m = "speaking"; lv = Math.min(1, Math.sqrt(sum / td.length) * 4);
      } else if (micPeak > 0.05) { m = "listening"; lv = Math.min(1, micPeak * 1.6); }
      else m = wsRef.current?.readyState === 1 ? "idle" : "thinking";
      level.current = lv;
      if (m !== mode.current) { mode.current = m; setUi(m); }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    return () => {
      ended.current = true;
      cancelAnimationFrame(raf);
      stopPlayback();
      try { wsRef.current?.close(); } catch {}
      stream?.getTracks().forEach((t) => t.stop());
      try { node?.disconnect(); out.disconnect(); an.disconnect(); } catch {}
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [encounterId]);

  function toggleMute() { const m = !muted; setMuted(m); mutedRef.current = m; }
  function endCall() {
    const ws = wsRef.current;
    if (ws && ws.readyState === 1) { ws.send(JSON.stringify({ type: "end" })); setStatus("Wrapping up…"); setTimeout(() => { if (!ended.current) { ended.current = true; onDone(); } }, 5000); }
    else onDone();
  }
  async function attach(f: File) {
    onAttach(f);
    const b64 = await toJpegBase64(f);
    const ws = wsRef.current;
    if (ws && ws.readyState === 1) {
      if (b64) ws.send(JSON.stringify({ type: "image", data: b64, mime: "image/jpeg" }));
      else ws.send(JSON.stringify({ type: "text", text: "(The patient attached a video for the clinician. Acknowledge it briefly.)" }));
    }
  }

  const covered = cov ? cov.filter((c) => c.done).length : Math.min(answers + 1, 12);
  const total = cov ? cov.length : 12;
  const pct = Math.round((covered / Math.max(1, total)) * 100);
  const label = status !== "Connected" ? status : muted ? "You're muted" : ui === "speaking" ? "Lena is speaking" : ui === "listening" ? "Listening" : "Your turn — just talk";

  return (
    <div className={s.room} data-mode={ui}>
      <header className={s.top}>
        <div className={s.progress} aria-label={`${covered} of ${total} topics covered`}>
          <svg width="34" height="34" viewBox="0 0 36 36" aria-hidden="true">
            <circle cx="18" cy="18" r="15" fill="none" stroke="rgba(234,245,242,.15)" strokeWidth="3" />
            <circle cx="18" cy="18" r="15" fill="none" stroke="#9FE7D6" strokeWidth="3" strokeLinecap="round" strokeDasharray={`${(pct / 100) * 94.2} 94.2`} transform="rotate(-90 18 18)" style={{ transition: "stroke-dasharray .6s ease" }} />
          </svg>
          <span>Live with Lena</span>
        </div>
        <div className={s.topActions}>
          <button className={s.ghost} onClick={() => { ended.current = true; onType(); }}>Type instead</button>
        </div>
      </header>

      <main className={s.stage}>
        <VoiceOrb levelRef={level} modeRef={mode} />
        <p className={s.status} aria-live="polite">{label}</p>
      </main>

      <footer className={s.controls}>
        <button className={s.side} onClick={() => file.current?.click()} aria-label="Show Lena a photo" title="Show Lena a photo">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3.5" /></svg>
        </button>
        <input ref={file} type="file" accept="image/*,video/*" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) attach(f); e.target.value = ""; }} />
        <button className={`${s.mic} ${muted ? s.micMuted : ""}`} onClick={toggleMute} aria-pressed={muted} aria-label={muted ? "Unmute microphone" : "Mute microphone"}>
          {muted
            ? <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M3 3l18 18M9 9v2a3 3 0 0 0 5 2.2M15 9.3V6a3 3 0 0 0-5.7-1.3M5 11a7 7 0 0 0 11.6 5.3M19 11a7 7 0 0 1-.6 2.8M12 18v3" /></svg>
            : <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>}
        </button>
        <button className={`${s.side} ${s.end}`} onClick={endCall} aria-label="End and get my summary" title="End and get my summary">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M12 9c-3.5 0-6.6 1.2-8.8 3.2a1.5 1.5 0 0 0 0 2.1l1.6 1.6a1.5 1.5 0 0 0 1.9.2l2-1.3a1.5 1.5 0 0 0 .7-1.3v-1.6a12 12 0 0 1 5.2 0v1.6c0 .5.3 1 .7 1.3l2 1.3a1.5 1.5 0 0 0 1.9-.2l1.6-1.6a1.5 1.5 0 0 0 0-2.1C18.6 10.2 15.5 9 12 9z" /></svg>
        </button>
      </footer>
      <p className={s.fine}>Headphones help Lena hear you clearly. In an emergency, call 911. Lena is an AI and doesn't diagnose.</p>
    </div>
  );
}
