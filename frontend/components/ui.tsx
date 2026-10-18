"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getSession, setSession } from "@/lib/api";
import { setTheme, useTheme } from "@/lib/theme";
import Notifications from "./Notifications";
import { setDevice, useDevice } from "./PhoneFrame";

export function Mark({ size = 26 }: { size?: number }) {
  // a single heartbeat trace that ends in a tick: the history is taken, you're ready
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect x="0.5" y="0.5" width="31" height="31" rx="9" fill="var(--surface-2)" stroke="var(--line-2)" />
      <path d="M5 17h5l2.4-6.5 4 12 2.8-7.5 1.8 2H27" fill="none" stroke="var(--accent)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function ThemeToggle() {
  const t = useTheme();
  const next = t === "dark" ? "light" : "dark";
  return (
    <button className="theme-toggle" onClick={() => setTheme(next)} aria-label={`Switch to ${next} mode`} title={`Switch to ${next} mode`}>
      {t === "dark" ? (
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="12" cy="12" r="4.2" /><path d="M12 2.5v2.2M12 19.3v2.2M4.6 4.6l1.6 1.6M17.8 17.8l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.6 19.4l1.6-1.6M17.8 6.2l1.6-1.6" /></svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round"><path d="M20.5 14.2A8.5 8.5 0 0 1 9.8 3.5a8.5 8.5 0 1 0 10.7 10.7z" /></svg>
      )}
    </button>
  );
}

export function TopBar() {
  const path = usePathname();
  const router = useRouter();
  const [role, setRole] = useState<string | null>(null);
  useEffect(() => setRole(getSession()?.role ?? null), [path]);
  const links =
    role === "patient"
      ? [["/home", "Home"], ["/care-now", "Book & walk-in"], ["/appointments", "Appointments"], ["/medications", "Medications"], ["/connect", "Health data"], ["/physio", "Physio"], ["/safety", "Safety"], ["/vault", "Records"], ["/profile", "Profile"]]
      : role === "clinician"
      ? [["/doctor", "Today"], ["/doctor/patients", "Patients"]]
      : role === "care_team"
      ? [["/care", "Residents"]]
      : [];
  return (
    <>
    <header className="topbar">
      <Link href={role === "patient" ? "/home" : role === "clinician" ? "/doctor" : role ? "/care" : "/"} className="brand">
        <Mark /> ClinicQuick
      </Link>
      <nav className="nav" aria-label="Main">
        {links.map(([href, label]) => (
          <Link key={href} href={href} aria-current={path === href || (href !== "/doctor" && path.startsWith(href + "/")) ? "page" : undefined}>
            {label}
          </Link>
        ))}
        {role && <Notifications role={role} />}
        <DeviceToggle />
        <ThemeToggle />
        {role ? (
          <button className="linkish" onClick={() => { setSession(null); router.push("/"); }}>Sign out</button>
        ) : (
          <Link href="/login">Sign in</Link>
        )}
      </nav>
    </header>
    {/* outside the header: its backdrop blur would otherwise pin the fixed tab bar to the header */}
    {role && <TabBar role={role} links={links} path={path} onSignOut={() => { setSession(null); router.push("/"); }} />}
    </>
  );
}

/** Switch between the normal desktop layout and the app shown inside a phone. */
export function DeviceToggle() {
  const { device } = useDevice();
  const next = device === "phone" ? "desktop" : "phone";
  return (
    <button className="theme-toggle device-toggle" onClick={() => setDevice(next)} aria-label={next === "phone" ? "Show phone view" : "Show desktop view"} title={next === "phone" ? "Phone view" : "Desktop view"}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><rect x="6.5" y="2.5" width="11" height="19" rx="2.6" /><path d="M10.5 18.5h3" /></svg>
    </button>
  );
}

const ICONS: Record<string, React.ReactElement> = {
  "/home": <path d="M3.5 11 12 4l8.5 7M6 9.5V20h12V9.5" />,
  "/care-now": <><rect x="3.5" y="5" width="17" height="15.5" rx="3" /><path d="M3.5 10h17M8 3v4M16 3v4" /></>,
  "/physio": <><circle cx="12" cy="4.6" r="1.9" /><path d="M5 9.5l7 1.5 7-1.5M12 11v4.5l-3.5 5.5M12 15.5l3.5 5.5" /></>,
  "/safety": <path d="M12 3 4.5 6v5.5c0 4.6 3.2 8 7.5 9.5 4.3-1.5 7.5-4.9 7.5-9.5V6L12 3zM9 12l2.2 2.2L15.5 10" />,
  "/doctor": <><rect x="3.5" y="5" width="17" height="15.5" rx="3" /><path d="M3.5 10h17M8 3v4M16 3v4" /></>,
  "/doctor/patients": <><circle cx="9" cy="8" r="3.2" /><path d="M3 20c.6-3.4 3-5.4 6-5.4s5.4 2 6 5.4M16 4.8a3.2 3.2 0 0 1 0 6.4M18 14.8c1.7.7 2.8 2.6 3 5.2" /></>,
  more: <><circle cx="5.5" cy="12" r="1.4" /><circle cx="12" cy="12" r="1.4" /><circle cx="18.5" cy="12" r="1.4" /></>,
};

function TabBar({ role, links, path, onSignOut }: { role: string; links: string[][]; path: string; onSignOut: () => void }) {
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [path]);
  const main = role === "patient" ? ["/home", "/care-now", "/physio", "/safety"] : links.map((l) => l[0]).slice(0, 4);
  const label = (h: string) => (h === "/care-now" ? "Book" : links.find((l) => l[0] === h)?.[1] || h);
  const rest = links.filter((l) => !main.includes(l[0]));
  const on = (h: string) => path === h || (h !== "/doctor" && path.startsWith(h + "/"));
  return (
    <>
      {open && (
        <div className="more-sheet" role="menu">
          {rest.map(([h, l]) => <Link key={h} href={h} role="menuitem" aria-current={on(h) ? "page" : undefined}>{l}</Link>)}
          <button role="menuitem" onClick={onSignOut}>Sign out</button>
        </div>
      )}
      <nav className="tabbar" aria-label="Main" style={{ gridTemplateColumns: `repeat(${main.length + 1}, 1fr)` }}>
        {main.map((h) => (
          <Link key={h} href={h} aria-current={on(h) ? "page" : undefined}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICONS[h] || ICONS.more}</svg>
            {label(h)}
          </Link>
        ))}
        <button aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true">{ICONS.more}</svg>
          More
        </button>
      </nav>
    </>
  );
}

export function Footer() {
  return (
    <p className="footer-note">
      ClinicQuick is pre-visit decision support, not a diagnosis. All people and records in this demo are synthetic.
      In an emergency call 911. For a mental-health crisis call or text 9‑8‑8.
    </p>
  );
}

export const URGENCY_CLASS: Record<string, string> = { green: "u-green", yellow: "u-yellow", orange: "u-orange", red: "u-red" };

/** Sparkline drawn against the person's own baseline band (median ±15%). */
export function Sparkline({
  points, baseline, width = 160, height = 36, label, colour = "var(--accent)",
}: { points: { day: string; value: number }[]; baseline?: number; width?: number; height?: number; label: string; colour?: string }) {
  if (!points || points.length < 2) return <span className="small">No data</span>;
  const vals = points.map((p) => p.value);
  const lo = Math.min(...vals, baseline ? baseline * 0.8 : Infinity);
  const hi = Math.max(...vals, baseline ? baseline * 1.2 : -Infinity);
  const pad = 3;
  const x = (i: number) => pad + (i / (points.length - 1)) * (width - pad * 2);
  const y = (v: number) => height - pad - ((v - lo) / (hi - lo || 1)) * (height - pad * 2);
  const d = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");
  const last = points[points.length - 1];
  return (
    <svg width={width} height={height} role="img" aria-label={label} style={{ display: "block", overflow: "visible" }}>
      {baseline ? (
        <rect x={0} width={width} y={y(baseline * 1.15)} height={Math.max(1, y(baseline * 0.85) - y(baseline * 1.15))} fill="var(--accent)" opacity={0.07} />
      ) : null}
      {baseline ? <line x1={0} x2={width} y1={y(baseline)} y2={y(baseline)} stroke="var(--accent)" strokeDasharray="3 3" opacity={0.3} /> : null}
      <path d={d} fill="none" stroke={colour} strokeWidth={1.8} strokeLinejoin="round" />
      <circle cx={x(points.length - 1)} cy={y(last.value)} r={2.8} fill={colour} />
    </svg>
  );
}

export function useRequireRole(roles: string[]) {
  const router = useRouter();
  const [ok, setOk] = useState(false);
  useEffect(() => {
    const s = getSession();
    if (!s || !roles.includes(s.role)) router.replace("/login");
    else setOk(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return ok;
}
