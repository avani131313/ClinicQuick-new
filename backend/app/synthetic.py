"""Synthetic wearable data for a patient who has no watch connected (the "populate" / sample-data buttons).

Generates what an Apple Watch + phone would record, shaped to the person: steps (hourly), resting heart
rate, heart-rate variability, blood oxygen, respiratory rate, sleep, active energy, weight, home blood
pressure, and intraday heart rate every 5 minutes for the last three days (drives the live heart trace).
"""
from __future__ import annotations

import math
import random
from datetime import datetime, time, timedelta, timezone

from . import db
from .scores import age_from_dob

TZ = timezone(timedelta(hours=-4))
CODES = ("steps", "rhr", "sleep_min", "weight", "spo2", "hrv", "resp_rate", "active_kcal", "bp_sys", "bp_dia", "hr")


def _person(patient_id: str) -> dict:
    p = db.q1("SELECT dob, sex FROM patients WHERE id = %s", (patient_id,)) or {}
    prof = db.q1("SELECT weight_kg, high_bp FROM profiles WHERE patient_id = %s", (patient_id,)) or {}
    conds = " ".join(r["name"].lower() for r in db.q("SELECT name FROM conditions WHERE patient_id=%s AND status='active'", (patient_id,)))
    age = age_from_dob(p["dob"]) if p.get("dob") else 40
    return {"age": age, "sex": p.get("sex") or "female", "weight": prof.get("weight_kg"),
            "af": "atrial fibrillation" in conds or "afib" in conds,
            "htn": bool(prof.get("high_bp")) or "hypertension" in conds or "blood pressure" in conds}


def demo_wearables(patient_id: str, days: int = 45, seed: int | None = None) -> int:
    who = _person(patient_id)
    rng = random.Random(seed or hash(patient_id) % 10_000)
    now = datetime.now(TZ)
    today = now.date()
    older = who["age"] >= 60
    base_steps = rng.randint(4200, 6500) if older else rng.randint(6500, 10500)
    base_rhr = rng.randint(64, 74) if older else rng.randint(56, 68)
    base_hrv = rng.randint(22, 34) if older else rng.randint(42, 70)
    base_sleep = rng.randint(390, 450)
    base_kg = float(who["weight"] or (82 if who["sex"] == "male" else 64))
    sys0, dia0 = (136, 84) if who["htn"] else (rng.randint(112, 122), rng.randint(70, 78))
    rows: list[tuple] = []
    # never double up on a metric the person already gets from a real source (Apple Health, seed data)
    have = {r["code"] for r in db.q("""SELECT DISTINCT code FROM observations WHERE patient_id = %s
                                         AND source <> 'demo-wearable' AND ts >= now() - interval '45 days'""", (patient_id,))}

    def add(ts: datetime, code: str, v: float, unit: str):
        if code not in have:
            rows.append((patient_id, ts, code, round(v, 1), unit, "demo-wearable"))

    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        weekend = d.weekday() >= 5
        day_steps = base_steps * rng.uniform(0.72, 1.22) * (0.85 if weekend else 1.0)
        hours = list(range(7, 22))
        weights = [rng.uniform(0.4, 1.6) * (1.8 if h in (8, 12, 17, 18) else 1) for h in hours]
        tot = sum(weights)
        for h, w in zip(hours, weights):
            ts = datetime.combine(d, time(h, rng.randint(0, 59)), TZ)
            if ts <= now:
                add(ts, "steps", round(day_steps * w / tot), "count")
        add(datetime.combine(d, time(6, 30), TZ), "rhr", base_rhr + rng.randint(-3, 3), "bpm")
        add(datetime.combine(d, time(6, 35), TZ), "hrv", base_hrv * rng.uniform(.8, 1.2), "ms")
        add(datetime.combine(d, time(6, 40), TZ), "spo2", rng.uniform(95.2, 98.8) - (0.6 if older else 0), "%")
        add(datetime.combine(d, time(6, 45), TZ), "resp_rate", rng.uniform(13, 16.5), "breaths/min")
        add(datetime.combine(d, time(7, 0), TZ), "sleep_min", base_sleep * rng.uniform(0.85, 1.08) * (1.06 if weekend else 1), "min")
        if d < today or now.hour >= 20:
            add(datetime.combine(d, time(21, 30), TZ), "active_kcal", day_steps * 0.045 * rng.uniform(.85, 1.15), "kcal")
        if i % 7 == 0:
            add(datetime.combine(d, time(7, 15), TZ), "weight", base_kg + rng.uniform(-0.6, 0.6), "kg")
        if i % 3 == 0 or (who["htn"] and i % 2 == 0):
            add(datetime.combine(d, time(8, 0), TZ), "bp_sys", sys0 + rng.randint(-7, 7), "mmHg")
            add(datetime.combine(d, time(8, 0), TZ), "bp_dia", dia0 + rng.randint(-5, 5), "mmHg")

    # intraday heart rate, every 5 minutes, last 3 days up to now
    t = (now - timedelta(days=3)).replace(second=0, microsecond=0)
    t -= timedelta(minutes=t.minute % 5)
    while t <= now:
        h = t.hour + t.minute / 60
        asleep = h < 6.5 or h >= 23
        level = base_rhr - 4 if asleep else base_rhr + 9 + 6 * math.sin((h - 7) / 15 * math.pi)
        if not asleep and rng.random() < 0.05:
            level += rng.uniform(20, 45)            # a brisk walk or stairs
        level += rng.gauss(0, 7 if who["af"] else 2.5)
        add(t, "hr", max(45, level), "bpm")
        t += timedelta(minutes=5)

    db.exe("DELETE FROM observations WHERE patient_id = %s AND source = 'demo-wearable'", (patient_id,))
    with db.conn() as c:
        with c.cursor().copy("COPY observations (patient_id, ts, code, value, unit, source) FROM STDIN") as cp:
            for r in rows:
                cp.write_row(r)
    db.refresh_daily_obs()
    return len(rows)


def connections(patient_id: str) -> dict:
    rows = db.q("""SELECT source, count(*) AS n, max(ts) AS last, array_agg(DISTINCT code) AS codes FROM observations
                   WHERE patient_id = %s AND code = ANY(%s) GROUP BY source""", (patient_id, list(CODES)))
    out = {r["source"]: {"readings": r["n"], "last": r["last"].isoformat(), "codes": sorted(r["codes"] or [])} for r in rows}
    return {"apple_health": out.get("apple-health"), "demo": out.get("demo-wearable"),
            "other": {k: v for k, v in out.items() if k not in ("apple-health", "demo-wearable")}}
