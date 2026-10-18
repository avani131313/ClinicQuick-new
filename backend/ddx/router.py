"""DDX endpoints. Rankings are clinician-only; patients can only upload Samsung Health data."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app import db
from app.accounts import _doctor_can_see
from app.auth import current_user, require_role

from . import runtime, samsung, service

router = APIRouter(prefix="/ddx", tags=["ddx"])


def _audit(actor: str, action: str, patient_id: str | None, detail: dict):
    db.exe("INSERT INTO audit_log (actor, action, patient_id, detail) VALUES (%s,%s,%s,%s)",
           (actor, action, patient_id, db.J(detail)))


@router.get("/status")
def status():
    ok = runtime.available()
    return {"model_loaded": ok, "conditions": len(runtime.labels()) if ok else 0}


@router.get("/doctor/encounters/{encounter_id}")
def doctor_ranking(encounter_id: str, refresh: bool = False, user=Depends(current_user)):
    """Top 5 with probabilities, for the clinician linked to this encounter's appointment."""
    a = _doctor_can_see(user, encounter_id)
    _audit(user["uid"], "ddx_viewed", str(a["patient_id"]), {"encounter": encounter_id})
    try:
        return service.compute(encounter_id, force=refresh)
    except LookupError:
        raise HTTPException(404, "Intake not found")


@router.get("/share/{token}")
def share_ranking(token: str):
    """Same panel for the no-login clinician share link."""
    s = db.q1("SELECT * FROM shares WHERE token = %s", (token,))
    if not s or s["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(404, "This link has expired or doesn't exist.")
    _audit("clinician-link", "ddx_viewed", str(s["patient_id"]), {"encounter": str(s["encounter_id"])})
    return service.compute(str(s["encounter_id"]))


@router.post("/wearables/samsung")
async def samsung_upload(file: UploadFile = File(...), user=Depends(current_user)):
    """Patient uploads a Samsung Health export (.zip of CSVs). Stored like Apple Health data."""
    require_role(user, "patient")
    if not user.get("pid"):
        raise HTTPException(400, "No patient profile on this account")
    try:
        return samsung.import_export(user["pid"], await file.read())
    except ValueError as e:
        raise HTTPException(400, str(e))
