"use client";

// DDX decision-support panel: the symptom model's top 5 with probabilities. Clinician-only.
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import s from "./ddx.module.css";

type Ranked = { name: string; probability: number; icd10?: string; severity?: number; must_rule_out: boolean };
type Payload = {
  in_scope: boolean; extraction: string; error?: string; disclaimer: string; generated_at: string;
  ranked: Ranked[]; confidence: { level: string; text?: string };
  questions: { code: string; question: string; favours_if_yes: string }[];
  evidence: { code: string; label: string; source: string; detail: string }[];
  denied: { code: string; label: string }[];
  health_context: string[];
  main_complaint?: string[];
};

const SOURCES: [string, string][] = [["conversation", "From Lena's conversation"], ["profile", "From the patient profile"],
  ["condition", "From the patient profile"], ["medication", "From the patient profile"], ["family history", "From the patient profile"],
  ["health data", "From connected health data (watch / Apple Health)"]];

function group(src: string): string {
  return (SOURCES.find(([k]) => src.startsWith(k)) || ["", "Other"])[1];
}

export default function DdxPanel({ encounterId, shareToken }: { encounterId?: string; shareToken?: string }) {
  const [d, setD] = useState<Payload | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = (refresh = false) => {
    setBusy(true);
    const path = shareToken ? `/ddx/share/${shareToken}` : `/ddx/doctor/encounters/${encounterId}${refresh ? "?refresh=true" : ""}`;
    api<Payload>(path, { auth: !shareToken }).then((x) => { setD(x); setErr(""); })
      .catch((e) => setErr(e.message)).finally(() => setBusy(false));
  };
  useEffect(() => { load(); }, [encounterId, shareToken]); // eslint-disable-line react-hooks/exhaustive-deps

  const groups: Record<string, Payload["evidence"]> = {};
  (d?.evidence || []).filter((e) => !e.code.startsWith("E_204")).forEach((e) => {
    (groups[group(e.source)] ||= []).push(e);
  });

  return (
    <section className={s.panel} aria-labelledby="ddx-h">
      <div className={s.head}>
        <div>
          <h2 id="ddx-h" className={s.title}>Symptom model: top 5</h2>
          <p className={s.sub}>Decision support for you only. Never shown to the patient.</p>
        </div>
        {d?.confidence?.level && d.confidence.level !== "none" && (
          <span className={s.conf} data-level={d.confidence.level}>{d.confidence.level} confidence</span>
        )}
      </div>

      {err && <p className="error">{err}</p>}
      {!d && !err && <p className="muted">Ranking conditions…</p>}
      {d?.error && <p className="error">{d.error}</p>}
      {d && !d.error && !d.in_scope && (
        <p className={s.scope}>This complaint is outside the 59 conditions the model knows (mainly breathing, throat, chest
          and blood-in-urine problems), so no ranking is shown.</p>
      )}

      {d && d.ranked.length > 0 && (
        <>
          <ol className={s.list}>
            {d.ranked.map((r) => (
              <li key={r.name} className={s.row}>
                <div className={s.rowTop}>
                  <span className={s.name}>{r.name.replace(" (must rule out)", "")}</span>
                  {(r.must_rule_out || r.name.includes("must rule out")) && <span className={s.flag}>must rule out</span>}
                  <span className={s.pct}>{Math.round(r.probability * 100)}%</span>
                </div>
                <div className={s.bar} aria-hidden="true"><span style={{ width: `${Math.max(r.probability * 100, 1.5)}%` }} /></div>
                {r.icd10 && <span className={s.icd}>ICD-10 {r.icd10}</span>}
              </li>
            ))}
          </ol>
          {d.confidence.text && <p className={s.note}>{d.confidence.text}</p>}
          {d.main_complaint && d.main_complaint.length > 0 && (
            <p className={s.note}>Ranked among the conditions that can cause the main complaint: {d.main_complaint.join(", ").toLowerCase()}.</p>
          )}

          {d.questions.length > 0 && (
            <>
              <h3 className={s.h3}>Questions that would best separate these</h3>
              <ul className={s.qs}>
                {d.questions.map((q) => (
                  <li key={q.code}>{q.question} <span className={s.muted}>(a yes favours {q.favours_if_yes.replace(" (must rule out)", "")})</span></li>
                ))}
              </ul>
            </>
          )}
        </>
      )}

      {d && (d.evidence.length > 0 || d.health_context.length > 0) && (
        <details className={s.details}>
          <summary>What the model used ({d.evidence.length} findings{d.health_context.length ? ", plus health data" : ""})</summary>
          {Object.entries(groups).map(([g, items]) => (
            <div key={g} className={s.group}>
              <h4>{g}</h4>
              <ul className={s.chips}>
                {items.map((e) => <li key={e.code} title={e.detail}>{e.label}</li>)}
              </ul>
            </div>
          ))}
          {d.denied.length > 0 && (
            <div className={s.group}>
              <h4>Patient said no to</h4>
              <ul className={s.chips}>{d.denied.map((e) => <li key={e.code} className={s.no}>{e.label}</li>)}</ul>
            </div>
          )}
          {d.health_context.length > 0 && (
            <div className={s.group}>
              <h4>Apple / Samsung Health context</h4>
              <ul className={s.facts}>{d.health_context.map((f, i) => <li key={i}>{f}</li>)}</ul>
            </div>
          )}
          <p className={s.muted}>Conversation read by: {d.extraction}.</p>
        </details>
      )}

      {d && (
        <div className={s.foot}>
          <p className={s.disc}>{d.disclaimer}</p>
          {!shareToken && <button className="btn ghost" onClick={() => load(true)} disabled={busy}>{busy ? "Updating…" : "Recalculate"}</button>}
        </div>
      )}
    </section>
  );
}
