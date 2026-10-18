"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import AuthShell, { authStyles as s } from "@/components/AuthShell";
import { api, setSession } from "@/lib/api";
import { routeAfterLogin } from "@/lib/route";


export default function Login() {
  const router = useRouter();
  const [f, setF] = useState({ email: "", password: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const r = await api("/auth/login", { body: f, auth: false });
      setSession(r);
      router.push(routeAfterLogin(r));
    } catch (e: any) { setErr(e.message); setBusy(false); }
  }
  return (
    <AuthShell>
      <form className={s.card} onSubmit={submit}>
        <h1>Welcome back</h1>
        <div className="field"><label htmlFor="e">Email</label><input id="e" type="email" required autoComplete="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></div>
        <div className="field"><label htmlFor="p">Password</label><input id="p" type="password" required autoComplete="current-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></div>
        {err && <p className={s.err} role="alert">{err}</p>}
        <button className={`btn ${s.primary}`} disabled={busy}>{busy ? "Logging in…" : "Log in"}</button>
        <p className={s.switch}>New to ClinicQuick? <Link href="/signup">Create an account</Link></p>
        <p className={s.fine}>Demo accounts use the password demo1234.</p>
      </form>
    </AuthShell>
  );
}
