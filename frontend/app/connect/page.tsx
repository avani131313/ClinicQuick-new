"use client";

import { useEffect, useRef, useState } from "react";
import HealthDashboard from "@/components/health/HealthDashboard";
import { Footer, TopBar, useRequireRole } from "@/components/ui";
import { api } from "@/lib/api";
import s from "./connect.module.css";

const when = (iso?: string) => iso ? new Date(iso).toLocaleDateString("en-CA", { month: "short", day: "numeric" }) : "";

export default function Connect() {
  const ok = useRequireRole(["patient"]);
  const [h, setH] = useState<any>(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const file = useRef<HTMLInputElement>(null);

  const load = async () => {
    try { setH(await api("/health/me")); } catch (e: any) { setMsg(e.message); }
  };
  useEffect(() => { if (ok) load(); }, [ok]);

  async function importApple(f: File) {
    setBusy("apple"); setMsg("");
    const fd = new FormData(); fd.append("file", f);
    try { const r = await api("/wearables/apple-health", { form: fd }); setMsg(`Imported ${r.imported.toLocaleString()} readings from Apple Health.`); await load(); }
    catch (e: any) { setMsg(e.message); }
    setBusy("");
  }
  async function demo() {
    setBusy("demo"); setMsg("");
    try { await api("/wearables/demo", { method: "POST" }); setMsg("Added six weeks of sample watch data."); await load(); }
    catch (e: any) { setMsg(e.message); }
    setBusy("");
  }
  async function remove(src: string) {
    await api(`/wearables/${src}`, { method: "DELETE" }); await load();
  }

  if (!ok) return null;
  const c = h?.connections;
  const apple = c?.apple_health, sample = c?.demo;
  return (
    <>
      <TopBar />
      <main className={`wrap ${s.page}`}>
        <header className={s.head}>
          <p className="eyebrow">Health data</p>
          <h1>Your body, this month.</h1>
          <p className="muted">Heart rate, sleep, steps, blood oxygen and blood pressure from your watch. Your clinician sees the same trends with your check-in, so they know how you've been, not just how you feel today.</p>
        </header>

        <HealthDashboard data={h} sex={h?.sex || "female"} onPopulate={demo} populating={busy === "demo"} who="patient" />

        <h2 className={s.sourcesTitle}>Sources</h2>
        <div className={s.grid}>
          <article className={`${s.tile} ${s.apple}`}>
            <div className={s.tileHead}>
              <span className={s.logo} aria-hidden="true">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9" stroke="var(--pulse)" /><circle cx="12" cy="12" r="5.5" stroke="var(--accent)" /><path d="M12 2.9v2.2M12 18.9v2.2" stroke="var(--pulse)" /></svg>
              </span>
              <div><h3>Apple Health</h3><p className={s.state}>{apple ? `${apple.readings.toLocaleString()} readings, latest ${when(apple.last)}` : "Not connected"}</p></div>
              <span className={s.badge} data-on={apple ? true : undefined}>{apple ? "Connected" : "Off"}</span>
            </div>
            <ol className={s.how}>
              <li>On your iPhone, open <strong>Health</strong> and tap your photo.</li>
              <li>Tap <strong>Export All Health Data</strong> and save the file.</li>
              <li>Upload <strong>export.zip</strong> here.</li>
            </ol>
            <input ref={file} type="file" accept=".zip,.xml" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) importApple(f); e.target.value = ""; }} />
            <div className={s.actions}>
              <button className="btn" onClick={() => file.current?.click()} disabled={busy === "apple"}>{busy === "apple" ? "Reading your export…" : apple ? "Upload a newer export" : "Upload export.zip"}</button>
              {apple && <button className="linkish" onClick={() => remove("apple_health")}>Remove</button>}
            </div>
            <p className={s.why}>Websites can't read HealthKit directly, so live syncing needs the ClinicQuick iPhone app (on the roadmap).</p>
          </article>

          <article className={s.tile}>
            <div className={s.tileHead}>
              <span className={s.logo} aria-hidden="true">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round"><path d="M3 12h4l3-7 4 14 3-7h4" /></svg>
              </span>
              <div><h3>Sample watch data</h3><p className={s.state}>{sample ? `${sample.readings.toLocaleString()} synthetic readings` : "For trying ClinicQuick without a watch"}</p></div>
              <span className={s.badge} data-on={sample ? true : undefined}>{sample ? "On" : "Off"}</span>
            </div>
            <p className={s.body}>Six weeks of realistic synthetic heart rate, HRV, blood oxygen, breathing, sleep, steps, weight and home blood pressure, shaped to your age and conditions.</p>
            <div className={s.actions}>
              <button className="btn ghost" onClick={demo} disabled={busy === "demo"}>{busy === "demo" ? "Adding…" : sample ? "Regenerate" : "Add sample data"}</button>
              {sample && <button className="linkish" onClick={() => remove("demo")}>Remove</button>}
            </div>
          </article>

          <article className={`${s.tile} ${s.soon}`}>
            <h3>Samsung Health, Google Health Connect, Fitbit</h3>
            <p className={s.body}>These sync through the phone's own health store, which only a mobile app can read. They're planned for the ClinicQuick Android app.</p>
          </article>
        </div>
        {msg && <p className={s.msg} role="status">{msg}</p>}
      </main>
      <Footer />
    </>
  );
}
