"""Builds the two outputs: the patient report (no disease list) and the nurse-style clinician note."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel

from . import care, db, gemini, scores, triage
from .context import compact, load_patient, memory, modifiers, remember
from .interview import SLOT_LABELS, SLOTS, transcript
from ddx.service import patient_next_steps as ddx_next_steps

DISCLAIMER = ("ClinicQuick is a pre-visit intake tool. It does not diagnose. Your clinician makes all decisions "
              "about your care. If you feel worse or have new severe symptoms, call 911.")

WATCH_FOR = {
    "general": ["New chest pain, trouble breathing, fainting, or confusion → call 911.",
                "A high fever that won't come down, or you feel much worse → be seen today."],
    "skin_scalp": ["Spreading redness, warmth, pus or fever → be seen today.",
                   "Patchy hair loss or no improvement after 2–4 weeks of treatment → see a doctor."],
    "skin": ["Spreading redness, warmth, swelling, red streaks or fever → be seen today.",
             "Blisters in the mouth or eyes, or skin peeling → go to the emergency department."],
    "hematuria": ["Clots, being unable to pee, fever, or severe side/back pain → go to the emergency department.",
                  "Feeling faint or very weak → call 911."],
    "headache": ["A sudden 'worst ever' headache, weakness, trouble speaking, or a stiff neck with fever → call 911."],
    "mood": ["If you have thoughts of harming yourself, call or text 9-8-8 any time, or 911 if you're in danger."],
}

SYSTEM = """You are a clinical documentation assistant writing up a nurse-style pre-visit intake.
Inputs: patient context with context_modifiers, the full Q&A transcript, rule-based urgency, and computed risk scores.

Write:
- chief_complaint: the main concern as a clinician would write it, 2-8 words, sentence case, no filler words or
  "I see/I have" (e.g. "Um, I see blood in urine" → "Blood in urine"; add duration if stated, e.g. "Headache for 3 days").
- patient_summary: 2-4 sentences in second person ("You told us..."), plain language, NO disease names,
  NO probabilities, no reassurance that it's nothing. Summarise what they reported and why the next step makes sense.
- ai_urgency: your independent view of urgency from the allowed list. It can only RAISE the rule-based level.
- urgency_reason: one sentence.
- hpi: one entry per OPQRST slot you have information for (onset, provocation, quality, region, severity, timing),
  concise clinical phrasing.
- associated: positives; relevant_negatives: pertinent negatives actually stated by the patient.
- considerations (clinician-only): 2-5 conditions to consider, ranked. likelihood in
  [higher, moderate, lower, must rule out]. 'because' = 1-3 short reasons, each citing an answer or a context
  modifier with ↑ or ↓ (e.g. "↑ age 68", "↑ former smoker", "↓ no fever"). Use age-appropriate priors.
  Never invent facts not in the transcript or context.
  wearable_trends (Apple Health / watch, last 7 days vs usual) may be cited too, e.g. "↓ steps 60% this week".
- ice: the patient's ideas, concerns and expectations in their words (short).
- one_liner: a clinical one-line summary (e.g. "19F, 3 wk itchy greasy scalp flaking, no hair loss, OTC shampoo tried").
JSON only."""


class HPI(BaseModel):
    slot: Literal["onset", "provocation", "quality", "region", "severity", "timing"]
    text: str


class Cons(BaseModel):
    name: str
    likelihood: Literal["higher", "moderate", "lower", "must rule out"]
    because: list[str]


class ReportOut(BaseModel):
    chief_complaint: str
    patient_summary: str
    ai_urgency: Literal["self_care", "pharmacist", "primary_care_soon", "walk_in_today", "er"]
    urgency_reason: str
    one_liner: str
    hpi: list[HPI]
    associated: list[str]
    relevant_negatives: list[str]
    considerations: list[Cons]
    ice: str


def _encounter_scores(ctx: dict, state: dict) -> list[scores.ScoreResult]:
    prof = dict(ctx["profile"])
    scr = state.get("screeners", {})
    if "phq2_1" in scr and "phq2_2" in scr:
        prof["phq2"] = [scr["phq2_1"], scr["phq2_2"]]
    if "gad2_1" in scr and "gad2_2" in scr:
        prof["gad2"] = [scr["gad2_1"], scr["gad2_2"]]
    if prof.get("audit_c"):
        prof["audit_c"] = list(prof["audit_c"])
    return scores.compute_profile_scores(prof)


def generate(encounter_id: str) -> dict:
    enc = db.q1("SELECT * FROM encounters WHERE id = %s", (encounter_id,))
    state = enc["state"]
    ctx = load_patient(str(enc["patient_id"]))
    tx = transcript(encounter_id)
    answered = [t for t in tx if t["answer"]]
    all_answers = "\n".join(t["answer"] for t in answered)
    complaint = enc["chief_complaint"] or state.get("slots", {}).get("chief_complaint", "")
    category = state.get("category") or triage.categorise(complaint)
    sev = None
    for t in answered:
        if t["slot"] == "severity":
            m = re.search(r"\b(10|[0-9])\b", t["answer"])
            sev = int(m.group(1)) if m else None
    rule_level, rule_reasons = triage.rule_urgency(ctx, category, complaint, all_answers, sev)
    score_results = _encounter_scores(ctx, state)
    if any(s.name in ("PHQ-2", "GAD-2") and s.severity == 2 for s in score_results) and triage.URGENCY[rule_level]["rank"] < 2:
        rule_level = "primary_care_soon"
        rule_reasons.append("A mood or anxiety screen was positive; a clinician follow-up is recommended.")

    ai: ReportOut | None = None
    if gemini.enabled():
        prompt = (f"PATIENT CONTEXT:\n{compact(ctx, memory(ctx['id'], k=4))}\n\n"
                  f"CHIEF COMPLAINT: {complaint}\nCATEGORY: {category}\n"
                  f"RULE-BASED URGENCY: {rule_level} — {rule_reasons}\n"
                  f"RISK SCORES: {[s.summary for s in score_results]}\n"
                  f"PATIENT PHOTOS/VIDEOS (objective descriptions): {[m['description'] for m in state.get('media', [])]}\n\n"
                  "TRANSCRIPT:\n" + "\n".join(f"[{t['type']}] Q: {t['question']}\nA: {t['answer']}" for t in answered))
        ai = gemini.generate_json(SYSTEM, prompt, ReportOut, smart=True, temperature=0.2)

    level = triage.combine(rule_level, ai.ai_urgency if ai else None)
    u = triage.URGENCY[level]
    reasons = list(rule_reasons)
    if ai and level != rule_level:
        reasons.append(f"Raised by AI review: {ai.urgency_reason}")
    ailment = triage.match_minor_ailment(complaint)
    complaint = (ai.chief_complaint.strip().rstrip(".") if ai and ai.chief_complaint.strip() else triage.tidy_complaint(complaint))

    # ---------------- patient report ----------------
    if ai:
        summary = ai.patient_summary
    else:
        bits = [f"You told us about: {complaint.strip().rstrip('.')}."]
        if state["slots"].get("onset"):
            bits.append(f"It started {state['slots']['onset'].lower().rstrip('.')}.")
        bits.append(f"Based on your answers, the best next step is: {u['label'].lower()}.")
        summary = " ".join(bits)
    next_steps = [f"{u['where']} — {u['when'].lower()}."]
    if level == "pharmacist" and ailment:
        next_steps.append(f"In Ontario, pharmacists can assess and prescribe for {ailment.lower()}. Show them your ClinicQuick summary.")
    if level in ("primary_care_soon", "walk_in_today"):
        next_steps.append("No family doctor? Use a walk-in clinic, or call Health811 (8-1-1) for nurse advice any time.")
    next_steps.extend(s for s in ddx_next_steps(encounter_id) if s not in next_steps)
    next_steps.append("Share your clinician summary at check-in so you don't have to repeat your story.")
    patient_report = {
        "urgency": {"level": level, **u, "reasons": reasons},
        "summary": summary,
        "next_steps": next_steps,
        "watch_for": WATCH_FOR.get(category, []) + WATCH_FOR["general"],
        "scores": [{"name": s.name, "band": s.band, "severity": s.severity, "summary": s.summary, "value": s.value}
                   for s in score_results if s.applicable],
        "snapshot": {"age": ctx["age"], "sex": ctx["sex"],
                     "bmi": next((s.value for s in score_results if s.name == "BMI"), None),
                     "medications": len(ctx["medications"]), "conditions": len(ctx["conditions"]),
                     "allergies": len(ctx["allergies"])},
        "disclaimer": DISCLAIMER,
    }

    # ---------------- clinician note ----------------
    slots = state.get("slots", {})
    if ai:
        hpi = [{"slot": h.slot, "label": SLOT_LABELS[h.slot], "text": h.text} for h in ai.hpi]
        associated, negatives, ice, one_liner = ai.associated, ai.relevant_negatives, ai.ice, ai.one_liner
        considerations = [c.model_dump() for c in ai.considerations]
    else:
        hpi = [{"slot": s, "label": SLOT_LABELS[s], "text": slots[s]} for s in
               ("onset", "provocation", "quality", "region", "severity", "timing") if s in slots]
        associated = [slots["associated"]] if "associated" in slots else []
        negatives = [slots["negatives"]] if "negatives" in slots else []
        ice = slots.get("ice", "")
        one_liner = f"{ctx['age']}{ctx['sex'][0].upper()}, {complaint.strip()[:90]}"
        considerations = triage.offline_considerations(ctx, category, all_answers + " " + complaint)
    screens = state.get("screens_negative", [])
    trends = care.daily_series(ctx["id"], 30)
    clinician = {
        "patient": {"name": ctx["name"], "age": ctx["age"], "sex": ctx["sex"], "dob": ctx["dob"]},
        "one_liner": one_liner,
        "chief_complaint": complaint,
        "hpi": hpi,
        "associated": associated,
        "relevant_negatives": negatives,
        "red_flag_screen": {"performed": True, "result": "negative",
                            "detail": "Every answer was scanned by the hard-coded red-flag engine"
                                      + (f"; targeted screens negative: {', '.join(screens)}" if screens else "") + "."},
        "pmh": ctx["conditions"], "medications": ctx["medications"], "allergies": ctx["allergies"],
        "family_history": ctx["profile"].get("family_history") or [],
        "social_history": {"smoking": ctx["profile"].get("smoking"),
                           "alcohol_audit_c": list(ctx["profile"]["audit_c"]) if ctx["profile"].get("audit_c") else None},
        "context_modifiers": modifiers(ctx),
        "risk_scores": [s.to_dict() for s in score_results],
        "trends": care._sparkline(trends, 30) if trends else {},
        "considerations": considerations,
        "considerations_note": "For clinician review only. Not shown to the patient. Not a diagnosis.",
        "ice": ice,
        "urgency": {"level": level, **u, "reasons": reasons},
        "minor_ailment_match": ailment,
        "transcript": tx,
        "media": state.get("media", []),
        "generated_by": "gemini" if ai else "offline-rules",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    db.exe("DELETE FROM risk_scores WHERE encounter_id = %s", (encounter_id,))
    for s in score_results:
        db.exe("""INSERT INTO risk_scores (patient_id, encounter_id, name, version, inputs, value, band, severity,
                  summary, citation, citation_url) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
               (ctx["id"], encounter_id, s.name, s.version, db.J(s.inputs), s.value, s.band, s.severity, s.summary,
                s.citation, s.citation_url))
    db.exe("""INSERT INTO reports (encounter_id, patient_json, clinician_json, generated_by) VALUES (%s,%s,%s,%s)
              ON CONFLICT (encounter_id) DO UPDATE SET patient_json = EXCLUDED.patient_json,
              clinician_json = EXCLUDED.clinician_json, generated_by = EXCLUDED.generated_by, created_at = now()""",
           (encounter_id, db.J(patient_report), db.J(clinician), clinician["generated_by"]))
    db.exe("UPDATE encounters SET urgency = %s, chief_complaint = %s, ended_at = now(), status = 'complete' WHERE id = %s",
           (level, complaint, encounter_id))
    remember(ctx["id"], f"{datetime.now().strftime('%b %Y')} intake: {one_liner}. Routed to: {u['label']}.")
    return {"patient": patient_report, "clinician": clinician}


def get(encounter_id: str) -> dict | None:
    r = db.q1("SELECT * FROM reports WHERE encounter_id = %s", (encounter_id,))
    if not r:
        return None
    return {"patient": r["patient_json"], "clinician": r["clinician_json"], "generated_by": r["generated_by"]}
