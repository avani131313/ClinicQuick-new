"""Walk-in clinics: nearby clinics with live-looking queues, and the person's place in line.

DEMO ONLY: clinics are invented and placed around wherever the person is; queue sizes and waits are
simulated from the time of day. A real version would read each clinic's queue system.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import db
from .auth import current_user, require_role

router = APIRouter()
TZ = ZoneInfo("America/Toronto")

NAMES = ["Bluebird Walk-in Clinic", "Cedarline Medical Centre", "Harbourview Health Walk-in", "Kestrel Family Clinic",
         "Northstar Walk-in", "Wren Street Medical", "Juniper Care Clinic"]
BLURBS = ["Family doctors and a nurse practitioner. Minor injuries, infections, prescription renewals.",
          "Walk-in and same-day appointments. On-site lab for blood work and urine tests.",
          "Busy downtown clinic. Strep and COVID swabs, stitches, sick notes.",
          "Small, quieter clinic. Good for chronic-condition follow-ups and medication questions.",
          "Evening and weekend hours. Pharmacy next door.",
          "Nurse practitioner led. Women's health, contraception, sexual health testing.",
          "Large clinic with X-ray on site. Sprains, suspected fractures, minor burns."]
HOURS = [(7, 23), (8, 21), (0, 24), (8, 22), (0, 24), (9, 21), (7, 23)]   # two run 24 hours


def clinics(lat: float, lng: float) -> list[dict]:
    la, ln = round(lat, 2), round(lng, 2)
    now = datetime.now(TZ)
    slot = now.hour * 6 + now.minute // 10            # queues change every 10 minutes
    out = []
    for i, name in enumerate(NAMES):
        r = random.Random(f"{la}:{ln}:{i}")
        # spread clinics around you: each gets its own slice of the compass and its own distance band,
        # so markers never pile on top of each other
        n = len(NAMES)
        base = random.Random(f"{la}:{ln}").uniform(0, 2 * math.pi)
        ang = base + (i / n) * 2 * math.pi + r.uniform(-0.25, 0.25)
        dist_km = 0.6 + (i * 3 % n) / n * 3.0 + r.uniform(0, 0.35)
        clat = lat + (dist_km / 111) * math.cos(ang)
        clng = lng + (dist_km / (111 * math.cos(math.radians(lat)))) * math.sin(ang)
        open_h, close_h = HOURS[i]
        hour = now.hour + now.minute / 60
        is_open = open_h <= hour < close_h
        doctors = 1 + (i % 3 == 0) + (i == 6)
        mpp = r.uniform(9, 15)
        busy = math.exp(-((hour - 11) / 2.5) ** 2) + 0.8 * math.exp(-((hour - 18) / 2) ** 2) + 0.25
        q = random.Random(f"{la}:{ln}:{i}:{now.date()}:{slot}")
        waiting = max(0, round((busy * r.uniform(5, 13) + q.uniform(-2, 2)))) if is_open else 0
        wait = math.ceil(waiting / doctors) * mpp
        out.append({
            "id": f"{la}:{ln}:{i}", "name": name, "lat": clat, "lng": clng, "distance_km": round(dist_km, 1),
            "walk_min": round(dist_km / 4.8 * 60), "drive_min": max(3, round(dist_km / 30 * 60 + 2)),
            "about": BLURBS[i], "open": is_open, "hours": "Open 24 hours" if close_h - open_h >= 24 else f"{_h(open_h)}–{_h(close_h)}",
            "doctors_on_shift": doctors if is_open else 0, "waiting": waiting, "minutes_per_patient": round(mpp, 1),
            "wait_min": round(wait), "clear_by": _clock(now.timestamp() + wait * 60) if is_open else None,
        })
    out.sort(key=lambda c: (not c["open"], c["distance_km"]))
    return out


def _h(h: int) -> str:
    h %= 24
    return f"{h % 12 or 12} {'a.m.' if h < 12 else 'p.m.'}"


def _clock(ts: float) -> str:
    return datetime.fromtimestamp(ts, TZ).strftime("%-I:%M %p").lower().replace("am", "a.m.").replace("pm", "p.m.")


def position(w: dict) -> dict:
    elapsed = (datetime.now(timezone.utc) - w["joined_at"]).total_seconds() / 60
    seen = int(elapsed / w["minutes_per_patient"])
    ahead = max(0, w["ahead_at_join"] - seen)
    eta = round(ahead * w["minutes_per_patient"] + (w["minutes_per_patient"] - elapsed % w["minutes_per_patient"]) * (ahead > 0))
    total = max(1, w["ahead_at_join"])
    return {"ahead": ahead, "eta_min": max(0, eta), "progress": round(min(1, (total - ahead) / total), 3),
            "elapsed_min": round(elapsed), "called": ahead == 0}


@router.get("/walkin/clinics")
def nearby(lat: float, lng: float, user=Depends(current_user)):
    return {"clinics": clinics(lat, lng), "simulated": True}


class Join(BaseModel):
    clinic_id: str


@router.post("/walkin/checkin")
def join(b: Join, user=Depends(current_user)):
    require_role(user, "patient")
    try:
        la, ln, i = b.clinic_id.split(":")
        c = next(x for x in clinics(float(la), float(ln)) if x["id"] == b.clinic_id)
    except Exception:
        raise HTTPException(404, "Clinic not found")
    if not c["open"]:
        raise HTTPException(400, f"{c['name']} is closed right now ({c['hours']}).")
    db.exe("UPDATE walkin_checkins SET status='left' WHERE patient_id=%s AND status='waiting'", (user["pid"],))
    db.exe("""INSERT INTO walkin_checkins (patient_id, clinic_id, clinic_name, ahead_at_join, minutes_per_patient)
              VALUES (%s,%s,%s,%s,%s)""", (user["pid"], c["id"], c["name"], c["waiting"],
                                           c["minutes_per_patient"] / max(1, c["doctors_on_shift"])))
    return me(user)


@router.get("/walkin/me")
def me(user=Depends(current_user)):
    require_role(user, "patient")
    w = db.q1("SELECT * FROM walkin_checkins WHERE patient_id=%s AND status='waiting' ORDER BY joined_at DESC LIMIT 1", (user["pid"],))
    if not w:
        return {"checked_in": False}
    enc = db.q1("""SELECT e.id, e.chief_complaint FROM encounters e JOIN reports r ON r.encounter_id = e.id
                   WHERE e.patient_id=%s ORDER BY e.started_at DESC LIMIT 1""", (user["pid"],))
    return {"checked_in": True, "clinic_id": w["clinic_id"], "clinic_name": w["clinic_name"],
            "joined_at": w["joined_at"].isoformat(), "ahead_at_join": w["ahead_at_join"], **position(w),
            "latest_summary": {"id": str(enc["id"]), "complaint": enc["chief_complaint"]} if enc else None}


@router.post("/walkin/leave")
def leave(user=Depends(current_user)):
    require_role(user, "patient")
    db.exe("UPDATE walkin_checkins SET status='left' WHERE patient_id=%s AND status='waiting'", (user["pid"],))
    return {"checked_in": False}
