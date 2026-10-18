"""Demo data: two patients and one doctor. Everything here is synthetic.

    python -m scripts.seed --reset    # from backend/: WIPES ALL DATA, then creates the 3 demo accounts
    python -m scripts.seed            # only seeds if the demo accounts aren't there yet

Accounts (password demo1234):
  aisha@prelude.demo   Aisha Khan, 23, female. Healthy, past UTI treated by a pharmacist. Period ~3-4 weeks ago.
  robert@prelude.demo  Robert Mackenzie, 68, male. Former smoker, atrial fibrillation on apixaban (blood thinner).
  dr.chen@prelude.demo Dr. Maya Chen, family doctor. Has seen both before, and has one upcoming appointment.

Both patients saying "I have blood in my urine" get different questions and reports:
  Aisha  → asked about her period; considerations led by UTI / menstrual contamination; see a clinician soon.
  Robert → asked about other bleeding (blood thinner); malignancy must be ruled out; same-day (walk-in) urgency.
"""
from __future__ import annotations

import argparse
import random
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app import db, gemini
from app.auth import hash_password

TZ = ZoneInfo("America/Toronto")
DAYS = 45
DEMO_PASSWORD = "demo1234"

DOCTOR = dict(email="dr.chen@prelude.demo", name="Dr. Maya Chen", clinic="Bloor West Family Health",
              specialty="Family medicine")

ALL_TABLES = ["appointments", "clinicians", "shares", "documents", "reports", "risk_scores", "red_flag_events",
              "interview_turns", "encounters", "alerts", "memory_chunks", "checkins", "observations", "allergies",
              "medications", "conditions", "profiles", "patients", "audit_log", "users"]


def persona_list(today: date) -> list[dict]:
    return [
        {
            "key": "aisha", "name": "Aisha Khan", "dob": "2003-04-09", "sex": "female", "email": "aisha@prelude.demo",
            "profile": dict(height_cm=163, weight_kg=57, smoking="never", audit_c=[1, 0, 0], active_30min_daily=True,
                            fruit_veg_daily=True, high_bp=False, high_blood_sugar=False, pregnant=False,
                            last_menstrual_period=today - timedelta(days=24), occupation="University student",
                            family_history=[], family_diabetes=[]),
            "conditions": [], "medications": [], "allergies": [("Sulfa drugs", "hives")],
            "memory": ["Plays intramural volleyball twice a week."],
            "steps": 9200, "pattern": "normal",
            "visits": [dict(
                days_ago=240, hour=10,
                complaint="Burning when I pee and needing to go all the time", label="Burning when urinating, frequency",
                turns=[("onset", "When did this start?", "Two days ago."),
                       ("associated", "Any fever, back pain, or blood in your urine?", "No fever, no back pain, no blood."),
                       ("tried", "Have you tried anything for it?", "Just drinking lots of water."),
                       ("ice", "What are you hoping to get from today?", "Something to make it stop, I have exams.")],
                slots={"onset": "2 days ago", "associated": "frequency; no fever, flank pain or blood",
                       "tried": "fluids only", "ice": "wants quick relief before exams"},
                memory="Feb 2026 intake: burning and frequency for 2 days, no fever or blood. Pharmacist treated an uncomplicated UTI; settled in 3 days.",
                note="Feb 2026 visit note (Dr. Maya Chen): uncomplicated cystitis, treated by pharmacist with nitrofurantoin; resolved. Return if recurrent."),
            ],
        },
        {
            "key": "robert", "name": "Robert Mackenzie", "dob": "1958-02-20", "sex": "male", "email": "robert@prelude.demo",
            "profile": dict(height_cm=176, weight_kg=94, waist_cm=104, smoking="former", audit_c=[2, 1, 0],
                            active_30min_daily=False, fruit_veg_daily=False, high_bp=True, high_blood_sugar=False,
                            occupation="Retired electrician",
                            family_diabetes=["mother"], family_history=["type 2 diabetes (mother)", "heart disease (father)"]),
            "conditions": ["Atrial fibrillation", "Hypertension"],
            "medications": [("Apixaban", "5 mg twice daily"), ("Ramipril", "5 mg daily")],
            "allergies": [],
            "memory": ["Former smoker: about 30 pack-years, quit in 2012."],
            "steps": 5400, "pattern": "recent_drop",
            "visits": [
                dict(days_ago=110, hour=9,
                     complaint="My heart keeps racing and fluttering on and off", label="Palpitations, on and off",
                     turns=[("onset", "When did the fluttering start?", "About two weeks ago, comes and goes."),
                            ("associated", "Any chest pain, fainting, or shortness of breath with it?", "No chest pain, no fainting. A bit winded on stairs."),
                            ("timing", "How long does each episode last?", "Maybe twenty minutes to an hour."),
                            ("ice", "What worries you most about it?", "My dad had heart problems.")],
                     slots={"onset": "2 weeks, intermittent", "associated": "mild exertional breathlessness; no chest pain or syncope",
                            "timing": "episodes 20-60 min", "ice": "worried given father's heart disease"},
                     memory="Jul 2026 intake: intermittent palpitations for 2 weeks. ECG showed atrial fibrillation; started apixaban 5 mg twice daily.",
                     note="Jul 2026 visit note (Dr. Maya Chen): new paroxysmal AF, CHA2DS2-VASc 2. Started apixaban 5 mg BID. Echo ordered."),
                dict(days_ago=30, hour=14,
                     complaint="Blood pressure follow-up", label="Blood pressure follow-up",
                     turns=[("onset", "How have your home blood pressure readings been?", "Mostly around 135 over 85."),
                            ("associated", "Any dizziness, headaches or swelling in your ankles?", "No, none of that."),
                            ("tried", "Are you taking your ramipril and apixaban every day?", "Yes, every day with breakfast and dinner.")],
                     slots={"onset": "home BP ~135/85", "associated": "no dizziness, headache or oedema",
                            "tried": "adherent to ramipril and apixaban"},
                     memory="Sep 2026 intake: blood pressure follow-up, home readings ~135/85, taking ramipril and apixaban daily.",
                     note="Sep 2026 visit note (Dr. Maya Chen): BP reasonably controlled, continue ramipril. Tolerating apixaban, no bleeding. Review in 1 month."),
            ],
            "upcoming": dict(
                days_ahead=6, at=time(10, 20), reason="Medication review (blood pressure and apixaban)",
                checkin=dict(
                    complaint="I've had a few nosebleeds since starting the blood thinner", label="Nosebleeds on apixaban",
                    turns=[("onset", "When did the nosebleeds start?", "About three weeks ago, maybe four of them."),
                           ("timing", "How long does each one last?", "Ten minutes or so, they stop if I pinch my nose."),
                           ("associated", "Any blood in your urine or stool, or unusual bruising?", "No, nothing like that."),
                           ("tried", "Are you still taking your apixaban twice a day?", "Yes, I haven't missed any."),
                           ("ice", "What would you like from the visit?", "To know if I should keep taking it.")],
                    slots={"onset": "~3 weeks, about 4 episodes", "timing": "~10 min each, stop with pressure",
                           "associated": "no haematuria, melaena or easy bruising", "tried": "adherent to apixaban 5 mg BID",
                           "ice": "wants to know whether to continue apixaban"},
                    memory="Oct 2026 intake: about 4 short nosebleeds in 3 weeks on apixaban, no other bleeding.",
                    note="")),
        },
    ]


def wipe():
    existing = {r["table_name"] for r in db.q("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")}
    tables = [t for t in ALL_TABLES if t in existing]
    db.exe("TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY CASCADE")
    print("wiped:", ", ".join(tables))


def make_user(email, role, name) -> str:
    row = db.q1("INSERT INTO users (email, password_hash, role, display_name) VALUES (%s,%s,%s,%s) RETURNING id",
                (email, hash_password(DEMO_PASSWORD), role, name))
    return str(row["id"])


def wearables(pid, base_steps, pattern, rng: random.Random, today: date) -> list[tuple]:
    """Hourly steps, daily resting HR and nightly sleep. 'recent_drop' = the last 6 days are noticeably lower."""
    rows = []
    base_rhr, base_sleep = rng.randint(60, 70), rng.randint(410, 470)
    for i in range(DAYS):
        d = today - timedelta(days=DAYS - 1 - i)
        days_left = DAYS - 1 - i
        f_steps, rhr_add, f_sleep = 1.0, 0, 1.0
        if pattern == "recent_drop" and days_left <= 5:
            f_steps, rhr_add, f_sleep = 0.6, 5, 0.85
        day_steps = base_steps * f_steps * rng.uniform(0.88, 1.12) * (0.9 if d.weekday() >= 5 else 1.0)
        weights = [rng.uniform(0.5, 1.5) * (1.6 if h in (9, 10, 15, 16) else 1.0) for h in range(7, 21)]
        tot = sum(weights)
        for h, w in zip(range(7, 21), weights):
            rows.append((pid, datetime.combine(d, time(h, rng.randint(0, 59)), TZ), "steps", round(day_steps * w / tot), "count", "apple-health"))
        rows.append((pid, datetime.combine(d, time(6, 30), TZ), "rhr", base_rhr + rhr_add + rng.randint(-2, 2), "bpm", "apple-health"))
        rows.append((pid, datetime.combine(d, time(7, 0), TZ), "sleep_min", round(base_sleep * f_sleep * rng.uniform(0.92, 1.06)), "min", "apple-health"))
    return rows


def weekday_slot(day: date, at: time) -> datetime:
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime.combine(day, at, TZ)


def make_checkin(pid: str, v: dict, started: datetime) -> str:
    """A finished check-in with its report (offline mode), started at `started`. Returns the encounter id."""
    from app import report, triage
    category = triage.categorise(v["complaint"])
    state = {"slots": {"chief_complaint": triage.tidy_complaint(v["complaint"]), **v["slots"]}, "category": category,
             "asked_questions": [], "considerations": [], "topics": [], "mode": "offline"}
    enc = db.q1("INSERT INTO encounters (patient_id, started_at, chief_complaint, state) VALUES (%s,%s,%s,%s) RETURNING id",
                (pid, started, triage.tidy_complaint(v["complaint"]), db.J(state)))
    eid = str(enc["id"])
    turns = [("chief_complaint", "What's brought you in today?", v["complaint"])] + v["turns"]
    for k, (slot, q, a) in enumerate(turns):
        db.exe("""INSERT INTO interview_turns (encounter_id, ts, question, answer, q_type, slot, rationale)
                  VALUES (%s,%s,%s,%s,'STANDARD',%s,'Intake framework')""",
               (eid, started + timedelta(minutes=k), q, a, slot))
    report.generate(eid)                      # offline (Gemini switched off for seeding): fast and free
    db.exe("""UPDATE reports SET clinician_json = jsonb_set(clinician_json, '{chief_complaint}', to_jsonb(%s::text))
              WHERE encounter_id=%s""", (v["label"], eid))
    db.exe("UPDATE encounters SET ended_at=%s, chief_complaint=%s WHERE id=%s", (started + timedelta(minutes=8), v["label"], eid))
    db.exe("UPDATE reports SET created_at=%s WHERE encounter_id=%s", (started + timedelta(minutes=8), eid))
    return eid


def past_visit(pid: str, doctor_uid: str, v: dict, today: date):
    """A finished check-in + clinician note + completed appointment, dated in the past."""
    when = weekday_slot(today - timedelta(days=v["days_ago"]), time(v["hour"], 0))
    eid = make_checkin(pid, v, when - timedelta(hours=20))
    db.exe("""INSERT INTO appointments (patient_id, clinician_id, encounter_id, starts_at, reason, status)
              VALUES (%s,%s,%s,%s,%s,'completed')""", (pid, doctor_uid, eid, when, v["label"]))
    db.exe("DELETE FROM memory_chunks WHERE patient_id=%s AND kind='visit'", (pid,))  # replaced by dated memory below
    db.exe("INSERT INTO memory_chunks (patient_id, kind, text) VALUES (%s,'history',%s)", (pid, v["memory"]))
    db.exe("INSERT INTO memory_chunks (patient_id, kind, text) VALUES (%s,'clinician_note',%s)", (pid, v["note"]))


def main(do_reset: bool):
    feats = db.init_schema()
    print("features:", feats)
    if do_reset:
        wipe()
    elif db.q1("SELECT 1 FROM users WHERE email=%s", (DOCTOR["email"],)):
        print("demo accounts already exist (run with --reset to wipe and recreate)")
        return
    gemini.enabled = lambda: False            # seeding never spends Gemini quota
    rng = random.Random(7)
    today = datetime.now(TZ).date()

    doc_uid = make_user(DOCTOR["email"], "clinician", DOCTOR["name"])
    db.exe("INSERT INTO clinicians (user_id, name, clinic, specialty, city) VALUES (%s,%s,%s,%s,'Toronto')",
           (doc_uid, DOCTOR["name"], DOCTOR["clinic"], DOCTOR["specialty"]))
    print("doctor", DOCTOR["name"])

    obs = []
    for p in persona_list(today):
        uid = make_user(p["email"], "patient", p["name"])
        pid = str(db.q1("""INSERT INTO patients (user_id, name, dob, sex, source) VALUES (%s,%s,%s,%s,'persona')
                           RETURNING id""", (uid, p["name"], p["dob"], p["sex"]))["id"])
        prof = p["profile"]
        cols = ["patient_id", "consent_at"] + list(prof.keys())
        db.exe(f"INSERT INTO profiles ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
               [pid, datetime.now(TZ)] + list(prof.values()))
        for c in p["conditions"]:
            db.exe("INSERT INTO conditions (patient_id, name, source) VALUES (%s,%s,'persona')", (pid, c))
        for m, dose in p["medications"]:
            db.exe("INSERT INTO medications (patient_id, name, dose, source) VALUES (%s,%s,%s,'persona')", (pid, m, dose))
        from scripts.demo_data import apply_meds, apply_profile
        apply_profile(pid, p["key"])          # every profile field filled in
        apply_meds(pid, p["key"], today)      # full medication history with doses and dates
        for s, r in p["allergies"]:
            db.exe("INSERT INTO allergies (patient_id, substance, reaction, source) VALUES (%s,%s,%s,'persona')", (pid, s, r))
        for text in p["memory"]:
            db.exe("INSERT INTO memory_chunks (patient_id, kind, text) VALUES (%s,'history',%s)", (pid, text))
        obs += wearables(pid, p["steps"], p["pattern"], rng, today)
        for v in p["visits"]:
            past_visit(pid, doc_uid, v, today)
        if p.get("upcoming"):
            u = p["upcoming"]
            eid = None
            if u.get("checkin"):   # the patient already talked to the intake assistant for this visit
                eid = make_checkin(pid, u["checkin"], datetime.now(TZ) - timedelta(hours=3))
            db.exe("""INSERT INTO appointments (patient_id, clinician_id, encounter_id, starts_at, reason, status)
                      VALUES (%s,%s,%s,%s,%s,'booked')""",
                   (pid, doc_uid, eid, weekday_slot(today + timedelta(days=u["days_ahead"]), u["at"]), u["reason"]))
        print("patient", p["name"], f"({len(p['visits'])} past visits)")

    with db.conn() as c:
        with c.cursor().copy("COPY observations (patient_id, ts, code, value, unit, source) FROM STDIN") as cp:
            for r in obs:
                cp.write_row(r)
    db.refresh_daily_obs()
    print(f"inserted {len(obs):,} wearable readings")
    print(f"\nLogins (password '{DEMO_PASSWORD}'):\n  aisha@prelude.demo   (patient, 23F)\n"
          f"  robert@prelude.demo  (patient, 68M, on a blood thinner)\n  dr.chen@prelude.demo (doctor)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="wipe ALL data first")
    try:
        main(ap.parse_args().reset)
    finally:
        db.close()
