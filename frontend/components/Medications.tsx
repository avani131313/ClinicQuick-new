"use client";

import { useMemo, useState } from "react";
import s from "./meds.module.css";

export type Med = {
  id: number; name: string; dose: string | null; frequency: string | null; route: string | null; reason: string | null;
  prescriber: string | null; start_date: string | null; end_date: string | null; stop_reason: string | null; notes: string | null;
  source: string; active: boolean;
};
export type MedHistory = { current: Med[]; previous: Med[]; all: Med[] };

const DAY = 86400000;
const d = (iso: string | null) => (iso ? new Date(iso + "T12:00:00") : new Date());
const month = (iso: string | null) => (iso ? d(iso).toLocaleDateString("en-CA", { month: "short", year: "numeric" }) : "—");
const span = (a: string | null, b: string | null) => {
  const days = Math.max(1, Math.round((d(b).getTime() - d(a).getTime()) / DAY));
  if (days < 21) return `${days} day${days === 1 ? "" : "s"}`;
  if (days < 365) return `${Math.round(days / 30.4)} month${Math.round(days / 30.4) === 1 ? "" : "s"}`;
  const y = days / 365.25;
  return `${y < 10 ? y.toFixed(1).replace(".0", "") : Math.round(y)} years`;
};

type Range = "1y" | "5y" | "all";

function Timeline({ meds }: { meds: Med[] }) {
  const [range, setRange] = useState<Range>("5y");
  const [hover, setHover] = useState<Med | null>(null);
  const now = Date.now();
  const earliest = Math.min(...meds.map((m) => d(m.start_date).getTime()));
  const from = range === "1y" ? now - 365 * DAY : range === "5y" ? now - 5 * 365 * DAY : earliest - 60 * DAY;
  const to = now + 45 * DAY;
  const x = (t: number) => Math.max(0, Math.min(100, ((t - from) / (to - from)) * 100));
  const rows = useMemo(() => {
    const by: Record<string, Med[]> = {};
    meds.forEach((m) => (by[m.name] ||= []).push(m));
    return Object.entries(by).sort((a, b) => Number(b[1].some((m) => m.active)) - Number(a[1].some((m) => m.active)) || a[0].localeCompare(b[0]));
  }, [meds]);
  const years: number[] = [];
  for (let y = new Date(from).getFullYear() + 1; y <= new Date(to).getFullYear(); y++) years.push(y);
  const step = Math.ceil(years.length / 8) || 1;

  return (
    <section className={s.timeline}>
      <div className={s.tlHead}>
        <p className="panel-title">Timeline</p>
        <div className={s.seg} role="tablist" aria-label="Time range">
          {(["1y", "5y", "all"] as Range[]).map((r) => (
            <button key={r} role="tab" aria-selected={range === r} onClick={() => setRange(r)}>{r === "1y" ? "1 year" : r === "5y" ? "5 years" : "All"}</button>
          ))}
        </div>
      </div>
      <div className={s.grid}>
        <div className={s.axis} aria-hidden="true">
          {years.filter((_, i) => i % step === 0).map((y) => (
            <span key={y} style={{ left: `${x(new Date(y, 0, 1).getTime())}%` }}>{y}</span>
          ))}
          <span className={s.today} style={{ left: `${x(now)}%` }}>Today</span>
        </div>
        {rows.map(([name, list]) => (
          <div key={name} className={s.row}>
            <span className={s.rowName}>{name}</span>
            <div className={s.track}>
              <span className={s.nowLine} style={{ left: `${x(now)}%` }} aria-hidden="true" />
              {list.map((m) => {
                const a = d(m.start_date).getTime(), b = m.active ? now : d(m.end_date).getTime();
                if (b < from) return null;
                const left = x(a), width = Math.max(1.2, x(b) - left);
                return (
                  <button key={m.id} className={`${s.bar} ${m.active ? s.barOn : ""}`} style={{ left: `${left}%`, width: `${width}%` }}
                    onMouseEnter={() => setHover(m)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(m)} onBlur={() => setHover(null)}
                    aria-label={`${m.name} ${m.dose || ""}, ${month(m.start_date)} to ${m.active ? "now" : month(m.end_date)}`}>
                    <span>{m.dose}</span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      <p className={s.readout} aria-live="polite">
        {hover
          ? <><strong>{hover.name} {hover.dose}</strong> · {hover.frequency || "frequency not recorded"} · {month(hover.start_date)} to {hover.active ? "now" : month(hover.end_date)} ({span(hover.start_date, hover.active ? null : hover.end_date)}){hover.stop_reason ? ` · stopped: ${hover.stop_reason.toLowerCase()}` : ""}</>
          : "Hover a bar for details. A medicine with a dose change shows as two bars on one line."}
      </p>
    </section>
  );
}

export default function Medications({ data, onAdd, onStop, addLabel = "Add a medicine" }: {
  data: MedHistory | null; onAdd?: (m: any) => Promise<void>; onStop?: (id: number, reason: string) => Promise<void>; addLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", dose: "", frequency: "", reason: "", start_date: "" });
  const [busy, setBusy] = useState(false);
  const [stopping, setStopping] = useState<number | null>(null);
  const [why, setWhy] = useState("");
  if (!data) return <p className="muted">Loading medicines…</p>;

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!onAdd || !form.name.trim()) return;
    setBusy(true);
    await onAdd({ ...form, start_date: form.start_date || null });
    setForm({ name: "", dose: "", frequency: "", reason: "", start_date: "" }); setOpen(false); setBusy(false);
  }

  return (
    <div className={s.wrap}>
      <div className={s.summary}>
        <p><span className="num">{data.current.length}</span> taking now</p>
        <p><span className="num">{data.previous.length}</span> taken before</p>
        {onAdd && <button className="btn small" onClick={() => setOpen((v) => !v)}>{open ? "Close" : addLabel}</button>}
      </div>

      {open && onAdd && (
        <form className={`panel ${s.add}`} onSubmit={add}>
          <div className="field"><label htmlFor="mn">Medicine</label><input id="mn" type="text" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Metformin" /></div>
          <div className="field"><label htmlFor="md">Dose</label><input id="md" type="text" value={form.dose} onChange={(e) => setForm({ ...form, dose: e.target.value })} placeholder="e.g. 500 mg" /></div>
          <div className="field"><label htmlFor="mf">How often</label><input id="mf" type="text" value={form.frequency} onChange={(e) => setForm({ ...form, frequency: e.target.value })} placeholder="e.g. Twice a day with food" /></div>
          <div className="field"><label htmlFor="mr">What it's for</label><input id="mr" type="text" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} /></div>
          <div className="field"><label htmlFor="ms">Started</label><input id="ms" type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></div>
          <button className="btn" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
        </form>
      )}

      <h2 className={s.sub}>Taking now</h2>
      {data.current.length === 0 ? <p className="muted">No current medicines.</p> : (
        <ul className={s.cards}>
          {data.current.map((m, i) => (
            <li key={m.id} className={s.card} style={{ animationDelay: `${i * 70}ms` }}>
              <div className={s.cardTop}>
                <span className={s.pill} aria-hidden="true"><span /></span>
                <div>
                  <h3>{m.name}</h3>
                  <p className={s.reason}>{m.reason || "Reason not recorded"}</p>
                </div>
                {m.dose && <span className={s.dose}>{m.dose}</span>}
              </div>
              <dl className={s.facts}>
                <div><dt>How often</dt><dd>{m.frequency || "Not recorded"}</dd></div>
                <div><dt>Since</dt><dd>{month(m.start_date)} <small>({span(m.start_date, null)})</small></dd></div>
                <div><dt>Prescribed by</dt><dd>{m.prescriber || "Not recorded"}</dd></div>
                {m.route && <div><dt>How</dt><dd>{m.route}</dd></div>}
              </dl>
              {m.notes && <p className={s.note}>{m.notes}</p>}
              {onStop && (stopping === m.id ? (
                <form className={s.stopForm} onSubmit={async (e) => { e.preventDefault(); await onStop(m.id, why); setStopping(null); setWhy(""); }}>
                  <input type="text" value={why} onChange={(e) => setWhy(e.target.value)} placeholder="Why it was stopped (optional)" aria-label="Why it was stopped" />
                  <button className="btn small">Mark stopped</button>
                  <button type="button" className="linkish small" onClick={() => setStopping(null)}>Cancel</button>
                </form>
              ) : <button className={`linkish small ${s.stop}`} onClick={() => setStopping(m.id)}>Stopped taking it?</button>)}
            </li>
          ))}
        </ul>
      )}

      {data.all.length > 0 && <Timeline meds={data.all} />}

      <h2 className={s.sub}>Taken before</h2>
      {data.previous.length === 0 ? <p className="muted">Nothing recorded.</p> : (
        <table className={s.prev}>
          <thead><tr><th>Medicine</th><th>Dose</th><th className="hide-sm">When</th><th className="hide-sm">For</th><th>Why stopped</th></tr></thead>
          <tbody>
            {data.previous.map((m) => (
              <tr key={m.id}>
                <td><strong>{m.name}</strong><br /><small className="muted">{m.frequency}</small></td>
                <td className="num">{m.dose || "—"}</td>
                <td className="hide-sm">{month(m.start_date)} to {month(m.end_date)}<br /><small className="muted">{span(m.start_date, m.end_date)}</small></td>
                <td className="hide-sm">{m.reason || "—"}</td>
                <td>{m.stop_reason || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className={s.fine}>Always check with your pharmacist or clinician before starting or stopping a medicine.</p>
    </div>
  );
}
