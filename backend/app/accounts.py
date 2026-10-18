"""v2 endpoints: register as patient or doctor, editable profile, doctors + appointment booking,
doctor views of booked intakes, and photo/video in the interview."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from . import db, gemini, health, report, scores, synthetic, tts, vault
from .auth import current_user, hash_password, make_token, read_token, require_role

router = APIRouter()
TZ = ZoneInfo("America/Toronto")


def audit(actor, action, patient_id, detail=None):
    db.exe("INSERT INTO audit_log (actor, action, patient_id, detail) VALUES (%s,%s,%s,%s)",
           (actor, action, patient_id, db.J(detail or {})))


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------
class Register(BaseModel):
    role: str = Field(pattern="^(patient|clinician)$")
    email: str
    password: str = Field(min_length=6)
    name: str | None = None
    clinic: str | None = None
    specialty: str | None = None
    city: str | None = None


@router.post("/auth/register")
def register(r: Register):
    email = r.email.strip().lower()
    if "@" not in email:
        raise HTTPException(400, "Enter a valid email address.")
    if db.q1("SELECT 1 FROM users WHERE email = %s", (email,)):
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    if r.role == "clinician" and not (r.name or "").strip():
        raise HTTPException(400, "Add your name as it should appear to patients.")
    u = db.q1("INSERT INTO users (email, password_hash, role, display_name) VALUES (%s,%s,%s,%s) RETURNING id",
              (email, hash_password(r.password), r.role, (r.name or "").strip() or None))
    uid = str(u["id"])
    if r.role == "clinician":
        db.exe("INSERT INTO clinicians (user_id, name, clinic, specialty, city) VALUES (%s,%s,%s,%s,%s)",
               (uid, r.name.strip(), r.clinic, r.specialty or "Family medicine", r.city or "Toronto"))
    audit(email, "register", None, {"role": r.role})
    return {"token": make_token(uid, r.role, None), "role": r.role, "patient_id": None,
            "name": r.name, "profile_complete": False if r.role == "patient" else True}


# ---------------------------------------------------------------------------
# Profile (create once, edit any time). Age is always computed from DOB.
# ---------------------------------------------------------------------------
class ProfileIn(BaseModel):
    name: str
    dob: date
    sex: str = Field(pattern="^(female|male|intersex)$")
    gender: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    waist_cm: float | None = None
    pregnant: bool | None = None
    last_menstrual_period: date | None = None
    blood_type: str | None = None
    conditions: list[str] = []
    mental_health_history: list[str] = []
    surgeries: list[str] = []
    hospitalized_past_year: bool | None = None
    medications: list[str] = []
    allergies: list[str] = []
    family_history: list[str] = []
    family_diabetes: list[str] = []
    smoking: str | None = None
    audit_c: list[int] | None = None
    recreational_drugs: str | None = None
    active_30min_daily: bool | None = None
    fruit_veg_daily: bool | None = None
    sleep_hours: float | None = None
    high_bp: bool | None = None
    high_blood_sugar: bool | None = None
    baby_over_4kg: bool | None = None
    parent_ethnicities: list[str] = []
    education: str | None = None
    occupation: str | None = None
    vaccines_up_to_date: str | None = None
    lives_alone: bool | None = None
    walking_aid: bool | None = None
    emergency_contact: str | None = None
    consent: bool = False


PROFILE_COLS = ["height_cm", "weight_kg", "waist_cm", "pregnant", "last_menstrual_period", "blood_type",
                "mental_health_history", "surgeries", "hospitalized_past_year", "family_history", "family_diabetes",
                "smoking", "audit_c", "recreational_drugs", "active_30min_daily", "fruit_veg_daily", "sleep_hours",
                "high_bp", "high_blood_sugar", "baby_over_4kg", "parent_ethnicities", "education", "occupation",
                "vaccines_up_to_date", "lives_alone", "walking_aid", "emergency_contact"]


def _write_lists(pid: str, p: ProfileIn):
    db.exe("DELETE FROM conditions WHERE patient_id = %s AND source = 'self'", (pid,))
    db.exe("DELETE FROM medications WHERE patient_id = %s AND source = 'self'", (pid,))
    db.exe("DELETE FROM allergies WHERE patient_id = %s AND source = 'self'", (pid,))
    for c in p.conditions:
        db.exe("INSERT INTO conditions (patient_id, name, source) VALUES (%s,%s,'self')", (pid, c))
    # medicines tracked elsewhere (history, clinician) come back in the profile list; don't duplicate them
    tracked = {(r["name"] + (f" {r['dose']}" if r["dose"] else "")).strip().lower() for r in db.q(
        "SELECT name, dose FROM medications WHERE patient_id=%s AND source <> 'self'", (pid,))}
    for m in p.medications:
        if m.strip().lower() not in tracked:
            db.exe("INSERT INTO medications (patient_id, name, source, start_date) VALUES (%s,%s,'self',current_date)", (pid, m))
    for a in p.allergies:
        db.exe("INSERT INTO allergies (patient_id, substance, source) VALUES (%s,%s,'self')", (pid, a))


def _check_dob(d: date):
    today = datetime.now(TZ).date()
    if d >= today:
        raise HTTPException(400, "Check your date of birth. It can't be today or in the future.")
    if (today - d).days > 120 * 366:
        raise HTTPException(400, "Check your date of birth. That's more than 120 years ago.")


@router.post("/profile")
def create_profile(p: ProfileIn, user=Depends(current_user)):
    require_role(user, "patient")
    _check_dob(p.dob)
    if user.get("pid"):
        raise HTTPException(409, "Your profile already exists — edit it from Profile.")
    if not p.consent:
        raise HTTPException(400, "Consent is required before we save your information.")
    row = db.q1("SELECT id FROM patients WHERE user_id = %s", (user["uid"],))
    if row:
        pid = str(row["id"])
    else:
        pid = str(db.q1("""INSERT INTO patients (user_id, name, dob, sex, gender, source) VALUES (%s,%s,%s,%s,%s,'app')
                           RETURNING id""", (user["uid"], p.name.strip(), p.dob, p.sex, p.gender))["id"])
    vals = [getattr(p, c) for c in PROFILE_COLS]
    db.exe(f"""INSERT INTO profiles (patient_id, {', '.join(PROFILE_COLS)}, consent_at)
               VALUES (%s, {', '.join(['%s'] * len(PROFILE_COLS))}, now())
               ON CONFLICT (patient_id) DO NOTHING""", [pid] + vals)
    db.exe("UPDATE users SET display_name = %s WHERE id = %s", (p.name.strip(), user["uid"]))
    _write_lists(pid, p)
    audit(user["uid"], "profile_created+consent", pid)
    return {"token": make_token(user["uid"], "patient", pid), "role": "patient", "patient_id": pid,
            "name": p.name, "profile_complete": True}


@router.put("/profile")
def update_profile(p: ProfileIn, user=Depends(current_user)):
    require_role(user, "patient")
    pid = user.get("pid")
    if not pid:
        raise HTTPException(404, "Set up your profile first.")
    _check_dob(p.dob)
    db.exe("UPDATE patients SET name=%s, dob=%s, sex=%s, gender=%s WHERE id=%s", (p.name.strip(), p.dob, p.sex, p.gender, pid))
    sets = ", ".join(f"{c} = %s" for c in PROFILE_COLS)
    db.exe(f"UPDATE profiles SET {sets}, updated_at = now() WHERE patient_id = %s",
           [getattr(p, c) for c in PROFILE_COLS] + [pid])
    _write_lists(pid, p)
    from .context import invalidate
    invalidate(pid)
    audit(user["uid"], "profile_updated", pid)
    return get_profile(user)


@router.get("/profile")
def get_profile(user=Depends(current_user)):
    require_role(user, "patient")
    pid = user.get("pid")
    if not pid:
        return {"complete": False}
    p = db.q1("SELECT * FROM patients WHERE id=%s", (pid,))
    prof = db.q1("SELECT * FROM profiles WHERE patient_id=%s", (pid,)) or {}
    out = {k: prof.get(k) for k in PROFILE_COLS}
    for k in ("last_menstrual_period",):
        out[k] = str(out[k]) if out[k] else None
    if out.get("audit_c"):
        out["audit_c"] = list(out["audit_c"])
    out.update(name=p["name"], dob=str(p["dob"]), sex=p["sex"], gender=p["gender"],
               conditions=[r["name"] for r in db.q("SELECT name FROM conditions WHERE patient_id=%s ORDER BY id", (pid,))],
               medications=[r["name"] + (f" {r['dose']}" if r["dose"] else "") for r in db.q(
                   "SELECT name, dose FROM medications WHERE patient_id=%s AND (end_date IS NULL OR end_date >= current_date) ORDER BY id", (pid,))],
               allergies=[r["substance"] for r in db.q("SELECT substance FROM allergies WHERE patient_id=%s ORDER BY id", (pid,))])
    age = scores.age_from_dob(p["dob"])
    updated = prof.get("updated_at")
    latest_w = db.q1("SELECT value, ts FROM observations WHERE patient_id=%s AND code='weight' ORDER BY ts DESC LIMIT 1", (pid,))
    return {"complete": True, "profile": out, "age": age,
            "updated_at": updated.isoformat() if updated else None,
            "needs_review": bool(updated and (datetime.now(timezone.utc) - updated).days > 180),
            "latest_weight_reading": {"kg": round(latest_w["value"], 1), "ts": latest_w["ts"].isoformat()} if latest_w else None}


# ---------------------------------------------------------------------------
# Doctors and booking
# ---------------------------------------------------------------------------
SLOT_MIN = 20
DAY_START, DAY_END = time(9, 0), time(17, 0)


def _slots(clinician_id: str, days: int = 5, earliest: datetime | None = None) -> list[str]:
    now = datetime.now(TZ)
    start = max(now, earliest or now) + timedelta(minutes=30)
    booked = {r["starts_at"].astimezone(TZ).replace(second=0, microsecond=0) for r in db.q(
        "SELECT starts_at FROM appointments WHERE clinician_id=%s AND status='booked' AND starts_at > now()", (clinician_id,))}
    out, d = [], start.date()
    while len(out) < 40 and (d - start.date()).days < 14:
        if d.weekday() < 5:
            t = datetime.combine(d, DAY_START, TZ)
            while t.time() < DAY_END:
                if t > start and t not in booked:
                    out.append(t.isoformat())
                t += timedelta(minutes=SLOT_MIN)
        d += timedelta(days=1)
        if len({s[:10] for s in out}) >= days:
            break
    return out


@router.get("/clinicians")
def clinicians(user=Depends(current_user)):
    rows = db.q("SELECT user_id, name, clinic, specialty, city FROM clinicians ORDER BY name")
    return [{"id": str(r["user_id"]), "name": r["name"], "clinic": r["clinic"], "specialty": r["specialty"],
             "city": r["city"], "slots": _slots(str(r["user_id"]))} for r in rows]


class Book(BaseModel):
    clinician_id: str
    starts_at: datetime
    encounter_id: str | None = None
    reason: str | None = Field(default=None, max_length=200)


@router.post("/appointments")
def book(b: Book, user=Depends(current_user)):
    require_role(user, "patient")
    pid = user.get("pid")
    if not pid:
        raise HTTPException(400, "Set up your profile first.")
    if not db.q1("SELECT 1 FROM clinicians WHERE user_id=%s", (b.clinician_id,)):
        raise HTTPException(404, "Clinician not found")
    reason = (b.reason or "").strip() or None
    if b.encounter_id:
        enc = db.q1("SELECT urgency, chief_complaint FROM encounters WHERE id=%s AND patient_id=%s", (b.encounter_id, pid))
        if not enc:
            raise HTTPException(404, "Check-in not found")
        if enc["urgency"] in ("er", "emergency_911"):
            raise HTTPException(409, "This needs emergency care, not an appointment. Call 911 or go to the nearest emergency department.")
        reason = enc["chief_complaint"]
    t = b.starts_at.astimezone(TZ) if b.starts_at.tzinfo else b.starts_at.replace(tzinfo=TZ)
    valid = (t > datetime.now(TZ) and t.weekday() < 5 and DAY_START <= t.time() < DAY_END
             and (t.hour * 60 + t.minute - DAY_START.hour * 60) % SLOT_MIN == 0 and t.second == 0)
    if not valid:
        raise HTTPException(400, "Pick one of the available times.")
    b.starts_at = t
    try:
        row = db.q1("""INSERT INTO appointments (patient_id, clinician_id, encounter_id, starts_at, minutes, reason)
                       VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (pid, b.clinician_id, b.encounter_id, b.starts_at, SLOT_MIN, reason))
    except Exception:
        raise HTTPException(409, "That time was just taken. Pick another one.")
    audit(user["uid"], "appointment_booked", pid, {"clinician": b.clinician_id, "encounter": b.encounter_id})
    return my_appointments(user)[0] if row else None


def _appt_rows(where: str, params) -> list[dict]:
    rows = db.q(f"""SELECT a.*, c.name AS clinician_name, c.clinic, c.specialty, p.name AS patient_name, p.dob, p.sex,
                           e.urgency, e.chief_complaint, r.clinician_json->>'one_liner' AS one_liner
                    FROM appointments a JOIN clinicians c ON c.user_id = a.clinician_id
                    JOIN patients p ON p.id = a.patient_id
                    LEFT JOIN encounters e ON e.id = a.encounter_id
                    LEFT JOIN reports r ON r.encounter_id = a.encounter_id
                    WHERE {where} ORDER BY a.starts_at""", params)
    return [{"id": str(r["id"]), "starts_at": r["starts_at"].isoformat(), "minutes": r["minutes"], "status": r["status"],
             "clinician": {"id": str(r["clinician_id"]), "name": r["clinician_name"], "clinic": r["clinic"], "specialty": r["specialty"]},
             "patient": {"id": str(r["patient_id"]), "name": r["patient_name"], "age": scores.age_from_dob(r["dob"]), "sex": r["sex"]},
             "encounter_id": str(r["encounter_id"]) if r["encounter_id"] else None,
             "reason": r["reason"] or r["chief_complaint"], "urgency": r["urgency"], "one_liner": r["one_liner"]} for r in rows]


@router.get("/appointments")
def my_appointments(user=Depends(current_user)):
    require_role(user, "patient")
    return list(reversed(_appt_rows("a.patient_id = %s AND a.status <> 'cancelled'", (user.get("pid"),))))


@router.post("/appointments/{appt_id}/cancel")
def cancel(appt_id: str, user=Depends(current_user)):
    require_role(user, "patient")
    db.exe("UPDATE appointments SET status='cancelled' WHERE id=%s AND patient_id=%s", (appt_id, user.get("pid")))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Doctor views
# ---------------------------------------------------------------------------
@router.get("/doctor/me")
def doctor_me(user=Depends(current_user)):
    require_role(user, "clinician")
    c = db.q1("SELECT * FROM clinicians WHERE user_id=%s", (user["uid"],))
    return {"name": c["name"] if c else None, "clinic": c and c["clinic"], "specialty": c and c["specialty"]}


@router.get("/doctor/appointments")
def doctor_appointments(user=Depends(current_user)):
    require_role(user, "clinician")
    return _appt_rows("a.clinician_id = %s AND a.status IN ('booked','completed')", (user["uid"],))


def _is_my_patient(user: dict, patient_id: str) -> bool:
    return bool(db.q1("SELECT 1 FROM appointments WHERE clinician_id=%s AND patient_id=%s AND status <> 'cancelled'",
                      (user["uid"], patient_id)))


def _doctor_can_see(user: dict, encounter_id: str) -> dict:
    """A doctor can open any intake of a patient who has booked with them (their care relationship)."""
    require_role(user, "clinician")
    a = db.q1("SELECT patient_id FROM encounters WHERE id=%s", (encounter_id,))
    if not a or not _is_my_patient(user, str(a["patient_id"])):
        raise HTTPException(403, "This intake belongs to someone who hasn't booked with you.")
    return a


@router.get("/doctor/patients/{patient_id}")
def doctor_patient(patient_id: str, user=Depends(current_user)):
    """Everything a doctor needs before the visit: profile, medicines, trends, and every past check-in."""
    require_role(user, "clinician")
    if not _is_my_patient(user, patient_id):
        raise HTTPException(403, "This patient hasn't booked with you.")
    from . import care
    from .context import load_patient, modifiers
    ctx = load_patient(patient_id)
    if not ctx:
        raise HTTPException(404)
    visits = db.q("""SELECT e.id, e.started_at, e.chief_complaint, e.urgency, e.status,
                            r.clinician_json->>'one_liner' AS one_liner
                     FROM encounters e LEFT JOIN reports r ON r.encounter_id = e.id
                     WHERE e.patient_id=%s AND e.status <> 'active' ORDER BY e.started_at DESC""", (patient_id,))
    notes = db.q("""SELECT text FROM memory_chunks WHERE patient_id=%s AND kind IN ('clinician_note','history','visit')
                    ORDER BY ts DESC LIMIT 12""", (patient_id,))
    prof = ctx["profile"]
    audit(user["uid"], "doctor_viewed_patient", patient_id, {})
    return {
        "patient": {"id": ctx["id"], "name": ctx["name"], "age": ctx["age"], "sex": ctx["sex"], "dob": ctx["dob"]},
        "conditions": ctx["conditions"], "medications": ctx["medications"], "allergies": ctx["allergies"],
        "social": {"smoking": prof.get("smoking"), "occupation": prof.get("occupation")},
        "family_history": prof.get("family_history") or [],
        "context_modifiers": modifiers(ctx),
        "wearables": ctx.get("wearables") or [],
        "trends": care._sparkline(care.daily_series(patient_id, 30), 30),
        "visits": [{"id": str(v["id"]), "date": v["started_at"].isoformat(), "complaint": v["chief_complaint"],
                    "urgency": v["urgency"], "status": v["status"], "one_liner": v["one_liner"]} for v in visits],
        "appointments": _appt_rows("a.clinician_id = %s AND a.patient_id = %s AND a.status <> 'cancelled'",
                                   (user["uid"], patient_id)),
        "notes": [n["text"] for n in notes],
        "documents": [d for d in vault.list_documents(patient_id) if d["kind"] != "interview-media"],
    }


@router.get("/doctor/patients")
def doctor_patient_list(user=Depends(current_user)):
    """Everyone who has booked with this clinician, soonest upcoming visit first."""
    require_role(user, "clinician")
    rows = db.q("""SELECT p.id, p.name, p.dob, p.sex,
                          min(a.starts_at) FILTER (WHERE a.status='booked' AND a.starts_at >= now() - interval '30 minutes') AS next_at,
                          max(a.starts_at) FILTER (WHERE a.starts_at < now()) AS last_at,
                          count(*) AS visits
                   FROM appointments a JOIN patients p ON p.id = a.patient_id
                   WHERE a.clinician_id = %s AND a.status <> 'cancelled'
                   GROUP BY p.id ORDER BY min(a.starts_at) FILTER (WHERE a.status='booked' AND a.starts_at >= now() - interval '30 minutes') NULLS LAST, p.name""",
                (user["uid"],))
    out = []
    for r in rows:
        pid = str(r["id"])
        conds = [c["name"] for c in db.q("SELECT name FROM conditions WHERE patient_id=%s AND status='active' ORDER BY id", (pid,))]
        has = bool(db.q1("SELECT 1 FROM observations WHERE patient_id=%s AND code IN ('steps','rhr','hr') LIMIT 1", (pid,)))
        out.append({"id": pid, "name": r["name"], "age": scores.age_from_dob(r["dob"]), "sex": r["sex"], "conditions": conds,
                    "next_at": r["next_at"] and r["next_at"].isoformat(), "last_at": r["last_at"] and r["last_at"].isoformat(),
                    "visits": r["visits"], "has_data": has})
    return out


def _my_patient_or_403(user: dict, patient_id: str):
    require_role(user, "clinician")
    if not _is_my_patient(user, patient_id):
        raise HTTPException(403, "This patient hasn't booked with you.")


@router.get("/doctor/patients/{patient_id}/health")
def doctor_patient_health(patient_id: str, user=Depends(current_user)):
    _my_patient_or_403(user, patient_id)
    return health.payload(patient_id)


@router.post("/doctor/patients/{patient_id}/demo-data")
def doctor_patient_demo(patient_id: str, user=Depends(current_user)):
    """Populate a synthetic watch history for this patient so the dashboard can be demonstrated."""
    _my_patient_or_403(user, patient_id)
    n = synthetic.demo_wearables(patient_id)
    from .context import invalidate
    invalidate(patient_id)
    audit(user["uid"], "doctor_populated_demo_data", patient_id, {"rows": n})
    return health.payload(patient_id)


@router.post("/doctor/patients/{patient_id}/documents")
async def doctor_patient_upload(patient_id: str, file: UploadFile = File(...), note: str = Form(default=""),
                                user=Depends(current_user)):
    """Previous records (old labs, specialist letters, discharge summaries) uploaded by the clinician."""
    _my_patient_or_403(user, patient_id)
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "File too large (15 MB max)")
    c = db.q1("SELECT name FROM clinicians WHERE user_id=%s", (user["uid"],))
    doc = vault.save_document(patient_id, file.filename, file.content_type or "application/octet-stream", data,
                              uploaded_by=c["name"] if c else "Clinician", kind="record")
    if note.strip():
        db.exe("INSERT INTO memory_chunks (patient_id, kind, text) VALUES (%s,'history',%s)",
               (patient_id, f"{datetime.now(TZ).strftime('%b %d %Y')} record added by clinician ({file.filename}): {note.strip()}"))
    from .context import invalidate
    invalidate(patient_id)
    audit(user["uid"], "doctor_uploaded_record", patient_id, {"doc": doc["id"]})
    return doc


@router.post("/doctor/patients/{patient_id}/documents/{doc_id}/confirm")
def doctor_confirm_record(patient_id: str, doc_id: str, user=Depends(current_user)):
    _my_patient_or_403(user, patient_id)
    return {"observations_added": vault.confirm_document(doc_id, patient_id)}


@router.get("/health/me")
def my_health(user=Depends(current_user)):
    require_role(user, "patient")
    p = db.q1("SELECT sex, dob FROM patients WHERE id=%s", (user["pid"],))
    return {**health.payload(user["pid"]), "sex": p and p["sex"], "age": p and scores.age_from_dob(p["dob"])}


@router.get("/doctor/encounters/{encounter_id}")
def doctor_encounter(encounter_id: str, user=Depends(current_user)):
    a = _doctor_can_see(user, encounter_id)
    audit(user["uid"], "doctor_viewed_intake", str(a["patient_id"]), {"encounter": encounter_id})
    return {"report": report.get(encounter_id), "patient_id": str(a["patient_id"]),
            "documents": vault.list_documents(str(a["patient_id"])), "media": media_list(encounter_id)}


@router.post("/doctor/encounters/{encounter_id}/documents")
async def doctor_upload(encounter_id: str, file: UploadFile = File(...), note: str = Form(default=""),
                        user=Depends(current_user)):
    a = _doctor_can_see(user, encounter_id)
    c = db.q1("SELECT name FROM clinicians WHERE user_id=%s", (user["uid"],))
    pid = str(a["patient_id"])
    doc = vault.save_document(pid, file.filename, file.content_type or "application/octet-stream", await file.read(),
                              uploaded_by=c["name"], kind="post-visit")
    if note.strip():
        db.exe("INSERT INTO memory_chunks (patient_id, kind, text) VALUES (%s,'clinician_note',%s)",
               (pid, f"{datetime.now(TZ).strftime('%b %d %Y')} visit note ({c['name']}): {note.strip()}"))
    db.exe("UPDATE appointments SET status='completed' WHERE clinician_id=%s AND encounter_id=%s", (user["uid"], encounter_id))
    audit(user["uid"], "doctor_upload", pid, {"doc": doc["id"]})
    return doc


# ---------------------------------------------------------------------------
# Photo / video during the interview
# ---------------------------------------------------------------------------
class MediaDescription(BaseModel):
    description: str          # objective, visible features only
    body_area: str | None = None
    quality_ok: bool = True
    quality_note: str | None = None


MEDIA_SYSTEM = """You describe a patient's photo or short video for a nurse's intake note.
Describe ONLY what is visible: body area, colour, size relative to nearby features, shape, borders, texture,
distribution, any discharge, swelling or bleeding, and for video any movement, gait or breathing pattern.
Do NOT diagnose, name conditions, or speculate about causes. 2-4 sentences, clinical but plain.
If the image is too blurry, dark, or doesn't show a body part, set quality_ok=false and say how to retake it.
JSON only."""
MAX_MEDIA = 20 * 1024 * 1024


@router.post("/encounters/{encounter_id}/media")
async def add_media(encounter_id: str, file: UploadFile = File(...), user=Depends(current_user)):
    require_role(user, "patient")
    enc = db.q1("SELECT * FROM encounters WHERE id=%s AND patient_id=%s", (encounter_id, user.get("pid")))
    if not enc:
        raise HTTPException(404, "Check-in not found")
    mime = file.content_type or ""
    if not (mime.startswith("image/") or mime.startswith("video/")):
        raise HTTPException(415, "Attach a photo or a video.")
    data = await file.read()
    if len(data) > MAX_MEDIA:
        raise HTTPException(413, "That file is over 20 MB. Try a shorter clip (about 30 seconds) or a photo.")
    row = db.q1("""INSERT INTO documents (patient_id, encounter_id, uploaded_by, kind, filename, mime, content)
                   VALUES (%s,%s,'patient','interview-media',%s,%s,%s) RETURNING id""",
                (user["pid"], encounter_id, file.filename, mime, data))
    doc_id = str(row["id"])
    desc = None
    if gemini.enabled():
        out = gemini.generate_json(MEDIA_SYSTEM, f"Patient's main concern: {enc['chief_complaint'] or 'not stated yet'}. Describe this {'video' if mime.startswith('video/') else 'photo'}.",
                                   MediaDescription, smart=True, parts=[gemini.file_part(data, mime)], temperature=0)
        if out:
            desc = out.model_dump()
            db.exe("UPDATE documents SET extracted=%s WHERE id=%s", (db.J(desc), doc_id))
    text = desc["description"] if desc else f"{'Video' if mime.startswith('video/') else 'Photo'} attached (automatic description needs the Gemini API)."
    state = enc["state"]
    state.setdefault("media", []).append({"id": doc_id, "kind": "video" if mime.startswith("video/") else "photo",
                                          "description": text, "quality_ok": (desc or {}).get("quality_ok", True)})
    db.exe("UPDATE encounters SET state=%s WHERE id=%s", (db.J(state), encounter_id))
    return {"id": doc_id, "kind": state["media"][-1]["kind"], "description": text,
            "quality_ok": (desc or {}).get("quality_ok", True), "quality_note": (desc or {}).get("quality_note")}


def media_list(encounter_id: str) -> list[dict]:
    return [{"id": str(r["id"]), "mime": r["mime"], "description": (r["extracted"] or {}).get("description"),
             "ts": r["ts"].isoformat()}
            for r in db.q("SELECT id, mime, extracted, ts FROM documents WHERE encounter_id=%s AND kind='interview-media' ORDER BY ts", (encounter_id,))]


@router.get("/media/{doc_id}")
def get_media(doc_id: str, t: str):
    """Media is fetched with ?t=<token> so <img>/<video> tags can load it. Patient owner or linked doctor only."""
    user = read_token(t)
    d = db.q1("SELECT patient_id, encounter_id, mime, content FROM documents WHERE id=%s", (doc_id,))
    if not d:
        raise HTTPException(404)
    ok = (user["role"] == "patient" and user.get("pid") == str(d["patient_id"])) or (
        user["role"] == "clinician" and _is_my_patient(user, str(d["patient_id"])))
    if not ok:
        raise HTTPException(403)
    return Response(content=bytes(d["content"]), media_type=d["mime"], headers={"Cache-Control": "private, max-age=3600"})


# ---------------------------------------------------------------------------
# Lena's voice
# ---------------------------------------------------------------------------
class SpeakIn(BaseModel):
    text: str = Field(max_length=600)


@router.post("/tts")
def speak(b: SpeakIn, user=Depends(current_user)):
    wav = tts.speak(b.text)
    if not wav:
        raise HTTPException(503, "Natural voice unavailable; use the browser voice.")
    return Response(content=wav, media_type="audio/wav", headers={"Cache-Control": "private, max-age=86400"})


# ---------------------------------------------------------------------------
# Connected data
# ---------------------------------------------------------------------------
@router.get("/connections")
def get_connections(user=Depends(current_user)):
    require_role(user, "patient")
    return synthetic.connections(user["pid"])


@router.post("/wearables/demo")
def demo_data(user=Depends(current_user)):
    require_role(user, "patient")
    n = synthetic.demo_wearables(user["pid"])
    from .context import invalidate
    invalidate(user["pid"])
    return {"imported": n, **synthetic.connections(user["pid"])}


@router.delete("/wearables/{source}")
def remove_source(source: str, user=Depends(current_user)):
    require_role(user, "patient")
    src = {"apple_health": "apple-health", "demo": "demo-wearable"}.get(source)
    if not src:
        raise HTTPException(404)
    db.exe("DELETE FROM observations WHERE patient_id=%s AND source=%s", (user["pid"], src))
    db.refresh_daily_obs()
    from .context import invalidate
    invalidate(user["pid"])
    return synthetic.connections(user["pid"])
