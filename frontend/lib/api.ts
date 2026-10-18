"use client";

export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Session = { token: string; role: "patient" | "clinician" | "care_team"; patient_id?: string | null; name?: string };

export function getSession(): Session | null {
  try {
    const raw = localStorage.getItem("prelude.session");
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export function setSession(s: Session | null) {
  try {
    if (s) localStorage.setItem("prelude.session", JSON.stringify(s));
    else localStorage.removeItem("prelude.session");
  } catch {
    /* storage unavailable — session lives for this page only */
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T = any>(path: string, opts: { method?: string; body?: any; form?: FormData; auth?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const s = getSession();
  if (opts.auth !== false && s) headers["Authorization"] = `Bearer ${s.token}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, { method: opts.method || (body ? "POST" : "GET"), headers, body });
  } catch {
    throw new ApiError(0, "Can't reach the ClinicQuick server. Check that the API is running.");
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {}
    if (res.status === 401) setSession(null);
    throw new ApiError(res.status, msg);
  }
  return res.json();
}
