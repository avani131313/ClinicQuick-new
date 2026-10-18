"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import VoiceOrb, { OrbMode } from "./VoiceOrb";
import { listenOnce, micLevel, prefetchVoice, say, Speech } from "@/lib/voice";
import s from "./talk.module.css";

type Q = { text: string; type: string; slot: string; options?: string[] | null };

export default function TalkMode({
  question, asked, total, covered, writing, busy, onAnswer, onType, onFinish, onAttach, firstName, silent,
}: {
  question: Q | null; asked: number; total: number; covered: number; writing: boolean; busy: boolean;
  onAnswer: (text: string) => Promise<void>; onType: () => void; onFinish: () => void; onAttach: (f: File) => void; firstName?: string; silent?: boolean;
}) {
  const level = useRef(0);
  const mode = useRef<OrbMode>("idle");
  const [ui, setUi] = useState<OrbMode>("idle");
  const [heard, setHeard] = useState("");
  const [note, setNote] = useState("");
  const [muted, setMuted] = useState(false);
  const turn = useRef(0);
  const speech = useRef<Speech | null>(null);
  const listening = useRef<{ stop: () => void } | null>(null);
  const stopMic = useRef<() => void>(() => {});
  const file = useRef<HTMLInputElement>(null);

  const setMode = (m: OrbMode) => { mode.current = m; setUi(m); };

  const stopAll = useCallback(() => {
    speech.current?.stop(); speech.current = null;
    listening.current?.stop(); listening.current = null;
    stopMic.current(); stopMic.current = () => {};
  }, []);

  const listen = useCallback(async (id: number, retry = true) => {
    if (id !== turn.current) return;
    setMode("listening"); setHeard(""); setNote("");
    stopMic.current = await micLevel((v) => { if (mode.current === "listening") level.current = v; });
    const l = listenOnce((t) => setHeard(t));
    listening.current = l;
    let text = "";
    try { text = await l.result; } catch (e: any) { setNote(e.message); }
    stopMic.current(); stopMic.current = () => {};
    listening.current = null;
    if (id !== turn.current) return;
    if (!text) {
      if (retry) { setNote("I didn't catch that. Go ahead whenever you're ready."); return listen(id, false); }
      setMode("idle"); setNote("Tap the microphone when you're ready to answer, or type instead.");
      return;
    }
    setHeard(text);
    setMode("thinking");
    level.current = 0;
    await onAnswer(text);
  }, [onAnswer]);

  // Each new question: Lena speaks it, then listens.
  useEffect(() => {
    if (!question?.text || busy || writing) return;
    const id = ++turn.current;
    stopAll();
    (async () => {
      if (!muted) {
        setMode("speaking");
        const sp = await say(question.text, (v) => { if (mode.current === "speaking") level.current = v; });
        speech.current = sp;
        await sp.done;
      }
      if (id === turn.current && !question.options) await listen(id);
      else if (id === turn.current) setMode("idle");
    })();
    return () => { turn.current++; stopAll(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question?.text, busy, writing]);

  useEffect(() => { if (busy || writing) setMode("thinking"); }, [busy, writing]);
  useEffect(() => { prefetchVoice("Thank you. I'm writing up your summary now."); }, []);
  useEffect(() => {
    if (writing && !silent) say("Thank you. I'm writing up your summary now.", (v) => (level.current = v));
  }, [writing]);
  useEffect(() => () => stopAll(), [stopAll]);

  const status = writing ? "Writing your summary…"
    : ui === "speaking" ? "Lena is speaking"
    : ui === "listening" ? "Listening — just talk"
    : ui === "thinking" ? "Thinking about your answer…"
    : "Your turn";

  async function micTap() {
    if (ui === "listening") { listening.current?.stop(); return; }
    if (ui === "speaking") { speech.current?.stop(); }
    const id = ++turn.current;
    await listen(id, false);
  }
  async function replay() {
    if (!question) return;
    const id = ++turn.current;
    stopAll();
    setMode("speaking");
    const sp = await say(question.text, (v) => (level.current = v));
    speech.current = sp;
    await sp.done;
    if (id === turn.current && !question.options) listen(id);
  }
  async function choose(o: string) {
    stopAll(); turn.current++;
    setHeard(o); setMode("thinking");
    await onAnswer(question?.slot === "severity" ? `${o} out of 10` : o);
  }

  const options = question?.options || (question?.slot === "severity" ? Array.from({ length: 11 }, (_, i) => String(i)) : null);
  const pct = Math.round((covered / Math.max(1, total)) * 100);

  return (
    <div className={s.room} data-mode={ui}>
      <header className={s.top}>
        <div className={s.progress} aria-label={`${covered} of ${total} topics covered`}>
          <svg width="34" height="34" viewBox="0 0 36 36" aria-hidden="true">
            <circle cx="18" cy="18" r="15" fill="none" stroke="rgba(234,245,242,.15)" strokeWidth="3" />
            <circle cx="18" cy="18" r="15" fill="none" stroke="#9FE7D6" strokeWidth="3" strokeLinecap="round"
              strokeDasharray={`${(pct / 100) * 94.2} 94.2`} transform="rotate(-90 18 18)" style={{ transition: "stroke-dasharray .6s ease" }} />
          </svg>
          <span>{covered} of {total} covered</span>
        </div>
        <div className={s.topActions}>
          <button className={`${s.ghost} ${s.hideSm}`} onClick={() => setMuted(!muted)} aria-pressed={muted}>{muted ? "Voice off" : "Voice on"}</button>
          <button className={s.ghost} onClick={() => { stopAll(); onType(); }}>Type instead</button>
        </div>
      </header>

      <main className={s.stage}>
        <VoiceOrb levelRef={level} modeRef={mode} />
        <p className={s.status} aria-live="polite">{status}</p>
        <h1 className={s.caption} key={question?.text}>{writing ? "Thank you. I'm writing up your summary now." : question?.text}</h1>
        {heard && <p className={s.heard}>“{heard}”</p>}
        {note && <p className={s.note}>{note}</p>}
        {options && !writing && (
          <div className={s.opts}>{options.map((o) => <button key={o} className={s.opt} disabled={busy} onClick={() => choose(o)}>{o}</button>)}</div>
        )}
      </main>

      <footer className={s.controls}>
        <button className={s.side} onClick={() => file.current?.click()} aria-label="Add a photo or video" title="Add a photo or video">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3.5" /></svg>
        </button>
        <input ref={file} type="file" accept="image/*,video/*" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) onAttach(f); e.target.value = ""; }} />
        <button className={`${s.mic} ${ui === "listening" ? s.micLive : ""}`} onClick={micTap} disabled={busy || writing}
          aria-label={ui === "listening" ? "Done talking" : "Answer by voice"}>
          {ui === "listening"
            ? <svg width="30" height="30" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
            : <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>}
        </button>
        <button className={s.side} onClick={replay} disabled={busy || writing} aria-label="Hear the question again" title="Hear the question again">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5" /></svg>
        </button>
      </footer>
      {asked >= 5 && !writing && <button className={s.finish} onClick={() => { stopAll(); onFinish(); }}>That's everything — write my summary</button>}
      <p className={s.fine}>In an emergency, call 911. Lena is an AI and doesn't diagnose.</p>
    </div>
  );
}
