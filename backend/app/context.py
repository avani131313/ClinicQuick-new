"""Builds the patient context every AI call and every rule sees, including the
structured 'context modifiers' that drive personalisation (age band, anticoagulant, etc.)."""
from __future__ import annotations

import time

from . import db, gemini
from .scores import age_from_dob

ANTICOAGULANTS = {"apixaban", "rivaroxaban", "dabigatran", "edoxaban", "warfarin", "heparin", "enoxaparin",
                  "eliquis", "xarelto", "pradaxa", "coumadin"}
ANTIPLATELETS = {"aspirin", "clopidogrel", "ticagrelor", "prasugrel", "asa"}
IMMUNOSUPPRESSANTS = {"prednisone", "methotrexate", "tacrolimus", "cyclosporine", "azathioprine", "mycophenolate"}


_CACHE: dict[str, tuple[float, dict]] = {}
_TTL = 300  # seconds; the profile rarely changes mid-interview, and Tiger is a network hop away


def invalidate(patient_id: str) -> None:
    _CACHE.pop(str(patient_id), None)


def load_patient(patient_id: str) -> dict | None:
    hit = _CACHE.get(str(patient_id))
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    ctx = _load_patient(patient_id)
    if ctx:
        _CACHE[str(patient_id)] = (time.time(), ctx)
    return ctx


def _load_patient(patient_id: str) -> dict | None:
    p = db.q1("SELECT * FROM patients WHERE id = %s", (patient_id,))
    if not p:
        return None
    prof = db.q1("SELECT * FROM profiles WHERE patient_id = %s", (patient_id,)) or {}
    conds = [r["name"] for r in db.q("SELECT name FROM conditions WHERE patient_id=%s AND status='active' ORDER BY id", (patient_id,))]
    meds = [f'{r["name"]}{" " + r["dose"] if r["dose"] else ""}' for r in db.q("""SELECT name, dose FROM medications WHERE patient_id=%s
                                                                                                AND (end_date IS NULL OR end_date >= current_date) ORDER BY id""", (patient_id,))]
    alls = [f'{r["substance"]}{" (" + r["reaction"] + ")" if r["reaction"] else ""}' for r in db.q("SELECT substance, reaction FROM allergies WHERE patient_id=%s", (patient_id,))]
    age = age_from_dob(p["dob"])
    profile = {k: v for k, v in prof.items() if k not in ("patient_id", "updated_at", "consent_at")}
    profile.update(age=age, sex=p["sex"])
    return {
        "id": str(p["id"]), "name": p["name"], "first_name": p["name"].split()[0], "dob": str(p["dob"]),
        "age": age, "sex": p["sex"], "facility": p["facility"], "room": p["room"],
        "profile": profile, "conditions": conds, "medications": meds, "allergies": alls,
        "wearables": wearable_summary(str(p["id"])),
    }


WEAR_LABELS = {"steps": ("steps/day", 0), "rhr": ("resting heart rate, bpm", 0), "sleep_min": ("sleep, hours/night", 1),
               "weight": ("weight, kg", 1), "spo2": ("blood oxygen, %", 0)}


def wearable_summary(patient_id: str) -> list[str]:
    """Last 7 days vs the 30 days before, per wearable metric (Apple Health / demo watch), as short facts
    the AI can use: 'steps/day: 3,100 last 7 days vs 8,400 usual (down 63%)'."""
    try:
        rows = db.q("""SELECT code,
                         avg(CASE WHEN code IN ('steps','sleep_min') THEN sum_v ELSE avg_v END)
                           FILTER (WHERE day >= now() - interval '7 days') AS recent,
                         avg(CASE WHEN code IN ('steps','sleep_min') THEN sum_v ELSE avg_v END)
                           FILTER (WHERE day < now() - interval '7 days') AS usual,
                         max(day) AS last_day
                       FROM daily_obs WHERE patient_id = %s AND day >= now() - interval '37 days'
                       GROUP BY code""", (patient_id,))
    except Exception:
        return []
    out = []
    for r in rows:
        if r["code"] not in WEAR_LABELS or r["recent"] is None:
            continue
        label, dp = WEAR_LABELS[r["code"]]
        k = 1 / 60 if r["code"] == "sleep_min" else 1
        rec = float(r["recent"]) * k
        line = f"{label}: {rec:,.{dp}f} last 7 days"
        if r["usual"]:
            usual = float(r["usual"]) * k
            line += f" vs {usual:,.{dp}f} usual"
            if usual:
                ch = (rec - usual) / usual * 100
                if abs(ch) >= 10:
                    line += f" ({'up' if ch > 0 else 'down'} {abs(ch):.0f}%)"
        out.append(line)
    return out


def modifiers(ctx: dict) -> list[dict]:
    """Facts that should move clinical considerations up or down. Computed by code, cited by the AI."""
    out = []
    age = ctx["age"]
    band = "child" if age < 13 else "adolescent" if age < 18 else "young adult" if age < 40 else "middle-aged adult" if age < 65 else "older adult"
    out.append({"key": "age", "value": f"{age} ({band})"})
    out.append({"key": "sex", "value": ctx["sex"]})
    meds_l = " ".join(ctx["medications"]).lower()
    if any(a in meds_l for a in ANTICOAGULANTS):
        out.append({"key": "anticoagulant", "value": "takes an anticoagulant (blood thinner)"})
    if any(a in meds_l for a in ANTIPLATELETS):
        out.append({"key": "antiplatelet", "value": "takes an antiplatelet"})
    if any(a in meds_l for a in IMMUNOSUPPRESSANTS):
        out.append({"key": "immunosuppressed", "value": "takes an immunosuppressant"})
    prof = ctx["profile"]
    if prof.get("smoking") in ("current", "former"):
        out.append({"key": "smoking", "value": f"{prof['smoking']} smoker"})
    if prof.get("pregnant"):
        out.append({"key": "pregnant", "value": "pregnant or may be pregnant"})
    if str(ctx.get("sex") or "").lower().startswith("f") and 10 <= (age or 0) <= 55 and not prof.get("pregnant"):
        lmp = prof.get("last_menstrual_period")
        out.append({"key": "menstruating_age",
                    "value": "female of menstruating age" + (f"; last period recorded as {lmp}" if lmp else "")})
    if prof.get("walking_aid"):
        out.append({"key": "mobility", "value": "uses a walking aid"})
    for c in ctx["conditions"]:
        out.append({"key": "condition", "value": c})
    for f in prof.get("family_history") or []:
        out.append({"key": "family_history", "value": f})
    return out


def memory(patient_id: str, query: str | None = None, k: int = 6) -> list[str]:
    """Patient memory: semantic search with pgvector on Tiger, recency otherwise."""
    if query and db.FEATURES.get("vector") and gemini.enabled():
        vecs = gemini.embed([query])
        if vecs:
            rows = db.q("""SELECT text, ts FROM memory_chunks WHERE patient_id = %s AND embedding IS NOT NULL
                           ORDER BY embedding <=> %s::vector LIMIT %s""", (patient_id, str(vecs[0]), k))
            if rows:
                return [r["text"] for r in rows]
    rows = db.q("SELECT text FROM memory_chunks WHERE patient_id = %s ORDER BY ts DESC LIMIT %s", (patient_id, k))
    return [r["text"] for r in rows]


def remember(patient_id: str, text: str, kind: str = "visit") -> None:
    if db.FEATURES.get("vector") and gemini.enabled():
        vecs = gemini.embed([text])
        if vecs:
            db.exe("INSERT INTO memory_chunks (patient_id, kind, text, embedding) VALUES (%s,%s,%s,%s::vector)",
                   (patient_id, kind, text, str(vecs[0])))
            return
    db.exe("INSERT INTO memory_chunks (patient_id, kind, text) VALUES (%s,%s,%s)", (patient_id, kind, text))


def compact(ctx: dict, mem: list[str]) -> dict:
    """What the AI sees. No name, no DOB — age and facts only."""
    prof = ctx["profile"]
    return {
        "age": ctx["age"], "sex": ctx["sex"],
        "height_cm": prof.get("height_cm"), "weight_kg": prof.get("weight_kg"),
        "conditions": ctx["conditions"], "medications": ctx["medications"], "allergies": ctx["allergies"],
        "smoking": prof.get("smoking"), "pregnant": prof.get("pregnant"),
        "last_menstrual_period": str(prof["last_menstrual_period"]) if prof.get("last_menstrual_period") else None,
        "family_history": prof.get("family_history") or [],
        "context_modifiers": modifiers(ctx),
        "wearable_trends": ctx.get("wearables") or [],
        "memory_from_past_visits": mem,
    }
