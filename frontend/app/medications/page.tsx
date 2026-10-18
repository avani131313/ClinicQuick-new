"use client";

import { useEffect, useState } from "react";
import Medications, { MedHistory } from "@/components/Medications";
import { Footer, TopBar, useRequireRole } from "@/components/ui";
import { api } from "@/lib/api";

export default function MedicationsPage() {
  const ok = useRequireRole(["patient"]);
  const [data, setData] = useState<MedHistory | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { if (ok) api("/medications").then(setData).catch((e) => setErr(e.message)); }, [ok]);
  if (!ok) return null;
  return (
    <>
      <TopBar />
      <main className="wrap page">
        <p className="eyebrow">Medications</p>
        <h1 style={{ margin: "10px 0 10px" }}>What you take, and what you took.</h1>
        <p className="muted" style={{ marginBottom: 26 }}>Doses, how often, why, and who prescribed it. Your clinician sees this list with every check-in.</p>
        {err && <p className="error">{err}</p>}
        <Medications
          data={data}
          onAdd={async (m) => setData(await api("/medications", { body: m }))}
          onStop={async (id, reason) => setData(await api(`/medications/${id}/stop`, { body: { stop_reason: reason || null } }))}
        />
      </main>
      <Footer />
    </>
  );
}
