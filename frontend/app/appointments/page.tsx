"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fmtDay, fmtTime } from "@/components/Booking";
import { Footer, TopBar, useRequireRole } from "@/components/ui";
import { api } from "@/lib/api";
import s from "./appointments.module.css";

const until = (iso: string) => {
  const days = Math.round((new Date(new Date(iso).toDateString()).getTime() - new Date(new Date().toDateString()).getTime()) / 86400000);
  return days <= 0 ? "Today" : days === 1 ? "Tomorrow" : `In ${days} days`;
};

export default function Appointments() {
  const ok = useRequireRole(["patient"]);
  const [list, setList] = useState<any[] | null>(null);
  const [err, setErr] = useState("");
  const load = () => api("/appointments").then(setList).catch((e) => setErr(e.message));
  useEffect(() => { if (ok) load(); }, [ok]);
  async function cancel(id: string) {
    if (!confirm("Cancel this appointment?")) return;
    await api(`/appointments/${id}/cancel`, { method: "POST" });
    load();
  }
  if (!ok) return null;
  const now = Date.now();
  const upcoming = (list || []).filter((a) => new Date(a.starts_at).getTime() > now && a.status === "booked");
  const past = (list || []).filter((a) => !upcoming.includes(a));
  const [first, ...rest] = upcoming;

  return (
    <>
      <TopBar />
      <main className={`wrap ${s.page}`}>
        <header className={s.head}>
          <p className="eyebrow">Appointments</p>
          <h1>{first ? "You're booked." : "Nothing booked yet."}</h1>
          <p className="muted">Booking from the end of a check-in sends your intake summary with it, so you won't repeat your story in the room.</p>
        </header>
        {err && <p className="error">{err}</p>}

        {list && !first && (
          <section className={s.empty}>
            <div>
              <h2>Start with a check-in.</h2>
              <p className="muted">Tell Lena what's going on. At the end you'll see where to go and can book a clinician straight from your summary.</p>
            </div>
            <Link href="/visit/new" className="btn">Start a check-in</Link>
          </section>
        )}

        {first && (
          <article className={s.ticket}>
            <div className={s.tWhen}>
              <span className={s.tTag}>{until(first.starts_at)}</span>
              <span className={s.tTime}>{fmtTime(first.starts_at)}</span>
              <span className={s.tDay}>{fmtDay(first.starts_at)}</span>
            </div>
            <div className={s.tBody}>
              <p className="eyebrow">With</p>
              <h2>{first.clinician.name}</h2>
              <p className="muted">{first.clinician.clinic}</p>
              <p className={s.about}>{first.reason || "Check-in summary"}</p>
              <div className={s.tActions}>
                {first.encounter_id
                  ? <Link className="btn" href={`/visit/${first.encounter_id}/report`}>Your summary for this visit</Link>
                  : <Link className="btn" href="/visit/new">Do a check-in before the visit</Link>}
                <button className="linkish" onClick={() => cancel(first.id)}>Cancel</button>
              </div>
              <p className={s.sent}>{first.encounter_id ? "Your intake summary is already with your clinician." : "No intake summary attached yet. A quick check-in before the visit saves time in the room."}</p>
            </div>
          </article>
        )}

        {rest.length > 0 && (
          <section className={s.block}>
            <h2 className={s.blockTitle}>Also coming up</h2>
            <ul className={s.list}>
              {rest.map((a) => (
                <li key={a.id}>
                  <span className="num">{fmtDay(a.starts_at)}, {fmtTime(a.starts_at)}</span>
                  <span>{a.clinician.name}</span>
                  <span>{a.encounter_id ? <Link href={`/visit/${a.encounter_id}/report`}>{a.reason || "Summary"}</Link> : a.reason || "—"}</span>
                  <button className="linkish small" onClick={() => cancel(a.id)}>Cancel</button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {past.length > 0 && (
          <section className={s.block}>
            <h2 className={s.blockTitle}>Past visits</h2>
            <ol className={s.timeline}>
              {past.map((a) => (
                <li key={a.id}>
                  <time className="num">{new Date(a.starts_at).toLocaleDateString("en-CA", { month: "short", day: "numeric", year: "numeric" })}</time>
                  <strong>{a.reason || "Visit"}</strong>
                  <span className="muted">with {a.clinician.name}{a.status === "completed" ? "" : `, ${a.status}`}</span>
                  <span className={s.links}>
                    {a.encounter_id && <Link href={`/visit/${a.encounter_id}/report`}>Check-in summary</Link>}
                    {a.status === "completed" && <Link href="/vault">Visit notes in Records</Link>}
                  </span>
                </li>
              ))}
            </ol>
          </section>
        )}
      </main>
      <Footer />
    </>
  );
}
