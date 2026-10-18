"use client";

import QRCode from "qrcode";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import Booking, { fmtDay, fmtTime } from "@/components/Booking";
import ClinicianNote from "@/components/ClinicianNote";
import { Footer, TopBar, URGENCY_CLASS, useRequireRole } from "@/components/ui";
import { api } from "@/lib/api";
import s from "./report.module.css";

function mapsLink(level: string) {
  const q = level === "pharmacist" ? "pharmacy" : level === "er" || level === "emergency_911" ? "emergency room hospital" : "walk-in clinic";
  return `https://www.google.com/maps/search/${encodeURIComponent(q + " near me")}`;
}

export default function Report() {
  const ok = useRequireRole(["patient"]);
  const { id } = useParams<{ id: string }>();
  const [r, setR] = useState<any>(null);
  const [tab, setTab] = useState<"you" | "clinician">("you");
  const [share, setShare] = useState<{ url: string; qr: string; expires_at: string } | null>(null);
  const [fhir, setFhir] = useState<any>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(false);
  const [booking, setBooking] = useState(false);
  const [booked, setBooked] = useState<any>(null);

  useEffect(() => {
    if (!ok) return;
    api(`/encounters/${id}/report`).then(setR).catch((e) => setErr(e.message));
    api("/appointments").then((a) => setBooked(a.find((x: any) => x.encounter_id === id) || null)).catch(() => {});
  }, [ok, id]);

  async function makeShare() {
    setBusy("share"); setErr("");
    try {
      const x = await api(`/encounters/${id}/share`, { method: "POST" });
      const qr = await QRCode.toDataURL(x.url, { margin: 1, width: 220, color: { dark: "#123A40", light: "#FFFFFF" } });
      setShare({ ...x, qr });
    } catch (e: any) { setErr(e.message); }
    setBusy("");
  }
  async function pushFhir() {
    setBusy("fhir"); setErr("");
    try { setFhir(await api(`/encounters/${id}/fhir/push`, { method: "POST" })); } catch (e: any) { setErr(e.message); }
    setBusy("");
  }
  async function downloadFhir() {
    const b = await api(`/encounters/${id}/fhir`);
    const url = URL.createObjectURL(new Blob([JSON.stringify(b, null, 2)], { type: "application/fhir+json" }));
    const a = document.createElement("a"); a.href = url; a.download = `clinicquick-intake-${id.slice(0, 8)}.fhir.json`; a.click();
    URL.revokeObjectURL(url);
  }

  if (!ok) return null;
  if (!r) return (<><TopBar /><main className="wrap" style={{ padding: 40 }}>{err ? <p className="error">{err}</p> : <p className="muted">Loading your summary…</p>}</main></>);
  const p = r.patient;
  const u = p.urgency;
  const level: string = u.level;
  const urgent = level === "er" || level === "emergency_911";
  const secondary = level === "pharmacist"
    ? { title: "Find a pharmacy near me", sub: "Pharmacists can assess and prescribe for this", href: mapsLink(level) }
    : level === "self_care"
    ? { title: "Call Health811", sub: "Free nurse advice, 24/7, in Ontario", href: "tel:811" }
    : { title: "Find a walk-in clinic near me", sub: level === "walk_in_today" ? "Live waits nearby. Best if you need to be seen today" : "See live waits at clinics nearby", href: "/care-now#walkin" };

  return (
    <>
      <TopBar />
      <main className="wrap">
        <div className={`${s.tabs} no-print`} role="tablist">
          <button role="tab" aria-selected={tab === "you"} className={s.tab} onClick={() => setTab("you")}>For you</button>
          <button role="tab" aria-selected={tab === "clinician"} className={s.tab} onClick={() => setTab("clinician")}>For your clinician</button>
        </div>

        {tab === "you" ? (
          <div className={s.grid}>
            <div>
              <section className={`band ${URGENCY_CLASS[u.colour]}`}>
                <p className={s.bandKicker}>Your next step</p>
                <h2>{u.label}</h2>
                <p>{u.where}. {u.when}.</p>
              </section>

              <section className={s.options} aria-label="What you can do next">
                {booked ? (
                  <div className={s.confirm}>
                    <h3>Booked: {fmtDay(booked.starts_at)} at {fmtTime(booked.starts_at)}</h3>
                    <p>{booked.clinician.name}, {booked.clinician.clinic}. Your intake note has been sent to them.</p>
                    <Link href="/appointments">See my appointments</Link>
                  </div>
                ) : urgent ? (
                  <>
                    <a className={`${s.option} ${s.optionUrgent}`} href="tel:911"><strong>Call 911</strong><span>If symptoms are severe or getting worse</span></a>
                    <a className={s.option} href={mapsLink(level)} target="_blank" rel="noreferrer"><strong>Find the nearest emergency department</strong><span>Opens Google Maps</span></a>
                  </>
                ) : (
                  <>
                    <button className={`${s.option} ${booking ? s.optionOn : ""}`} onClick={() => setBooking(!booking)} aria-expanded={booking}>
                      <strong>Book an appointment</strong>
                      <span>{level === "walk_in_today" ? "Next available time with a ClinicQuick clinician" : "Choose a clinician and a time"}</span>
                    </button>
                    <a className={s.option} href={secondary.href} target={secondary.href.startsWith("http") ? "_blank" : undefined} rel="noreferrer">
                      <strong>{secondary.title}</strong><span>{secondary.sub}</span>
                    </a>
                  </>
                )}
              </section>
              {booking && !booked && (
                <section className={`sheet ${s.bookSheet}`}>
                  {level === "walk_in_today" && <p className="small">You should be seen today. If no time below is today, a walk-in clinic is the faster option.</p>}
                  <Booking encounterId={id} onBooked={(a) => { setBooked(a); setBooking(false); }} />
                </section>
              )}

              <section className="section">
                <h2>What you told us</h2>
                <p className={s.summary}>{p.summary}</p>
              </section>

              <section className="section">
                <h2>What to do</h2>
                <ul className={s.steps}>{p.next_steps.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
                <h3>Why we suggested this</h3>
                <ul className={s.reasons}>{u.reasons.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
              </section>

              <section className="section">
                <h2>Get help sooner if</h2>
                <ul className={s.watch}>{p.watch_for.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
              </section>

              {p.scores.length > 0 && (
                <section className="section">
                  <h2>Your screening scores</h2>
                  <dl className={s.scores}>
                    {p.scores.map((x: any) => (
                      <div key={x.name}>
                        <dt>{x.name}</dt>
                        <dd><strong className={x.severity ? s.flag : ""}>{x.band}</strong><br /><span className="small">{x.summary}</span></dd>
                      </div>
                    ))}
                  </dl>
                </section>
              )}
              <p className="small">{p.disclaimer}</p>
            </div>

            <aside className={`${s.share} no-print`}>
              <h2>Bring this to your visit</h2>
              <p className="muted">Share a link with your clinic, or show the QR code at check-in. They'll see the clinician note, not just this page.</p>
              {share ? (
                <div className={s.qrBox}>
                  <img src={share.qr} alt="QR code linking to your clinician summary" width={200} height={200} />
                  <div className={s.copyRow}>
                    <input type="text" readOnly value={share.url} aria-label="Share link" onFocus={(e) => e.target.select()} />
                    <button className="btn small" onClick={() => { navigator.clipboard?.writeText(share.url); setCopied(true); }}>{copied ? "Copied" : "Copy"}</button>
                  </div>
                  <p className="small">Expires {new Date(share.expires_at).toLocaleDateString("en-CA", { month: "long", day: "numeric" })}. Every view is logged.</p>
                </div>
              ) : (
                <button className="btn" onClick={makeShare} disabled={busy === "share"}>{busy === "share" ? "Creating…" : "Create share link"}</button>
              )}
              <div className={s.more}>
                <h3>Send to a clinic system</h3>
                <p className="small">Exports this visit as a standard FHIR R4 record that clinic software can import.</p>
                <div className="choices">
                  <button className="btn ghost small" onClick={pushFhir} disabled={busy === "fhir"}>{busy === "fhir" ? "Sending…" : "Send to FHIR test server"}</button>
                  <button className="btn ghost small" onClick={downloadFhir}>Download FHIR file</button>
                  <button className="btn ghost small" onClick={() => window.print()}>Print or save PDF</button>
                </div>
                {fhir && (
                  <p className="small" role="status">
                    Created {fhir.created.length} records on the public HAPI FHIR test server.{" "}
                    {fhir.patient_url && <a href={fhir.patient_url} target="_blank" rel="noreferrer">Open the patient record</a>}
                  </p>
                )}
              </div>
              {err && <p className="error" role="alert">{err}</p>}
              <p style={{ marginTop: 24 }}><Link href="/home">Back to home</Link></p>
            </aside>
          </div>
        ) : (
          <div style={{ padding: "8px 0 24px" }}>
            <p className="muted no-print">This is what your clinician sees. It includes possible conditions for them to consider; these are not a diagnosis.</p>
            <ClinicianNote c={r.clinician} />
          </div>
        )}
      </main>
      <Footer />
    </>
  );
}
