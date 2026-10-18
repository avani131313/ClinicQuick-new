"""Health vault: uploaded records + lab extraction (Gemini multimodal) + Apple Health import."""
from __future__ import annotations

import io
import zipfile
from datetime import datetime
from xml.etree.ElementTree import iterparse

from pydantic import BaseModel

from . import db, gemini


class LabValue(BaseModel):
    test: str
    value: float | None = None
    value_text: str | None = None
    unit: str | None = None
    reference_range: str | None = None
    flag: str | None = None          # H, L, or null
    date: str | None = None          # YYYY-MM-DD if shown


class Extraction(BaseModel):
    document_type: str               # lab report, discharge summary, prescription, imaging report, other
    date: str | None = None
    issuer: str | None = None
    summary: str
    lab_values: list[LabValue] = []
    diagnoses_mentioned: list[str] = []
    medications_mentioned: list[str] = []


EXTRACT_SYSTEM = """You extract structured data from a patient's medical document (PDF or photo).
Copy values exactly as printed. Never infer values that aren't on the page. If something is unreadable, omit it.
summary: one plain-language sentence describing what the document is (no interpretation of results).
JSON only."""


def save_document(patient_id: str, filename: str, mime: str, content: bytes, uploaded_by: str, kind: str = "record") -> dict:
    row = db.q1("""INSERT INTO documents (patient_id, uploaded_by, kind, filename, mime, content)
                   VALUES (%s,%s,%s,%s,%s,%s) RETURNING id, ts""", (patient_id, uploaded_by, kind, filename, mime, content))
    doc = {"id": str(row["id"]), "filename": filename, "mime": mime, "kind": kind, "uploaded_by": uploaded_by,
           "ts": row["ts"].isoformat(), "extracted": None}
    if not (mime.startswith("image/") or mime == "application/pdf"):
        doc["read_error"] = "Saved. Automatic reading works on photos (JPG/PNG) and PDFs, so this file wasn't read."
    elif not gemini.enabled():
        doc["read_error"] = "Saved. Automatic reading needs the Gemini API key on the server."
    else:
        ex = gemini.generate_json(EXTRACT_SYSTEM, "Extract this document.", Extraction, smart=True,
                                  parts=[gemini.file_part(content, mime)], temperature=0, thinking="MINIMAL")
        if ex:
            db.exe("UPDATE documents SET extracted = %s WHERE id = %s", (db.J(ex.model_dump()), doc["id"]))
            doc["extracted"] = ex.model_dump()
        else:
            doc["read_error"] = ("Saved, but the AI couldn't read it this time (" + (gemini.LAST_ERROR or "no answer")[:140]
                                 + "). Try a clearer photo or try again.")
    return doc


def confirm_document(doc_id: str, patient_id: str) -> int:
    """Patient confirms the extraction → lab values become time-series observations."""
    d = db.q1("SELECT extracted, ts FROM documents WHERE id = %s AND patient_id = %s", (doc_id, patient_id))
    if not d or not d["extracted"]:
        return 0
    ex = d["extracted"]
    n = 0
    for lv in ex.get("lab_values", []):
        if lv.get("value") is None:
            continue
        when = lv.get("date") or ex.get("date")
        try:
            ts = datetime.fromisoformat(when) if when else d["ts"]
        except ValueError:
            ts = d["ts"]
        db.exe("INSERT INTO observations (patient_id, ts, code, value, unit, source) VALUES (%s,%s,%s,%s,%s,%s)",
               (patient_id, ts, "lab:" + lv["test"].lower(), lv["value"], lv.get("unit"), f"document:{doc_id}"))
        n += 1
    db.exe("UPDATE documents SET confirmed = true WHERE id = %s", (doc_id,))
    return n


def list_documents(patient_id: str) -> list[dict]:
    rows = db.q("""SELECT id, filename, mime, kind, uploaded_by, extracted, confirmed, ts FROM documents
                   WHERE patient_id = %s ORDER BY ts DESC""", (patient_id,))
    return [{**r, "id": str(r["id"]), "ts": r["ts"].isoformat()} for r in rows]


# ---------------------------------------------------------------------------
# Apple Health: Health app → profile → Export All Health Data → export.zip (contains export.xml)
# ---------------------------------------------------------------------------
APPLE_TYPES = {
    "HKQuantityTypeIdentifierStepCount": ("steps", "count", 1.0),
    "HKQuantityTypeIdentifierRestingHeartRate": ("rhr", "bpm", 1.0),
    "HKQuantityTypeIdentifierBodyMass": ("weight", "kg", 1.0),
    "HKQuantityTypeIdentifierOxygenSaturation": ("spo2", "%", 100.0),
    "HKQuantityTypeIdentifierHeartRate": ("hr", "bpm", 1.0),
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": ("hrv", "ms", 1.0),
    "HKQuantityTypeIdentifierRespiratoryRate": ("resp_rate", "breaths/min", 1.0),
    "HKQuantityTypeIdentifierActiveEnergyBurned": ("active_kcal", "kcal", 1.0),
    "HKQuantityTypeIdentifierBloodPressureSystolic": ("bp_sys", "mmHg", 1.0),
    "HKQuantityTypeIdentifierBloodPressureDiastolic": ("bp_dia", "mmHg", 1.0),
}


def import_apple_health(patient_id: str, data: bytes, days: int = 90) -> dict:
    if data[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(data))
        name = next((n for n in z.namelist() if n.endswith("export.xml")), None)
        if not name:
            raise ValueError("No export.xml inside the zip")
        stream = z.open(name)
    else:
        stream = io.BytesIO(data)
    cutoff = datetime.now().astimezone().timestamp() - days * 86400
    rows, counts, sleep_by_night = [], {}, {}
    for _, el in iterparse(stream, events=("end",)):
        if el.tag != "Record":
            el.clear()
            continue
        t = el.get("type")
        try:
            start = datetime.strptime(el.get("startDate"), "%Y-%m-%d %H:%M:%S %z")
        except (TypeError, ValueError):
            el.clear()
            continue
        if start.timestamp() < cutoff:
            el.clear()
            continue
        if t in APPLE_TYPES:
            code, unit, mult = APPLE_TYPES[t]
            try:
                v = float(el.get("value")) * mult
            except (TypeError, ValueError):
                el.clear()
                continue
            if code == "weight" and el.get("unit") == "lb":
                v *= 0.453592
            rows.append((patient_id, start, code, v, unit, "apple-health"))
            counts[code] = counts.get(code, 0) + 1
        elif t == "HKCategoryTypeIdentifierSleepAnalysis" and "Asleep" in (el.get("value") or ""):
            end = datetime.strptime(el.get("endDate"), "%Y-%m-%d %H:%M:%S %z")
            night = (start.date() if start.hour >= 12 else start.date().fromordinal(start.date().toordinal() - 1))
            sleep_by_night[night] = sleep_by_night.get(night, 0) + (end - start).total_seconds() / 60
        el.clear()
    for night, mins in sleep_by_night.items():
        rows.append((patient_id, datetime.combine(night.fromordinal(night.toordinal() + 1), datetime.min.time()).astimezone(),
                     "sleep_min", round(mins), "min", "apple-health"))
    counts["sleep_min"] = len(sleep_by_night)
    if rows:
        with db.conn() as c:
            with c.cursor().copy("COPY observations (patient_id, ts, code, value, unit, source) FROM STDIN") as cp:
                for r in rows:
                    cp.write_row(r)
        db.refresh_daily_obs()
    return {"imported": len(rows), "by_type": counts}
