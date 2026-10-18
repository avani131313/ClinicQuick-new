"""Load Synthea FHIR R4 bundles into Prelude.

    java -jar synthea-with-dependencies.jar -p 25 --exporter.fhir.export=true --exporter.years_of_history=5
    python -m scripts.load_synthea path/to/synthea-output/fhir [--accounts 5]

Living patients only. Each gets demographics, height/weight, smoking status, active
conditions, active medications, allergies, and a short history memory. With --accounts N,
the first N also get a demo login (firstname.lastname@synthea.demo / demo1234).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from app import db
from app.auth import hash_password

LOINC_HEIGHT, LOINC_WEIGHT, LOINC_SMOKING = "8302-2", "29463-7", "72166-2"


def clean_name(n: dict) -> str:
    given = " ".join(n.get("given", []))
    return re.sub(r"\d+", "", f"{given} {n.get('family', '')}").strip()


def latest_obs(entries, code):
    obs = [r for r in entries if r["resourceType"] == "Observation"
           and any(c.get("code") == code for c in r.get("code", {}).get("coding", []))]
    obs.sort(key=lambda r: r.get("effectiveDateTime", ""))
    return obs[-1] if obs else None


def smoking_from(obs) -> str | None:
    if not obs:
        return None
    t = (obs.get("valueCodeableConcept", {}).get("text") or "").lower()
    return "current" if "every day" in t or "current" in t else "former" if "former" in t or "ex-" in t else "never" if "never" in t else None


def load_bundle(path: Path, make_account: bool) -> str | None:
    b = json.loads(path.read_text())
    res = [e["resource"] for e in b.get("entry", [])]
    pat = next((r for r in res if r["resourceType"] == "Patient"), None)
    if not pat or pat.get("deceasedDateTime"):
        return None
    name = clean_name(pat["name"][0])
    sex = pat.get("gender") if pat.get("gender") in ("female", "male") else None
    uid = None
    if make_account:
        email = re.sub(r"[^a-z.]", "", name.lower().replace(" ", ".")) + "@synthea.demo"
        u = db.q1("INSERT INTO users (email, password_hash, role, display_name) VALUES (%s,%s,'patient',%s) "
                  "ON CONFLICT (email) DO NOTHING RETURNING id", (email, hash_password("demo1234"), name))
        uid = u["id"] if u else None
        if uid:
            print("  login:", email)
    p = db.q1("INSERT INTO patients (user_id, name, dob, sex, source) VALUES (%s,%s,%s,%s,'synthea') RETURNING id",
              (uid, name, pat["birthDate"], sex))
    pid = str(p["id"])
    h, w = latest_obs(res, LOINC_HEIGHT), latest_obs(res, LOINC_WEIGHT)
    db.exe("INSERT INTO profiles (patient_id, height_cm, weight_kg, smoking, consent_at) VALUES (%s,%s,%s,%s, now())",
           (pid, h and h["valueQuantity"]["value"], w and w["valueQuantity"]["value"], smoking_from(latest_obs(res, LOINC_SMOKING))))
    n_cond = n_med = 0
    seen = set()
    for r in res:
        rt = r["resourceType"]
        if rt == "Condition" and r.get("clinicalStatus", {}).get("coding", [{}])[0].get("code") == "active":
            text = r["code"].get("text") or r["code"]["coding"][0].get("display", "")
            if "(disorder)" in text and text not in seen:
                seen.add(text)
                db.exe("INSERT INTO conditions (patient_id, name, code, onset, source) VALUES (%s,%s,%s,%s,'synthea')",
                       (pid, text.replace(" (disorder)", ""), r["code"]["coding"][0].get("code"), (r.get("onsetDateTime") or "")[:10] or None))
                n_cond += 1
        elif rt == "MedicationRequest" and r.get("status") == "active":
            text = r.get("medicationCodeableConcept", {}).get("text")
            if text and text not in seen:
                seen.add(text)
                db.exe("INSERT INTO medications (patient_id, name, source) VALUES (%s,%s,'synthea')", (pid, text))
                n_med += 1
        elif rt == "AllergyIntolerance":
            text = r.get("code", {}).get("text")
            if text and text not in seen:
                seen.add(text)
                db.exe("INSERT INTO allergies (patient_id, substance, source) VALUES (%s,%s,'synthea')", (pid, text))
    n_enc = sum(1 for r in res if r["resourceType"] == "Encounter")
    db.exe("INSERT INTO memory_chunks (patient_id, kind, text) VALUES (%s,'history',%s)",
           (pid, f"Imported record (Synthea): {n_enc} past encounters, {n_cond} active conditions, {n_med} active medications."))
    return f"{name} — {n_cond} conditions, {n_med} meds"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fhir_dir")
    ap.add_argument("--accounts", type=int, default=5)
    a = ap.parse_args()
    db.init_schema()
    files = sorted(p for p in Path(a.fhir_dir).glob("*.json") if not p.name.startswith(("hospital", "practitioner")))
    loaded = 0
    for f in files:
        out = load_bundle(f, loaded < a.accounts)
        if out:
            loaded += 1
            print(out)
    print(f"loaded {loaded} living Synthea patients")


if __name__ == "__main__":
    try:
        main()
    finally:
        db.close()
