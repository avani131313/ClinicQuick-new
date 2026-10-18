"""In-app notifications, computed from what already exists: upcoming visits, new bookings,
records a clinician added, and the person's place in a walk-in queue. Read/unread lives in the browser."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends

from . import db
from .auth import current_user

router = APIRouter()
TZ = ZoneInfo("America/Toronto")


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _when(ts: datetime) -> str:
    t = ts.astimezone(TZ)
    now = datetime.now(TZ)
    day = "today" if t.date() == now.date() else "tomorrow" if t.date() == (now + timedelta(days=1)).date() else t.strftime("%a, %b %-d")
    return f"{day} at {t.strftime('%-I:%M %p').lower().replace('am', 'a.m.').replace('pm', 'p.m.')}"


@router.get("/notifications")
def notifications(user=Depends(current_user)):
    now = datetime.now(timezone.utc)
    out: list[dict] = []
    if user["role"] == "patient" and user.get("pid"):
        pid = user["pid"]
        for a in db.q("""SELECT a.id, a.starts_at, a.created_at, a.encounter_id, c.name AS doc, c.clinic
                         FROM appointments a JOIN clinicians c ON c.user_id = a.clinician_id
                         WHERE a.patient_id=%s AND a.status='booked' AND a.starts_at > now()
                         ORDER BY a.starts_at""", (pid,)):
            soon = a["starts_at"] - now
            if soon <= timedelta(days=7):
                out.append({"id": f"remind-{a['id']}-{min(2, soon.days)}", "kind": "reminder", "urgent": soon <= timedelta(hours=24),
                            "title": f"Visit {_when(a['starts_at'])}", "ts": (a["starts_at"] - timedelta(days=min(7, soon.days + 1))).isoformat(),
                            "body": f"With {a['doc']}, {a['clinic']}. " + ("Your intake summary is already attached."
                                     if a["encounter_id"] else "A quick check-in before you go saves time in the room."),
                            "href": "/appointments", "at": a["starts_at"].isoformat()})
            if now - a["created_at"] <= timedelta(days=14):
                out.append({"id": f"booked-{a['id']}", "kind": "confirm", "title": "Appointment booked",
                            "body": f"{_cap(_when(a['starts_at']))} with {a['doc']}.", "ts": a["created_at"].isoformat(),
                            "href": "/appointments"})
        for d in db.q("""SELECT id, filename, uploaded_by, ts FROM documents WHERE patient_id=%s AND uploaded_by <> 'patient'
                         AND kind <> 'interview-media' AND ts > now() - interval '30 days' ORDER BY ts DESC""", (pid,)):
            out.append({"id": f"doc-{d['id']}", "kind": "record", "title": "New record in your file",
                        "body": f"{d['uploaded_by']} added {d['filename']}.", "ts": d["ts"].isoformat(), "href": "/vault"})
        w = db.q1("SELECT * FROM walkin_checkins WHERE patient_id=%s AND status='waiting' ORDER BY joined_at DESC LIMIT 1", (pid,))
        if w:
            from .walkin import position
            p = position(w)
            out.append({"id": f"walkin-{w['id']}-{p['ahead']}", "kind": "queue", "urgent": p["ahead"] <= 1,
                        "title": "You're next" if p["ahead"] == 0 else f"{p['ahead']} ahead of you",
                        "body": f"{w['clinic_name']}. About {p['eta_min']} min.", "ts": now.isoformat(), "href": "/care-now"})
    elif user["role"] == "clinician":
        for a in db.q("""SELECT a.id, a.starts_at, a.created_at, a.encounter_id, p.name FROM appointments a
                         JOIN patients p ON p.id = a.patient_id
                         WHERE a.clinician_id=%s AND a.status='booked' AND a.starts_at > now() ORDER BY a.starts_at""", (user["uid"],)):
            soon = a["starts_at"] - now
            if soon <= timedelta(days=7):
                out.append({"id": f"remind-{a['id']}-{min(2, soon.days)}", "kind": "reminder", "urgent": soon <= timedelta(hours=24),
                            "title": f"{a['name']}, {_when(a['starts_at'])}",
                            "body": "Intake summary ready." if a["encounter_id"] else "No check-in yet.",
                            "ts": (a["starts_at"] - timedelta(days=min(7, soon.days + 1))).isoformat(), "href": "/doctor",
                            "at": a["starts_at"].isoformat()})
            if now - a["created_at"] <= timedelta(days=7):
                out.append({"id": f"booked-{a['id']}", "kind": "confirm", "title": "New booking",
                            "body": f"{a['name']} booked {_when(a['starts_at'])}", "ts": a["created_at"].isoformat(), "href": "/doctor"})
    out.sort(key=lambda n: n["ts"], reverse=True)
    return out
