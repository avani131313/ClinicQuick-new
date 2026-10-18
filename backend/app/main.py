"""ClinicQuick API (FastAPI)."""
from __future__ import annotations

import logging
import secrets

import psycopg
from datetime import date, datetime, timedelta, timezone

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import accounts, care, live, db, fhir, gemini, interview, meds, notifications, report, scores, trendwatch, vault, walkin, physio
from .auth import current_user, hash_password, make_token, require_role, verify_password
from .config import CORS_ORIGINS, FRONTEND_URL
from .context import load_patient, modifiers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
app = FastAPI(title="ClinicQuick API", version="0.1.0")


@app.exception_handler(psycopg.errors.InvalidTextRepresentation)
async def _bad_id(request: Request, exc: Exception):
    # a malformed id in the URL or body (e.g. /encounters/abc) is "not found", not a server error
    return JSONResponse(status_code=404, content={"detail": "Not found"})
# Auth uses bearer tokens (no cookies), so credentials are off and "*" is safe for a demo.
app.include_router(accounts.router)
app.include_router(live.router)
from ddx.router import router as ddx_router  # DDX decision support (doctor-only)
app.include_router(ddx_router)
app.include_router(meds.router)
app.include_router(notifications.router)
app.include_router(walkin.router)
app.include_router(physio.router)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _startup():
    db.init_schema()


@app.on_event("shutdown")
def _shutdown():
    db.close()


def audit(actor: str, action: str, patient_id: str | None, detail: dict | None = None):
    db.exe("INSERT INTO audit_log (actor, action, patient_id, detail) VALUES (%s,%s,%s,%s)",
           (actor, action, patient_id, db.J(detail or {})))


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    from . import tts
    return {"ok": True, "features": db.FEATURES, "gemini": gemini.enabled(), "gemini_keys": len(gemini.KEYS), "gemini_active_key": gemini.active_key(),
            "gemini_last_error": gemini.LAST_ERROR,
            "tts_model": tts.TTS_MODEL, "tts_last_error": tts.LAST_ERROR, "live_model": live.LIVE_MODEL}


# ---------------------------------------------------------------------------
# Onboarding + auth
# ---------------------------------------------------------------------------
class Onboarding(BaseModel):
    name: str
    dob: date
    sex: str = Field(pattern="^(female|male|intersex)$")
    gender: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    waist_cm: float | None = None
    pregnant: bool | None = None
    conditions: list[str] = []
    medications: list[str] = []
    allergies: list[str] = []
    family_history: list[str] = []          # e.g. ["diabetes (mother)", "heart disease (father)"]
    family_diabetes: list[str] = []         # mother | father | sibling | child | other
    smoking: str | None = None              # never | former | current | vape
    audit_c: list[int] | None = None
    active_30min_daily: bool | None = None
    fruit_veg_daily: bool | None = None
    high_bp: bool | None = None
    high_blood_sugar: bool | None = None
    baby_over_4kg: bool | None = None
    parent_ethnicities: list[str] = []
    education: str | None = None
    lives_alone: bool | None = None
    walking_aid: bool | None = None


class Signup(BaseModel):
    email: str
    password: str = Field(min_length=6)
    onboarding: Onboarding
    consent: bool


class Login(BaseModel):
    email: str
    password: str


def _snapshot(o: Onboarding) -> dict:
    age = scores.age_from_dob(o.dob)
    prof = o.model_dump()
    prof.update(age=age)
    res = scores.compute_profile_scores(prof)
    return {"age": age, "scores": [r.to_dict() for r in res],
            "applicable": scores.applicable_scores(prof)}


@app.post("/onboarding/preview")
def onboarding_preview(o: Onboarding):
    """The 'health snapshot' shown before sign-up. Nothing is stored."""
    return _snapshot(o)


@app.post("/auth/signup")
def signup(s: Signup):
    if not s.consent:
        raise HTTPException(400, "Consent is required to create an account.")
    email = s.email.strip().lower()
    if db.q1("SELECT 1 FROM users WHERE email = %s", (email,)):
        raise HTTPException(409, "An account with this email already exists.")
    o = s.onboarding
    u = db.q1("INSERT INTO users (email, password_hash, role, display_name) VALUES (%s,%s,'patient',%s) RETURNING id",
              (email, hash_password(s.password), o.name))
    p = db.q1("INSERT INTO patients (user_id, name, dob, sex, gender, source, synthetic) VALUES (%s,%s,%s,%s,%s,'app',true) RETURNING id",
              (u["id"], o.name, o.dob, o.sex, o.gender))
    pid = str(p["id"])
    db.exe("""INSERT INTO profiles (patient_id, height_cm, weight_kg, waist_cm, pregnant, smoking, audit_c,
              active_30min_daily, fruit_veg_daily, high_bp, high_blood_sugar, baby_over_4kg, family_diabetes,
              family_history, parent_ethnicities, education, lives_alone, walking_aid, consent_at)
              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())""",
           (pid, o.height_cm, o.weight_kg, o.waist_cm, o.pregnant, o.smoking, o.audit_c, o.active_30min_daily,
            o.fruit_veg_daily, o.high_bp, o.high_blood_sugar, o.baby_over_4kg, o.family_diabetes, o.family_history,
            o.parent_ethnicities, o.education, o.lives_alone, o.walking_aid))
    for c in o.conditions:
        db.exe("INSERT INTO conditions (patient_id, name) VALUES (%s,%s)", (pid, c))
    for m in o.medications:
        db.exe("INSERT INTO medications (patient_id, name) VALUES (%s,%s)", (pid, m))
    for a in o.allergies:
        db.exe("INSERT INTO allergies (patient_id, substance) VALUES (%s,%s)", (pid, a))
    audit(email, "signup+consent", pid)
    return {"token": make_token(str(u["id"]), "patient", pid), "role": "patient", "patient_id": pid}


@app.post("/auth/login")
def login(body: Login):
    u = db.q1("SELECT * FROM users WHERE email = %s", (body.email.strip().lower(),))
    if not u or not verify_password(body.password, u["password_hash"]):
        raise HTTPException(401, "Email or password is incorrect.")
    p = db.q1("SELECT id FROM patients WHERE user_id = %s", (u["id"],))
    pid = str(p["id"]) if p else None
    return {"token": make_token(str(u["id"]), u["role"], pid), "role": u["role"], "patient_id": pid,
            "name": u["display_name"], "profile_complete": bool(pid) if u["role"] == "patient" else True}


def _patient_of(user: dict) -> str:
    require_role(user, "patient")
    if not user.get("pid"):
        raise HTTPException(400, "No patient profile on this account")
    return user["pid"]


@app.get("/me")
def me(user=Depends(current_user)):
    u = db.q1("SELECT email, role, display_name FROM users WHERE id = %s", (user["uid"],))
    out = {"user": u, "role": user["role"]}
    if user.get("pid"):
        ctx = load_patient(user["pid"])
        prof = dict(ctx["profile"])
        if prof.get("audit_c"):
            prof["audit_c"] = list(prof["audit_c"])
        out["patient"] = {k: ctx[k] for k in ("id", "name", "first_name", "age", "sex", "conditions", "medications", "allergies")}
        out["scores"] = [s.to_dict() for s in scores.compute_profile_scores(prof)]
        out["encounters"] = [
            {**e, "id": str(e["id"]), "started_at": e["started_at"].isoformat()}
            for e in db.q("""SELECT e.id, e.started_at, e.chief_complaint, e.status, e.urgency FROM encounters e
                             WHERE e.patient_id = %s AND EXISTS (SELECT 1 FROM interview_turns t
                               WHERE t.encounter_id = e.id AND t.answer IS NOT NULL)
                             ORDER BY e.started_at DESC LIMIT 10""", (user["pid"],))]
        out["has_wearable_data"] = bool(db.q1("SELECT 1 FROM observations WHERE patient_id=%s AND code IN ('steps','rhr') LIMIT 1", (user["pid"],)))
    return out


# ---------------------------------------------------------------------------
# Interview
# ---------------------------------------------------------------------------
class Answer(BaseModel):
    text: str


def _own_encounter(user: dict, encounter_id: str) -> dict:
    pid = _patient_of(user)
    enc = db.q1("SELECT * FROM encounters WHERE id = %s AND patient_id = %s", (encounter_id, pid))
    if not enc:
        raise HTTPException(404, "Interview not found")
    return enc


@app.post("/encounters")
def start_encounter(user=Depends(current_user)):
    return interview.start(_patient_of(user))


@app.post("/encounters/{encounter_id}/answer")
def answer(encounter_id: str, body: Answer, user=Depends(current_user)):
    _own_encounter(user, encounter_id)
    try:
        return interview.answer(encounter_id, body.text)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/encounters/{encounter_id}/finish")
def finish(encounter_id: str, user=Depends(current_user)):
    enc = _own_encounter(user, encounter_id)
    if enc["status"] == "stopped_red_flag":
        raise HTTPException(409, "This interview was stopped for safety.")
    if enc["status"] == "active":
        db.exe("UPDATE encounters SET status = 'complete' WHERE id = %s", (encounter_id,))
    return report.generate(encounter_id)


@app.get("/encounters/{encounter_id}")
def get_encounter(encounter_id: str, user=Depends(current_user)):
    enc = _own_encounter(user, encounter_id)
    q = None
    if enc["status"] == "active":
        pend = interview._pending(encounter_id)
        if pend:
            q = {"question": pend["question"], "q_type": pend["q_type"], "slot": pend["slot"],
                 "options": enc["state"].get("pending_options")}
    return {"encounter": interview.public_view(enc, q), "transcript": interview.transcript(encounter_id),
            "media": accounts.media_list(encounter_id),
            "report": report.get(encounter_id)}


@app.get("/encounters/{encounter_id}/report")
def get_report(encounter_id: str, user=Depends(current_user)):
    _own_encounter(user, encounter_id)
    r = report.get(encounter_id)
    if not r:
        raise HTTPException(404, "Report not generated yet")
    return r


@app.post("/encounters/{encounter_id}/share")
def share(encounter_id: str, user=Depends(current_user)):
    enc = _own_encounter(user, encounter_id)
    if not report.get(encounter_id):
        raise HTTPException(409, "Finish the interview first")
    token = secrets.token_urlsafe(16)
    expires = datetime.now(timezone.utc) + timedelta(days=7)
    db.exe("INSERT INTO shares (token, patient_id, encounter_id, expires_at) VALUES (%s,%s,%s,%s)",
           (token, enc["patient_id"], encounter_id, expires))
    audit(user["uid"], "share_created", str(enc["patient_id"]), {"encounter": encounter_id})
    return {"token": token, "url": f"{FRONTEND_URL}/clinician/{token}", "expires_at": expires.isoformat()}


@app.get("/encounters/{encounter_id}/fhir")
def fhir_bundle(encounter_id: str, user=Depends(current_user)):
    _own_encounter(user, encounter_id)
    r = report.get(encounter_id)
    if not r:
        raise HTTPException(409, "Finish the interview first")
    return fhir.build_bundle(r)


@app.post("/encounters/{encounter_id}/fhir/push")
def fhir_push(encounter_id: str, user=Depends(current_user)):
    enc = _own_encounter(user, encounter_id)
    r = report.get(encounter_id)
    if not r:
        raise HTTPException(409, "Finish the interview first")
    bundle = fhir.build_bundle(r)
    try:
        res = fhir.push(bundle)
    except Exception as e:
        raise HTTPException(502, f"FHIR server error: {e}")
    db.exe("UPDATE reports SET fhir_bundle = %s WHERE encounter_id = %s", (db.J(bundle), encounter_id))
    audit(user["uid"], "fhir_push", str(enc["patient_id"]), res)
    return res


# ---------------------------------------------------------------------------
# Clinician portal (share link — no login)
# ---------------------------------------------------------------------------
def _share(token: str) -> dict:
    s = db.q1("SELECT * FROM shares WHERE token = %s", (token,))
    if not s or s["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(404, "This link has expired or doesn't exist.")
    return s


@app.get("/share/{token}")
def view_share(token: str):
    s = _share(token)
    r = report.get(str(s["encounter_id"]))
    audit("clinician-link", "share_viewed", str(s["patient_id"]), {"token": token[:6] + "…"})
    views = db.q1("SELECT count(*) AS n FROM audit_log WHERE action='share_viewed' AND patient_id=%s", (s["patient_id"],))
    return {"report": r, "documents": vault.list_documents(str(s["patient_id"])),
            "expires_at": s["expires_at"].isoformat(), "view_count": views["n"]}


@app.post("/share/{token}/documents")
async def clinician_upload(token: str, file: UploadFile = File(...), note: str = Form(default=""),
                           clinician: str = Form(default="Clinician")):
    s = _share(token)
    data = await file.read()
    doc = vault.save_document(str(s["patient_id"]), file.filename, file.content_type or "application/octet-stream",
                              data, uploaded_by=clinician, kind="post-visit")
    if note.strip():
        db.exe("INSERT INTO memory_chunks (patient_id, kind, text) VALUES (%s,'clinician_note',%s)",
               (s["patient_id"], f"{datetime.now().strftime('%b %d %Y')} visit note ({clinician}): {note.strip()}"))
    audit(clinician, "clinician_upload", str(s["patient_id"]), {"doc": doc["id"]})
    return doc


# ---------------------------------------------------------------------------
# Vault, wearables, timeline
# ---------------------------------------------------------------------------
@app.get("/vault")
def get_vault(user=Depends(current_user)):
    return vault.list_documents(_patient_of(user))


@app.post("/vault/upload")
async def upload(file: UploadFile = File(...), user=Depends(current_user)):
    pid = _patient_of(user)
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "File too large (15 MB max)")
    return vault.save_document(pid, file.filename, file.content_type or "application/octet-stream", data, uploaded_by="patient")


@app.post("/vault/{doc_id}/confirm")
def confirm(doc_id: str, user=Depends(current_user)):
    return {"observations_added": vault.confirm_document(doc_id, _patient_of(user))}


@app.post("/wearables/apple-health")
async def apple(file: UploadFile = File(...), user=Depends(current_user)):
    pid = _patient_of(user)
    try:
        out = vault.import_apple_health(pid, await file.read())
        from .context import invalidate
        invalidate(pid)
        return out
    except Exception as e:
        raise HTTPException(400, f"Couldn't read that export: {e}")


@app.get("/trends/me")
def my_trends(user=Depends(current_user)):
    pid = _patient_of(user)
    return care._sparkline(care.daily_series(pid, 30), 30)


@app.get("/timeline")
def timeline(user=Depends(current_user)):
    pid = _patient_of(user)
    items = []
    for e in db.q("SELECT id, started_at, chief_complaint, urgency, status FROM encounters WHERE patient_id=%s", (pid,)):
        items.append({"kind": "intake", "ts": e["started_at"].isoformat(), "title": e["chief_complaint"] or "Intake",
                      "detail": e["urgency"], "id": str(e["id"]), "status": e["status"]})
    for d in vault.list_documents(pid):
        items.append({"kind": "document", "ts": d["ts"], "title": d["filename"],
                      "detail": (d["extracted"] or {}).get("summary"), "id": d["id"], "uploaded_by": d["uploaded_by"]})
    for o in db.q("""SELECT code, value, unit, ts FROM observations WHERE patient_id=%s AND code LIKE 'lab:%%'
                     ORDER BY ts DESC LIMIT 50""", (pid,)):
        items.append({"kind": "lab", "ts": o["ts"].isoformat(), "title": o["code"][4:].title(),
                      "detail": f"{o['value']:g} {o['unit'] or ''}".strip()})
    for m in db.q("SELECT kind, text, ts FROM memory_chunks WHERE patient_id=%s AND kind='clinician_note'", (pid,)):
        items.append({"kind": "note", "ts": m["ts"].isoformat(), "title": "Clinician note", "detail": m["text"]})
    return sorted(items, key=lambda x: x["ts"], reverse=True)


# ---------------------------------------------------------------------------
# Care team (PCC: Catch It Early)
# ---------------------------------------------------------------------------
EXPLAIN_SYSTEM = """You write a 2-3 sentence handover note for a nurse in a retirement residence.
Use ONLY the signals given — do not add any fact, number, or diagnosis that isn't in them.
Lead with what changed and by how much versus the resident's own baseline, then why it matters (the listed risks),
then the single most useful next check. Plain, calm, specific. No bullet points."""


def _explanation(patient: dict, trend: dict) -> tuple[str, str]:
    if trend["status"] == "ok" or not gemini.enabled():
        return trend["explanation"], "rules"
    today = date.today()
    cached = db.q1("""SELECT explanation FROM alerts WHERE patient_id=%s AND ts::date = %s AND headline = %s
                      ORDER BY ts DESC LIMIT 1""", (patient["id"], today, trend["headline"]))
    if cached:
        return cached["explanation"], "gemini"
    prompt = (f"Resident: {patient['name']}, {scores.age_from_dob(patient['dob'])}.\n"
              f"Headline: {trend['headline']}\nRisks: {trend['risks']}\n"
              f"Signals: {[ (s['label'], s['detail']) for s in trend['signals']]}\n"
              f"Suggested checks (fixed list): {[s['action'] for s in trend['signals']]}")
    text = gemini.generate_text(EXPLAIN_SYSTEM, prompt)
    if not text:
        return trend["explanation"], "rules"
    db.exe("""INSERT INTO alerts (patient_id, status, headline, risks, signals, explanation)
              VALUES (%s,%s,%s,%s,%s,%s)""",
           (patient["id"], trend["status"], trend["headline"], trend["risks"], db.J(trend["signals"]), text))
    return text, "gemini"


@app.get("/care/residents")
def residents(user=Depends(current_user)):
    require_role(user, "care_team", "clinician")
    rows = care.facility_overview()
    return {"facility": rows[0]["facility"] if rows else None, "residents": rows,
            "counts": {k: sum(1 for r in rows if r["status"] == k) for k in ("alert", "watch", "ok")}}


@app.get("/care/residents/{patient_id}")
def resident(patient_id: str, user=Depends(current_user)):
    require_role(user, "care_team", "clinician")
    p = db.q1("SELECT * FROM patients WHERE id = %s AND facility IS NOT NULL", (patient_id,))
    if not p:
        raise HTTPException(404, "Resident not found")
    t = care.resident_trend(p)
    t["explanation"], t["explained_by"] = _explanation(p, t)
    ctx = load_patient(patient_id)
    prof = dict(ctx["profile"])
    steadi = scores.steadi(prof.get("steadi")) if prof.get("steadi") else None
    ack = db.q1("SELECT acknowledged_by, acknowledged_at FROM alerts WHERE patient_id=%s AND acknowledged_at IS NOT NULL ORDER BY acknowledged_at DESC LIMIT 1", (patient_id,))
    audit(user["uid"], "resident_viewed", patient_id)
    return {"resident": {k: ctx[k] for k in ("id", "name", "age", "sex", "facility", "room", "conditions", "medications", "allergies")},
            "trend": t, "steadi": steadi.to_dict() if steadi else None, "context_modifiers": modifiers(ctx),
            "acknowledged": {**ack, "acknowledged_at": ack["acknowledged_at"].isoformat()} if ack else None}


class CheckIn(BaseModel):
    ate_meals: bool | None = None
    slept_ok: bool | None = None
    dizzy: bool = False
    fell: bool = False
    confused: bool = False
    pain: int | None = Field(default=None, ge=0, le=10)
    note: str | None = None


@app.post("/care/residents/{patient_id}/checkins")
def add_checkin(patient_id: str, c: CheckIn, user=Depends(current_user)):
    require_role(user, "care_team")
    if not db.q1("SELECT 1 FROM patients WHERE id = %s AND facility IS NOT NULL", (patient_id,)):
        raise HTTPException(404, "Resident not found")
    u = db.q1("SELECT display_name FROM users WHERE id=%s", (user["uid"],))
    db.exe("""INSERT INTO checkins (patient_id, ts, ate_meals, slept_ok, dizzy, fell, confused, pain, note, recorded_by)
              VALUES (%s, now(), %s,%s,%s,%s,%s,%s,%s,%s)""",
           (patient_id, c.ate_meals, c.slept_ok, c.dizzy, c.fell, c.confused, c.pain, c.note, u["display_name"]))
    p = db.q1("SELECT * FROM patients WHERE id = %s", (patient_id,))
    return care.resident_trend(p)


@app.post("/care/residents/{patient_id}/acknowledge")
def acknowledge(patient_id: str, user=Depends(current_user)):
    require_role(user, "care_team", "clinician")
    if not db.q1("SELECT 1 FROM patients WHERE id = %s AND facility IS NOT NULL", (patient_id,)):
        raise HTTPException(404, "Resident not found")
    u = db.q1("SELECT display_name FROM users WHERE id=%s", (user["uid"],))
    row = db.q1("SELECT id FROM alerts WHERE patient_id=%s ORDER BY ts DESC LIMIT 1", (patient_id,))
    if row:
        db.exe("UPDATE alerts SET acknowledged_by=%s, acknowledged_at=now() WHERE id=%s", (u["display_name"], row["id"]))
    else:
        p = db.q1("SELECT * FROM patients WHERE id=%s", (patient_id,))
        t = care.resident_trend(p)
        db.exe("""INSERT INTO alerts (patient_id, status, headline, risks, signals, explanation, acknowledged_by, acknowledged_at)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,now())""",
               (patient_id, t["status"], t["headline"], t["risks"], db.J(t["signals"]), t["explanation"], u["display_name"]))
    audit(user["uid"], "alert_acknowledged", patient_id)
    return {"ok": True, "acknowledged_by": u["display_name"]}
