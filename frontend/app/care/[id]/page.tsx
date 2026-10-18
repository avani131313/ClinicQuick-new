"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Footer, Sparkline, TopBar, useRequireRole } from "@/components/ui";
import { api, getSession } from "@/lib/api";
import s from "../care.module.css";

const BAND: Record<string, string> = { alert: "u-orange", watch: "u-yellow", ok: "u-green" };
const blank = { ate_meals: true, slept_ok: true, dizzy: false, fell: false, confused: false, pain: "", note: "" };

export default function Resident() {
  const ok = useRequireRole(["care_team", "clinician"]);
  const { id } = useParams<{ id: string }>();
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  const [ci, setCi] = useState<any>(blank);
  const [msg, setMsg] = useState("");
  const load = () => api(`/care/residents/${id}`).then(setD).catch((e) => setErr(e.message));
  useEffect(() => { if (ok) load(); }, [ok, id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function saveCheckin(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api(`/care/residents/${id}/checkins`, { body: { ...ci, pain: ci.pain === "" ? null : +ci.pain, note: ci.note || null } });
      setMsg("Check-in saved. Trend Watch has re-run.");
      setCi(blank); load();
    } catch (e: any) { setMsg(e.message); }
  }
  async function ack() {
    const r = await api(`/care/residents/${id}/acknowledge`, { method: "POST" });
    setMsg(`Marked as reviewed by ${r.acknowledged_by}.`); load();
  }

  if (!ok) return null;
  if (!d) return (<><TopBar /><main className="wrap" style={{ padding: 40 }}>{err ? <p className="error">{err}</p> : <p className="muted">Loading…</p>}</main></>);
  const r = d.resident, t = d.trend;
  const isCare = getSession()?.role === "care_team";
  const toggle = (k: string) => setCi({ ...ci, [k]: !ci[k] });

  return (
    <>
      <TopBar />
      <main className="wrap">
        <p style={{ marginTop: 18 }}><Link href="/care">All residents</Link></p>
        <div className={s.detailHead}>
          <div>
            <h1>{r.name}</h1>
            <p className="muted" style={{ margin: 0 }}>{r.age}, {r.sex}. Room {r.room}. {r.conditions.join(", ")}.</p>
          </div>
          {t.status !== "ok" && (
            d.acknowledged ? <span className="small">Reviewed by {d.acknowledged.acknowledged_by}, {new Date(d.acknowledged.acknowledged_at).toLocaleTimeString("en-CA", { hour: "numeric", minute: "2-digit" })}</span>
              : <button className="btn" onClick={ack}>Mark as reviewed</button>
          )}
        </div>

        <section className={`band ${BAND[t.status]}`}>
          <h2>{t.headline}</h2>
          <p>Compared with {r.name.split(" ")[0]}'s own pattern over the two weeks before {new Date(t.window.start).toLocaleDateString("en-CA", { month: "short", day: "numeric" })}.</p>
        </section>

        <div className={s.grid}>
          <div>
            <h2>Why {r.name.split(" ")[0]} was flagged</h2>
            <p className={s.why}>{t.explanation}</p>
            <p className={s.by}>Signals are found by fixed rules; {t.explained_by === "gemini" ? "this summary was written by Gemini from those signals only." : "this summary is generated from the rules."} The nurse decides what to do.</p>

            {t.signals.length > 0 && (
              <>
                <h2 style={{ marginTop: 26 }}>What changed, and what to check</h2>
                <ul className={s.signals}>
                  {t.signals.map((sg: any) => (
                    <li key={sg.key}>
                      <h3>{sg.label}</h3>
                      <p>{sg.detail}</p>
                      <p className={s.check}>Suggested check: {sg.action}</p>
                    </li>
                  ))}
                </ul>
              </>
            )}
            {d.steadi && (
              <p className="small" style={{ marginTop: 18 }}>
                Last fall-risk checklist (CDC STEADI): {d.steadi.value}/14, {d.steadi.band}. The checklist alone wouldn't have flagged this — the trend did.
              </p>
            )}

            <h2 style={{ marginTop: 26 }}>Recent check-ins</h2>
            <table className={s.ci}>
              <thead><tr><th>Day</th><th>Ate</th><th>Slept</th><th>Pain</th><th>Notes</th></tr></thead>
              <tbody>
                {[...t.checkins].reverse().map((c: any, i: number) => (
                  <tr key={i}>
                    <td>{new Date(c.ts).toLocaleDateString("en-CA", { weekday: "short", day: "numeric" })}</td>
                    <td>{c.ate_meals === false ? <strong>Skipped</strong> : "Yes"}</td>
                    <td>{c.slept_ok === false ? <strong>Poorly</strong> : "OK"}</td>
                    <td>{c.pain ?? "—"}</td>
                    <td>{[c.confused && "Confused", c.dizzy && "Dizzy", c.fell && "Fell", c.note].filter(Boolean).join(". ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <aside>
            <h2>Last 3 weeks vs usual</h2>
            <div className={s.charts}>
              {t.series.steps && <div className={s.chart}><strong>Steps per day</strong><span className="small">Usual about {t.baselines.steps?.toLocaleString()}. Shaded band is their normal range.</span><Sparkline points={t.series.steps} baseline={t.baselines.steps} width={320} height={70} label="Steps per day" colour={t.signals.some((x: any) => x.key === "mobility_down") ? "#C0531C" : "#123A40"} /></div>}
              {t.series.rhr && <div className={s.chart}><strong>Resting heart rate</strong><span className="small">Usual about {t.baselines.rhr} bpm</span><Sparkline points={t.series.rhr} baseline={t.baselines.rhr} width={320} height={60} label="Resting heart rate" /></div>}
              {t.series.sleep_min && <div className={s.chart}><strong>Sleep</strong><span className="small">Usual about {(t.baselines.sleep_min / 60).toFixed(1)} h</span><Sparkline points={t.series.sleep_min} baseline={t.baselines.sleep_min} width={320} height={60} label="Sleep minutes" colour={t.signals.some((x: any) => x.key === "sleep_down") ? "#C0531C" : "#123A40"} /></div>}
            </div>

            {isCare && (
              <form className={`sheet ${s.form}`} style={{ marginTop: 28 }} onSubmit={saveCheckin}>
                <h2 style={{ margin: 0 }}>Today's check-in</h2>
                <div className="choices">
                  <button type="button" className="chip" aria-pressed={!ci.ate_meals} onClick={() => toggle("ate_meals")}>Skipped a meal</button>
                  <button type="button" className="chip" aria-pressed={!ci.slept_ok} onClick={() => toggle("slept_ok")}>Slept poorly</button>
                  <button type="button" className="chip" aria-pressed={ci.confused} onClick={() => toggle("confused")}>Seemed confused</button>
                  <button type="button" className="chip" aria-pressed={ci.dizzy} onClick={() => toggle("dizzy")}>Dizzy or unsteady</button>
                  <button type="button" className="chip" aria-pressed={ci.fell} onClick={() => toggle("fell")}>Had a fall</button>
                </div>
                <div className="field" style={{ maxWidth: 160, margin: 0 }}><label htmlFor="pain">Pain (0–10)</label><input id="pain" type="number" min={0} max={10} value={ci.pain} onChange={(e) => setCi({ ...ci, pain: e.target.value })} /></div>
                <div className="field" style={{ margin: 0 }}><label htmlFor="note">Note</label><textarea id="note" rows={2} value={ci.note} onChange={(e) => setCi({ ...ci, note: e.target.value })} /></div>
                <button className="btn">Save check-in</button>
              </form>
            )}
            {msg && <p className="small" role="status">{msg}</p>}
          </aside>
        </div>
      </main>
      <Footer />
    </>
  );
}
