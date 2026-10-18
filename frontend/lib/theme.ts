"use client";

import { useEffect, useState } from "react";

export type Theme = "dark" | "light";

export function currentTheme(): Theme {
  if (typeof document === "undefined") return "dark";
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

export function setTheme(t: Theme) {
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("cq.theme", t); } catch {}
}

/** Read a CSS custom property (e.g. "--accent") as a string, for canvas and WebGL drawing. */
export function cssVar(name: string, fallback = "#8EE3CB") {
  if (typeof document === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

/** Re-renders when the theme changes anywhere on the page. */
export function useTheme(): Theme {
  const [t, setT] = useState<Theme>("dark");
  useEffect(() => {
    setT(currentTheme());
    const mo = new MutationObserver(() => setT(currentTheme()));
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => mo.disconnect();
  }, []);
  return t;
}
