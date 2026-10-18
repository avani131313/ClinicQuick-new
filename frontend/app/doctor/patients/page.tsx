"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fmtDay, fmtTime } from "@/components/Booking";
import { Footer, TopBar, useRequireRole } from "@/components/ui";
import { api } from "@/lib/api";
import s from "./patients.module.css";

const initials = (n: string) => n.split(" ").map((x) => x[0]).slice(0, 2).join("");

export default function Patients() {
  const ok = useRequireRole(["clinician"]);
  const [list, setList] = useState<any[] | null>(null);
  const [q, setQ] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => { if (ok) api("/doctor/patients").then(setList).catch((e) => setErr(e.message)); }, [ok]);
  if (!ok) return null;
  const shown = (list || []).filter((p) => (p.name + " " + p.conditions.join(" ")).toLowerCase().includes(q.toLowerCase()));

  return (
    <>
      <TopBar />
      <main className={`wrap ${s.page}`}>
        <header className={s.head}>
          <div>
            <p className="eyebrow">Your patients</p>
            <h1>Choose a patient.</h1>
            <p className="muted">Everyone who has booked with you. Open one for their body, vitals, history and records on one screen.</p>
          </div>
          <label className={s.search}>
            <span className="sr-only">Search patients</span>
            <input type="search" placeholder="Search by name or condition" value={q} onChange={(e) => setQ(e.target.value)} />
          </label>
        </header>
        {err && <p className="error">{err}</p>}
        {list && list.length === 0 && <p className="muted">No patients yet. They appear here once they book with you.</p>}

        <ul className={s.grid}>
          {shown.map((p, i) => (
            <li key={p.id} style={{ animationDelay: `${i * 60}ms` }}>
              <Link href={`/doctor/patients/${p.id}`} className={s.card}>
                <span className={s.avatar} data-sex={p.sex} aria-hidden="true">{initials(p.name)}</span>
                <span className={s.name}>{p.name}</span>
                <span className={s.meta}>{p.age}, {p.sex}</span>
                <span className={s.conds}>
                  {p.conditions.length ? p.conditions.map((c: string) => <span key={c}>{c}</span>) : <span className={s.none}>No conditions recorded</span>}
                </span>
                <span className={s.foot}>
                  <span>
                    <small>Next visit</small>
                    {p.next_at ? <>{fmtDay(p.next_at)}, {fmtTime(p.next_at)}</> : "None booked"}
                  </span>
                  <span className={s.watch} data-on={p.has_data || undefined}>
                    <span aria-hidden="true" />{p.has_data ? "Watch data" : "No watch"}
                  </span>
                </span>
                <span className={s.go} aria-hidden="true">→</span>
              </Link>
            </li>
          ))}
        </ul>
      </main>
      <Footer />
    </>
  );
}
