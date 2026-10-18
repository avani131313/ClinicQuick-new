"use client";

import { API, getSession } from "@/lib/api";
import { Sparkline } from "./ui";
import s from "./note.module.css";

const TYPE_LABEL: Record<string, string> = { STANDARD: "Standard", AI_PERSONALISED: "AI-personalised", PERSONALISED: "Personalised (rule)", SAFETY_SCREEN: "Safety check" };

export default function ClinicianNote({ c }: { c: any }) {
  const p = c.patient;
  return (
    <article className={s.note}>
      <header className={s.head}>
        <div>
          <h1 className={s.name}>{p.name}</h1>
          <p className={s.meta}>{p.age} y, {p.sex}, born {p.dob}. Intake {new Date(c.generated_at).toLocaleString("en-CA", { dateStyle: "medium", timeStyle: "short" })}</p>
        </div>
        <p className={s.urg} data-c={c.urgency.colour}><small>Patient was told</small>{c.urgency.label}</p>
      </header>
      <p className={s.oneLiner}>{c.one_liner}</p>

      <div className={s.grid}>
        <section className={s.main}>
          <h2>Chief complaint</h2>
          <p>{c.chief_complaint}</p>

          <h2>History of presenting illness</h2>
          {c.hpi.length ? (
            <dl className={s.hpi}>
              {c.hpi.map((h: any) => <div key={h.slot}><dt>{h.label}</dt><dd>{h.text}</dd></div>)}
            </dl>
          ) : <p className="muted">Not collected.</p>}

          <div className={s.two}>
            <div><h3>Associated symptoms</h3><ul>{(c.associated.length ? c.associated : ["None reported"]).map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></div>
            <div><h3>Relevant negatives</h3><ul>{(c.relevant_negatives.length ? c.relevant_negatives : ["None recorded"]).map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></div>
          </div>

          <p className={s.screen}><strong>Red-flag screen: {c.red_flag_screen.result}.</strong> {c.red_flag_screen.detail}</p>

          <h2>Conditions to consider</h2>
          <p className="small">{c.considerations_note}</p>
          <ol className={s.cons}>
            {c.considerations.map((x: any, i: number) => (
              <li key={i}>
                <span className={s.consName}>{x.name}</span> <span className={s.lik} data-l={x.likelihood}>{x.likelihood}</span>
                <span className={s.because}>{(x.because || []).join("; ")}</span>
              </li>
            ))}
          </ol>

          <h2>Patient's ideas, concerns, expectations</h2>
          <p>{c.ice || "—"}</p>

          <h2>Navigation given to patient</h2>
          <p><strong>{c.urgency.label}:</strong> {c.urgency.where}, {c.urgency.when.toLowerCase()}.</p>
          <ul>{c.urgency.reasons.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>
        </section>

        <aside className={s.side}>
          <h2>History</h2>
          <dl className={s.kv}>
            <div><dt>Conditions</dt><dd>{c.pmh.join(", ") || "None reported"}</dd></div>
            <div><dt>Medications</dt><dd>{c.medications.join(", ") || "None"}</dd></div>
            <div><dt>Allergies</dt><dd>{c.allergies.join(", ") || "No known allergies"}</dd></div>
            <div><dt>Family</dt><dd>{c.family_history.join(", ") || "None reported"}</dd></div>
            <div><dt>Smoking</dt><dd>{c.social_history.smoking || "—"}</dd></div>
          </dl>

          <h2>Risk scores</h2>
          <ul className={s.scores}>
            {c.risk_scores.filter((r: any) => r.applicable && r.value !== null).map((r: any) => (
              <li key={r.name}>
                <span className={s.scoreName}>{r.name}</span>
                <span className={s.scoreVal} data-sev={r.severity}>{r.value}, {r.band}</span>
                <a href={r.citation_url} target="_blank" rel="noreferrer" className="small">{r.citation}</a>
              </li>
            ))}
          </ul>

          {c.trends && Object.keys(c.trends).length > 0 && (
            <>
              <h2>Wearable trends, 30 days</h2>
              <div className={s.trends}>
                {c.trends.steps && <div><span>Steps</span><Sparkline points={c.trends.steps} label="Steps" width={150} /></div>}
                {c.trends.rhr && <div><span>Resting HR</span><Sparkline points={c.trends.rhr} label="Resting heart rate" width={150} /></div>}
                {c.trends.sleep_min && <div><span>Sleep</span><Sparkline points={c.trends.sleep_min} label="Sleep" width={150} /></div>}
              </div>
            </>
          )}

          <h2>Personalised by</h2>
          <ul className={s.mods}>{c.context_modifiers.map((m: any, i: number) => <li key={i}>{m.value}</li>)}</ul>
        </aside>
      </div>

      {c.media && c.media.length > 0 && (
        <section className={s.tx}>
          <h2>Photos and videos the patient shared</h2>
          <div className={s.media}>
            {c.media.map((m: any) => {
              const src = `${API}/media/${m.id}?t=${encodeURIComponent(getSession()?.token || "")}`;
              return (
                <figure key={m.id}>
                  {m.kind === "video" ? <video src={src} controls muted playsInline /> : <img src={src} alt="Patient-shared" />}
                  <figcaption>{m.description}</figcaption>
                </figure>
              );
            })}
          </div>
          <p className="small">Descriptions are of visible features only, written by Gemini. They are not a diagnosis.</p>
        </section>
      )}

      <section className={s.tx}>
        <h2>Full transcript</h2>
        <p className="small">Every question is tagged. Standard questions come from the intake framework; personalised ones show why they were asked.</p>
        <ol>
          {c.transcript.filter((t: any) => t.answer).map((t: any, i: number) => (
            <li key={i}>
              <p className={s.txQ}><span className={`tag ${t.type}`}>{TYPE_LABEL[t.type] || t.type}</span> {t.question}</p>
              {t.type !== "STANDARD" && t.rationale && <p className={s.txWhy}>Why asked: {t.rationale}</p>}
              <p className={s.txA}>{t.answer}</p>
            </li>
          ))}
        </ol>
      </section>
      <p className="small">Generated by {c.generated_by === "gemini" ? "Gemini with rule-based safety and scores" : "rule-based offline mode"}. Decision support only, not a diagnosis.</p>
    </article>
  );
}
