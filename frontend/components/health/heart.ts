/** The anatomical heart point cloud (public/models/heart-points.json, made by scripts/body/make_heart.py). */
export type HeartData = { points: [number, number, number, number][]; regions: string[] };

let cache: Promise<HeartData> | null = null;
export function loadHeart(): Promise<HeartData> {
  if (!cache) cache = fetch("/models/heart-points.json").then((r) => r.json());
  return cache;
}

/** Colour per region: muscle, atria, aorta (oxygenated), pulmonary trunk and venae cavae (deoxygenated). */
export const HEART_COLOURS = {
  dark: ["#FF8E7E", "#E0645A", "#FF5A55", "#8FA2FF", "#A48CFF"],
  light: ["#D8503D", "#B53A30", "#C92A26", "#3F5CC9", "#6A4CC9"],
};
