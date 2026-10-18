"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import Booking from "@/components/Booking";
import ClinicMap, { Clinic, waitTone } from "@/components/ClinicMap";
import { Footer, TopBar, useRequireRole } from "@/components/ui";
import { api } from "@/lib/api";
import s from "./care.module.css";

const DEFAULT: [number, number] = [43.4723, -80.5449]; // University of Waterloo, used when location is off
type Queue = { checked_in: boolean; clinic_id?: string; clinic_name?: string; ahead?: number; ahead_at_join?: number; eta_min?: number;
  progress?: number; elapsed_min?: number; called?: boolean; latest_summary?: { id: string; complaint: string } | null };

const clock = (min: number) => new Date(Date.now() + min * 60000).toLocaleTimeString("en-CA", { hour: "numeric", minute: "2-digit" });

function Ring({ value, size = 220 }: { value: number; size?: number }) {
  const r = size / 2 - 12, c = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className={s.ring} aria-hidden="true">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--line-2)" strokeWidth="8" />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--accent)" strokeWidth="8" strokeLinecap="round"
        strokeDasharray={c} strokeDashoffset={c * (1 - value)} transform={`rotate(-90 ${size / 2} ${size / 2})`} className={s.ringArc} />
    </svg>
  );
}

export default function CareNow() {
  const ok = useRequireRole(["patient"]);
  const [tab, setTab] = useState<"appointment" | "walkin" | null>(null);
  const [pos, setPos] = useState<[number, number]>(DEFAULT);
  const [located, setLocated] = useState<"default" | "device" | "denied">("default");
  const [clinics, setClinics] = useState<Clinic[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [q, setQ] = useState<Queue | null>(null);
  const [pick, setPick] = useState("");
  const [err, setErr] = useState("");
  const [booked, setBooked] = useState<any>(null);
  const [reason, setReason] = useState("");

  const loadClinics = useCallback((p: [number, number]) =>
    api(`/walkin/clinics?lat=${p[0]}&lng=${p[1]}`).then((r) => setClinics(r.clinics)).catch((e) => setErr(e.message)), []);
  const loadQueue = useCallback(() => api<Queue>("/walkin/me").then((r) => { setQ(r); setTab((t) => (t ?? (r.checked_in || location.hash === "#walkin" ? "walkin" : "appointment"))); }).catch(() => {}), []);

  useEffect(() => {
    if (!ok) return;
    loadClinics(DEFAULT); loadQueue();
    if (navigator.geolocation) navigator.geolocation.getCurrentPosition(
      (g) => { const p: [number, number] = [g.coords.latitude, g.coords.longitude]; setPos(p); setLocated("device"); loadClinics(p); },
      () => setLocated("denied"), { timeout: 6000, maximumAge: 300000 });
    const t = setInterval(loadQueue, 20000);
    const t2 = setInterval(() => loadClinics(pos), 120000);
    return () => { clearInterval(t); clearInterval(t2); };
  }, [ok]); // eslint-disable-line react-hooks/exhaustive-deps

  async function join(id: string) {
    setErr("");
    try { setQ(await api("/walkin/checkin", { body: { clinic_id: id } })); setTab("walkin"); window.scrollTo({ top: 0, behavior: "smooth" }); }
    catch (e: any) { setErr(e.message); }
  }
  async function leave() { setQ(await api("/walkin/leave", { method: "POST" })); }

  const open = useMemo(() => clinics.filter((c) => c.open), [clinics]);
  if (!ok) return null;

  return (
    <>
      <TopBar />
      <main className={`wrap ${s.page}`}>
        <header className={s.head}>
          <div>
            <p className="eyebrow">Book & walk-in</p>
            <h1>Get seen, your way.</h1>
          </div>
          <div className={s.switch} role="tablist" aria-label="How do you want to be seen?">
            <button role="tab" aria-selected={tab === "appointment"} aria-checked={tab === "appointment"} onClick={() => setTab("appointment")}>
              <span className={s.dot} data-on={booked ? true : undefined} />
              <span><strong>Appointment</strong><small>{booked ? "Booked" : "Pick a time with a clinician"}</small></span>
            </button>
            <button role="tab" aria-selected={tab === "walkin"} aria-checked={tab === "walkin"} onClick={() => setTab("walkin")}>
              <span className={s.dot} data-on={q?.checked_in || undefined} />
              <span><strong>Walk-in</strong><small>{q?.checked_in ? `In line at ${q.clinic_name}` : "Clinics near you and their waits"}</small></span>
            </button>
          </div>
        </header>
        {err && <p className="error" role="alert">{err}</p>}

        {tab === "walkin" && q?.checked_in && (
            <section className={s.queue}>
              <div className={s.ringBox}>
                <Ring value={q.progress || 0} />
                <div className={s.ringText}>
                  {q.called ? <><span className={s.big}>Now</span><span>You're next</span></> : <><span className={s.big}>{q.ahead}</span><span>{q.ahead === 1 ? "patient ahead" : "patients ahead"}</span></>}
                </div>
              </div>
              <div className={s.qInfo}>
                <p className="eyebrow">You're in line</p>
                <h2>{q.clinic_name}</h2>
                <dl className={s.qStats}>
                  <div><dt>Estimated wait</dt><dd><span className="num">{q.called ? "0" : q.eta_min}</span> min</dd></div>
                  <div><dt>Expected to be called</dt><dd className="num">{clock(q.eta_min || 0)}</dd></div>
                  <div><dt>Waiting so far</dt><dd><span className="num">{q.elapsed_min}</span> min</dd></div>
                </dl>
                <div className={s.line} aria-label={`${q.ahead} people ahead of you`}>
                  {Array.from({ length: Math.min(14, (q.ahead || 0)) }).map((_, i) => <span key={i} className={s.person} style={{ animationDelay: `${i * 60}ms` }} />)}
                  <span className={`${s.person} ${s.you}`}>You</span>
                </div>
                <div className={s.qActions}>
                  {q.latest_summary && <Link className="btn" href={`/visit/${q.latest_summary.id}/report`}>Show my intake summary at the desk</Link>}
                  {!q.latest_summary && <Link className="btn" href="/visit/new">Do a check-in while you wait</Link>}
                  <button className="btn ghost" onClick={leave}>Leave the line</button>
                </div>
                <p className={s.fine}>We'll send a notification when you're close. Wait times are simulated in this demo.</p>
              </div>
            </section>
        )}

        {tab === "walkin" && !q?.checked_in && (
          <>
            <section className={`panel ${s.joinBox}`}>
              <h2>Already at a clinic?</h2>
              <p className="muted">Join the line from here and watch your place update.</p>
              <div className={s.joinRow}>
                <select value={pick} onChange={(e) => setPick(e.target.value)} aria-label="Clinic">
                  <option value="">Choose a clinic</option>
                  {open.map((c) => <option key={c.id} value={c.id}>{c.name} · {c.waiting} waiting · {c.distance_km} km</option>)}
                </select>
                <button className="btn" disabled={!pick} onClick={() => join(pick)}>Join the line</button>
              </div>
            </section>
          <section className={s.find}>
            <div className={s.mapCol}>
              <ClinicMap center={pos} clinics={clinics} selected={sel} onSelect={(id) => { setSel(id); document.getElementById(`c-${id}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }} />
              <p className={s.loc}>
                {located === "device" ? "Showing clinics near you." : "Showing clinics near the University of Waterloo."}{" "}
                {located !== "device" && <button className="linkish small" onClick={() => navigator.geolocation?.getCurrentPosition((g) => { const p: [number, number] = [g.coords.latitude, g.coords.longitude]; setPos(p); setLocated("device"); loadClinics(p); }, () => setLocated("denied"))}>Use my location</button>}
                <span className={s.demo}>Demo: clinics and waits are simulated</span>
              </p>
            </div>
            <ul className={s.list}>
              {clinics.map((c) => (
                <li key={c.id} id={`c-${c.id}`}>
                  <article className={`${s.card} ${sel === c.id ? s.cardOn : ""}`} onClick={() => setSel(c.id)}>
                    <div className={s.cardHead}>
                      <h3>{c.name}</h3>
                      <span className={s.status} data-tone={waitTone(c)}>{c.open ? `${c.wait_min} min wait` : "Closed"}</span>
                    </div>
                    <p className={s.meta}>
                      <span className={c.open ? s.openTxt : s.closedTxt}>{c.open ? "Open" : "Closed"}</span> · {c.hours} · {c.distance_km} km · {c.walk_min} min walk · {c.drive_min} min drive
                    </p>
                    <p className={s.about}>{c.about}</p>
                    {c.open && (
                      <dl className={s.stats}>
                        <div><dt>Waiting now</dt><dd className="num">{c.waiting}</dd></div>
                        <div><dt>Clinicians</dt><dd className="num">{c.doctors_on_shift}</dd></div>
                        <div><dt>All seen by</dt><dd className="num">{c.clear_by}</dd></div>
                      </dl>
                    )}
                    <div className={s.cardActions}>
                      <a className="btn ghost small" href={`https://www.google.com/maps/dir/?api=1&destination=${c.lat},${c.lng}`} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>Directions</a>
                      {c.open && <button className="btn small" onClick={(e) => { e.stopPropagation(); join(c.id); }}>Join line remotely</button>}
                    </div>
                  </article>
                </li>
              ))}
            </ul>
          </section>
          </>
        )}

        {tab === "appointment" && <section className={s.book} id="book">
          <div className={s.bookHead}>
            <p className="eyebrow">Book an appointment</p>
            <h2>Pick a time that suits you.</h2>
            <p className="muted">For anything that isn't urgent. Best of all, <Link href="/visit/new">do a check-in first</Link> and book from your summary, so your clinician gets the whole story.</p>
          </div>
          {booked ? (
            <div className={`panel ${s.done}`}>
              <h3>Booked.</h3>
              <p>{new Date(booked.starts_at).toLocaleString("en-CA", { weekday: "long", month: "long", day: "numeric", hour: "numeric", minute: "2-digit" })} with {booked.clinician.name}.</p>
              <Link href="/appointments">See your appointments</Link>
            </div>
          ) : (
            <div className="panel">
              <div className="field"><label htmlFor="why">What's it about? (optional)</label><input id="why" type="text" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Repeat prescription, follow-up on blood test" /></div>
              <Booking reason={reason} onBooked={setBooked} />
            </div>
          )}
        </section>}
      </main>
      <Footer />
    </>
  );
}
