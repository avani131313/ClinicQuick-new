"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import AuthShell, { authStyles as s } from "@/components/AuthShell";
import { api, setSession } from "@/lib/api";

function SignupInner() {
  const router = useRouter();
  const [role, setRole] = useState<"patient" | "clinician" | null>(null);
  const [f, setF] = useState({ name: "", email: "", password: "", clinic: "", specialty: "Family medicine" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const r = new URLSearchParams(window.location.search).get("role");
    if (r === "clinician" || r === "patient") setRole(r);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const r = await api("/auth/register", { body: { role, email: f.email, password: f.password, name: role === "clinician" ? f.name : undefined, clinic: f.clinic || undefined, specialty: f.specialty || undefined }, auth: false });
      setSession(r);
      router.push(role === "clinician" ? "/doctor" : "/start");
    } catch (e: any) { setErr(e.message); setBusy(false); }
  }

  return (
    <AuthShell>
      <div className={s.card} key={role || "choose"}>
        {!role ? (
          <>
            <h1>I'm a…</h1>
            <div className={s.roles}>
              <button className={s.role} onClick={() => setRole("patient")}>
                <span className={s.icon} aria-hidden="true">
                  <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="12" cy="8" r="4" /><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6" /></svg>
                </span>
                <strong>Patient</strong>
              </button>
              <button className={s.role} onClick={() => setRole("clinician")}>
                <span className={s.icon} aria-hidden="true">
                  <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M6 3v6a4 4 0 0 0 8 0V3" /><path d="M10 13v3a5 5 0 0 0 10 0v-2" /><circle cx="20" cy="12" r="2" /></svg>
                </span>
                <strong>Clinician</strong>
              </button>
            </div>
            <p className={s.switch}>Already have an account? <Link href="/login">Log in</Link></p>
          </>
        ) : (
          <form onSubmit={submit}>
            <button type="button" className={s.back} onClick={() => setRole(null)}>← {role === "clinician" ? "Clinician" : "Patient"}</button>
            <h1>Create your account</h1>
            {role === "clinician" && (
              <>
                <div className="field"><label htmlFor="n">Your name</label><input id="n" type="text" required placeholder="Dr. Maya Chen" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
                <div className={s.two}>
                  <div className="field"><label htmlFor="c">Clinic</label><input id="c" type="text" value={f.clinic} onChange={(e) => setF({ ...f, clinic: e.target.value })} /></div>
                  <div className="field"><label htmlFor="sp">Specialty</label><input id="sp" type="text" value={f.specialty} onChange={(e) => setF({ ...f, specialty: e.target.value })} /></div>
                </div>
              </>
            )}
            <div className="field"><label htmlFor="e">Email</label><input id="e" type="email" required autoComplete="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></div>
            <div className="field"><label htmlFor="p">Password</label><input id="p" type="password" required minLength={6} autoComplete="new-password" placeholder="6+ characters" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></div>
            {err && <p className={s.err} role="alert">{err}</p>}
            <button className={`btn ${s.primary}`} disabled={busy}>{busy ? "Creating account…" : "Create account"}</button>
            {role === "clinician" && <p className={s.fine}>Licence verification (CPSO/CNO) would happen here in production.</p>}
            <p className={s.switch}>Already have an account? <Link href="/login">Log in</Link></p>
          </form>
        )}
      </div>
    </AuthShell>
  );
}

export default function Signup() {
  return <Suspense><SignupInner /></Suspense>;
}
