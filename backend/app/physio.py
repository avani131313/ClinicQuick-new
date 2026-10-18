"""Home exercises a clinician assigns. The app's camera coach knows how to track each exercise key."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import db
from .auth import current_user, require_role

router = APIRouter()

CATALOG = {
    "squat": {"name": "Sit-to-stand squat", "target": "Legs and balance", "how": "Feet hip-width apart. Sit back as if into a chair, then stand tall."},
    "arm_raise": {"name": "Front arm raise", "target": "Shoulders", "how": "Arms straight, lift them in front of you to overhead, then lower slowly."},
    "knee_raise": {"name": "Standing knee raise", "target": "Hips and core", "how": "Stand tall and lift one knee to hip height, then the other."},
}
DEFAULTS = [("squat", 2, 10, "Use a chair behind you if you feel unsteady."), ("arm_raise", 2, 12, "Stop if your shoulder hurts."), ("knee_raise", 2, 10, None)]


def _clinician_for(pid: str) -> str:
    r = db.q1("""SELECT c.name FROM appointments a JOIN clinicians c ON c.user_id = a.clinician_id
                 WHERE a.patient_id=%s AND a.status <> 'cancelled' ORDER BY a.starts_at DESC LIMIT 1""", (pid,))
    return r["name"] if r else "Your clinician"


def plan(pid: str | None) -> list[dict]:
    if not pid:
        raise HTTPException(400, "Set up your profile first.")
    rows = db.q("SELECT id, exercise, sets, reps, notes, assigned_by, created_at FROM exercise_plans WHERE patient_id=%s AND active ORDER BY id", (pid,))
    if not rows and not db.q1("SELECT 1 FROM exercise_plans WHERE patient_id=%s", (pid,)):
        # demo: start everyone with a gentle plan from their clinician
        who = _clinician_for(pid)
        for ex, sets, reps, notes in DEFAULTS:
            db.exe("INSERT INTO exercise_plans (patient_id, exercise, sets, reps, notes, assigned_by) VALUES (%s,%s,%s,%s,%s,%s)", (pid, ex, sets, reps, notes, who))
        rows = db.q("SELECT id, exercise, sets, reps, notes, assigned_by, created_at FROM exercise_plans WHERE patient_id=%s AND active ORDER BY id", (pid,))
    out = []
    for r in rows:
        r = dict(r)
        r["created_at"] = r["created_at"].isoformat()
        r.update(CATALOG.get(r["exercise"], {"name": r["exercise"], "target": "", "how": ""}))
        out.append(r)
    return out


class ExerciseIn(BaseModel):
    exercise: str
    sets: int = Field(2, ge=1, le=10)
    reps: int = Field(10, ge=1, le=50)
    notes: str | None = None


@router.get("/physio")
def my_plan(user=Depends(current_user)):
    require_role(user, "patient")
    return {"plan": plan(user["pid"]), "catalog": CATALOG}


def _doctor(user: dict, pid: str) -> str:
    from .meds import _doctor as check
    return check(user, pid)


@router.get("/doctor/patients/{patient_id}/physio")
def patient_plan(patient_id: str, user=Depends(current_user)):
    _doctor(user, patient_id)
    return {"plan": plan(patient_id), "catalog": CATALOG}


@router.post("/doctor/patients/{patient_id}/physio")
def assign(patient_id: str, e: ExerciseIn, user=Depends(current_user)):
    who = _doctor(user, patient_id)
    if e.exercise not in CATALOG:
        raise HTTPException(400, "The camera coach doesn't know that exercise yet.")
    db.exe("INSERT INTO exercise_plans (patient_id, exercise, sets, reps, notes, assigned_by) VALUES (%s,%s,%s,%s,%s,%s)",
           (patient_id, e.exercise, e.sets, e.reps, e.notes, who))
    return {"plan": plan(patient_id), "catalog": CATALOG}


@router.post("/doctor/patients/{patient_id}/physio/{plan_id}/remove")
def remove(patient_id: str, plan_id: int, user=Depends(current_user)):
    _doctor(user, patient_id)
    db.exe("UPDATE exercise_plans SET active=false WHERE id=%s AND patient_id=%s", (plan_id, patient_id))
    return {"plan": plan(patient_id), "catalog": CATALOG}
