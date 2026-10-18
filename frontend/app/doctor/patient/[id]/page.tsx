"use client";

/** Old address for a patient's history; the dashboard now lives at /doctor/patients/[id]. */
import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";

export default function OldPatientRoute() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  useEffect(() => { router.replace(`/doctor/patients/${id}`); }, [id, router]);
  return null;
}
