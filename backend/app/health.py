"""One payload for every health dashboard (patient's own and the clinician's patient view)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import care, db, synthetic

LABELS = {
    "steps": ("Steps", "", 0), "active_kcal": ("Active energy", "kcal", 0), "rhr": ("Resting heart rate", "bpm", 0),
    "hrv": ("Heart rate variability", "ms", 0), "spo2": ("Blood oxygen", "%", 0), "resp_rate": ("Respiratory rate", "/min", 1),
    "sleep_min": ("Sleep", "h", 1), "weight": ("Weight", "kg", 1), "bp_sys": ("Systolic", "mmHg", 0), "bp_dia": ("Diastolic", "mmHg", 0),
}


def payload(patient_id: str, days: int = 30) -> dict:
    daily = care.daily_series(patient_id, days)
    series: dict[str, list] = {}
    for r in daily:
        if r["code"] in LABELS:
            series.setdefault(r["code"], []).append({"day": str(r["day"]), "value": round(r["value"], 1)})
    latest = {}
    for r in db.q("""SELECT DISTINCT ON (code) code, ts, value, source FROM observations
                     WHERE patient_id = %s AND code = ANY(%s) ORDER BY code, ts DESC""", (patient_id, list(LABELS) + ["hr"])):
        latest[r["code"]] = {"value": round(float(r["value"]), 1), "ts": r["ts"].isoformat(), "source": r["source"]}
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    hr = db.q("""SELECT ts, value, source FROM observations WHERE patient_id = %s AND code = 'hr' AND ts >= %s
                 ORDER BY ts""", (patient_id, since))
    labs = db.q("""SELECT DISTINCT ON (code) code, ts, value, unit FROM observations
                   WHERE patient_id = %s AND code LIKE 'lab:%%' ORDER BY code, ts DESC""", (patient_id,))
    conn = synthetic.connections(patient_id)
    return {
        "series": series,
        "latest": latest,
        "hr_today": [{"ts": r["ts"].isoformat(), "value": round(float(r["value"]))} for r in hr],
        "hr_source": hr[-1]["source"] if hr else None,
        "labs": [{"test": r["code"][4:], "value": float(r["value"]), "unit": r["unit"], "ts": r["ts"].isoformat()} for r in labs],
        "connections": conn,
        "has_data": bool(series or latest),
        "labels": {k: {"label": v[0], "unit": v[1], "dp": v[2]} for k, v in LABELS.items()},
    }
