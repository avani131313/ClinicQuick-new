"use client";

import Link from "next/link";
import { Mark, ThemeToggle } from "./ui";
import s from "./auth.module.css";

/** Quiet, focused frame for sign-up and log-in: one line of brand, one card, nothing moving. */
export default function AuthShell({ children }: { children: React.ReactNode; shape?: number }) {
  return (
    <div className={s.shell}>
      <aside className={s.brandSide}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}><Link href="/" className={s.brand}><Mark size={30} /> ClinicQuick</Link><ThemeToggle /></div>
        <p className={s.line}>Your story,<br />ready before<br />the visit.</p>
        <svg className={s.trace} viewBox="0 0 600 80" preserveAspectRatio="none" aria-hidden="true">
          <path d="M0 50 H230 l18 -34 26 58 22 -40 14 16 H600" fill="none" stroke="var(--accent)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </aside>
      <main className={s.main}>{children}</main>
    </div>
  );
}

export { s as authStyles };
