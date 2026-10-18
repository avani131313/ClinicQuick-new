"use client";

/**
 * Phone view: shows the whole app inside a phone-sized frame (an iframe of the same page at 390 px wide),
 * so the mobile layout, the bottom tab bar and phone-only features like fall detection can be demoed on a laptop.
 * The choice is remembered (cq.device). Inside the frame the app runs normally and knows it is "in-phone".
 */
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

const KEY = "cq.device";
export type Device = "desktop" | "phone";

export function setDevice(d: Device) {
  try { localStorage.setItem(KEY, d); } catch {}
  window.dispatchEvent(new CustomEvent("cq-device", { detail: d }));
}

export function useDevice(): { device: Device; framed: boolean } {
  const [device, setD] = useState<Device>("desktop");
  const [framed, setFramed] = useState(false);
  useEffect(() => {
    setFramed(window.self !== window.top);
    try { setD((localStorage.getItem(KEY) as Device) || "desktop"); } catch {}
    const on = (e: Event) => setD((e as CustomEvent).detail);
    window.addEventListener("cq-device", on);
    return () => window.removeEventListener("cq-device", on);
  }, []);
  return { device, framed };
}

function Clock() {
  const [t, setT] = useState("");
  useEffect(() => {
    const f = () => setT(new Date().toLocaleTimeString("en-CA", { hour: "numeric", minute: "2-digit" }).replace(/\s?[ap]\.?m\.?/i, ""));
    f(); const i = setInterval(f, 15000); return () => clearInterval(i);
  }, []);
  return <span>{t}</span>;
}

export default function PhoneFrame({ children }: { children: React.ReactNode }) {
  const { device, framed } = useDevice();
  const path = usePathname();
  const frame = useRef<HTMLIFrameElement>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [scale, setScale] = useState(1);

  // keep the theme in step between the frame and the page around it
  useEffect(() => {
    const on = (e: StorageEvent) => { if (e.key === "cq.theme" && e.newValue) document.documentElement.dataset.theme = e.newValue; };
    window.addEventListener("storage", on);
    if (framed) document.documentElement.classList.add("in-phone");
    return () => window.removeEventListener("storage", on);
  }, [framed]);

  useEffect(() => {
    if (device !== "phone" || framed) return;
    setSrc((s) => s ?? path + location.search + location.hash);
    const fit = () => setScale(Math.min(1, (window.innerHeight - 40) / 860));
    fit(); window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, [device, framed, path]);

  if (device !== "phone" || framed) return <>{children}</>;

  const exit = () => {
    // land on whatever page the phone was showing
    let to = path;
    try { const l = frame.current?.contentWindow?.location; if (l) to = l.pathname + l.search + l.hash; } catch {}
    setDevice("desktop");
    if (to !== path) window.location.assign(to);
  };

  return (
    <div className="phone-stage">
      <div className="phone-side">
        <p className="eyebrow">Phone view</p>
        <h2>ClinicQuick on a phone</h2>
        <p className="muted">The app as a patient sees it on their phone. Fall detection and the camera coach live in the bottom tabs.</p>
        <button className="btn ghost small" onClick={exit}>Back to desktop view</button>
      </div>
      <div className="phone" style={{ transform: `scale(${scale})` }}>
        <div className="phone-status" aria-hidden="true">
          <Clock />
          <span className="phone-island" />
          <span className="phone-icons">
            <svg width="17" height="11" viewBox="0 0 17 11"><rect x="0" y="7" width="3" height="4" rx="1" /><rect x="4.5" y="5" width="3" height="6" rx="1" /><rect x="9" y="2.5" width="3" height="8.5" rx="1" /><rect x="13.5" y="0" width="3" height="11" rx="1" /></svg>
            <svg width="25" height="12" viewBox="0 0 25 12"><rect x="0.5" y="0.5" width="21" height="11" rx="3.5" fill="none" stroke="currentColor" opacity=".5" /><rect x="2" y="2" width="15" height="8" rx="2" /><rect x="22.5" y="4" width="2" height="4" rx="1" opacity=".5" /></svg>
          </span>
        </div>
        {src && <iframe ref={frame} src={src} title="ClinicQuick on a phone" className="phone-screen" allow="camera; microphone; accelerometer; gyroscope; geolocation" />}
        <span className="phone-home" aria-hidden="true" />
      </div>
    </div>
  );
}
