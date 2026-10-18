"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Mark } from "@/components/ui";
import { api, getSession, setSession } from "@/lib/api";
import s from "./start.module.css";

type Data = {
  name: string; dob: string; sex: string; gender: string;
  height_cm?: number; weight_kg?: number; waist_cm?: number; pregnant?: boolean | null;
  conditions: string[]; medications: string[]; allergies: string[];
  family_diabetes: string[]; family_other: string[];
  smoking?: string; audit: (number | null)[];
  active_30min_daily?: boolean; fruit_veg_daily?: boolean; high_bp?: boolean; high_blood_sugar?: boolean;
  baby_over_4kg?: boolean; parent_ethnicities: string[]; education?: string; lives_alone?: boolean; walking_aid?: boolean;
  surgeries: string[]; hospitalized_past_year?: boolean; lmp: string; occupation: string; sleep_hours?: number;
  recreational_drugs?: string; vaccines_up_to_date?: string; blood_type: string; emergency_contact: string;
};

const COMMON_CONDITIONS = ["Asthma", "High blood pressure", "Type 2 diabetes", "Type 1 diabetes", "High cholesterol", "Depression", "Anxiety", "Eczema", "Migraine", "Hypothyroidism", "Atrial fibrillation", "Arthritis"];
const AUDIT_Q = [
  { q: "How often do you have a drink containing alcohol?", o: ["Never", "Monthly or less", "2–4 times a month", "2–3 times a week", "4+ times a week"] },
  { q: "On a typical day when you drink, how many drinks do you have?", o: ["1–2", "3–4", "5–6", "7–9", "10 or more"] },
  { q: "How often do you have six or more drinks on one occasion?", o: ["Never", "Less than monthly", "Monthly", "Weekly", "Daily or almost daily"] },
];
const ETHNICITIES = [
  ["white", "White"], ["indigenous", "Indigenous"], ["black", "Black"], ["east_asian", "East Asian"],
  ["south_asian", "South Asian"], ["other_non_white", "Latin American, Arab, West Asian or other"], ["prefer_not_to_say", "Prefer not to say"],
];
const EDUCATION = [["some_high_school_or_less", "Some high school or less"], ["high_school", "High school diploma"], ["some_college", "Some college or university"], ["degree", "College or university degree"], ["prefer_not_to_say", "Prefer not to say"]];

function age(dob: string) {
  if (!dob) return null;
  const d = new Date(dob), t = new Date();
  let a = t.getFullYear() - d.getFullYear();
  if (t.getMonth() < d.getMonth() || (t.getMonth() === d.getMonth() && t.getDate() < d.getDate())) a--;
  return a;
}

function YesNo({ value, onChange, labels = ["Yes", "No"] }: { value?: boolean | null; onChange: (v: boolean) => void; labels?: [string, string] | string[] }) {
  return (
    <div className="choices">
      <button type="button" className="chip" aria-pressed={value === true} onClick={() => onChange(true)}>{labels[0]}</button>
      <button type="button" className="chip" aria-pressed={value === false} onClick={() => onChange(false)}>{labels[1]}</button>
    </div>
  );
}

function ListInput({ items, onChange, placeholder, suggestions = [] }: { items: string[]; onChange: (v: string[]) => void; placeholder: string; suggestions?: string[] }) {
  const [v, setV] = useState("");
  const add = (x: string) => { const t = x.trim(); if (t && !items.includes(t)) onChange([...items, t]); setV(""); };
  return (
    <div>
      {suggestions.length > 0 && (
        <div className="choices" style={{ marginBottom: 14 }}>
          {suggestions.map((c) => (
            <button key={c} type="button" className="chip" aria-pressed={items.includes(c)}
              onClick={() => onChange(items.includes(c) ? items.filter((i) => i !== c) : [...items, c])}>{c}</button>
          ))}
        </div>
      )}
      <div style={{ display: "flex", gap: 8 }}>
        <input type="text" value={v} placeholder={placeholder} onChange={(e) => setV(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(v); } }} aria-label={placeholder} />
        <button type="button" className="btn ghost" onClick={() => add(v)}>Add</button>
      </div>
      {items.filter((i) => !suggestions.includes(i)).length > 0 && (
        <ul className={s.added}>
          {items.filter((i) => !suggestions.includes(i)).map((i) => (
            <li key={i}>{i} <button type="button" className="linkish" onClick={() => onChange(items.filter((x) => x !== i))} aria-label={`Remove ${i}`}>remove</button></li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function Start() {
  const router = useRouter();
  const [d, setD] = useState<Data>({
    name: "", dob: "", sex: "", gender: "", conditions: [], medications: [], allergies: [],
    family_diabetes: [], family_other: [], audit: [null, null, null], parent_ethnicities: [],
    surgeries: [], lmp: "", occupation: "", blood_type: "", emergency_contact: "",
  });
  const [units, setUnits] = useState<"metric" | "imperial">("metric");
  const [imp, setImp] = useState({ ft: "", inch: "", lb: "" });
  const [i, setI] = useState(0);
  const [phase, setPhase] = useState<"questions" | "snapshot" | "consent">("questions");
  const [snap, setSnap] = useState<any>(null);
  const [consent, setConsent] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (p: Partial<Data>) => setD((x) => ({ ...x, ...p }));
  useEffect(() => {
    const sess = getSession();
    if (!sess) router.replace("/signup");
    else if (sess.role !== "patient") router.replace("/");
    else if (sess.patient_id) router.replace("/home");
    else if (sess.name) setD((x) => ({ ...x, name: x.name || sess.name || "" }));
  }, [router]);
  const a = age(d.dob);

  const steps = useMemo(() => {
    const list: { key: string; q: string; why?: string; optional?: boolean; valid: () => boolean; body: () => React.ReactNode }[] = [
      { key: "name", q: "First, what's your name?", valid: () => d.name.trim().length > 1,
        body: () => <input type="text" autoFocus value={d.name} onChange={(e) => set({ name: e.target.value })} placeholder="First and last name" aria-label="Your name" /> },
      { key: "dob", q: "When were you born?", why: "Age changes which causes are likely and which checks apply to you.", valid: () => !!d.dob && new Date(d.dob + "T00:00") < new Date(new Date().toDateString()) && (a ?? 0) < 120,
        body: () => <>
          <input type="date" value={d.dob} max={new Date(Date.now() - 864e5).toISOString().slice(0, 10)} onChange={(e) => set({ dob: e.target.value })} aria-label="Date of birth" />
          {d.dob && new Date(d.dob + "T00:00") >= new Date(new Date().toDateString()) && <p className="error" style={{ marginTop: 8 }}>That date is today or in the future. Check the year.</p>}
        </> },
      { key: "sex", q: "What sex were you assigned at birth?", why: "Lab ranges and some risk scores depend on it. You can add your gender too.", valid: () => !!d.sex,
        body: () => (
          <>
            <div className="choices">
              {[["female", "Female"], ["male", "Male"], ["intersex", "Intersex"]].map(([v, l]) => (
                <button key={v} type="button" className="chip" aria-pressed={d.sex === v} onClick={() => set({ sex: v })}>{l}</button>
              ))}
            </div>
            <div className="field" style={{ marginTop: 20 }}>
              <label htmlFor="g">Gender (optional)</label>
              <input id="g" type="text" value={d.gender} onChange={(e) => set({ gender: e.target.value })} />
            </div>
          </>
        ) },
      { key: "hw", q: "How tall are you, and what do you weigh?", why: "Used for your BMI and diabetes risk score.", valid: () => !!d.height_cm && !!d.weight_kg,
        body: () => (
          <>
            <div className="choices" style={{ marginBottom: 16 }}>
              <button type="button" className="chip" aria-pressed={units === "metric"} onClick={() => setUnits("metric")}>cm / kg</button>
              <button type="button" className="chip" aria-pressed={units === "imperial"} onClick={() => setUnits("imperial")}>ft, in / lb</button>
            </div>
            {units === "metric" ? (
              <div className={s.pair}>
                <div className="field"><label htmlFor="h">Height (cm)</label><input id="h" type="number" inputMode="decimal" value={d.height_cm ?? ""} onChange={(e) => set({ height_cm: e.target.value ? +e.target.value : undefined })} /></div>
                <div className="field"><label htmlFor="w">Weight (kg)</label><input id="w" type="number" inputMode="decimal" value={d.weight_kg ?? ""} onChange={(e) => set({ weight_kg: e.target.value ? +e.target.value : undefined })} /></div>
              </div>
            ) : (
              <div className={s.pair}>
                <div className="field"><label htmlFor="ft">Feet</label><input id="ft" type="number" value={imp.ft} onChange={(e) => { const n = { ...imp, ft: e.target.value }; setImp(n); set({ height_cm: n.ft ? Math.round((+n.ft * 12 + +(n.inch || 0)) * 2.54) : undefined }); }} /></div>
                <div className="field"><label htmlFor="in">Inches</label><input id="in" type="number" value={imp.inch} onChange={(e) => { const n = { ...imp, inch: e.target.value }; setImp(n); set({ height_cm: n.ft ? Math.round((+n.ft * 12 + +(n.inch || 0)) * 2.54) : undefined }); }} /></div>
                <div className="field"><label htmlFor="lb">Pounds</label><input id="lb" type="number" value={imp.lb} onChange={(e) => { setImp({ ...imp, lb: e.target.value }); set({ weight_kg: e.target.value ? Math.round(+e.target.value * 0.4536 * 10) / 10 : undefined }); }} /></div>
              </div>
            )}
          </>
        ) },
      { key: "waist", q: "Do you know your waist measurement?", optional: true, why: "Measure around your belly button, breathing out normally. Skip if you don't know.", valid: () => true,
        body: () => <div className="field" style={{ maxWidth: 220 }}><label htmlFor="wa">Waist (cm)</label><input id="wa" type="number" value={d.waist_cm ?? ""} onChange={(e) => set({ waist_cm: e.target.value ? +e.target.value : undefined })} /></div> },
    ];
    if (d.sex === "female" && a !== null && a >= 12 && a <= 55)
      list.push({ key: "preg", q: "Are you pregnant, or could you be?", why: "It changes which medicines are safe and how urgent some symptoms are.", valid: () => d.pregnant !== undefined && d.pregnant !== null,
        body: () => (
          <>
            <YesNo value={d.pregnant} onChange={(v) => set({ pregnant: v })} labels={["Yes, or maybe", "No"]} />
            <div className="field" style={{ maxWidth: 260, marginTop: 22 }}><label htmlFor="lmp">First day of your last period (optional)</label>
              <input id="lmp" type="date" value={d.lmp} max={new Date().toISOString().slice(0, 10)} onChange={(e) => set({ lmp: e.target.value })} /></div>
          </>
        ) });
    list.push(
      { key: "cond", q: "Do you have any ongoing health conditions?", optional: true, valid: () => true,
        body: () => <ListInput items={d.conditions} onChange={(v) => set({ conditions: v })} placeholder="Add another condition" suggestions={COMMON_CONDITIONS} /> },
      { key: "meds", q: "What medicines do you take?", why: "Include over-the-counter medicines, inhalers, birth control and supplements.", optional: true, valid: () => true,
        body: () => <ListInput items={d.medications} onChange={(v) => set({ medications: v })} placeholder="e.g. Apixaban 5 mg twice daily" /> },
      { key: "allergy", q: "Any allergies to medicines, foods or anything else?", optional: true, valid: () => true,
        body: () => <ListInput items={d.allergies} onChange={(v) => set({ allergies: v })} placeholder="e.g. Penicillin — rash" /> },
      { key: "surg", q: "Have you had any surgeries or hospital stays?", optional: true, why: "Add each one with the year if you remember it.", valid: () => true,
        body: () => (
          <>
            <ListInput items={d.surgeries} onChange={(v) => set({ surgeries: v })} placeholder="e.g. Appendix removed, 2019" />
            <fieldset className={s.fs} style={{ marginTop: 22 }}><legend>Have you stayed overnight in hospital in the past year?</legend>
              <YesNo value={d.hospitalized_past_year} onChange={(v) => set({ hospitalized_past_year: v })} /></fieldset>
          </>
        ) },
      { key: "fam", q: "Have any blood relatives had these conditions?", optional: true, valid: () => true,
        body: () => (
          <div className={s.famGrid}>
            <div>
              <h3>Diabetes</h3>
              <div className="choices">
                {[["mother", "Mother"], ["father", "Father"], ["sibling", "Brother or sister"], ["child", "My child"], ["other", "Other relative"]].map(([v, l]) => (
                  <button key={v} type="button" className="chip" aria-pressed={d.family_diabetes.includes(v)}
                    onClick={() => set({ family_diabetes: d.family_diabetes.includes(v) ? d.family_diabetes.filter((x) => x !== v) : [...d.family_diabetes, v] })}>{l}</button>
                ))}
              </div>
            </div>
            <div>
              <h3>Other</h3>
              <div className="choices">
                {["Heart disease", "Stroke", "Cancer", "High blood pressure", "Kidney disease"].map((c) => (
                  <button key={c} type="button" className="chip" aria-pressed={d.family_other.includes(c)}
                    onClick={() => set({ family_other: d.family_other.includes(c) ? d.family_other.filter((x) => x !== c) : [...d.family_other, c] })}>{c}</button>
                ))}
              </div>
            </div>
          </div>
        ) },
      { key: "smoke", q: "Do you smoke or vape?", valid: () => !!d.smoking,
        body: () => (
          <div className="choices">
            {[["never", "Never"], ["former", "I used to"], ["current", "Yes, I smoke"], ["vape", "I vape"]].map(([v, l]) => (
              <button key={v} type="button" className="chip" aria-pressed={d.smoking === v} onClick={() => set({ smoking: v })}>{l}</button>
            ))}
          </div>
        ) },
      { key: "alcohol", q: "A few questions about alcohol.", why: "This is the AUDIT-C, a standard 3-question check doctors use.", valid: () => d.audit[0] === 0 || d.audit.every((x) => x !== null),
        body: () => (
          <div>
            {AUDIT_Q.map((item, qi) => (qi > 0 && d.audit[0] === 0) ? null : (
              <fieldset key={qi} className={s.fs}>
                <legend>{item.q}</legend>
                <div className="choices">
                  {item.o.map((o, oi) => (
                    <button key={o} type="button" className="chip" aria-pressed={d.audit[qi] === oi}
                      onClick={() => { const n = [...d.audit]; n[qi] = oi; if (qi === 0 && oi === 0) { n[1] = 0; n[2] = 0; } set({ audit: n }); }}>{o}</button>
                  ))}
                </div>
              </fieldset>
            ))}
          </div>
        ) },
      { key: "life", q: "Two quick lifestyle questions.", valid: () => d.active_30min_daily !== undefined && d.fruit_veg_daily !== undefined,
        body: () => (
          <>
            <fieldset className={s.fs}><legend>Are you active for at least 30 minutes most days? Brisk walking counts.</legend>
              <YesNo value={d.active_30min_daily} onChange={(v) => set({ active_30min_daily: v })} /></fieldset>
            <fieldset className={s.fs}><legend>Do you eat vegetables or fruit every day?</legend>
              <YesNo value={d.fruit_veg_daily} onChange={(v) => set({ fruit_veg_daily: v })} /></fieldset>
          </>
        ) },
      { key: "sleep", q: "Sleep and other substances.", valid: () => d.sleep_hours !== undefined && !!d.recreational_drugs,
        body: () => (
          <>
            <div className="field" style={{ maxWidth: 240 }}><label htmlFor="sl">Hours of sleep on a typical night</label>
              <input id="sl" type="number" min={0} max={16} step={0.5} value={d.sleep_hours ?? ""} onChange={(e) => set({ sleep_hours: e.target.value ? +e.target.value : undefined })} /></div>
            <fieldset className={s.fs}><legend>Do you use cannabis or other recreational drugs?</legend>
              <div className="choices">
                {[["none", "No"], ["cannabis", "Cannabis"], ["other", "Other drugs"], ["prefer_not_to_say", "Prefer not to say"]].map(([v, l]) => (
                  <button key={v} type="button" className="chip" aria-pressed={d.recreational_drugs === v} onClick={() => set({ recreational_drugs: v })}>{l}</button>
                ))}
              </div>
            </fieldset>
          </>
        ) },
      { key: "bp", q: "Has a doctor or nurse ever told you…", valid: () => d.high_bp !== undefined && d.high_blood_sugar !== undefined,
        body: () => (
          <>
            <fieldset className={s.fs}><legend>…that you have high blood pressure, or have you taken pills for it?</legend>
              <YesNo value={d.high_bp} onChange={(v) => set({ high_bp: v })} labels={["Yes", "No or not sure"]} /></fieldset>
            <fieldset className={s.fs}><legend>…that your blood sugar was high, even once (including during pregnancy)?</legend>
              <YesNo value={d.high_blood_sugar} onChange={(v) => set({ high_blood_sugar: v })} labels={["Yes", "No or not sure"]} /></fieldset>
            {d.sex === "female" && (a ?? 0) >= 18 && (
              <fieldset className={s.fs}><legend>Have you given birth to a baby weighing 4.1 kg (9 lb) or more?</legend>
                <YesNo value={d.baby_over_4kg} onChange={(v) => set({ baby_over_4kg: v })} labels={["Yes", "No or not applicable"]} /></fieldset>
            )}
          </>
        ) },
    );
    list.push({ key: "more", q: "A few last details for your chart.", optional: true, valid: () => true,
      body: () => (
        <>
          <div className="field"><label htmlFor="oc">What do you do for work or study?</label><input id="oc" type="text" value={d.occupation} placeholder="e.g. Student, nurse, retired" onChange={(e) => set({ occupation: e.target.value })} /></div>
          <fieldset className={s.fs}><legend>Are your vaccines up to date?</legend>
            <div className="choices">
              {[["yes", "Yes"], ["no", "No"], ["not_sure", "Not sure"]].map(([v, l]) => (
                <button key={v} type="button" className="chip" aria-pressed={d.vaccines_up_to_date === v} onClick={() => set({ vaccines_up_to_date: v })}>{l}</button>
              ))}
            </div>
          </fieldset>
          <div className={s.pair}>
            <div className="field"><label htmlFor="bt">Blood type, if you know it</label>
              <select id="bt" value={d.blood_type} onChange={(e) => set({ blood_type: e.target.value })}>
                <option value="">Don't know</option>{["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"].map((b) => <option key={b}>{b}</option>)}
              </select></div>
            <div className="field"><label htmlFor="ec">Emergency contact</label><input id="ec" type="text" value={d.emergency_contact} placeholder="Name and phone" onChange={(e) => set({ emergency_contact: e.target.value })} /></div>
          </div>
        </>
      ) });
    if (a !== null && a >= 40 && a <= 74)
      list.push({ key: "canrisk", q: "Two more for your diabetes risk score.", optional: true,
        why: "Canada's diabetes risk questionnaire (CANRISK) asks about your parents' background and your education because both change risk. You can skip either.",
        valid: () => true,
        body: () => (
          <>
            <fieldset className={s.fs}><legend>Your biological parents' background (pick any that apply)</legend>
              <div className="choices">
                {ETHNICITIES.map(([v, l]) => (
                  <button key={v} type="button" className="chip" aria-pressed={d.parent_ethnicities.includes(v)}
                    onClick={() => set({ parent_ethnicities: d.parent_ethnicities.includes(v) ? d.parent_ethnicities.filter((x) => x !== v) : [...d.parent_ethnicities, v] })}>{l}</button>
                ))}
              </div>
            </fieldset>
            <fieldset className={s.fs}><legend>Highest level of education you've completed</legend>
              <div className="choices">
                {EDUCATION.map(([v, l]) => <button key={v} type="button" className="chip" aria-pressed={d.education === v} onClick={() => set({ education: v })}>{l}</button>)}
              </div>
            </fieldset>
          </>
        ) });
    if (a !== null && a >= 65)
      list.push({ key: "home", q: "About getting around at home.", valid: () => d.lives_alone !== undefined && d.walking_aid !== undefined,
        body: () => (
          <>
            <fieldset className={s.fs}><legend>Do you live alone?</legend><YesNo value={d.lives_alone} onChange={(v) => set({ lives_alone: v })} /></fieldset>
            <fieldset className={s.fs}><legend>Do you use a cane, walker or other walking aid?</legend><YesNo value={d.walking_aid} onChange={(v) => set({ walking_aid: v })} /></fieldset>
          </>
        ) });
    return list;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d, units, imp, a]);

  const step = steps[Math.min(i, steps.length - 1)];

  function payload() {
    const fam = [
      ...d.family_diabetes.map((r) => `diabetes (${r === "sibling" ? "brother or sister" : r === "other" ? "other relative" : r})`),
      ...d.family_other,
    ];
    return {
      name: d.name.trim(), dob: d.dob, sex: d.sex, gender: d.gender || null,
      height_cm: d.height_cm ?? null, weight_kg: d.weight_kg ?? null, waist_cm: d.waist_cm ?? null, pregnant: d.pregnant ?? null,
      conditions: d.conditions, medications: d.medications, allergies: d.allergies,
      family_history: fam, family_diabetes: d.family_diabetes, smoking: d.smoking ?? null,
      audit_c: d.audit.every((x) => x !== null) ? d.audit : null,
      active_30min_daily: d.active_30min_daily ?? null, fruit_veg_daily: d.fruit_veg_daily ?? null,
      high_bp: d.high_bp ?? null, high_blood_sugar: d.high_blood_sugar ?? null, baby_over_4kg: d.baby_over_4kg ?? null,
      parent_ethnicities: d.parent_ethnicities, education: d.education ?? null,
      lives_alone: d.lives_alone ?? null, walking_aid: d.walking_aid ?? null,
      surgeries: d.surgeries, hospitalized_past_year: d.hospitalized_past_year ?? null,
      last_menstrual_period: d.lmp || null, occupation: d.occupation || null, sleep_hours: d.sleep_hours ?? null,
      recreational_drugs: d.recreational_drugs ?? null, vaccines_up_to_date: d.vaccines_up_to_date ?? null,
      blood_type: d.blood_type || null, emergency_contact: d.emergency_contact || null,
      mental_health_history: d.conditions.filter((c) => ["Depression", "Anxiety", "Bipolar disorder", "ADHD", "PTSD"].includes(c)),
    };
  }

  async function next() {
    setErr("");
    if (i < steps.length - 1) return setI(i + 1);
    setBusy(true);
    try {
      setSnap(await api("/onboarding/preview", { body: payload(), auth: false }));
      setPhase("snapshot");
    } catch (e: any) { setErr(e.message); }
    setBusy(false);
  }

  async function create() {
    setErr(""); setBusy(true);
    try {
      const r = await api("/profile", { body: { ...payload(), consent } });
      setSession({ ...r, name: d.name });
      router.push("/home");
    } catch (e: any) { setErr(e.message); setBusy(false); }
  }

  return (
    <div className={`ecg ${s.page}`}>
      <header className={s.head}>
        <a href="/" className="brand"><Mark /> ClinicQuick</a>
        {phase === "questions" && (
          <ol className={s.ticks} aria-label={`Question ${i + 1} of ${steps.length}`}>
            {steps.map((st, k) => <li key={st.key} className={k < i ? s.done : k === i ? s.now : ""} />)}
          </ol>
        )}
      </header>

      <main className={s.main}>
        {phase === "questions" && (
          <form onSubmit={(e) => { e.preventDefault(); if (step.valid()) next(); }} key={step.key} className={s.step}>
            <p className={s.count}>{i + 1} of {steps.length}{step.optional ? ", optional" : ""}</p>
            <h1 className={s.q}>{step.q}</h1>
            {step.why && <p className={s.why}>{step.why}</p>}
            <div className={s.body}>{step.body()}</div>
            {err && <p className="error" role="alert">{err}</p>}
            <div className={s.actions}>
              {i > 0 && <button type="button" className="btn ghost" onClick={() => setI(i - 1)}>Back</button>}
              <button type="submit" className="btn" disabled={!step.valid() || busy}>{i === steps.length - 1 ? (busy ? "Working…" : "See my snapshot") : "Continue"}</button>
              {step.optional && <button type="button" className="linkish" onClick={next}>Skip</button>}
            </div>
          </form>
        )}

        {phase === "snapshot" && snap && (
          <section className={s.step}>
            <p className={s.count}>Your health snapshot</p>
            <h1 className={s.q}>Here's what your answers add up to, {d.name.split(" ")[0]}.</h1>
            <dl className={s.snap}>
              <div><dt>Age</dt><dd>{snap.age}</dd></div>
              {snap.scores.filter((x: any) => x.applicable && x.value !== null).map((x: any) => (
                <div key={x.name}>
                  <dt>{x.name === "AUDIT-C" ? "Alcohol (AUDIT-C)" : x.name === "CANRISK" ? "Diabetes risk (CANRISK)" : x.name}</dt>
                  <dd>{x.value} <span className={x.severity ? s.flag : ""}>{x.band}</span></dd>
                  <p className="small">{x.summary}</p>
                </div>
              ))}
              <div><dt>Medicines</dt><dd>{d.medications.length}</dd></div>
              <div><dt>Conditions</dt><dd>{d.conditions.length}</dd></div>
            </dl>
            <p className="muted">These are screening scores, not diagnoses. Each one comes from a published, validated questionnaire.</p>
            <div className={s.actions}>
              <button className="btn ghost" onClick={() => setPhase("questions")}>Change answers</button>
              <button className="btn" onClick={() => setPhase("consent")}>Continue</button>
            </div>
          </section>
        )}

        {phase === "consent" && (
          <section className={s.step}>
            <p className={s.count}>Before we save anything</p>
            <h1 className={s.q}>How ClinicQuick uses your information</h1>
            {err && <p className="error" role="alert">{err}</p>}
            <ul className={s.consent}>
              <li>We store your answers and interview notes so your clinician doesn't have to ask them again.</li>
              <li>Your summary is only shared when you create a link or QR code. Links expire after 7 days, and every view is logged.</li>
              <li>An AI model (Google Gemini) writes the questions and notes. Emergency checks and risk scores use fixed rules, not the AI.</li>
              <li>ClinicQuick does not diagnose. A clinician makes every decision about your care.</li>
              <li>You can change any answer later from your profile. Your age updates by itself from your date of birth.</li>
              <li>This is a hackathon demo. Please use made-up details, not your real health information.</li>
            </ul>
            <label className={s.check}>
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
              <span>I understand and agree</span>
            </label>
            <div className={s.actions}>
              <button className="btn ghost" onClick={() => setPhase("snapshot")}>Back</button>
              <button className="btn" disabled={!consent || busy} onClick={create}>{busy ? "Saving…" : "Agree and save my profile"}</button>
            </div>
          </section>
        )}

      </main>
    </div>
  );
}
