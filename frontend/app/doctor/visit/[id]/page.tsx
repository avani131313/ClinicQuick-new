"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import ClinicianNote from "@/components/ClinicianNote";
import { Footer, TopBar, useRequireRole } from "@/components/ui";
import { api } from "@/lib/api";

export default function DoctorVisit() {
  const ok = useRequireRole(["clinician"]);
  const { id } = useParams<{ id: string }>();
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState("");
  const [status, setStatus] = useState("");
  const load = () => api(`/doctor/encounters/${id}`).then(setD).catch((e) => setErr(e.message));
  useEffect(() => { if (ok) load(); }, [ok, id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setStatus("Uploading…");
    const fd = new FormData(); fd.append("file", file); fd.append("note", note);
    try {
      await api(`/doctor/encounters/${id}/documents`, { form: fd });
      setStatus("Saved to the patient's health record, and the appointment is marked complete.");
      setFile(null); setNote(""); load();
    } catch (e: any) { setStatus(e.message); }
  }

  if (!ok) return null;
  return (
    <>
      <TopBar />
      <main className="wrap" style={{ paddingTop: 26, paddingBottom: 30 }}>
        <p style={{ margin: "0 0 18px" }}><Link href="/doctor" style={{ color: "var(--text-2)", textDecoration: "none" }}>← Today</Link>{d?.patient_id ? <> · <Link href={`/doctor/patients/${d.patient_id}`} style={{ color: "var(--text-2)", textDecoration: "none" }}>Patient dashboard</Link></> : null}</p>
        {err && <p className="error">{err}</p>}
        {d?.report ? <ClinicianNote c={d.report.clinician} /> : !err && <p className="muted">Loading the intake note…</p>}
        {d && (
          <section className="sheet" style={{ marginTop: 24 }}>
            <p className="panel-title">After the visit</p>
            <h2 style={{ fontWeight: 400 }}>Add your visit summary.</h2>
            <p className="muted">Upload your visit summary, lab requisition or referral. It goes into the patient's own record, and your note becomes part of Lena's memory for their next check-in.</p>
            <form onSubmit={upload} style={{ maxWidth: 560 }}>
              <div className="field"><label htmlFor="f">Document</label><input id="f" type="file" accept=".pdf,image/*" onChange={(e) => setFile(e.target.files?.[0] || null)} /></div>
              <div className="field"><label htmlFor="n">Note for the patient's record (optional)</label><textarea id="n" rows={3} value={note} onChange={(e) => setNote(e.target.value)} /></div>
              <button className="btn" disabled={!file}>Save to patient record</button>
              {status && <p className="small" role="status">{status}</p>}
            </form>
            {d.documents?.length > 0 && (
              <>
                <h3 style={{ marginTop: 22 }}>Documents on file</h3>
                <table><tbody>{d.documents.filter((x: any) => x.kind !== "interview-media").map((x: any) => (
                  <tr key={x.id}><td>{x.filename}</td><td className="small">{x.uploaded_by}</td><td className="small">{new Date(x.ts).toLocaleDateString("en-CA")}</td></tr>
                ))}</tbody></table>
              </>
            )}
          </section>
        )}
      </main>
      <Footer />
    </>
  );
}
