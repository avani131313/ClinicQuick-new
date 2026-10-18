"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Footer, Sparkline, TopBar, useRequireRole } from "@/components/ui";
import { api } from "@/lib/api";
import s from "./care.module.css";

export default function Care() {
  const ok = useRequireRole(["care_team", "clinician"]);
  const router = useRouter();
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => { if (ok) api("/care/residents").then(setD).catch((e) => setErr(e.message)); }, [ok]);
  if (!ok) return null;
  const c = d?.counts;
  return (
    <>
      <TopBar />
      <main className="wrap">
        <section className={s.head}>
          <h1>{d?.facility || "Residents"}</h1>
          {c && (
            <p className={s.sum}>
              <strong>{c.alert} {c.alert === 1 ? "resident needs" : "residents need"} attention today</strong>, {c.watch} to watch, {c.ok} stable.
              <span className="muted"> Each resident is compared with their own last two weeks, not an average.</span>
            </p>
          )}
          {err && <p className="error">{err}</p>}
        </section>
        {d && (
          <table className={s.table}>
            <thead>
              <tr><th>Status</th><th>Resident</th><th className="hide-sm">Room</th><th className="hide-sm">What changed</th><th>Steps, 3 weeks</th></tr>
            </thead>
            <tbody>
              {d.residents.map((r: any) => (
                <tr key={r.id} className={`clickable ${s[r.status]}`} onClick={() => router.push(`/care/${r.id}`)}>
                  <td><span className={`dot ${r.status}`} /><span className={s.headline}>{r.headline}</span></td>
                  <td><a href={`/care/${r.id}`} onClick={(e) => e.stopPropagation()}><strong>{r.name}</strong></a><br /><span className="small">{r.age}, {r.sex}</span></td>
                  <td className="hide-sm">{r.room}</td>
                  <td className="hide-sm">{r.signal_labels.join(", ") || <span className="muted">Nothing new</span>}</td>
                  <td><Sparkline points={r.steps} label={`${r.name} daily steps`} width={140} height={30} colour={r.status === "alert" ? "#C0531C" : "#123A40"} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </main>
      <Footer />
    </>
  );
}
