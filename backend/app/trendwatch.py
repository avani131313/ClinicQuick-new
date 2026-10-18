"""Trend Watch — rule-based early warning for care teams (the PCC piece).

Each resident is compared with their OWN baseline, not a population norm.
Rules are deliberately simple and explainable; every signal carries the
numbers that triggered it so the dashboard can say exactly why.

"Rules catch it, AI explains it, the nurse decides."
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import date, timedelta
from statistics import median

WINDOW_DAYS = 5        # recent window we evaluate
BASELINE_DAYS = 14     # personal baseline length, immediately before the window

SUGGESTED_ACTIONS = {
    "mobility_down": "Observe gait and transfers; check for pain, new weakness or footwear issues.",
    "rhr_up": "Take a full set of vitals (temp, BP, SpO2); consider infection or dehydration.",
    "sleep_down": "Ask about night-time pain, toileting, or confusion; review sedating meds.",
    "intake_down": "Offer fluids and preferred foods; record intake for 48 h; check weight.",
    "cognition": "Do a quick delirium screen (e.g. 4AT); check hydration, bowels, urine and new meds.",
    "dizziness_or_fall": "Check orthostatic BP; review meds that cause dizziness; post-fall huddle if a fall occurred.",
    "pain_up": "Reassess pain location and severity; review analgesia.",
}


@dataclass
class Signal:
    key: str
    label: str
    detail: str
    evidence: dict
    action: str

    def to_dict(self):
        return asdict(self)


@dataclass
class TrendResult:
    status: str                    # "ok" | "watch" | "alert"
    headline: str
    risks: list[str]
    signals: list[Signal] = field(default_factory=list)
    baselines: dict = field(default_factory=dict)
    window: dict = field(default_factory=dict)

    def to_dict(self):
        d = asdict(self)
        d["signals"] = [s.to_dict() for s in self.signals]
        return d


def _series(daily: list[dict], code: str) -> dict[date, float]:
    out: dict[date, float] = {}
    for row in daily:
        if row["code"] == code and row.get("value") is not None:
            d = date.fromisoformat(str(row["day"])[:10])
            out[d] = float(row["value"])
    return out


def _split(series: dict[date, float], end: date):
    win_start = end - timedelta(days=WINDOW_DAYS - 1)
    base_start = win_start - timedelta(days=BASELINE_DAYS)
    base = [v for d, v in series.items() if base_start <= d < win_start]
    window = sorted((d, v) for d, v in series.items() if win_start <= d <= end)
    return base, window


def _consecutive_tail(flags: list[bool]) -> int:
    n = 0
    for f in reversed(flags):
        if not f:
            break
        n += 1
    return n


def evaluate(daily: list[dict], checkins: list[dict], end: date | None = None, name: str = "Resident") -> TrendResult:
    """daily: [{day, code in (steps, rhr, sleep_min), value}]  — one row per day per code
    checkins: [{ts|day, ate_meals, slept_ok, dizzy, fell, confused, pain, note}]"""
    if end is None:
        days = [r["day"] for r in daily] + [c.get("day") or c.get("ts") for c in checkins]
        days = [date.fromisoformat(str(d)[:10]) for d in days if d]
        end = max(days) if days else date.today()
    signals: list[Signal] = []
    baselines, window_vals = {}, {}

    # --- Mobility: steps < 70% of baseline on >=3 days in the window (counting the tail run)
    steps = _series(daily, "steps")
    base, win = _split(steps, end)
    if len(base) >= 7 and win:
        b = median(base)
        baselines["steps"] = round(b)
        window_vals["steps"] = [round(v) for _, v in win]
        low = [v < 0.7 * b for _, v in win]
        if sum(low) >= 3:
            recent = [v for (_, v), l in zip(win, low) if l]
            drop = round(100 * (1 - (sum(recent) / len(recent)) / b))
            signals.append(Signal("mobility_down", "Mobility down",
                                  f"Steps {drop}% below {name.split()[0]}'s usual for {sum(low)} of the last {len(win)} days "
                                  f"(usual ~{round(b):,}/day, recently ~{round(sum(recent)/len(recent)):,}).",
                                  {"baseline": round(b), "recent_avg": round(sum(recent) / len(recent)), "days_low": sum(low), "drop_pct": drop},
                                  SUGGESTED_ACTIONS["mobility_down"]))

    # --- Resting HR: > baseline + 10 bpm on >=2 days
    rhr = _series(daily, "rhr")
    base, win = _split(rhr, end)
    if len(base) >= 7 and win:
        b = median(base)
        baselines["rhr"] = round(b)
        window_vals["rhr"] = [round(v) for _, v in win]
        high = [v > b + 10 for _, v in win]
        if sum(high) >= 2:
            peak = max(v for _, v in win)
            signals.append(Signal("rhr_up", "Resting heart rate up",
                                  f"Resting HR above usual by >10 bpm on {sum(high)} days (usual ~{round(b)}, peak {round(peak)}).",
                                  {"baseline": round(b), "peak": round(peak), "days_high": sum(high)},
                                  SUGGESTED_ACTIONS["rhr_up"]))

    # --- Sleep: < 75% of baseline on >=3 nights
    sleep = _series(daily, "sleep_min")
    base, win = _split(sleep, end)
    if len(base) >= 7 and win:
        b = median(base)
        baselines["sleep_min"] = round(b)
        window_vals["sleep_min"] = [round(v) for _, v in win]
        short = [v < 0.75 * b for _, v in win]
        if sum(short) >= 3:
            signals.append(Signal("sleep_down", "Sleep down",
                                  f"Slept under 75% of usual on {sum(short)} nights (usual ~{b/60:.1f} h).",
                                  {"baseline_min": round(b), "nights_short": sum(short)},
                                  SUGGESTED_ACTIONS["sleep_down"]))

    # --- Check-ins in the window
    win_start = end - timedelta(days=WINDOW_DAYS - 1)

    def cday(c):
        d = c.get("day") or c.get("ts")
        if hasattr(d, "hour"):          # datetime
            return d.date()
        return d if isinstance(d, date) else date.fromisoformat(str(d)[:10])

    recent = [c for c in checkins if win_start <= cday(c) <= end]
    skipped = [c for c in recent if c.get("ate_meals") is False]
    if len(skipped) >= 2:
        signals.append(Signal("intake_down", "Eating less",
                              f"Skipped meals reported on {len(skipped)} of the last {WINDOW_DAYS} days.",
                              {"days": [str(cday(c)) for c in skipped]}, SUGGESTED_ACTIONS["intake_down"]))
    confused = [c for c in recent if c.get("confused")]
    if confused:
        quote = next((c.get("note") for c in confused if c.get("note")), None)
        detail = f"Confusion reported on {', '.join(cday(c).strftime('%a %b %-d') for c in confused)}"
        detail += f' ("{quote}")' if quote else ""
        signals.append(Signal("cognition", "New confusion", detail + ".",
                              {"days": [str(cday(c)) for c in confused]}, SUGGESTED_ACTIONS["cognition"]))
    dizzy = [c for c in recent if c.get("dizzy") or c.get("fell")]
    if dizzy:
        fell = any(c.get("fell") for c in dizzy)
        signals.append(Signal("dizziness_or_fall", "Fall reported" if fell else "Dizziness reported",
                              f"{'A fall' if fell else 'Dizziness or unsteadiness'} reported on "
                              f"{', '.join(cday(c).strftime('%a %b %-d') for c in dizzy)}.",
                              {"days": [str(cday(c)) for c in dizzy], "fell": fell}, SUGGESTED_ACTIONS["dizziness_or_fall"]))
    pains = [c["pain"] for c in sorted(recent, key=cday) if c.get("pain") is not None]
    if len(pains) >= 2 and pains[-1] >= 6 and pains[-1] - pains[0] >= 3:
        signals.append(Signal("pain_up", "Pain rising", f"Pain score rose from {pains[0]} to {pains[-1]} out of 10.",
                              {"series": pains}, SUGGESTED_ACTIONS["pain_up"]))

    # --- Composite
    keys = {s.key for s in signals}
    risks = []
    if keys & {"mobility_down", "dizziness_or_fall", "cognition", "sleep_down"} and len(signals) >= 2:
        risks.append("falls")
    if "cognition" in keys and keys & {"intake_down", "rhr_up", "sleep_down", "mobility_down"}:
        risks.append("delirium")
    if "rhr_up" in keys and keys & {"intake_down", "cognition"}:
        risks.append("infection or dehydration")
    if "intake_down" in keys and "infection or dehydration" not in risks:
        risks.append("poor nutrition / hydration")

    if len(signals) >= 2:
        status = "alert"
        headline = "Early warning: " + (" and ".join(risks[:2]) if risks else "several changes at once") + " risk rising"
    elif signals:
        status = "watch"
        headline = f"Watch: {signals[0].label.lower()}"
    else:
        status = "ok"
        headline = "Stable"
    return TrendResult(status, headline, risks, signals, baselines,
                       {"start": str(win_start), "end": str(end), **{f"{k}_recent": v for k, v in window_vals.items()}})


def explain_offline(result: TrendResult, name: str) -> str:
    """Deterministic explanation used when Gemini is unavailable (and as Gemini's grounding)."""
    if result.status == "ok":
        return f"{name} is in line with their usual pattern over the last {WINDOW_DAYS} days."
    first = name.split()[0]
    parts = [s.detail.rstrip(".") for s in result.signals]
    parts = [p[0].lower() + p[1:] if p else p for p in parts]
    lead = f"{first} was flagged because: " + "; ".join(parts) + "."
    if result.risks:
        lead += f" Together these changes are associated with a higher short-term risk of {', '.join(result.risks)}."
    return lead
