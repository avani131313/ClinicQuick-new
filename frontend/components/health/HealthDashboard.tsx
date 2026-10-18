"use client";

import { useState } from "react";
import BodyScene, { Hotspot } from "./BodyScene";
import { Bars, DayHeart, LiveHeart, Metric, Pressure, WeekChanges, fmt } from "./charts";
import s from "./dash.module.css";

type Payload = {
  series: Record<string, { day: string; value: number }[]>;
  latest: Record<string, { value: number; ts: string; source: string }>;
  hr_today: { ts: string; value: number }[];
  hr_source: string | null;
  labs: { test: string; value: number; unit: string | null; ts: string }[];
  has_data: boolean;
};

const SOURCE: Record<string, string> = { "demo-wearable": "Sample watch stream, synthetic", "apple-health": "Apple Health import" };
const ago = (iso?: string) => {
  if (!iso) return "";
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  return m < 2 ? "just now" : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : new Date(iso).toLocaleDateString("en-CA", { month: "short", day: "numeric" });
};

export default function HealthDashboard({ data, sex, onPopulate, populating, who = "patient" }: {
  data: Payload | null; sex: string; onPopulate?: () => void; populating?: boolean; who?: "patient" | "clinician";
}) {
  const [active, setActive] = useState<string | null>(null);
  const [bpm, setBpm] = useState<number>(68);
  const L = data?.latest || {};
  const S = data?.series || {};
  const lastHr = data?.hr_today?.at(-1);
  const hrBase = lastHr ? lastHr.value : L.rhr?.value ?? null;
  const live = data?.hr_source === "demo-wearable" || (!!lastHr && Date.now() - new Date(lastHr.ts).getTime() < 30 * 60000);
  const today = S.steps?.at(-1);
  const sleepH = S.sleep_min?.at(-1) ? S.sleep_min.at(-1)!.value / 60 : null;
  const sys = L.bp_sys?.value, dia = L.bp_dia?.value;
  const has = !!data?.has_data;
  const partial = has && (!data?.hr_today?.length || !L.hrv || !L.spo2);

  const spots: Hotspot[] = [
    { id: "heart", anchor: "heart", label: "Heart", value: hrBase ? `${bpm} bpm` : "—", tone: "pulse" },
    { id: "spo2", anchor: "lungs", label: "Blood oxygen", value: L.spo2 ? `${fmt(L.spo2.value)}%` : "—", tone: L.spo2 && L.spo2.value < 94 ? "watch" : "ok" },
    { id: "sleep", anchor: "head", label: "Sleep", value: sleepH ? `${fmt(sleepH, 1)} h` : "—", tone: sleepH && sleepH < 6 ? "watch" : "ok" },
    { id: "bp", anchor: "arm", label: "Blood pressure", value: sys ? `${fmt(sys)}/${fmt(dia)}` : "—", tone: sys && (sys >= 135 || (dia || 0) >= 85) ? "watch" : "ok" },
    { id: "hrv", anchor: "wrist", label: "Watch · HRV", value: L.hrv ? `${fmt(L.hrv.value)} ms` : has ? "Connected" : "Not connected" },
    { id: "steps", anchor: "legs", label: "Steps today", value: today ? fmt(today.value) : "—" },
  ];

  const pick = (id: string) => {
    setActive(id);
    document.getElementById(`m-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  return (
    <div className={s.dash}>
      <div className={s.top}>
        <section className={s.figure} aria-label="Body overview">
          <BodyScene sex={sex} bpm={bpm} hotspots={spots} active={active} onSelect={pick} height={660} />
        </section>

        <div className={s.right}>
          <section className={`panel ${s.livePanel}`} id="m-heart" data-on={active === "heart" || undefined}>
            <LiveHeart base={hrBase} live={live} onBpm={setBpm}
              source={data?.hr_source ? `${SOURCE[data.hr_source] || data.hr_source}${live && data.hr_source !== "demo-wearable" ? "" : lastHr ? `, ${ago(lastHr.ts)}` : ""}` : has ? "Resting rate, from daily readings" : "No watch connected"} />
          </section>

          {(!has || partial) && onPopulate && (
            <section className={`panel ${s.empty}`}>
              <p className="panel-title">{has ? "Some metrics missing" : "No watch data yet"}</p>
              <h3>{has ? "Only part of the picture is synced." : who === "clinician" ? "Nothing synced for this patient." : "Connect a watch to see your body's week."}</h3>
              <p className="muted">
                {has
                  ? "Fill in the rest with realistic synthetic watch data: live heart rate, HRV, blood oxygen, breathing, blood pressure. Real readings are kept as they are."
                  : who === "clinician"
                  ? "Populate six weeks of realistic synthetic watch data to see how the dashboard reads: heart rate, sleep, steps, blood oxygen, blood pressure."
                  : "Upload an Apple Health export, or add sample data to see how your trends appear to your clinician."}
              </p>
              <button className="btn" onClick={onPopulate} disabled={populating}>{populating ? "Generating…" : "Populate watch data"}</button>
            </section>
          )}

          <div className={s.metrics}>
            <Metric id="m-rhr" label="Resting HR" value={L.rhr?.value} unit="bpm" points={S.rhr} color="var(--pulse)" better="down" />
            <Metric id="m-hrv" active={active === "hrv"} label="HRV" value={L.hrv?.value} unit="ms" points={S.hrv} better="up" />
            <Metric id="m-spo2" active={active === "spo2"} label="Blood oxygen" value={L.spo2?.value} unit="%" points={S.spo2} better="up" />
            <Metric id="m-steps" active={active === "steps"} label="Steps today" value={today?.value} points={S.steps} better="up" />
            <Metric id="m-sleep" active={active === "sleep"} label="Last night" value={sleepH} unit="h" dp={1} points={S.sleep_min?.map((p) => ({ ...p, value: p.value / 60 }))} color="var(--sleep)" better="up" />
            <Metric id="m-resp" label="Respiration" value={L.resp_rate?.value} unit="/min" dp={1} points={S.resp_rate} />
          </div>

          {has && (
            <section className="panel">
              <p className="panel-title">What changed this week</p>
              <WeekChanges series={S} />
            </section>
          )}
        </div>
      </div>

      {has && (
        <div className={s.lower}>
          <section className={`panel ${s.wide}`}>
            <div className={s.head}><p className="panel-title">Heart rate, last 24 hours</p></div>
            <DayHeart data={data!.hr_today} />
          </section>
          <section className="panel">
            <div className={s.head}><p className="panel-title">Sleep, last 14 nights</p></div>
            <Bars points={S.sleep_min || []} scale={1 / 60} dp={1} unit="h" color="var(--sleep)" />
          </section>
          <section className="panel">
            <div className={s.head}><p className="panel-title">Steps, last 14 days</p></div>
            <Bars points={S.steps || []} unit="steps" />
          </section>
          <section className={`panel ${active === "bp" ? s.on : ""}`} id="m-bp">
            <div className={s.head}><p className="panel-title">Home blood pressure</p></div>
            <Pressure sys={S.bp_sys || []} dia={S.bp_dia || []} />
          </section>
          <section className="panel">
            <div className={s.head}><p className="panel-title">Body</p></div>
            <dl className={s.kv}>
              <div><dt>Weight</dt><dd><span className="num">{fmt(L.weight?.value, 1)}</span> kg</dd></div>
              <div><dt>Active energy, today</dt><dd><span className="num">{fmt(S.active_kcal?.at(-1)?.value)}</span> kcal</dd></div>
              <div><dt>Respiratory rate</dt><dd><span className="num">{fmt(L.resp_rate?.value, 1)}</span> /min</dd></div>
              {(data!.labs || []).slice(0, 4).map((l) => <div key={l.test}><dt>{l.test}</dt><dd><span className="num">{fmt(l.value, 1)}</span> {l.unit || ""}</dd></div>)}
            </dl>
            {onPopulate && who === "clinician" && <button className={`linkish ${s.regen}`} onClick={onPopulate} disabled={populating}>{populating ? "Generating…" : "Regenerate sample data"}</button>}
          </section>
        </div>
      )}
    </div>
  );
}
