"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Mark, useRequireRole } from "@/components/ui";
import { api, getSession, API } from "@/lib/api";
import { speak, stopSpeaking, useSpeechInput } from "@/lib/speech";
import TalkMode from "@/components/TalkMode";
import LiveMode from "@/components/LiveMode";
import VoiceOrb, { OrbMode } from "@/components/VoiceOrb";
import { audio, say, speechRecognitionSupported, unlockAudio } from "@/lib/voice";
import s from "./visit.module.css";

type View = {
  encounter_id: string; status: string; done: boolean; mode: string; asked: number; max_questions: number;
  question: { text: string; type: string; slot: string; options?: string[] | null } | null;
  coverage: { slot: string; label: string; done: boolean; summary?: string }[];
  red_flag: null | { title: string; message: string; label: string; action: string; resources: { label: string; href: string }[] };
};
type Turn = { question: string; answer: string | null; type: string };
type Media = { id?: string; kind: "photo" | "video"; url: string; description?: string; quality_note?: string | null; uploading?: boolean };

const TYPE_LABEL: Record<string, string> = { STANDARD: "Standard question", AI_PERSONALISED: "Personalised by AI", PERSONALISED: "Personalised", SAFETY_SCREEN: "Safety check" };

export default function Visit() {
  const ok = useRequireRole(["patient"]);
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [view, setView] = useState<View | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [writing, setWriting] = useState(false);
  const [err, setErr] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [media, setMedia] = useState<Media[]>([]);
  const [voiceOn, setVoiceOn] = useState(false);
  const [mode, setMode] = useState<"choose" | "talk" | "live" | "type" | null>(null);
  const [notice, setNotice] = useState("");
  const orbLevel = useRef(0);
  const orbMode = useRef<OrbMode>("idle");
  useEffect(() => {
    if (!speechRecognitionSupported()) { setMode("type"); return; }
    let pref: string | null = null;
    try { pref = localStorage.getItem("prelude.mode"); } catch {}
    let running = false;
    try { running = audio().state === "running"; } catch {}
    setMode(pref === "type" ? "type" : (pref === "talk" || pref === "live") && running ? "live" : "choose");
  }, []);
  async function pick(m: "talk" | "live" | "type") {
    if (m === "talk") m = "live";   // Talk = live voice; standard talk mode is the fallback
    if (m === "live") await unlockAudio();
    try { localStorage.setItem("prelude.mode", m); } catch {}
    setMode(m);
  }
  const voice = useSpeechInput((t) => setText(t));
  useEffect(() => { try { setVoiceOn(localStorage.getItem("prelude.voice") === "1"); } catch {} }, []);
  useEffect(() => {
    if (voiceOn && view?.question?.text && !busy) speak(view.question.text);
  }, [voiceOn, view?.question?.text, busy]);
  useEffect(() => () => stopSpeaking(), []);
  function toggleVoice() {
    const v = !voiceOn; setVoiceOn(v);
    try { localStorage.setItem("prelude.voice", v ? "1" : "0"); } catch {}
    if (!v) stopSpeaking(); else if (view?.question?.text) speak(view.question.text);
  }
  async function attach(f: File) {
    const kind = f.type.startsWith("video/") ? "video" : "photo";
    if (f.size > 20 * 1024 * 1024) { setErr("That file is over 20 MB. Try a photo or a clip of about 30 seconds."); return; }
    const url = URL.createObjectURL(f);
    setMedia((m) => [...m, { kind, url, uploading: true }]);
    const fd = new FormData(); fd.append("file", f);
    try {
      const r = await api(`/encounters/${id}/media`, { form: fd });
      setMedia((m) => m.map((x) => (x.url === url ? { ...x, id: r.id, description: r.description, quality_note: r.quality_ok ? null : r.quality_note, uploading: false } : x)));
    } catch (e: any) {
      setErr(e.message);
      setMedia((m) => m.filter((x) => x.url !== url));
    }
  }

  useEffect(() => {
    if (!ok) return;
    api(`/encounters/${id}`).then((r) => {
      setView(r.encounter);
      setTurns(r.transcript.filter((t: Turn) => t.answer !== null));
      const tok = getSession()?.token || "";
      setMedia((r.media || []).map((m: any) => ({ id: m.id, kind: m.mime.startsWith("video/") ? "video" : "photo", url: `${API}/media/${m.id}?t=${encodeURIComponent(tok)}`, description: m.description })));
      if (r.report) router.replace(`/visit/${id}/report`);
      else if (r.encounter.status === "complete") finish();
    }).catch((e) => setErr(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ok, id]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); inputRef.current?.focus(); }, [turns, view?.question?.text]);

  async function finish() {
    setWriting(true);
    try {
      await api(`/encounters/${id}/finish`, { method: "POST" });
      router.replace(`/visit/${id}/report`);
    } catch (e: any) { setErr(e.message); setWriting(false); }
  }

  async function send(answer: string) {
    const a = answer.trim();
    if (!a || !view?.question) return;
    setBusy(true); setErr("");
    stopSpeaking(); if (voice.listening) voice.stop();
    const q = view.question;
    setTurns((t) => [...t, { question: q.text, answer: a, type: q.type }]);
    setText("");
    try {
      const r: View = await api(`/encounters/${id}/answer`, { body: { text: a } });
      setView(r);
      if (r.done) finish();
    } catch (e: any) {
      setErr(e.message);
      setTurns((t) => t.slice(0, -1));
      setText(a);
    }
    setBusy(false);
  }

  if (!ok) return null;

  if (view?.red_flag) {
    const rf = view.red_flag;
    if (mode === "talk" && !(window as any).__prelude_rf_spoken) { (window as any).__prelude_rf_spoken = true; say(`${rf.title}. ${rf.message}`, () => {}); }
    return (
      <main className={s.stop} role="alert">
        <div className={s.stopInner}>
          <p className={s.stopKicker}>We've stopped the check-in</p>
          <h1>{rf.title}</h1>
          <p className={s.stopMsg}>{rf.message}</p>
          <div className={s.stopActions}>
            {rf.resources.map((r) => <a key={r.href} href={r.href} className={s.stopBtn}>{r.label}</a>)}
          </div>
          <p className={s.stopWhy}>Why: you mentioned something that can be an emergency ({rf.label.toLowerCase()}). This decision is made by fixed safety rules, not by the AI.</p>
          <button className="linkish" style={{ color: "#fff" }} onClick={() => router.push("/home")}>I'm safe, back to home</button>
        </div>
      </main>
    );
  }

  if (mode === "choose" && view) {
    return (
      <div className={s.choose}>
        <div className={s.chooseOrb}><VoiceOrb levelRef={orbLevel} modeRef={orbMode} size={300} /></div>
        <h1>How would you like to talk to Lena?</h1>
        <div className={s.chooseRow}>
          <button className={s.choosePrimary} onClick={() => pick("talk")}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>
            Talk
          </button>
          <button className={s.chooseSecondary} onClick={() => pick("type")}>Type</button>
        </div>
        <p className={s.chooseFine}>You can switch at any time.</p>
      </div>
    );
  }

  if (mode === "live" && view && view.status === "active" && !writing) {
    return (
      <LiveMode
        encounterId={id}
        onRedFlag={(rf) => setView({ ...view, red_flag: rf, status: "stopped_red_flag" })}
        onDone={finish}
        onFallback={(why) => { setNotice(why); setMode("talk"); api(`/encounters/${id}`).then((r) => { setView(r.encounter); setTurns(r.transcript.filter((t: Turn) => t.answer !== null)); }).catch(() => {}); }}
        onType={() => { try { localStorage.setItem("prelude.mode", "type"); } catch {} setMode("type"); api(`/encounters/${id}`).then((r) => { setView(r.encounter); setTurns(r.transcript.filter((t: Turn) => t.answer !== null)); }).catch(() => {}); }}
        onAttach={attach}
      />
    );
  }

  if ((mode === "talk" || (mode === "live" && writing)) && view) {
    return (
      <TalkMode
        question={view.question}
        asked={view.asked}
        total={view.coverage.length}
        covered={view.coverage.filter((c) => c.done).length}
        writing={writing}
        silent={mode === "live"}
        busy={busy}
        onAnswer={send}
        onType={() => pick("type")}
        onFinish={finish}
        onAttach={attach}
      />
    );
  }

  const severityQ = view?.question?.slot === "severity";
  const options = view?.question?.options || (severityQ ? Array.from({ length: 11 }, (_, i) => String(i)) : null);

  return (
    <div className={s.page}>
      <aside className={s.rail} aria-label="What we've covered">
        <a href="/home" className="brand"><Mark /> ClinicQuick</a>
        <h2 className={s.railTitle}>Intake sheet</h2>
        {view && (
          <div className={s.progress} aria-hidden="true">
            <span style={{ width: `${Math.round((view.coverage.filter((c) => c.done).length / Math.max(1, view.coverage.length)) * 100)}%` }} />
          </div>
        )}
        <ul className={s.sheet}>
          {view?.coverage.map((c) => (
            <li key={c.slot} className={c.done ? s.covered : ""}>
              <span className={s.box} aria-hidden="true">{c.done ? <svg viewBox="0 0 16 16" width="14" height="14"><path d="M3 8.5l3 3 7-7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" /></svg> : null}</span>
              <span>
                <span className={s.slotLabel}>{c.label}</span>
                {c.done && c.summary && <span className={s.slotSum}>{c.summary}</span>}
              </span>
              <span className="sr-only">{c.done ? "covered" : "not yet"}</span>
            </li>
          ))}
        </ul>
        <p className={s.railNote}>
          {view ? `${view.asked} of about ${view.max_questions} questions` : ""}
          <br />
          {view?.mode === "gemini" ? "Questions written by Gemini, checked by safety rules." : "Running on the built-in question set."}
        </p>
      </aside>

      <main className={`ecg ${s.chat}`}>
        <div className={s.log}>
          {turns.map((t, i) => (
            <div key={i} className={s.turn}>
              <p className={s.pastQ}><span className={`tag ${t.type}`}>{TYPE_LABEL[t.type] || t.type}</span> {t.question}</p>
              <p className={s.pastA}>{t.answer}</p>
            </div>
          ))}

          {media.length > 0 && (
            <div className={s.mediaRow}>
              {media.map((m, i) => (
                <figure key={i} className={s.mediaItem}>
                  {m.kind === "video" ? <video src={m.url} controls muted playsInline /> : <img src={m.url} alt="What you shared" />}
                  <figcaption>{m.uploading ? "Looking at it…" : m.quality_note ? m.quality_note : m.description}</figcaption>
                </figure>
              ))}
            </div>
          )}

          {writing ? (
            <div className={s.current}>
              <p className={s.who}>Lena, AI intake assistant</p>
              <h1 className={s.q}>Thank you. I'm writing up your summary and a note for your clinician…</h1>
            </div>
          ) : busy ? (
            <div className={s.current} aria-live="polite">
              <p className={s.who}>Lena, AI intake assistant</p>
              <p className={s.thinking}><span /><span /><span /> Thinking about your answer</p>
            </div>
          ) : view?.question ? (
            <div className={s.current} aria-live="polite">
              <p className={s.who}>Lena, AI intake assistant <span className={`tag ${view.question.type}`}>{TYPE_LABEL[view.question.type] || view.question.type}</span></p>
              <h1 className={s.q}>{view.question.text}</h1>
            </div>
          ) : null}
          <div ref={endRef} />
        </div>

        {!writing && view?.question && (
          <form className={s.composer} onSubmit={(e) => { e.preventDefault(); send(text); }}>
            {options && (
              <div className={`choices ${severityQ ? s.scale : ""}`}>
                {options.map((o) => (
                  <button key={o} type="button" className="chip" disabled={busy} onClick={() => send(severityQ ? `${o} out of 10` : o)}>{o}</button>
                ))}
              </div>
            )}
            <div className={s.inputRow}>
              <div className={s.tools}>
                {voice.supported && (
                  <button type="button" className={`${s.tool} ${voice.listening ? s.live : ""}`} onClick={() => (voice.listening ? voice.stop() : voice.start())}
                    aria-pressed={voice.listening} aria-label={voice.listening ? "Stop listening" : "Answer by voice"} title={voice.listening ? "Stop listening" : "Answer by voice"}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>
                  </button>
                )}
                <button type="button" className={s.tool} onClick={() => fileRef.current?.click()} aria-label="Add a photo or video" title="Add a photo or video">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3.5" /></svg>
                </button>
                <input ref={fileRef} type="file" accept="image/*,video/*" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) attach(f); e.target.value = ""; }} />
              </div>
              <textarea ref={inputRef} rows={2} value={text} disabled={busy} placeholder={voice.listening ? "Listening… speak now" : options ? "Or type or say your answer" : "Type or say your answer"}
                aria-label="Your answer" onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }} />
              <button className="btn" disabled={busy || !text.trim()}>{busy ? "…" : "Send"}</button>
            </div>
            <div className={s.below}>
              {err || voice.error ? <span className="error" role="alert">{err || voice.error}</span> : <span className="small">If this is an emergency, call 911. ClinicQuick doesn't diagnose.</span>}
              {speechRecognitionSupported() && <button type="button" className="linkish small" onClick={() => pick("talk")}>Switch to talking</button>}
              {(view.asked ?? 0) >= 5 && <button type="button" className="linkish small" onClick={finish}>That's everything, write my summary</button>}
            </div>
          </form>
        )}
      </main>
    </div>
  );
}
