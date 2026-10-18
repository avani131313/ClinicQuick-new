"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import PulseField from "@/components/PulseField";
import { Mark, ThemeToggle } from "@/components/ui";
import { api, getSession, setSession } from "@/lib/api";
import { routeAfterLogin } from "@/lib/route";
import s from "./landing.module.css";

const DEMOS = [
  { email: "aisha@prelude.demo", who: "Aisha, 23", what: "Patient. Healthy student, new symptom" },
  { email: "robert@prelude.demo", who: "Robert, 68", what: "Patient. Heart rhythm condition, on a blood thinner" },
  { email: "dr.chen@prelude.demo", who: "Clinician", what: "Today's visits, patient dashboards, records" },
];

const route = routeAfterLogin;

export default function Landing() {
  const router = useRouter();
  const story = useRef<HTMLDivElement>(null);
  const progress = useRef(0);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    const sess = getSession();
    if (sess) router.replace(route(sess));
  }, [router]);

  useEffect(() => {
    const onScroll = () => {
      const el = story.current;
      if (!el) return;
      const p = -el.getBoundingClientRect().top / window.innerHeight;
      progress.current = Math.max(0, Math.min(1, p));
      setStep(p > 0.5 ? 1 : 0);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  async function demo(email: string) {
    setBusy(email); setErr("");
    try {
      const r = await api("/auth/login", { body: { email, password: "demo1234" }, auth: false });
      setSession(r);
      router.push(route(r));
    } catch (e: any) { setErr(e.message); setBusy(null); }
  }

  return (
    <div className={s.night}>
      <header className={s.bar}>
        <span className={s.brand}><Mark size={28} /> ClinicQuick</span>
        <nav className={s.barNav}>
          <ThemeToggle />
          <Link href="/login" className={s.barLink}>Log in</Link>
          <Link href="/signup" className={s.barCta}>Create account</Link>
        </nav>
      </header>

      <div ref={story} className={s.story}>
        <div className={s.stage}>
          <div className={s.mist} aria-hidden="true" />
          <PulseField progress={progress} />
          <p className={`${s.scrollHint} ${step ? s.gone : ""}`} aria-hidden="true"><span />Scroll</p>
        </div>

        <div className={s.chapters}>
          <section className={`${s.chapter} ${step === 0 ? s.on : ""}`}>
            <div className={s.copy}>
              <p className="eyebrow">Pre-visit intake</p>
              <h1 className={s.heroTitle}>Your story, told before the visit.</h1>
              <p className={s.body}>Tell ClinicQuick what's wrong, by voice or text. It asks the follow-up questions a nurse would, then hands your doctor one clear page.</p>
              <div className={s.ctas}>
                <Link href="/signup" className={s.primary}>Start a check-in</Link>
                <a href="#demo" className={s.secondary}>Try a demo</a>
              </div>
            </div>
          </section>
          <section className={`${s.chapter} ${step === 1 ? s.on : ""}`}>
            <div className={s.copy}>
              <p className="eyebrow">Three minutes</p>
              <h2 className={s.title}>Your doctor walks in already knowing.</h2>
              <p className={s.body}>Fixed safety rules stop the conversation for emergencies. Everything else arrives with your booking, so you never repeat yourself.</p>
              <div className={s.ctas}>
                <Link href="/signup" className={s.primary}>Create an account</Link>
                <Link href="/signup?role=clinician" className={s.secondary}>I'm a clinician</Link>
              </div>
            </div>
          </section>
        </div>
      </div>

      <section className={s.demo} id="demo">
        <div className={s.demoHead}>
          <p className="eyebrow">Demo accounts</p>
          <h2>See it from either side.</h2>
          <p>Synthetic people, one click to sign in.</p>
        </div>
        <ul>
          {DEMOS.map((d, i) => (
            <li key={d.email}>
              <button onClick={() => demo(d.email)} disabled={!!busy}>
                <span className={s.idx}>0{i + 1}</span>
                <strong>{d.who}</strong>
                <span className={s.what}>{busy === d.email ? "Signing in…" : d.what}</span>
                <span className={s.arrow} aria-hidden="true">→</span>
              </button>
            </li>
          ))}
        </ul>
        {err && <p className={s.err} role="alert">{err}</p>}
        <p className={s.fine}>ClinicQuick is pre-visit decision support, not a diagnosis. In an emergency call 911. For a mental-health crisis call or text 9‑8‑8.</p>
      </section>
    </div>
  );
}
