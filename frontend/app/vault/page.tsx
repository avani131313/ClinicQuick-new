"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Footer, TopBar, useRequireRole } from "@/components/ui";
import { api } from "@/lib/api";
import s from "./vault.module.css";

const KIND_LABEL: Record<string, string> = { intake: "Check-in", document: "Document", lab: "Lab result", note: "Clinician note" };

export default function Vault() {
  const ok = useRequireRole(["patient"]);
  const [items, setItems] = useState<any[]>([]);
  const [docs, setDocs] = useState<any[]>([]);
  const [status, setStatus] = useState("");
  const [pending, setPending] = useState<any>(null);
  const file = useRef<HTMLInputElement>(null);

  const load = async () => {
    try {
      const [t, d] = await Promise.all([api("/timeline"), api("/vault")]);
      setItems(t); setDocs(d);
    } catch (e: any) { setStatus(e.message); }
  };
  useEffect(() => { if (ok) load(); }, [ok]);

  async function upload(f: File) {
    setStatus("Uploading and reading your document…");
    const fd = new FormData(); fd.append("file", f);
    try {
      const doc = await api("/vault/upload", { form: fd });
      setStatus(doc.extracted ? "Here's what we read. Check it before saving the values." : (doc.read_error || "Saved, but no values could be read from it."));
      if (doc.extracted) setPending(doc);
      load();
    } catch (e: any) { setStatus(e.message); }
  }
  async function confirm() {
    const r = await api(`/vault/${pending.id}/confirm`, { method: "POST" });
    setStatus(`Saved ${r.observations_added} results to your timeline.`);
    setPending(null); load();
  }

  if (!ok) return null;
  return (
    <>
      <TopBar />
      <main className="wrap">
        <section className={s.head}>
          <h1>Health records</h1>
          <p className="muted">Lab results, discharge letters, prescriptions. Upload a PDF or a photo and ClinicQuick reads the values into your timeline, so the next clinician sees them.</p>
          <input ref={file} type="file" accept=".pdf,image/*" hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          <button className="btn" onClick={() => file.current?.click()}>Upload a record</button>
          {status && <p className="small" role="status" style={{ marginTop: 12 }}>{status}</p>}
        </section>

        {pending && (
          <section className="sheet" style={{ marginBottom: 28 }}>
            <h2>Check what we read</h2>
            <p>{pending.extracted.summary}</p>
            {pending.extracted.lab_values.length > 0 ? (
              <table>
                <thead><tr><th>Test</th><th>Result</th><th>Reference range</th><th>Flag</th></tr></thead>
                <tbody>{pending.extracted.lab_values.map((v: any, i: number) => (
                  <tr key={i}><td>{v.test}</td><td>{v.value ?? v.value_text} {v.unit}</td><td>{v.reference_range || "—"}</td><td>{v.flag || ""}</td></tr>
                ))}</tbody>
              </table>
            ) : <p className="muted">No lab values found on this document.</p>}
            <div className="choices" style={{ marginTop: 16 }}>
              <button className="btn" onClick={confirm}>Looks right, save to timeline</button>
              <button className="btn ghost" onClick={() => setPending(null)}>Don't save values</button>
            </div>
          </section>
        )}

        <div className={s.cols}>
          <section>
            <h2>Timeline</h2>
            {items.length === 0 ? <p className="muted">Nothing yet. Check-ins and uploaded records appear here in date order.</p> : (
              <ol className={s.timeline}>
                {items.map((it, i) => (
                  <li key={i} data-kind={it.kind}>
                    <time>{new Date(it.ts).toLocaleDateString("en-CA", { month: "short", day: "numeric", year: "numeric" })}</time>
                    <div>
                      <span className={s.kind}>{KIND_LABEL[it.kind]}</span>
                      <p className={s.title}>{it.kind === "intake" && it.status !== "active" ? <Link href={`/visit/${it.id}/report`}>{it.title}</Link> : it.title}</p>
                      {it.detail && <p className="small">{it.detail}</p>}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>
          <aside>
            <h2>Files</h2>
            {docs.length === 0 ? <p className="muted small">No files yet.</p> : (
              <ul className={s.files}>{docs.map((d) => <li key={d.id}><strong>{d.filename}</strong><span className="small">Added by {d.uploaded_by}, {new Date(d.ts).toLocaleDateString("en-CA")}</span></li>)}</ul>
            )}
          </aside>
        </div>
      </main>
      <Footer />
    </>
  );
}
