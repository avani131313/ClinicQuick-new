"use client";

import { useEffect, useState } from "react";
import PoseCoach from "@/components/physio/PoseCoach";
import { Footer, TopBar, useRequireRole } from "@/components/ui";
import { api } from "@/lib/api";
import s from "./physio.module.css";

type Item = { id: number; exercise: string; sets: number; reps: number; notes: string | null; name: string; target: string; how: string };
const today = () => new Date().toISOString().slice(0, 10);

export default function Physio() {
  const ok = useRequireRole(["patient"]);
  const [plan, setPlan] = useState<Item[] | null>(null);
  const [cur, setCur] = useState<number | null>(null);
  const [voice, setVoice] = useState(true);
  const [done, setDone] = useState<number[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!ok) return;
    api<{ plan: Item[] }>("/physio").then((r) => { setPlan(r.plan); setCur(r.plan[0]?.id ?? null); }).catch((e) => setErr(e.message));
    try { setDone(JSON.parse(localStorage.getItem(`cq.physio.${today()}`) || "[]")); } catch {}
    try { setVoice(localStorage.getItem("cq.coachVoice") !== "off"); } catch {}
  }, [ok]);

  const markDone = (id: number) => setDone((d) => {
    const n = d.includes(id) ? d : [...d, id];
    try { localStorage.setItem(`cq.physio.${today()}`, JSON.stringify(n)); } catch {}
    return n;
  });
  const toggleVoice = () => setVoice((v) => { try { localStorage.setItem("cq.coachVoice", v ? "off" : "on"); } catch {} return !v; });

  if (!ok) return null;
  const item = plan?.find((p) => p.id === cur);
  return (
    <>
      <TopBar />
      <main className={`wrap page ${s.page}`}>
        <header className={s.head}>
          <div>
            <p className="eyebrow">Physio</p>
            <h1>Your exercises</h1>
            <p className="muted">Assigned by your clinician. The camera coach watches your form, counts reps and tells you how to adjust.</p>
          </div>
          {plan && <p className={s.progress}><span className="num">{done.filter((d) => plan.some((p) => p.id === d)).length}</span> of {plan.length} done today</p>}
        </header>
        {err && <p className="error" role="alert">{err}</p>}
        <div className={s.layout}>
          <ol className={s.list}>
            {plan?.map((p) => (
              <li key={p.id}>
                <button className={s.item} aria-current={p.id === cur || undefined} onClick={() => setCur(p.id)}>
                  <span className={s.check} data-done={done.includes(p.id) || undefined} aria-hidden="true">
                    {done.includes(p.id) && <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>}
                  </span>
                  <span className={s.itemText}>
                    <strong>{p.name}</strong>
                    <small>{p.sets} sets × {p.reps} reps · {p.target}</small>
                    {p.notes && <em>{p.notes}</em>}
                  </span>
                </button>
              </li>
            ))}
            {!plan && !err && <li className="muted">Loading your plan…</li>}
          </ol>
          <section className={s.coach}>
            {item && <PoseCoach key={item.id} exerciseKey={item.exercise} reps={item.reps} sets={item.sets} voice={voice} onComplete={() => markDone(item.id)} />}
            <div className={s.under}>
              {item && <p className={s.how}><strong>How:</strong> {item.how}</p>}
              <button className="chip" aria-pressed={voice} onClick={toggleVoice}>Voice coach {voice ? "on" : "off"}</button>
            </div>
            <p className="small">Stop if anything hurts and tell your clinician. Tracking runs on your device; no video is uploaded.</p>
          </section>
        </div>
      </main>
      <Footer />
    </>
  );
}
