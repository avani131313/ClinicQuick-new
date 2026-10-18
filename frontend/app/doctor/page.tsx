"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fmtDay, fmtTime } from "@/components/Booking";
import { Footer, TopBar, useRequireRole } from "@/components/ui";
import { api } from "@/lib/api";
import s from "./doctor.module.css";

/** Only the cases that changed what the patient was told to do get a marker; everything else is just a visit. */
const URGENT: Record<string, string> = { walk_in_today: "Flagged same-day", er: "Sent to emergency", emergency_911: "Stopped: 911" };

const greeting = () => { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"; };
const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString();
const longDate = (iso: string) => new Date(iso).toLocaleDateString("en-CA", { weekday: "long", month: "long", day: "numeric" });
const until = (iso: string) => {
  const d = new Date(iso), now = new Date();
  if (sameDay(d, now)) return "Today";
  const days = Math.round((new Date(d.toDateString()).getTime() - new Date(now.toDateString()).getTime()) / 86400000);
  return days === 1 ? "Tomorrow" : `In ${days} days`;
};

function Brief({ appt }: { appt: any }) {
  const [note, setNote] = useState<any>(null);
  const [hist, setHist] = useState<any>(null);
  useEffect(() => {
    setNote(null); setHist(null);
    if (appt.encounter_id) api(`/doctor/encounters/${appt.encounter_id}`).then((d) => setNote(d.report?.clinician)).catch(() => {});
    api(`/doctor/patients/${appt.patient.id}`).then(setHist).catch(() => {});
  }, [appt]);
  const last = hist?.visits?.[0];
  const c = note;
  return (
    <article className={s.brief}>
      <header className={s.briefHead}>
        <div className={s.when}>
          <span className={s.whenTag}>{until(appt.starts_at)}</span>
          <span className={s.whenTime}>{fmtTime(appt.starts_at)}</span>
          <span className={s.whenDay}>{longDate(appt.starts_at)}</span>
        </div>
        <div className={s.who}>
          <p className="eyebrow">Next visit</p>
          <h2 className={s.whoName}><Link href={`/doctor/patients/${appt.patient.id}`}>{appt.patient.name}</Link></h2>
          <p className={s.whoMeta}>{appt.patient.age}, {appt.patient.sex}{hist?.conditions?.length ? ` · ${hist.conditions.join(", ")}` : ""}</p>
          <p className={s.reason}>{appt.reason}</p>
        </div>
      </header>

      {c ? (
        <div className={s.briefBody}>
          <section>
            <p className="panel-title">Intake summary, for this visit</p>
            <p className={s.oneLiner}>{c.one_liner}</p>
            <dl className={s.hpi}>
              {(c.hpi || []).slice(0, 5).map((h: any) => <div key={h.slot}><dt>{h.label}</dt><dd>{h.text}</dd></div>)}
            </dl>
            {appt.urgency && URGENT[appt.urgency] && <p className={s.urgent}>{URGENT[appt.urgency]} by the safety rules</p>}
          </section>
          <aside className={s.briefSide}>
            <div><p className="panel-title">Medications</p><p>{c.medications.join(", ") || "None"}</p></div>
            <div><p className="panel-title">Allergies</p><p>{c.allergies.join(", ") || "No known allergies"}</p></div>
            <div><p className="panel-title">Patient is worried about</p><p>{c.ice || "Not stated"}</p></div>
          </aside>
        </div>
      ) : (
        <div className={s.briefEmpty}>
          <p><strong>No check-in for this visit yet.</strong> When {appt.patient.name.split(" ")[0]} talks to the intake assistant before coming in, the summary appears here.</p>
          {last && (
            <p className="muted">
              Most recent check-in, {new Date(last.date).toLocaleDateString("en-CA", { month: "short", day: "numeric" })}:{" "}
              <Link href={`/doctor/visit/${last.id}`}>{last.one_liner || last.complaint}</Link>
            </p>
          )}
        </div>
      )}

      <footer className={s.briefActions}>
        {appt.encounter_id && <Link className="btn" href={`/doctor/visit/${appt.encounter_id}`}>Open full intake note</Link>}
        <Link className={appt.encounter_id ? "btn ghost" : "btn"} href={`/doctor/patients/${appt.patient.id}`}>Patient dashboard</Link>
      </footer>
    </article>
  );
}

export default function Doctor() {
  const ok = useRequireRole(["clinician"]);
  const [me, setMe] = useState<any>(null);
  const [list, setList] = useState<any[] | null>(null);
  const [err, setErr] = useState("");
  const [focus, setFocus] = useState<string | null>(null);
  useEffect(() => {
    if (!ok) return;
    api("/doctor/me").then(setMe).catch(() => {});
    api("/doctor/appointments").then(setList).catch((e) => setErr(e.message));
  }, [ok]);
  if (!ok) return null;

  const now = Date.now() - 30 * 60 * 1000;
  const upcoming = (list || []).filter((a) => a.status === "booked" && new Date(a.starts_at).getTime() >= now);
  const past = (list || []).filter((a) => !upcoming.includes(a)).reverse();
  const todays = upcoming.filter((a) => sameDay(new Date(a.starts_at), new Date()));
  const current = upcoming.find((a) => a.id === focus) || upcoming[0];

  return (
    <>
      <TopBar />
      <main className={`wrap ${s.page}`}>
        <header className={s.head}>
          <p className="eyebrow">{new Date().toLocaleDateString("en-CA", { weekday: "long", month: "long", day: "numeric" })}{me?.clinic ? ` · ${me.clinic}` : ""}</p>
          <h1>{greeting()}.</h1>
          {list && (
            <p className={s.lede}>
              {todays.length ? `${todays.length} ${todays.length === 1 ? "visit" : "visits"} today` : "No visits today"}
              {upcoming.length > todays.length ? `, ${upcoming.length - todays.length} coming up` : ""}.
              {upcoming.length ? " Each one arrives with the patient's intake summary." : ""}
            </p>
          )}
        </header>
        {err && <p className="error">{err}</p>}

        {list && upcoming.length === 0 && (
          <section className={`panel ${s.none}`}>
            <h2>Nothing booked.</h2>
            <p className="muted">When a patient finishes a check-in and books you, the visit appears here with their intake summary ready.</p>
            <Link className="btn ghost" href="/doctor/patients">See your patients</Link>
          </section>
        )}

        {current && <Brief appt={current} />}

        {upcoming.length > 1 && (
          <section className={s.block}>
            <h2 className={s.blockTitle}>Coming up</h2>
            <ul className={s.queue}>
              {upcoming.map((a) => (
                <li key={a.id}>
                  <button className={a.id === current?.id ? s.queueOn : ""} onClick={() => setFocus(a.id)}>
                    <span className={s.qTime}><span className="num">{fmtTime(a.starts_at)}</span><small>{fmtDay(a.starts_at)}</small></span>
                    <span className={s.qWho}><strong>{a.patient.name}</strong><small>{a.patient.age}, {a.patient.sex}</small></span>
                    <span className={s.qWhat}>{a.one_liner || a.reason}</span>
                    <span className={s.qState}>{a.encounter_id ? "Summary ready" : "No check-in yet"}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        <details className={s.history}>
          <summary>
            <span>Past visits</span>
            <span className={s.count}>{past.length}</span>
          </summary>
          {past.length === 0 ? <p className="muted">No past visits yet.</p> : (
            <table>
              <thead><tr><th>Date</th><th>Patient</th><th>Intake</th><th className="hide-sm" /></tr></thead>
              <tbody>
                {past.map((a) => (
                  <tr key={a.id}>
                    <td className="num">{new Date(a.starts_at).toLocaleDateString("en-CA", { month: "short", day: "numeric", year: "numeric" })}</td>
                    <td><Link href={`/doctor/patients/${a.patient.id}`}>{a.patient.name}</Link></td>
                    <td>{a.encounter_id ? <Link href={`/doctor/visit/${a.encounter_id}`}>{a.one_liner || a.reason}</Link> : a.reason}</td>
                    <td className="hide-sm">{a.urgency && URGENT[a.urgency] ? <span className={s.urgentChip}>{URGENT[a.urgency]}</span> : null}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </details>
      </main>
      <Footer />
    </>
  );
}
