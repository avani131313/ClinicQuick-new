"""Care-team queries: Trend Watch over every resident, backed by the daily_obs rollup."""
from __future__ import annotations

from datetime import date, timedelta

from . import db, trendwatch
from .scores import age_from_dob

LOOKBACK_DAYS = 30
SUM_CODES = {"steps", "sleep_min", "active_kcal"}


def daily_series(patient_id: str, days: int = LOOKBACK_DAYS) -> list[dict]:
    rows = db.q("""SELECT code, day, sum_v, avg_v FROM daily_obs
                   WHERE patient_id = %s AND day >= now() - make_interval(days => %s)
                   ORDER BY day""", (patient_id, days))
    return [{"code": r["code"], "day": r["day"].date() if hasattr(r["day"], "date") else r["day"],
             "value": float(r["sum_v"] if r["code"] in SUM_CODES else r["avg_v"])} for r in rows]


def checkins(patient_id: str, days: int = LOOKBACK_DAYS) -> list[dict]:
    return db.q("""SELECT ts, ate_meals, slept_ok, dizzy, fell, confused, pain, note, recorded_by FROM checkins
                   WHERE patient_id = %s AND ts >= now() - make_interval(days => %s) ORDER BY ts""",
                (patient_id, days))


def resident_trend(patient: dict) -> dict:
    pid = str(patient["id"])
    daily = daily_series(pid)
    cks = checkins(pid)
    end = max([r["day"] for r in daily], default=date.today())
    res = trendwatch.evaluate(daily, cks, end=end, name=patient["name"])
    out = res.to_dict()
    out["explanation"] = trendwatch.explain_offline(res, patient["name"])
    out["series"] = _sparkline(daily)
    out["checkins"] = [{**c, "ts": c["ts"].isoformat()} for c in cks[-7:]]
    return out


def _sparkline(daily: list[dict], days: int = 21) -> dict:
    out: dict[str, list] = {}
    if not daily:
        return out
    end = max(r["day"] for r in daily)
    start = end - timedelta(days=days - 1)
    for r in daily:
        if r["day"] >= start:
            out.setdefault(r["code"], []).append({"day": str(r["day"]), "value": round(r["value"], 1)})
    return out


def facility_overview(facility: str | None = None) -> list[dict]:
    where, params = ("WHERE facility IS NOT NULL", ()) if not facility else ("WHERE facility = %s", (facility,))
    patients = db.q(f"SELECT id, name, dob, sex, facility, room FROM patients {where} ORDER BY name", params)
    rank = {"alert": 0, "watch": 1, "ok": 2}
    out = []
    for p in patients:
        t = resident_trend(p)
        out.append({"id": str(p["id"]), "name": p["name"], "age": age_from_dob(p["dob"]), "sex": p["sex"],
                    "room": p["room"], "facility": p["facility"], "status": t["status"], "headline": t["headline"],
                    "risks": t["risks"], "signal_labels": [s["label"] for s in t["signals"]],
                    "steps": t["series"].get("steps", [])})
    out.sort(key=lambda r: (rank[r["status"]], -len(r["signal_labels"]), r["name"]))
    return out
