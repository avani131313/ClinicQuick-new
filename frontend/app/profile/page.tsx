"use client";

import { useEffect, useState } from "react";
import { Footer, TopBar, useRequireRole } from "@/components/ui";
import { api } from "@/lib/api";
import s from "./profile.module.css";

const lines = (v: string) => v.split("\n").map((x) => x.trim()).filter(Boolean);
const AUDIT_LABELS = [
  ["Never", "Monthly or less", "2–4 times a month", "2–3 times a week", "4+ times a week"],
  ["1–2", "3–4", "5–6", "7–9", "10 or more"],
  ["Never", "Less than monthly", "Monthly", "Weekly", "Daily or almost daily"],
];

function Tri({ value, onChange, labels = ["Yes", "No"] }: { value: any; onChange: (v: boolean | null) => void; labels?: string[] }) {
  return (
    <div className="choices">
      <button type="button" className="chip" aria-pressed={value === true} onClick={() => onChange(true)}>{labels[0]}</button>
      <button type="button" className="chip" aria-pressed={value === false} onClick={() => onChange(false)}>{labels[1]}</button>
    </div>
  );
}

export default function Profile() {
  const ok = useRequireRole(["patient"]);
  const [data, setData] = useState<any>(null);
  const [p, setP] = useState<any>(null);
  const [txt, setTxt] = useState<Record<string, string>>({});
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);

  const load = (r: any) => {
    setData(r);
    setP(r.profile);
    setTxt({
      conditions: (r.profile.conditions || []).join("\n"), medications: (r.profile.medications || []).join("\n"),
      allergies: (r.profile.allergies || []).join("\n"), surgeries: (r.profile.surgeries || []).join("\n"),
      family_history: (r.profile.family_history || []).join("\n"),
    });
  };
  useEffect(() => { if (ok) api("/profile").then(load).catch((e) => setStatus(e.message)); }, [ok]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true); setStatus("");
    try {
      const body = { ...p, conditions: lines(txt.conditions), medications: lines(txt.medications), allergies: lines(txt.allergies),
        surgeries: lines(txt.surgeries), family_history: lines(txt.family_history), consent: true };
      for (const k of ["height_cm", "weight_kg", "waist_cm", "sleep_hours"]) body[k] = body[k] === "" || body[k] === null ? null : Number(body[k]);
      if (Array.isArray(body.audit_c) && body.audit_c.some((x: any) => x === null)) body.audit_c = null;
      for (const k of ["last_menstrual_period", "blood_type", "occupation", "emergency_contact", "gender"]) if (body[k] === "") body[k] = null;
      load(await api("/profile", { method: "PUT", body }));
      setStatus("Saved. Your next check-in will use these answers.");
    } catch (e: any) { setStatus(e.message); }
    setSaving(false);
  }

  if (!ok) return null;
  if (!p) return (<><TopBar /><main className="wrap" style={{ padding: 40 }}><p className="muted">{status || "Loading your profile…"}</p></main></>);
  const set = (k: string, v: any) => setP({ ...p, [k]: v });
  const female = p.sex === "female";
  const audit = p.audit_c || [null, null, null];

  return (
    <>
      <TopBar />
      <main className="wrap">
        <header className={s.head}>
          <div>
            <h1>Your health profile</h1>
            <p className="muted">This is what Lena and your clinicians see before every visit. Change anything that's out of date.</p>
          </div>
          <dl className={s.auto}>
            <div><dt>Age</dt><dd>{data.age}</dd></div>
            <div><dt>Last updated</dt><dd>{data.updated_at ? new Date(data.updated_at).toLocaleDateString("en-CA", { month: "short", day: "numeric", year: "numeric" }) : "—"}</dd></div>
          </dl>
        </header>
        <p className={s.note}>Your age is worked out from your date of birth every time, so it updates on your birthday without you doing anything. Weight readings imported from Apple Health appear below so you can keep this current.</p>
        {data.needs_review && <p className={s.review} role="status">It's been more than 6 months since you updated your profile. Please check your medicines and conditions are still right.</p>}

        <form onSubmit={save} className={s.form}>
          <section className={s.sec}>
            <h2>About you</h2>
            <div className={s.grid}>
              <div className="field"><label htmlFor="name">Name</label><input id="name" type="text" value={p.name} onChange={(e) => set("name", e.target.value)} /></div>
              <div className="field"><label htmlFor="dob">Date of birth</label><input id="dob" type="date" value={p.dob} onChange={(e) => set("dob", e.target.value)} /></div>
              <div className="field"><label htmlFor="sex">Sex assigned at birth</label>
                <select id="sex" value={p.sex} onChange={(e) => set("sex", e.target.value)}><option value="female">Female</option><option value="male">Male</option><option value="intersex">Intersex</option></select></div>
              <div className="field"><label htmlFor="gender">Gender (optional)</label><input id="gender" type="text" value={p.gender || ""} onChange={(e) => set("gender", e.target.value)} /></div>
              <div className="field"><label htmlFor="occ">Work or study</label><input id="occ" type="text" value={p.occupation || ""} onChange={(e) => set("occupation", e.target.value)} /></div>
              <div className="field"><label htmlFor="ec">Emergency contact</label><input id="ec" type="text" value={p.emergency_contact || ""} onChange={(e) => set("emergency_contact", e.target.value)} /></div>
            </div>
          </section>

          <section className={s.sec}>
            <h2>Body</h2>
            <div className={s.grid}>
              <div className="field"><label htmlFor="h">Height (cm)</label><input id="h" type="number" value={p.height_cm ?? ""} onChange={(e) => set("height_cm", e.target.value)} /></div>
              <div className="field"><label htmlFor="w">Weight (kg)</label><input id="w" type="number" step="0.1" value={p.weight_kg ?? ""} onChange={(e) => set("weight_kg", e.target.value)} />
                {data.latest_weight_reading && Math.abs(data.latest_weight_reading.kg - (p.weight_kg || 0)) > 0.4 && (
                  <p className="hint">Apple Health says {data.latest_weight_reading.kg} kg. <button type="button" className="linkish" onClick={() => set("weight_kg", data.latest_weight_reading.kg)}>Use it</button></p>
                )}</div>
              <div className="field"><label htmlFor="wa">Waist (cm)</label><input id="wa" type="number" value={p.waist_cm ?? ""} onChange={(e) => set("waist_cm", e.target.value)} /></div>
              <div className="field"><label htmlFor="bt">Blood type</label>
                <select id="bt" value={p.blood_type || ""} onChange={(e) => set("blood_type", e.target.value)}><option value="">Don't know</option>{["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"].map((b) => <option key={b}>{b}</option>)}</select></div>
            </div>
          </section>

          <section className={s.sec}>
            <h2>Medical history</h2>
            <p className="hint">One per line.</p>
            <div className={s.grid}>
              <div className="field"><label htmlFor="c">Ongoing conditions</label><textarea id="c" rows={4} value={txt.conditions} onChange={(e) => setTxt({ ...txt, conditions: e.target.value })} /></div>
              <div className="field"><label htmlFor="su">Surgeries and hospital stays</label><textarea id="su" rows={4} value={txt.surgeries} onChange={(e) => setTxt({ ...txt, surgeries: e.target.value })} /></div>
              <div className="field"><label htmlFor="m">Medicines (with dose if you know it)</label><textarea id="m" rows={4} value={txt.medications} onChange={(e) => setTxt({ ...txt, medications: e.target.value })} /></div>
              <div className="field"><label htmlFor="a">Allergies and reactions</label><textarea id="a" rows={4} value={txt.allergies} onChange={(e) => setTxt({ ...txt, allergies: e.target.value })} /></div>
              <div className="field"><label htmlFor="f">Family history</label><textarea id="f" rows={3} value={txt.family_history} onChange={(e) => setTxt({ ...txt, family_history: e.target.value })} placeholder="e.g. diabetes (mother)" /></div>
              <fieldset className={s.fs}><legend>Overnight hospital stay in the past year?</legend><Tri value={p.hospitalized_past_year} onChange={(v) => set("hospitalized_past_year", v)} /></fieldset>
              <fieldset className={s.fs}><legend>Ever told you have high blood pressure?</legend><Tri value={p.high_bp} onChange={(v) => set("high_bp", v)} labels={["Yes", "No or not sure"]} /></fieldset>
              <fieldset className={s.fs}><legend>Ever told your blood sugar was high?</legend><Tri value={p.high_blood_sugar} onChange={(v) => set("high_blood_sugar", v)} labels={["Yes", "No or not sure"]} /></fieldset>
              <fieldset className={s.fs}><legend>Vaccines up to date?</legend>
                <div className="choices">{[["yes", "Yes"], ["no", "No"], ["not_sure", "Not sure"]].map(([v, l]) => <button key={v} type="button" className="chip" aria-pressed={p.vaccines_up_to_date === v} onClick={() => set("vaccines_up_to_date", v)}>{l}</button>)}</div></fieldset>
            </div>
          </section>

          {female && (
            <section className={s.sec}>
              <h2>Reproductive health</h2>
              <div className={s.grid}>
                <fieldset className={s.fs}><legend>Pregnant, or could be?</legend><Tri value={p.pregnant} onChange={(v) => set("pregnant", v)} labels={["Yes, or maybe", "No"]} /></fieldset>
                <div className="field"><label htmlFor="lmp">First day of last period</label><input id="lmp" type="date" value={p.last_menstrual_period || ""} onChange={(e) => set("last_menstrual_period", e.target.value)} /></div>
              </div>
            </section>
          )}

          <section className={s.sec}>
            <h2>Lifestyle</h2>
            <div className={s.grid}>
              <fieldset className={s.fs}><legend>Smoking or vaping</legend>
                <div className="choices">{[["never", "Never"], ["former", "Used to"], ["current", "Smoke"], ["vape", "Vape"]].map(([v, l]) => <button key={v} type="button" className="chip" aria-pressed={p.smoking === v} onClick={() => set("smoking", v)}>{l}</button>)}</div></fieldset>
              <fieldset className={s.fs}><legend>Cannabis or other drugs</legend>
                <div className="choices">{[["none", "No"], ["cannabis", "Cannabis"], ["other", "Other"], ["prefer_not_to_say", "Prefer not to say"]].map(([v, l]) => <button key={v} type="button" className="chip" aria-pressed={p.recreational_drugs === v} onClick={() => set("recreational_drugs", v)}>{l}</button>)}</div></fieldset>
              <fieldset className={s.fs}><legend>Active 30+ minutes most days?</legend><Tri value={p.active_30min_daily} onChange={(v) => set("active_30min_daily", v)} /></fieldset>
              <fieldset className={s.fs}><legend>Vegetables or fruit every day?</legend><Tri value={p.fruit_veg_daily} onChange={(v) => set("fruit_veg_daily", v)} /></fieldset>
              <div className="field"><label htmlFor="sl">Hours of sleep a night</label><input id="sl" type="number" step="0.5" value={p.sleep_hours ?? ""} onChange={(e) => set("sleep_hours", e.target.value)} /></div>
            </div>
            <h3 className={s.sub}>Alcohol</h3>
            {AUDIT_LABELS.map((opts, qi) => (
              <div className="field" key={qi}>
                <label htmlFor={`au${qi}`}>{["How often do you drink alcohol?", "Drinks on a typical day when you drink", "How often six or more drinks at once?"][qi]}</label>
                <select id={`au${qi}`} value={audit[qi] ?? ""} onChange={(e) => { const n = [...audit]; n[qi] = e.target.value === "" ? null : +e.target.value; set("audit_c", n); }}>
                  <option value="">Not answered</option>{opts.map((o, i) => <option key={o} value={i}>{o}</option>)}
                </select>
              </div>
            ))}
          </section>

          {data.age >= 65 && (
            <section className={s.sec}>
              <h2>Getting around</h2>
              <div className={s.grid}>
                <fieldset className={s.fs}><legend>Live alone?</legend><Tri value={p.lives_alone} onChange={(v) => set("lives_alone", v)} /></fieldset>
                <fieldset className={s.fs}><legend>Use a cane or walker?</legend><Tri value={p.walking_aid} onChange={(v) => set("walking_aid", v)} /></fieldset>
              </div>
            </section>
          )}

          <div className={s.saveBar}>
            <span className="small" role="status">{status}</span>
            <button className="btn" disabled={saving}>{saving ? "Saving…" : "Save changes"}</button>
          </div>
        </form>
      </main>
      <Footer />
    </>
  );
}
