"use client";

/**
 * Bell in the top bar. Notifications are computed by the server (visit reminders, bookings, new records,
 * walk-in queue); which ones you've read is remembered in this browser. If you turn on reminders,
 * the browser also shows a system notification for anything urgent you haven't seen.
 */
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import s from "./notify.module.css";

type N = { id: string; kind: string; title: string; body: string; ts: string; href: string; urgent?: boolean };
const KEY = "cq.read", SHOWN = "cq.shown";
const load = (k: string): string[] => { try { return JSON.parse(localStorage.getItem(k) || "[]"); } catch { return []; } };
const save = (k: string, v: string[]) => { try { localStorage.setItem(k, JSON.stringify(v.slice(-200))); } catch {} };
const ago = (iso: string) => {
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 0) return "upcoming";
  return m < 1 ? "now" : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`;
};

function Icon({ kind }: { kind: string }) {
  const p: Record<string, React.ReactElement> = {
    reminder: <path d="M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z" />,
    confirm: <path d="M5 12.5l4.5 4.5L19 7.5" />,
    record: <path d="M7 3h7l4 4v14H7zM14 3v4h4M9.5 12h6M9.5 16h6" />,
    queue: <path d="M5 20v-1a4 4 0 0 1 4-4h0a4 4 0 0 1 4 4v1M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM16 11a3 3 0 1 0 0-6M19 20v-1a4 4 0 0 0-3-3.9" />,
  };
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{p[kind] || p.reminder}</svg>;
}

export default function Notifications({ role }: { role: string }) {
  const [list, setList] = useState<N[]>([]);
  const [read, setRead] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const [perm, setPerm] = useState<string>("default");
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setRead(load(KEY));
    setPerm(typeof Notification !== "undefined" ? Notification.permission : "unsupported");
    const pull = () => api<N[]>("/notifications").then((l) => {
      setList(l);
      // system notifications for urgent, unseen items (only if the person turned them on)
      if (typeof Notification !== "undefined" && Notification.permission === "granted") {
        const shown = load(SHOWN);
        l.filter((n) => n.urgent && !shown.includes(n.id)).forEach((n) => { new Notification(n.title, { body: n.body, tag: n.id }); shown.push(n.id); });
        save(SHOWN, shown);
      }
    }).catch(() => {});
    pull();
    const t = setInterval(pull, 60000);
    return () => clearInterval(t);
  }, [role]);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);

  const unread = list.filter((n) => !read.includes(n.id));
  const markAll = () => { const r = Array.from(new Set([...read, ...list.map((n) => n.id)])); setRead(r); save(KEY, r); };
  const markOne = (id: string) => { if (!read.includes(id)) { const r = [...read, id]; setRead(r); save(KEY, r); } setOpen(false); };

  return (
    <div className={s.wrap} ref={box}>
      <button className={s.bell} onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-haspopup="dialog"
        aria-label={unread.length ? `Notifications, ${unread.length} unread` : "Notifications"}>
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M6 9a6 6 0 1 1 12 0c0 6 2.5 7.5 2.5 7.5h-17S6 15 6 9zM10 20a2.2 2.2 0 0 0 4 0" /></svg>
        {unread.length > 0 && <span className={s.badge}>{unread.length > 9 ? "9+" : unread.length}</span>}
      </button>
      {open && (
        <div className={s.panel} role="dialog" aria-label="Notifications">
          <div className={s.head}>
            <strong>Notifications</strong>
            {unread.length > 0 && <button className="linkish small" onClick={markAll}>Mark all read</button>}
          </div>
          {list.length === 0 ? <p className={s.empty}>You're all caught up.</p> : (
            <ul className={s.list}>
              {list.map((n) => (
                <li key={n.id} data-unread={!read.includes(n.id) || undefined} data-kind={n.kind} data-urgent={n.urgent || undefined}>
                  <Link href={n.href} onClick={() => markOne(n.id)}>
                    <span className={s.icon}><Icon kind={n.kind} /></span>
                    <span className={s.text}><strong>{n.title}</strong><span>{n.body}</span><time>{ago(n.ts)}</time></span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          {perm === "default" && (
            <button className={s.enable} onClick={async () => setPerm(await Notification.requestPermission())}>
              Turn on reminders on this device
            </button>
          )}
          {perm === "granted" && <p className={s.on}>Reminders are on for this device.</p>}
        </div>
      )}
    </div>
  );
}
