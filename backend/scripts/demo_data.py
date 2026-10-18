"""Complete health profiles and medication histories for the demo patients.

Used by scripts.seed (fresh database) and scripts.fill_demo (fills an existing database without wiping it).
All people, phone numbers and history here are synthetic.
"""
from __future__ import annotations

from datetime import date, timedelta

from app import db

PROFILES = {
    "aisha": dict(
        gender="Woman", height_cm=163, weight_kg=57, waist_cm=70, blood_type="O+", pregnant=False,
        surgeries=["Wisdom teeth removed (2021)"], hospitalized_past_year=False,
        family_history=["Asthma (brother)", "High blood pressure (father)"], family_diabetes=[],
        smoking="never", audit_c=[1, 0, 0], recreational_drugs="none", active_30min_daily=True, fruit_veg_daily=True,
        sleep_hours=7.5, high_bp=False, high_blood_sugar=False, vaccines_up_to_date="yes",
        education="Undergraduate, in progress", occupation="University student",
        emergency_contact="Sara Khan (sister), 416-555-0142", lives_alone=False, walking_aid=False,
    ),
    "robert": dict(
        gender="Man", height_cm=176, weight_kg=94, waist_cm=104, blood_type="A+",
        surgeries=["Appendectomy (1979)", "Right knee arthroscopy (2015)"], hospitalized_past_year=False,
        family_history=["Type 2 diabetes (mother)", "Heart disease (father)"], family_diabetes=["mother"],
        smoking="former", audit_c=[2, 1, 0], recreational_drugs="none", active_30min_daily=False, fruit_veg_daily=False,
        sleep_hours=6.5, high_bp=True, high_blood_sugar=False, vaccines_up_to_date="yes",
        education="College diploma", occupation="Retired electrician",
        emergency_contact="Linda Mackenzie (wife), 416-555-0187", lives_alone=False, walking_aid=False,
    ),
}


def med_history(key: str, today: date) -> list[dict]:
    d = lambda days: today - timedelta(days=days)  # noqa: E731
    if key == "aisha":
        return [
            dict(name="Ibuprofen", dose="200–400 mg", frequency="As needed, up to 3 times a day with food", route="By mouth",
                 reason="Period cramps", prescriber="Over the counter", start_date=date(2022, 9, 1)),
            dict(name="Nitrofurantoin", dose="100 mg", frequency="Twice a day for 5 days", route="By mouth",
                 reason="Urinary tract infection", prescriber="Pharmacist (minor ailment)", start_date=d(240), end_date=d(235),
                 stop_reason="Course finished"),
            dict(name="Cetirizine", dose="10 mg", frequency="Once a day", route="By mouth", reason="Seasonal allergies",
                 prescriber="Over the counter", start_date=d(150), end_date=d(110), stop_reason="Allergy season ended"),
        ]
    if key == "robert":
        return [
            dict(name="Ramipril", dose="2.5 mg", frequency="Once a day", route="By mouth", reason="High blood pressure",
                 prescriber="Dr. Maya Chen", start_date=date(2021, 3, 15), end_date=date(2024, 6, 10), stop_reason="Dose increased"),
            dict(name="Ramipril", dose="5 mg", frequency="Once a day, morning", route="By mouth", reason="High blood pressure",
                 prescriber="Dr. Maya Chen", start_date=date(2024, 6, 10)),
            dict(name="Atorvastatin", dose="20 mg", frequency="Once a day, at bedtime", route="By mouth", reason="High cholesterol",
                 prescriber="Dr. Maya Chen", start_date=date(2022, 1, 20)),
            dict(name="Apixaban", dose="5 mg", frequency="Twice a day, with breakfast and dinner", route="By mouth",
                 reason="Atrial fibrillation, stroke prevention", prescriber="Dr. Maya Chen", start_date=d(110),
                 notes="Blood thinner. Report any unusual bleeding."),
            dict(name="Metoprolol", dose="25 mg", frequency="Twice a day", route="By mouth", reason="Atrial fibrillation, rate control",
                 prescriber="Dr. Maya Chen", start_date=d(110), end_date=d(60), stop_reason="Tiredness; heart rate settled without it"),
            dict(name="Nicotine patch", dose="21 mg/24 h", frequency="Once a day", route="On the skin", reason="Quitting smoking",
                 prescriber="Family doctor", start_date=date(2012, 1, 9), end_date=date(2012, 4, 30), stop_reason="Quit smoking"),
        ]
    return []


def apply_profile(pid: str, key: str) -> None:
    p = dict(PROFILES[key])
    gender = p.pop("gender")
    db.exe("UPDATE patients SET gender=%s WHERE id=%s", (gender, pid))
    if not db.q1("SELECT 1 FROM profiles WHERE patient_id=%s", (pid,)):
        db.exe("INSERT INTO profiles (patient_id, consent_at) VALUES (%s, now())", (pid,))
    sets = ", ".join(f"{k} = %s" for k in p)
    db.exe(f"UPDATE profiles SET {sets}, updated_at = now() WHERE patient_id = %s", list(p.values()) + [pid])


def apply_meds(pid: str, key: str, today: date) -> None:
    db.exe("DELETE FROM medications WHERE patient_id=%s AND source IN ('persona','self')", (pid,))
    for m in med_history(key, today):
        cols = ["patient_id", "source"] + list(m)
        db.exe(f"INSERT INTO medications ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
               [pid, "persona"] + list(m.values()))
