"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import s from "./booking.module.css";

type Doc = { id: string; name: string; clinic: string; specialty: string; slots: string[] };

const dayKey = (iso: string) => iso.slice(0, 10);
const fmtDay = (iso: string) => new Date(iso).toLocaleDateString("en-CA", { weekday: "short", month: "short", day: "numeric" });
const fmtTime = (iso: string) => new Date(iso).toLocaleTimeString("en-CA", { hour: "numeric", minute: "2-digit" });

export default function Booking({ encounterId, onBooked, reason }: { encounterId?: string | null; onBooked: (a: any) => void; reason?: string }) {
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [doc, setDoc] = useState<Doc | null>(null);
  const [day, setDay] = useState<string>("");
  const [slot, setSlot] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { api("/clinicians").then((d) => { setDocs(d); if (d[0]) setDoc(d[0]); }).catch((e) => setErr(e.message)); }, []);
  const days = useMemo(() => Array.from(new Set((doc?.slots || []).map(dayKey))), [doc]);
  useEffect(() => { setDay(days[0] || ""); setSlot(""); }, [days]);

  async function confirm() {
    if (!doc || !slot) return;
    setBusy(true); setErr("");
    try {
      const a = await api("/appointments", { body: { clinician_id: doc.id, starts_at: slot, encounter_id: encounterId || null, reason: reason || null } });
      onBooked(a);
    } catch (e: any) {
      setErr(e.message);
      api("/clinicians").then((d) => { setDocs(d); setDoc(d.find((x: Doc) => x.id === doc.id) || d[0]); });
    }
    setBusy(false);
  }

  if (!docs) return <p className="muted">{err || "Loading available clinicians…"}</p>;
  if (!docs.length) return <p className="muted">No clinicians on ClinicQuick are taking bookings yet.</p>;
  return (
    <div className={s.wrap}>
      <fieldset className={s.fs}>
        <legend>Choose a clinician</legend>
        <div className={s.docs}>
          {docs.map((d) => (
            <button key={d.id} type="button" className={s.doc} aria-pressed={doc?.id === d.id} onClick={() => setDoc(d)}>
              <strong>{d.name}</strong>
              <span>{d.specialty}</span>
              <span className="small">{d.clinic}</span>
            </button>
          ))}
        </div>
      </fieldset>
      {doc && (
        <fieldset className={s.fs}>
          <legend>Pick a time</legend>
          <div className={s.days} role="tablist">
            {days.map((d) => <button key={d} type="button" role="tab" aria-selected={d === day} className={s.day} onClick={() => { setDay(d); setSlot(""); }}>{fmtDay(d + "T12:00:00")}</button>)}
          </div>
          <div className="choices">
            {doc.slots.filter((x) => dayKey(x) === day).map((x) => (
              <button key={x} type="button" className="chip" aria-pressed={slot === x} onClick={() => setSlot(x)}>{fmtTime(x)}</button>
            ))}
          </div>
        </fieldset>
      )}
      {err && <p className="error" role="alert">{err}</p>}
      <button className="btn" disabled={!slot || busy} onClick={confirm}>
        {busy ? "Booking…" : slot ? `Book ${fmtDay(slot)}, ${fmtTime(slot)}` : "Pick a time"}
      </button>
      <p className="small" style={{ marginTop: 10 }}>{encounterId ? `Your intake note goes to ${doc?.name || "the clinician"} with the booking, so you won't need to repeat your story.` : "Tip: book from the end of a check-in and your intake summary goes with the booking."}</p>
    </div>
  );
}

export { fmtDay, fmtTime };
