"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useRequireRole } from "@/components/ui";
import { api } from "@/lib/api";

/** Starts a check-in straight away, so signing in takes you to Lena. */
export default function NewVisit() {
  const ok = useRequireRole(["patient"]);
  const router = useRouter();
  const [err, setErr] = useState("");
  const started = useRef(false);
  useEffect(() => {
    if (!ok || started.current) return;
    started.current = true;
    api("/encounters", { method: "POST" })
      .then((r) => router.replace(`/visit/${r.encounter_id}`))
      .catch((e) => (e.status === 400 ? router.replace("/start") : setErr(e.message)));
  }, [ok, router]);
  return (
    <main className="ecg" style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24 }}>
      {err ? <p className="error" role="alert">{err}</p> : <p className="muted">Connecting you to Lena…</p>}
    </main>
  );
}
