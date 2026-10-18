"use client";

/** Leaflet map of nearby walk-in clinics. Marker colour = how long the wait is. Tiles follow the theme. */
import { useEffect, useRef } from "react";
import "leaflet/dist/leaflet.css";
import { useTheme } from "@/lib/theme";
import s from "./clinicmap.module.css";

export type Clinic = {
  id: string; name: string; lat: number; lng: number; distance_km: number; walk_min: number; drive_min: number; about: string;
  open: boolean; hours: string; doctors_on_shift: number; waiting: number; minutes_per_patient: number; wait_min: number; clear_by: string | null;
};

export const waitTone = (c: Clinic) => (!c.open ? "closed" : c.wait_min < 30 ? "short" : c.wait_min < 75 ? "medium" : "long");

export default function ClinicMap({ center, clinics, selected, onSelect }: {
  center: [number, number]; clinics: Clinic[]; selected: string | null; onSelect: (id: string) => void;
}) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<any>(null);
  const L = useRef<any>(null);
  const layer = useRef<any>(null);
  const tiles = useRef<any>(null);
  const markers = useRef<Record<string, any>>({});
  const theme = useTheme();

  useEffect(() => {
    let alive = true;
    (async () => {
      const Lmod = (await import("leaflet")).default;
      if (!alive || !el.current || map.current) return;
      L.current = Lmod;
      map.current = Lmod.map(el.current, { zoomControl: false, attributionControl: true }).setView(center, 13);
      Lmod.control.zoom({ position: "bottomright" }).addTo(map.current);
      layer.current = Lmod.layerGroup().addTo(map.current);
      draw();
    })();
    return () => { alive = false; map.current?.remove(); map.current = null; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // tiles follow light/dark
  useEffect(() => {
    if (!map.current || !L.current) return;
    tiles.current?.remove();
    // OpenStreetMap's standard tiles need no key; dark mode re-tones them with a CSS filter (see clinicmap.module.css)
    tiles.current = L.current.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
    }).addTo(map.current);
  }, [theme, map.current]); // eslint-disable-line react-hooks/exhaustive-deps

  const draw = () => {
    const Lm = L.current;
    if (!Lm || !layer.current) return;
    layer.current.clearLayers();
    markers.current = {};
    Lm.marker(center, { icon: Lm.divIcon({ className: s.me, html: "<span></span>", iconSize: [18, 18] }), keyboard: false }).addTo(layer.current).bindTooltip("You");
    clinics.forEach((c) => {
      const label = c.open ? `${c.wait_min} min` : "Closed";
      const m = Lm.marker([c.lat, c.lng], {
        icon: Lm.divIcon({ className: `${s.pin} ${s[waitTone(c)]} ${selected === c.id ? s.on : ""}`, html: `<span class="${s.bubble}">${label}</span><span class="${s.tip}"></span>`, iconSize: [74, 40], iconAnchor: [37, 40] }),
        title: c.name, riseOnHover: true,
      }).addTo(layer.current);
      m.on("click", () => onSelect(c.id));
      markers.current[c.id] = m;
    });
  };

  useEffect(() => {
    draw();
    if (map.current && L.current && clinics.length && !selected) {
      const b = L.current.latLngBounds([center, ...clinics.map((c) => [c.lat, c.lng])]);
      map.current.fitBounds(b, { padding: [60, 60], maxZoom: 15 });
    }
  }, [clinics, selected]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { map.current?.setView(center, 13); draw(); }, [center[0], center[1]]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const c = clinics.find((x) => x.id === selected);
    if (c && map.current) map.current.flyTo([c.lat, c.lng], 15, { duration: 0.8 });
  }, [selected]); // eslint-disable-line react-hooks/exhaustive-deps

  return <div ref={el} className={s.map} data-theme={theme} role="region" aria-label="Map of nearby walk-in clinics" />;
}
