"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { fmtDay, fmtTime } from "@/components/Booking";
import HealthDashboard from "@/components/health/HealthDashboard";
import Medications, { MedHistory } from "@/components/Medications";
import PhysioPlan from "@/components/physio/PhysioPlan";
import { Footer, TopBar, useRequireRole } from "@/components/ui";
import { api } from "@/lib/api";
import d from "./dashboard.module.css";

type Tab = "overview" | "medications" | "physio" | "history" | "records";
const date = (iso: string) => new Date(iso).toLocaleDateString("en-CA", { month: "short", day: "numeric", year: "numeric" });

function Chips({ items, empty }: { items: string[]; empty: string }) {
  return items.length ? <ul className={d.chips}>{items.map((x) => <li key={x}>{x}</li>)}</ul> : <p className={d.empty}>{empty}</p>;
}

export default function PatientDashboard() {
  const ok = useRequireRole(["clinician"]);
  const { id } = useParams<{ id: string }>();
  const [p, setP] = useState<any>(null);
  const [h, setH] = useState<any>(null);
  const [err, setErr] = useState("");
  const [tab, setTab] = useState<Tab>("overview");
  const [busy, setBusy] = useState(false);
  const [meds, setMeds] = useState<MedHistory | null>(null);

  const load = () => {
    api(`/doctor/patients/${id}/medications`).then(setMeds).catch(() => {});
    api(`/doctor/patients/${id}`).then(setP).catch((e) => setErr(e.message));
    api(`/doctor/patients/${id}/health`).then(setH).catch(() => {});
  };
  useEffect(() => { if (ok) load(); }, [ok, id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function populate() {
    setBusy(true);
    try { setH(await api(`/doctor/patients/${id}/demo-data`, { method: "POST" })); } catch (e: any) { setErr(e.message); }
    setBusy(false);
  }

  if (!ok) return null;
  const pt = p?.patient;
  const next = (p?.appointments || []).find((a: any) => a.status === "booked" && new Date(a.starts_at) > new Date(Date.now() - 1800000));
  const latest = p?.visits?.[0];

  return (
    <>
      <TopBar />
      <main className={`wrap ${d.page}`}>
        <p className={d.back}><Link href="/doctor/patients">← All patients</Link></p>
        {err && <p className="error">{err}</p>}
        {!p && !err && <p className="muted">Loading…</p>}
        {pt && (
          <>
            <header className={d.head}>
              <div>
                <h1 className={d.name}>{pt.name}</h1>
                <p className={d.meta}>
                  <span>{pt.age} years</span><span>{pt.sex}</span><span>Born {pt.dob}</span>
                  {p.social?.occupation && <span>{p.social.occupation}</span>}
                </p>
              </div>
              <div className={d.headSide}>
                {next ? (
                  <p className={d.next}><small>Next visit</small>{fmtDay(next.starts_at)}, {fmtTime(next.starts_at)}<span>{next.reason}</span></p>
                ) : <p className={d.next}><small>Next visit</small>None booked</p>}
                {latest && <Link className="btn ghost small" href={`/doctor/visit/${latest.id}`}>Latest intake</Link>}
              </div>
            </header>

            <nav className={d.tabs} role="tablist" aria-label="Patient sections">
              {(["overview", "medications", "physio", "history", "records"] as Tab[]).map((t) => (
                <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>
                  {t === "overview" ? "Overview" : t === "medications" ? `Medications${meds ? ` · ${meds.current.length}` : ""}` : t === "physio" ? "Physio" : t === "history" ? `History · ${p.visits.length}` : `Records · ${p.documents.length}`}
                </button>
              ))}
            </nav>

            {tab === "overview" && (
              <div className={d.panelIn} key="o">
                <HealthDashboard data={h} sex={pt.sex} onPopulate={populate} populating={busy} who="clinician" />
                <div className={d.clinical}>
                  <section className="panel"><p className="panel-title">Conditions</p><Chips items={p.conditions} empty="None recorded" /></section>
                  <section className="panel"><p className="panel-title">Medications</p><Chips items={p.medications} empty="None recorded" /></section>
                  <section className="panel"><p className="panel-title">Allergies</p><Chips items={p.allergies} empty="No known allergies" /></section>
                  <section className="panel">
                    <p className="panel-title">Family and social</p>
                    <Chips items={[...(p.social?.smoking ? [`Smoking: ${p.social.smoking}`] : []), ...p.family_history]} empty="Nothing recorded" />
                  </section>
                </div>
              </div>
            )}

            {tab === "medications" && (
              <div className={d.panelIn} key="m">
                <Medications
                  data={meds}
                  addLabel="Prescribe"
                  onAdd={async (m) => setMeds(await api(`/doctor/patients/${id}/medications`, { body: m }))}
                  onStop={async (mid, reason) => setMeds(await api(`/doctor/patients/${id}/medications/${mid}/stop`, { body: { stop_reason: reason || null } }))}
                />
              </div>
            )}

            {tab === "history" && (
              <div className={d.panelIn} key="h">
                <div className={d.twoCol}>
                  <section>
                    <h2 className={d.sub}>Check-ins</h2>
                    {p.visits.length === 0 ? <p className="muted">No check-ins yet.</p> : (
                      <ol className={d.timeline}>
                        {p.visits.map((v: any) => (
                          <li key={v.id}>
                            <time className="num">{date(v.date)}</time>
                            <Link href={`/doctor/visit/${v.id}`} className={d.tlTitle}>{v.complaint || "Check-in"}</Link>
                            <p>{v.one_liner || (v.status === "stopped_red_flag" ? "Stopped by the emergency screen" : "")}</p>
                          </li>
                        ))}
                      </ol>
                    )}
                  </section>
                  <section>
                    <h2 className={d.sub}>Appointments with you</h2>
                    <ul className={d.appts}>
                      {p.appointments.slice().reverse().map((a: any) => (
                        <li key={a.id}>
                          <span className="num">{fmtDay(a.starts_at)}, {fmtTime(a.starts_at)}</span>
                          <span>{a.encounter_id ? <Link href={`/doctor/visit/${a.encounter_id}`}>{a.reason}</Link> : a.reason}</span>
                          <span className={d.status} data-s={a.status}>{a.status === "booked" ? "Upcoming" : "Completed"}</span>
                        </li>
                      ))}
                    </ul>
                    <h2 className={d.sub}>Notes</h2>
                    {p.notes.length ? <ul className={d.notes}>{p.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}</ul> : <p className="muted">No notes yet.</p>}
                  </section>
                </div>
              </div>
            )}

            {tab === "physio" && <PhysioPlan patientId={id} />}
            {tab === "records" && <Records id={id} docs={p.documents} onChange={load} />}
          </>
        )}
      </main>
      <Footer />
    </>
  );
}

function Records({ id, docs, onChange }: { id: string; docs: any[]; onChange: () => void }) {
  const file = useRef<HTMLInputElement>(null);
  const [picked, setPicked] = useState<File | null>(null);
  const [note, setNote] = useState("");
  const [status, setStatus] = useState("");
  const [pending, setPending] = useState<any>(null);
  const [drag, setDrag] = useState(false);

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!picked) return;
    setStatus("Uploading and reading the document…");
    const fd = new FormData(); fd.append("file", picked); fd.append("note", note);
    try {
      const doc = await api(`/doctor/patients/${id}/documents`, { form: fd });
      setStatus(doc.extracted ? "Read it. Check the values before adding them to the chart." : doc.read_error || "Saved to the patient's record.");
      if (doc.extracted?.lab_values?.length) setPending(doc);
      setPicked(null); setNote(""); onChange();
    } catch (e: any) { setStatus(e.message); }
  }
  async function confirm() {
    const r = await api(`/doctor/patients/${id}/documents/${pending.id}/confirm`, { method: "POST" });
    setStatus(`Added ${r.observations_added} results to the chart.`); setPending(null); onChange();
  }

  return (
    <div className={d.panelIn} key="r">
      <div className={d.twoCol}>
        <section className="panel">
          <p className="panel-title">Upload previous records</p>
          <p className="muted">Old lab results, specialist letters, discharge summaries, imaging reports. PDFs and photos are read automatically and the values can go straight into the chart.</p>
          <form onSubmit={upload}>
            <input ref={file} type="file" accept=".pdf,image/*" hidden onChange={(e) => setPicked(e.target.files?.[0] || null)} />
            <button type="button" className={d.drop} data-drag={drag || undefined}
              onClick={() => file.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) setPicked(f); }}>
              {picked ? <><strong>{picked.name}</strong><span>{(picked.size / 1024).toFixed(0)} KB · click to change</span></> : <><strong>Drop a file here</strong><span>or click to choose a PDF or photo</span></>}
            </button>
            <div className="field" style={{ marginTop: 16 }}>
              <label htmlFor="rn">Note for the chart (optional)</label>
              <textarea id="rn" rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Cardiology letter, 2024, rate control plan" />
            </div>
            <button className="btn" disabled={!picked}>Add to record</button>
            {status && <p className="small" role="status" style={{ marginTop: 12 }}>{status}</p>}
          </form>
          {pending && (
            <div className={d.review}>
              <p className="panel-title">Check what was read</p>
              <p>{pending.extracted.summary}</p>
              <table>
                <thead><tr><th>Test</th><th>Result</th><th>Range</th></tr></thead>
                <tbody>{pending.extracted.lab_values.map((v: any, i: number) => (
                  <tr key={i}><td>{v.test}</td><td className="num">{v.value ?? v.value_text} {v.unit}</td><td>{v.reference_range || "—"}</td></tr>
                ))}</tbody>
              </table>
              <div className="choices" style={{ marginTop: 14 }}>
                <button className="btn small" onClick={confirm}>Looks right, add to chart</button>
                <button className="btn ghost small" onClick={() => setPending(null)}>Keep the file only</button>
              </div>
            </div>
          )}
        </section>
        <section>
          <h2 className={d.sub}>On file</h2>
          {docs.length === 0 ? <p className="muted">No records yet.</p> : (
            <ul className={d.files}>
              {docs.map((x) => (
                <li key={x.id}>
                  <span className={d.fileIcon} aria-hidden="true">{(x.filename.split(".").pop() || "doc").slice(0, 4).toUpperCase()}</span>
                  <span className={d.fileMain}>
                    <strong>{x.filename}</strong>
                    <small>{x.uploaded_by} · {date(x.ts)}</small>
                    {x.extracted?.summary && <span className={d.fileSum}>{x.extracted.summary}</span>}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
