"use client";

/** Clinician view of a patient's home exercises: see the plan, add an exercise the camera coach can track, remove one. */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import s from "./plan.module.css";

type Item = { id: number; exercise: string; sets: number; reps: number; notes: string | null; name: string; target: string };
type Catalog = Record<string, { name: string; target: string; how: string }>;

export default function PhysioPlan({ patientId }: { patientId: string }) {
  const [plan, setPlan] = useState<Item[]>([]);
  const [catalog, setCatalog] = useState<Catalog>({});
  const [form, setForm] = useState({ exercise: "", sets: 2, reps: 10, notes: "" });
  const [err, setErr] = useState("");
  const take = (r: { plan: Item[]; catalog: Catalog }) => { setPlan(r.plan); setCatalog(r.catalog); };
  useEffect(() => { api(`/doctor/patients/${patientId}/physio`).then(take).catch((e) => setErr(e.message)); }, [patientId]);

  async function add(e: React.FormEvent) {
    e.preventDefault(); setErr("");
    try { take(await api(`/doctor/patients/${patientId}/physio`, { body: { ...form, notes: form.notes || null } })); setForm({ exercise: "", sets: 2, reps: 10, notes: "" }); }
    catch (x: any) { setErr(x.message); }
  }
  async function remove(id: number) { take(await api(`/doctor/patients/${patientId}/physio/${id}/remove`, { method: "POST" })); }

  return (
    <div className={s.wrap}>
      <section className="panel">
        <p className="panel-title">Home exercises · {plan.length}</p>
        {plan.length === 0 ? <p className="muted">No exercises assigned.</p> : (
          <ul className={s.list}>
            {plan.map((p) => (
              <li key={p.id}>
                <div><strong>{p.name}</strong><small>{p.sets} sets × {p.reps} reps · {p.target}</small>{p.notes && <em>{p.notes}</em>}</div>
                <button className="btn ghost small" onClick={() => remove(p.id)}>Remove</button>
              </li>
            ))}
          </ul>
        )}
        <p className="small">The patient does these with the camera coach in the app, which counts reps and checks form.</p>
      </section>
      <form className="panel" onSubmit={add}>
        <p className="panel-title">Assign an exercise</p>
        <div className="field">
          <label htmlFor="px-ex">Exercise</label>
          <select id="px-ex" value={form.exercise} onChange={(e) => setForm({ ...form, exercise: e.target.value })} required>
            <option value="">Choose</option>
            {Object.entries(catalog).map(([k, c]) => <option key={k} value={k}>{c.name} · {c.target}</option>)}
          </select>
        </div>
        <div className={s.row}>
          <div className="field"><label htmlFor="px-sets">Sets</label><input id="px-sets" type="number" min={1} max={10} value={form.sets} onChange={(e) => setForm({ ...form, sets: +e.target.value })} /></div>
          <div className="field"><label htmlFor="px-reps">Reps</label><input id="px-reps" type="number" min={1} max={50} value={form.reps} onChange={(e) => setForm({ ...form, reps: +e.target.value })} /></div>
        </div>
        <div className="field"><label htmlFor="px-notes">Note for the patient (optional)</label><input id="px-notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="e.g. Hold the back of a chair" /></div>
        {err && <p className="error" role="alert">{err}</p>}
        <button className="btn" disabled={!form.exercise}>Assign</button>
      </form>
    </div>
  );
}
