"""Medicines: what the person takes now, what they took before, with doses, dates and reasons."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db
from .auth import current_user, require_role

router = APIRouter()
FIELDS = "id, name, dose, frequency, route, reason, prescriber, start_date, end_date, stop_reason, notes, source"


def history(patient_id: str) -> dict:
    rows = db.q(f"SELECT {FIELDS} FROM medications WHERE patient_id=%s ORDER BY start_date NULLS LAST, id", (patient_id,))
    today = date.today()
    out = []
    for r in rows:
        r = dict(r)
        r["active"] = r["end_date"] is None or r["end_date"] >= today
        for k in ("start_date", "end_date"):
            r[k] = r[k].isoformat() if r[k] else None
        out.append(r)
    return {"current": [r for r in out if r["active"]], "previous": [r for r in out if not r["active"]][::-1], "all": out}


class MedIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    dose: str | None = None
    frequency: str | None = None
    route: str | None = None
    reason: str | None = None
    start_date: date | None = None
    notes: str | None = None


class StopIn(BaseModel):
    end_date: date | None = None
    stop_reason: str | None = None


def _add(pid: str, m: MedIn, source: str, prescriber: str | None):
    db.exe("""INSERT INTO medications (patient_id, name, dose, frequency, route, reason, prescriber, start_date, notes, source)
              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
           (pid, m.name.strip(), m.dose, m.frequency, m.route, m.reason, prescriber, m.start_date or date.today(), m.notes, source))
    from .context import invalidate
    invalidate(pid)


def _stop(pid: str, med_id: int, s: StopIn):
    db.exe("UPDATE medications SET end_date=%s, stop_reason=%s WHERE id=%s AND patient_id=%s",
           (s.end_date or date.today(), s.stop_reason, med_id, pid))
    from .context import invalidate
    invalidate(pid)


@router.get("/medications")
def my_meds(user=Depends(current_user)):
    require_role(user, "patient")
    return history(user["pid"])


@router.post("/medications")
def add_my_med(m: MedIn, user=Depends(current_user)):
    require_role(user, "patient")
    _add(user["pid"], m, "tracked", "Self-reported")
    return history(user["pid"])


@router.post("/medications/{med_id}/stop")
def stop_my_med(med_id: int, s: StopIn, user=Depends(current_user)):
    require_role(user, "patient")
    _stop(user["pid"], med_id, s)
    return history(user["pid"])


def _doctor(user: dict, patient_id: str) -> str:
    from .accounts import _is_my_patient
    require_role(user, "clinician")
    if not _is_my_patient(user, patient_id):
        raise HTTPException(403, "This patient hasn't booked with you.")
    c = db.q1("SELECT name FROM clinicians WHERE user_id=%s", (user["uid"],))
    return c["name"] if c else "Clinician"


@router.get("/doctor/patients/{patient_id}/medications")
def patient_meds(patient_id: str, user=Depends(current_user)):
    _doctor(user, patient_id)
    return history(patient_id)


@router.post("/doctor/patients/{patient_id}/medications")
def prescribe(patient_id: str, m: MedIn, user=Depends(current_user)):
    name = _doctor(user, patient_id)
    _add(patient_id, m, "clinician", name)
    return history(patient_id)


@router.post("/doctor/patients/{patient_id}/medications/{med_id}/stop")
def doctor_stop(patient_id: str, med_id: int, s: StopIn, user=Depends(current_user)):
    _doctor(user, patient_id)
    _stop(patient_id, med_id, s)
    return history(patient_id)
