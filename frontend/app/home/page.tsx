"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { fmtDay, fmtTime } from "@/components/Booking";
import BodyScene, { Hotspot } from "@/components/health/BodyScene";
import { Metric, WeekChanges, fmt } from "@/components/health/charts";
import { Footer, TopBar, useRequireRole } from "@/components/ui";
import { api } from "@/lib/api";
import { speechRecognitionSupported, unlockAudio } from "@/lib/voice";
import s from "./home.module.css";

const URG: Record<string, [string, string]> = {
  self_care: ["ok", "Self-care"], pharmacist: ["watch", "Pharmacist"], primary_care_soon: ["watch", "See someone soon"],
  walk_in_today: ["alert", "Seen today"], er: ["alert", "Emergency dept."], emergency_911: ["alert", "Stopped: 911"],
};

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export default function Home() {
  const ok = useRequireRole(["patient"]);
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [h, setH] = useState<any>(null);
  const [appts, setAppts] = useState<any[]>([]);
  const [err, setErr] = useState("");
  const [canTalk, setCanTalk] = useState(false);
  const [busy, setBusy] = useState(false);

  const loadHealth = () => api("/health/me").then(setH).catch(() => {});
  useEffect(() => {
    if (!ok) return;
    setCanTalk(speechRecognitionSupported());
    api("/me").then(setMe).catch((e) => setErr(e.message));
    api("/appointments").then(setAppts).catch(() => {});
    loadHealth();
  }, [ok]);

  async function start(how: "talk" | "type") {
    if (how === "talk") await unlockAudio();
    try { localStorage.setItem("prelude.mode", how); } catch {}
    router.push("/visit/new");
  }
  async function sample() {
    setBusy(true);
    try { await api("/wearables/demo", { method: "POST" }); await loadHealth(); } catch (e: any) { setErr(e.message); }
    setBusy(false);
  }

  if (!ok) return null;
  const p = me?.patient;
  const next = appts.find((a) => a.status === "booked" && new Date(a.starts_at) > new Date());
  const L = h?.latest || {}, S = h?.series || {};
  const hr = h?.hr_today?.at(-1)?.value ?? L.rhr?.value;
  const sleepH = S.sleep_min?.at(-1) ? S.sleep_min.at(-1).value / 60 : null;
  const spots: Hotspot[] = [
    { id: "heart", anchor: "heart", label: "Heart", value: hr ? `${fmt(hr)} bpm` : "—", tone: "pulse" },
    { id: "sleep", anchor: "head", label: "Sleep", value: sleepH ? `${fmt(sleepH, 1)} h` : "—" },
    { id: "spo2", anchor: "lungs", label: "Blood oxygen", value: L.spo2 ? `${fmt(L.spo2.value)}%` : "—" },
    { id: "steps", anchor: "legs", label: "Steps today", value: S.steps?.at(-1) ? fmt(S.steps.at(-1).value) : "—" },
  ].filter((x) => x.value !== "—" || x.id === "heart") as Hotspot[];

  return (
    <>
      <TopBar />
      <section className={s.hero}>
        <div className={`wrap ${s.heroInner}`}>
          <div className={s.heroText}>
            <p className="eyebrow">{new Date().toLocaleDateString("en-CA", { weekday: "long", month: "long", day: "numeric" })}</p>
            <p className={s.hello}>{greeting()}{p ? `, ${p.first_name}` : ""}.</p>
            <h1 className={s.ask}>How are you feeling today?</h1>
            <p className={s.sub}>Tell Lena what's going on. She asks the follow-up questions, then your clinician gets one clear page.</p>
            <div className={s.ctas}>
              {canTalk && (
                <button className={s.talk} onClick={() => start("talk")}>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>
                  Talk to Lena
                </button>
              )}
              <button className={s.type} onClick={() => start("type")}>Type instead</button>
            </div>
            {next && (
              <Link href="/appointments" className={s.nextPill}>
                <span className={s.pillDot} aria-hidden="true" />
                Next visit {fmtDay(next.starts_at)}, {fmtTime(next.starts_at)} with {next.clinician.name}
              </Link>
            )}
            {err && <p className="error" role="alert">{err}</p>}
          </div>
          <div className={s.figure}>
            {p && <BodyScene sex={p.sex} bpm={hr || 68} hotspots={spots} height={560} />}
            {h && !h.has_data && (
              <div className={s.figureCta}>
                <p>No watch connected.</p>
                <button className="btn small" onClick={sample} disabled={busy}>{busy ? "Adding…" : "Add sample data"}</button>
                <Link href="/connect" className="small">Connect Apple Health</Link>
              </div>
            )}
          </div>
        </div>
      </section>

      <main className="wrap">
        <div className={s.board}>
          <section className={s.main}>
            <div className={s.sectionHead}>
              <h2>Recent check-ins</h2>
              <Link href="/vault" className="small">All records</Link>
            </div>
            {me?.encounters?.length ? (
              <ul className={s.visits}>
                {me.encounters.map((e: any, i: number) => (
                  <li key={e.id} style={{ animationDelay: `${i * 60}ms` }}>
                    <Link href={e.status === "active" ? `/visit/${e.id}` : `/visit/${e.id}/report`}>
                      <time className="num">{new Date(e.started_at).toLocaleDateString("en-CA", { month: "short", day: "numeric" })}</time>
                      <span className={s.what}>{e.chief_complaint || "Not finished"}</span>
                      <span className={s.step}>{e.urgency ? <><span className={`dot ${URG[e.urgency]?.[0]}`} />{URG[e.urgency]?.[1]}</> : e.status === "active" ? "Continue →" : ""}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : <p className="muted">Your summaries will appear here after your first check-in.</p>}

            {h?.has_data && (
              <>
                <div className={s.sectionHead} style={{ marginTop: 40 }}>
                  <h2>Your body this week</h2>
                  <Link href="/connect" className="small">Full health data</Link>
                </div>
                <div className={s.metrics}>
                  <Metric label="Resting HR" value={L.rhr?.value} unit="bpm" points={S.rhr} color="var(--pulse)" better="down" />
                  <Metric label="Steps today" value={S.steps?.at(-1)?.value} points={S.steps} better="up" />
                  <Metric label="Last night" value={sleepH} unit="h" dp={1} points={S.sleep_min?.map((x: any) => ({ ...x, value: x.value / 60 }))} color="var(--sleep)" better="up" />
                </div>
              </>
            )}
          </section>

          <aside className={s.side}>
            <section className="panel">
              <p className="panel-title">Next appointment</p>
              {next ? (
                <>
                  <p className={s.big}>{fmtDay(next.starts_at)}<br /><span className="num">{fmtTime(next.starts_at)}</span></p>
                  <p className="muted">{next.clinician.name}, {next.clinician.clinic}</p>
                </>
              ) : <p className="muted">Nothing booked. You can book from the summary at the end of any check-in.</p>}
              <Link href="/appointments" className="small">All appointments</Link>
            </section>

            {h?.has_data && (
              <section className="panel">
                <p className="panel-title">What changed</p>
                <WeekChanges series={S} />
              </section>
            )}

            {p && (
              <section className="panel">
                <p className="panel-title">Health profile</p>
                <p className={s.profile}>{p.age} years old. {p.conditions.length ? p.conditions.join(", ") : "No conditions recorded"}. {p.medications.length} medicine{p.medications.length === 1 ? "" : "s"}.</p>
                <Link href="/profile" className="small">Review or edit</Link>
              </section>
            )}
          </aside>
        </div>
      </main>
      <Footer />
    </>
  );
}
