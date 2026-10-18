"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import ClinicianNote from "@/components/ClinicianNote";
import { Footer, Mark } from "@/components/ui";
import { api } from "@/lib/api";

export default function ClinicianPortal() {
  const { token } = useParams<{ token: string }>();
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState({ clinician: "", note: "" });
  const [status, setStatus] = useState("");

  const load = () => api(`/share/${token}`, { auth: false }).then(setD).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setStatus("Uploading…");
    const fd = new FormData();
    fd.append("file", file);
    fd.append("note", form.note);
    fd.append("clinician", form.clinician || "Clinician");
    try {
      await api(`/share/${token}/documents`, { form: fd, auth: false });
      setStatus("Added to the patient's health record.");
      setFile(null); setForm({ ...form, note: "" });
      load();
    } catch (e: any) { setStatus(e.message); }
  }

  return (
    <>
      <header className="topbar">
        <span className="brand"><Mark /> ClinicQuick for clinicians</span>
        {d && <span className="small">Link expires {new Date(d.expires_at).toLocaleDateString("en-CA", { month: "short", day: "numeric" })}. Viewed {d.view_count} time{d.view_count === 1 ? "" : "s"}.</span>}
      </header>
      <main className="wrap" style={{ padding: "24px 20px" }}>
        {err && <p className="error" role="alert">{err}</p>}
        {d?.report && <ClinicianNote c={d.report.clinician} />}

        {d && (
          <section className="sheet no-print" style={{ marginTop: 24 }}>
            <h2>After the visit</h2>
            <p className="muted">Upload a visit summary, lab results or a referral letter. It goes into the patient's own health record so they have it next time.</p>
            <form onSubmit={upload} style={{ maxWidth: 560 }}>
              <div className="field"><label htmlFor="cn">Your name</label><input id="cn" type="text" value={form.clinician} placeholder="e.g. Dr. Lena Chen" onChange={(e) => setForm({ ...form, clinician: e.target.value })} /></div>
              <div className="field"><label htmlFor="f">Document</label><input id="f" type="file" accept=".pdf,image/*" onChange={(e) => setFile(e.target.files?.[0] || null)} /></div>
              <div className="field"><label htmlFor="n">Visit note for the patient (optional)</label><textarea id="n" rows={3} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} /></div>
              <button className="btn" disabled={!file}>Add to health record</button>
              {status && <p className="small" role="status">{status}</p>}
            </form>
            {d.documents.length > 0 && (
              <>
                <h3 style={{ marginTop: 24 }}>Documents on file</h3>
                <table><tbody>
                  {d.documents.map((x: any) => (
                    <tr key={x.id}><td>{x.filename}</td><td className="small">{x.uploaded_by}</td><td className="small">{new Date(x.ts).toLocaleDateString("en-CA")}</td><td className="small">{x.extracted?.summary || ""}</td></tr>
                  ))}
                </tbody></table>
              </>
            )}
          </section>
        )}
      </main>
      <Footer />
    </>
  );
}
