"""Computes, caches and serves DDX rankings for an encounter."""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app import db
from app.context import load_patient

from . import evidence, guidance, runtime

log = logging.getLogger("prelude.ddx")
_schema_ready = False
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ddx")
_running: set[str] = set()
_running_lock = threading.Lock()

DISCLAIMER = ("Decision support for the clinician, not a diagnosis. Probabilities are the model's confidence among the "
              "59 conditions it knows (DDXPlus, synthetic, plus a generated urinary module); they are not calibrated "
              "clinical risks. No condition is shown above 80%: the model never claims certainty. Never shown to the patient.")


def ensure_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    db.exe("""CREATE TABLE IF NOT EXISTS ddx_predictions (
                ts timestamptz NOT NULL DEFAULT now(), encounter_id uuid NOT NULL, input_hash text NOT NULL,
                payload jsonb NOT NULL)""")
    db.exe("CREATE INDEX IF NOT EXISTS ddx_predictions_enc_ts ON ddx_predictions (encounter_id, ts DESC)")
    if db.FEATURES.get("timescaledb"):
        try:  # Tiger: a hypertable, so every prediction is a time series you can query and aggregate
            db.exe("SELECT create_hypertable('ddx_predictions', by_range('ts', INTERVAL '7 days'), "
                   "if_not_exists => true, migrate_data => true)")
        except Exception as e:  # noqa: BLE001
            log.info("ddx_predictions stays a plain table: %s", e)
    _schema_ready = True


def _inputs(encounter_id: str) -> tuple[dict, dict, list[dict], list[dict]]:
    enc = db.q1("SELECT * FROM encounters WHERE id = %s", (encounter_id,))
    if not enc:
        raise LookupError("encounter not found")
    ctx = load_patient(str(enc["patient_id"]))
    turns = db.q("SELECT question, answer, slot FROM interview_turns WHERE encounter_id = %s AND answer IS NOT NULL "
                 "ORDER BY id", (encounter_id,))
    # only the metrics the model reads (skips intraday heart rate, which would also churn the cache)
    obs = db.q("SELECT ts, code, value, unit, source FROM observations WHERE patient_id = %s "
               "AND ts > now() - interval '45 days' AND (code = ANY(%s) OR code LIKE 'lab:%%')",
               (str(enc["patient_id"]), list(HEALTH_CODES)))
    return enc, ctx, turns, obs


HEALTH_CODES = ("steps", "rhr", "spo2", "sleep_min", "weight", "bp_sys", "bp_dia", "resp_rate",
                "temp", "body_temp", "temperature")
CODE_VERSION = "6"  # bump when the evidence or ranking logic changes, so cached rankings refresh


def _model_version() -> str:
    try:
        st = (runtime.MODEL_DIR / "best_model.pkl").stat()
        return f"{st.st_size}-{int(st.st_mtime)}"
    except OSError:
        return "none"


def _hash(ctx: dict, turns: list[dict], obs: list[dict]) -> str:
    h = hashlib.sha1()
    h.update(f"{CODE_VERSION}|{_model_version()}|".encode())
    h.update(json.dumps({"p": ctx.get("profile"), "c": ctx.get("conditions"), "m": ctx.get("medications"),
                         "t": [(t["question"], t["answer"]) for t in turns],
                         "o": [len(obs), max((o["ts"] for o in obs), default=None)]}, default=str).encode())
    return h.hexdigest()[:16]


def _sex(ctx: dict) -> str | None:
    return {"female": "F", "male": "M"}.get(ctx.get("sex"))


def compute(encounter_id: str, force: bool = False) -> dict:
    ensure_schema()
    enc, ctx, turns, obs = _inputs(encounter_id)
    key = _hash(ctx, turns, obs)
    if not force:
        row = db.q1("SELECT payload FROM ddx_predictions WHERE encounter_id = %s AND input_hash = %s "
                    "ORDER BY ts DESC LIMIT 1", (encounter_id, key))
        if row:
            return row["payload"]
    media = [m.get("description") for m in (enc.get("state") or {}).get("media", []) if m.get("description")]
    ev = evidence.build(ctx, turns, obs, media_notes=media)
    age, sex = int(ctx["age"]), _sex(ctx)
    payload = {
        "encounter_id": encounter_id, "generated_at": datetime.now(timezone.utc).isoformat(),
        "patient": {"age": age, "sex": ctx.get("sex")},
        "in_scope": ev["in_scope"], "extraction": ev["extraction"],
        "evidence": [{"code": c, "label": evidence.label(c), "source": ev["sources"][c].split(":")[0],
                      "detail": ev["sources"][c]} for c in ev["codes"]],
        "denied": [{"code": c, "label": evidence.label(c)} for c in ev["denied"]],
        "health_context": ev["facts"], "disclaimer": DISCLAIMER,
        "ranked": [], "questions": [], "patient_steps": [], "confidence": {"level": "none"},
    }
    if not runtime.available():
        payload["error"] = "The DDX model files are missing on the server (backend/ddx/model)."
    elif ev["in_scope"]:
        ranked = guidance.rank(age, sex, ev["codes"], chief=ev["chief"])
        yes_no = [c for c in ev["chief"] if evidence.catalog()["evidences"].get(c, {}).get("data_type") == "B"]
        payload["main_complaint"] = [evidence.label(c) for c in (yes_no or ev["chief"])]
        payload.update(ranked=ranked, confidence=guidance.confidence(ranked),
                       questions=guidance.discriminating_questions(age, sex, ev["codes"], ranked, exclude=ev["denied"]),
                       patient_steps=guidance.patient_steps(ranked))
    db.exe("INSERT INTO ddx_predictions (encounter_id, input_hash, payload) VALUES (%s,%s,%s)",
           (encounter_id, key, db.J(payload)))
    return payload


def latest(encounter_id: str) -> dict | None:
    ensure_schema()
    row = db.q1("SELECT payload FROM ddx_predictions WHERE encounter_id = %s ORDER BY ts DESC LIMIT 1", (encounter_id,))
    return row["payload"] if row else None


def refresh_async(encounter_id: str) -> None:
    with _running_lock:
        if encounter_id in _running:
            return
        _running.add(encounter_id)

    def job():
        try:
            compute(encounter_id)
        except Exception as e:  # noqa: BLE001
            log.warning("ddx refresh failed for %s: %s", encounter_id[:8], e)
        finally:
            with _running_lock:
                _running.discard(encounter_id)

    _pool.submit(job)


# ----------------------------------------------------------------- hooks used by ClinicQuick
def lena_hint(encounter_id: str) -> str:
    """For interview._gemini_next(): the latest hint (non-blocking) + a background refresh for this turn."""
    try:
        refresh_async(encounter_id)
        return guidance.lena_hint(latest(encounter_id) or {})
    except Exception as e:  # noqa: BLE001  never break the interview
        log.warning("ddx hint failed: %s", e)
        return ""


def live_hint(encounter_id: str) -> str:
    """For live voice (app/live.py): recompute now (blocking, so call it from a thread) and return the hint."""
    try:
        return guidance.lena_hint(compute(encounter_id))
    except Exception as e:  # noqa: BLE001  never break the call
        log.warning("ddx live hint failed: %s", e)
        return ""


def patient_next_steps(encounter_id: str) -> list[str]:
    """For report.generate(): safe next steps for the patient (no condition names, no probabilities)."""
    try:
        return compute(encounter_id).get("patient_steps", [])
    except Exception as e:  # noqa: BLE001
        log.warning("ddx next steps failed: %s", e)
        return []
