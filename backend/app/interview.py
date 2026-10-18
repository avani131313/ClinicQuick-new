"""The interview engine: a slot-driven state machine with Gemini choosing the next question.

Every turn:  (1) red-flag check in code  →  (2) next question (Gemini, or offline protocol)
             →  (3) store the turn with its type tag and rationale.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from . import db, gemini, safety, triage
from .config import MAX_QUESTIONS
from .context import compact, load_patient, memory
from ddx.service import lena_hint as ddx_hint

log = logging.getLogger("prelude.interview")

SLOTS = ["onset", "provocation", "quality", "region", "severity", "timing",
         "associated", "negatives", "tried", "impact", "ice"]
SLOT_LABELS = {
    "chief_complaint": "Main concern", "onset": "Onset", "provocation": "Triggers / relief", "quality": "Quality",
    "region": "Location / spread", "severity": "Severity", "timing": "Timing / pattern",
    "associated": "Other symptoms", "negatives": "Relevant negatives", "tried": "What you've tried",
    "impact": "Impact on life", "ice": "Your concerns",
}
REQUIRED = ["onset", "severity", "timing", "associated", "negatives", "tried", "ice"]


def required_for(category: str | None) -> list[str]:
    """Painless complaints (e.g. blood in urine) don't need a 0-10 severity."""
    if category in ("hematuria",):
        return [s for s in REQUIRED if s != "severity"]
    return REQUIRED

PHQ_OPTIONS = ["Not at all", "Several days", "More than half the days", "Nearly every day"]
SCREENER_ITEMS = {
    "phq2_1": "Over the last 2 weeks, how often have you had little interest or pleasure in doing things?",
    "phq2_2": "Over the last 2 weeks, how often have you felt down, depressed, or hopeless?",
    "gad2_1": "Over the last 2 weeks, how often have you felt nervous, anxious, or on edge?",
    "gad2_2": "Over the last 2 weeks, how often have you not been able to stop or control worrying?",
}

INTERVIEWER_SYSTEM = """You are Lena, an AI intake assistant working like an experienced triage nurse.
You interview a patient BEFORE they see a clinician and gather a complete, structured history.

Rules:
- Ask exactly ONE short question (max 25 words), warm and professional, plain language, no jargon.
- Never diagnose, never name a disease to the patient, never reassure that something is "nothing".
- Cover the OPQRST framework plus associated symptoms, relevant negatives, what they've tried, impact on life,
  and ICE (their ideas, concerns, expectations). Use the slot list to see what is still missing.
- Prefer DISCRIMINATING questions: ones whose answer would separate the leading considerations
  (e.g. flaky scalp → greasy-yellow vs dry-white flakes; eyebrows/behind ears involved; patchy hair loss; new products).
- Personalise using the patient context and context_modifiers (age, medications such as anticoagulants, smoking,
  pregnancy, conditions, past-visit memory). When you do, set question_type to AI_PERSONALISED and say why in rationale.
  Use STANDARD when the question is a generic framework question anyone would be asked.
- If an emergency is plausible but not yet asked about, set screen_red_flag to one of:
  chest_pain, stroke, breathing, suicide_risk, meningitis, major_bleeding, anaphylaxis. Code will ask a fixed
  safety question and judge the answer. Otherwise leave it null.
- topics: tag broad themes from this list if present: mood, sleep, fatigue, stress, anxiety, pain, skin, urinary, breathing.
- Keep output SHORT so the patient isn't kept waiting: rationale ≤ 15 words, at most 4 considerations,
  each 'because' ≤ 12 words, slot summaries ≤ 12 words. Only list slots_filled that changed this turn.
- considerations are for the CLINICIAN only (never shown to the patient): 2-4 conditions worth considering,
  each with a direction relative to the general population and a 'because' that cites a specific context modifier
  or answer (e.g. "↑ age 68, ↑ former smoker"). Use age-appropriate priors: in a 16-year-old athlete with hematuria,
  exercise-related and infectious causes lead; in a 68-year-old former smoker, malignancy must be ruled out.
- slots_filled: list each slot you now have enough information for, with a 3-12 word summary in the patient's terms.
- If the patient shared a photo or video, use its description: ask about what it shows (how it has changed,
  whether it hurts, how big it was at first) and never contradict it. If a skin or visible complaint has no
  photo yet, you may invite one once ("If you can, add a photo using the camera button").
- If wearable_trends in the patient context show a clear change that could relate to their concern (e.g. steps down, resting heart rate up, less sleep), mention it once, naturally, and ask about it — e.g. "Your watch shows you've been walking a lot less this week than usual — is that because of this?" Never read out raw numbers lists.
- Set done=true when the required slots are covered (or nothing important is left), otherwise false.
Respond with JSON only."""


class SlotFill(BaseModel):
    slot: Literal["onset", "provocation", "quality", "region", "severity", "timing",
                  "associated", "negatives", "tried", "impact", "ice", "other"]
    summary: str


class Consideration(BaseModel):
    name: str
    direction: Literal["up", "down", "neutral"] = "neutral"
    because: str


class InterviewerOut(BaseModel):
    next_question: str = Field(description="the single next question to ask")
    question_type: Literal["STANDARD", "AI_PERSONALISED"]
    slot: Literal["onset", "provocation", "quality", "region", "severity", "timing",
                  "associated", "negatives", "tried", "impact", "ice", "other"]
    rationale: str
    screen_red_flag: Literal["chest_pain", "stroke", "breathing", "suicide_risk", "meningitis",
                             "major_bleeding", "anaphylaxis"] | None = None
    slots_filled: list[SlotFill] = []
    considerations: list[Consideration] = []
    topics: list[str] = []
    done: bool = False


# ---------------------------------------------------------------------------
# Offline protocol (no API key / API down). Category-specific, still systematic.
# ---------------------------------------------------------------------------
GENERIC = [
    ("onset", "When did this start, and did it come on suddenly or gradually?"),
    ("severity", "On a scale of 0 to 10, how bad is it at its worst?"),
    ("timing", "Is it there all the time, or does it come and go? Is it getting better, worse, or staying the same?"),
    ("provocation", "Does anything make it better or worse?"),
    ("associated", "Have you noticed any other symptoms alongside it?"),
    ("negatives", "Any fever, weight loss you can't explain, or night sweats?"),
    ("tried", "Have you tried anything for it so far, and did it help?"),
    ("impact", "How is this affecting your daily life — sleep, work, school, or activities?"),
    ("ice", "What are you most worried this might be, and what are you hoping we can help with?"),
]
CATEGORY_Q = {
    "skin_scalp": [
        ("onset", "When did you first notice the flaking or itch?"),
        ("quality", "Are the flakes more greasy and yellowish, or dry and white? Any thick, raised patches?"),
        ("region", "Is it only on your scalp, or also on your eyebrows, around your nose, behind your ears, or elsewhere?"),
        ("severity", "How itchy is it from 0 to 10, and does it ever bleed or ooze when you scratch?"),
        ("provocation", "Does it get worse with cold weather, stress, or a new shampoo, hair dye, or product?"),
        ("associated", "Any hair loss or bald patches, or any rashes on your elbows, knees, or nails?"),
        ("tried", "Have you tried any shampoos or treatments yet? What happened?"),
        ("impact", "Is it affecting your sleep, confidence, or daily routine?"),
        ("ice", "What are you most worried about with this, and what would you like to get out of a visit?"),
    ],
    "skin": [
        ("onset", "When did you first notice it, and did it appear suddenly or slowly?"),
        ("quality", "What does it look like — what colour, is it raised or flat, and is there any flaking, blisters or oozing?"),
        ("region", "Where on your body is it, and has it spread anywhere since it started?"),
        ("severity", "How itchy or sore is it from 0 to 10?"),
        ("provocation", "Did anything new happen before it started — a new soap, cream, detergent, food, medicine, plant, or pet?"),
        ("associated", "Is the skin warm, swollen or getting bigger, and have you had a fever or felt unwell?"),
        ("tried", "Have you put anything on it or taken anything for it? Did it help?"),
        ("impact", "Is it affecting your sleep or daily life?"),
        ("ice", "What are you most worried about, and what would you like help with?"),
    ],
    "hematuria": [
        ("onset", "When did you first notice blood in your urine, and how many times has it happened?"),
        ("quality", "What colour is it — pink, red, or brown like cola? Have you seen any clots?"),
        ("timing", "Is the blood there for the whole stream, or just at the start or end?"),
        ("associated", "Any pain or burning when you pee, needing to go more often, or pain in your side or back?"),
        ("provocation", "Did it follow hard exercise, an injury, or a recent sore throat or infection?"),
        ("negatives", "Any fever, chills, unexplained weight loss, or feeling unusually tired?"),
        ("tried", "Have you changed anything since — drinking more water, stopping exercise, any medicines?"),
        ("ice", "What worries you most about this, and what are you hoping to get from your visit?"),
    ],
    "headache": [
        ("onset", "When did this headache start, and did it build up or hit suddenly?"),
        ("region", "Where is the pain — front, sides, back of the head, or behind one eye?"),
        ("quality", "What does it feel like — tight band, throbbing, or stabbing?"),
        ("severity", "From 0 to 10, how bad is it at its worst?"),
        ("associated", "Any nausea, sensitivity to light or sound, or changes in your vision?"),
        ("timing", "How often do you get headaches like this, and how long do they last?"),
        ("tried", "Have you taken anything for it? How much and how often this week?"),
        ("impact", "Is it stopping you from working, studying, or sleeping?"),
        ("ice", "What are you most worried this might be?"),
    ],
}
PERSONALISED_RULES = [
    # (category or '*', modifier key, slot, question, rationale)
    ("hematuria", "menstruating_age", "associated",
     "Could this be linked to your period — when did your last period start, and are you on it now?",
     "Female of menstruating age; menstrual blood can look like blood in urine."),
    ("hematuria", "anticoagulant", "associated",
     "Since you take a blood thinner — have you noticed other bleeding, like bleeding gums, nosebleeds, or easy bruising?",
     "Patient takes an anticoagulant; checks for generalised bleeding."),
    ("hematuria", "smoking", "negatives",
     "Your profile says you used to smoke — have you noticed any change in your energy, appetite, or weight lately?",
     "Former smoker with hematuria; screens for systemic features."),
    ("*", "pregnant", "associated",
     "Since you may be pregnant — any bleeding, cramping, or changes you've noticed?",
     "Pregnancy changes urgency and medication options."),
]


def must_ask(ctx: dict, category: str | None) -> list[str]:
    """Personalised questions code insists on for this patient + complaint (e.g. period timing for hematuria in a woman)."""
    mods = {m["key"] for m in compact(ctx, [])["context_modifiers"]}
    return [f"{q} ({why})" for c, mod, _slot, q, why in PERSONALISED_RULES
            if (c == category or c == "*") and mod in mods]


def _offline_next(state: dict, ctx: dict) -> dict | None:
    cat = state.get("category", "general")
    asked_qs = set(state.get("asked_questions", []))
    filled = set(state.get("slots", {}).keys())
    mods = {m["key"] for m in compact(ctx, [])["context_modifiers"]}
    for c, mod, slot, q, why in PERSONALISED_RULES:
        if len(asked_qs) >= 2 and (c == cat or c == "*") and mod in mods and q not in asked_qs:
            return {"question": q, "q_type": "PERSONALISED", "slot": slot, "rationale": f"Rule-based: {why}"}
    for slot, q in CATEGORY_Q.get(cat, GENERIC):
        if q not in asked_qs and slot not in filled:
            return {"question": q, "q_type": "STANDARD", "slot": slot, "rationale": f"Protocol ({cat}) — {SLOT_LABELS[slot]}"}
    for slot, q in GENERIC:
        if slot in required_for(cat) and slot not in filled and q not in asked_qs:
            return {"question": q, "q_type": "STANDARD", "slot": slot, "rationale": f"Framework — {SLOT_LABELS[slot]}"}
    return None


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------
def _turns(encounter_id: str) -> list[dict]:
    return db.q("SELECT * FROM interview_turns WHERE encounter_id = %s ORDER BY id", (encounter_id,))


def _pending(encounter_id: str) -> dict | None:
    return db.q1("SELECT * FROM interview_turns WHERE encounter_id = %s AND answer IS NULL ORDER BY id DESC LIMIT 1",
                 (encounter_id,))


def _save_state(encounter_id: str, state: dict, **cols) -> None:
    sets = ", ".join([f"{k} = %s" for k in cols] + ["state = %s"])
    db.exe(f"UPDATE encounters SET {sets} WHERE id = %s", list(cols.values()) + [db.J(state), encounter_id])


def _ask(encounter_id: str, state: dict, q: dict) -> dict:
    db.exe("INSERT INTO interview_turns (encounter_id, question, q_type, slot, rationale) VALUES (%s,%s,%s,%s,%s)",
           (encounter_id, q["question"], q["q_type"], q.get("slot"), q.get("rationale")))
    state.setdefault("asked_questions", []).append(q["question"])
    if q.get("options"):
        state["pending_options"] = q["options"]
    else:
        state.pop("pending_options", None)
    return q


def coverage(state: dict) -> list[dict]:
    slots = state.get("slots", {})
    keys = ["chief_complaint"] + SLOTS
    return [{"slot": k, "label": SLOT_LABELS[k], "done": k in slots, "summary": slots.get(k)} for k in keys]


def public_view(encounter: dict, q: dict | None = None, stop: dict | None = None, done: bool = False) -> dict:
    state = encounter["state"]
    if stop is None and encounter.get("status") == "stopped_red_flag":
        stop = state.get("red_flag")
    return {
        "encounter_id": str(encounter["id"]),
        "status": "stopped_red_flag" if stop else ("complete" if done else encounter["status"]),
        "question": None if q is None else {"text": q["question"], "type": q["q_type"], "slot": q.get("slot"),
                                            "options": q.get("options")},
        "coverage": coverage(state),
        "asked": len(state.get("asked_questions", [])),
        "max_questions": MAX_QUESTIONS,
        "red_flag": stop,
        "done": done,
        "mode": state.get("mode", "offline"),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def start(patient_id: str) -> dict:
    ctx = load_patient(patient_id)
    state = {"slots": {}, "asked_questions": [], "considerations": [], "topics": [],
             "mode": "gemini" if gemini.enabled() else "offline", "screen_unclear": 0}
    enc = db.q1("INSERT INTO encounters (patient_id, state) VALUES (%s, %s) RETURNING *", (patient_id, db.J(state)))
    hello = f"Hi {ctx['first_name']}, I'm Lena, an AI intake assistant. I'll ask a few questions so your clinician has the full picture before you meet."
    q = {"question": hello + " What's brought you in today?", "q_type": "STANDARD", "slot": "chief_complaint",
         "rationale": "Opening question — chief complaint"}
    _ask(str(enc["id"]), state, q)
    _save_state(str(enc["id"]), state)
    enc["state"] = state
    return public_view(enc, q)


def _stop(enc: dict, state: dict, rf: safety.RedFlagResult) -> dict:
    eid = str(enc["id"])
    db.exe("INSERT INTO red_flag_events (encounter_id, flag, label, matched_text, action) VALUES (%s,%s,%s,%s,%s)",
           (eid, rf.flag, rf.label, rf.matched_text, rf.action))
    state["red_flag"] = rf.to_dict()
    _save_state(eid, state, status="stopped_red_flag", urgency="emergency_911" if rf.action != "GO_TO_ER" else "er",
                ended_at=datetime.now(timezone.utc))
    enc["state"] = state
    return public_view(enc, None, stop=rf.to_dict())


def answer(encounter_id: str, text: str) -> dict:
    t0 = time.time()
    try:
        return _answer(encounter_id, text)
    finally:
        log.info("turn %s took %.1fs", encounter_id[:8], time.time() - t0)


def _answer(encounter_id: str, text: str) -> dict:
    enc = db.q1("SELECT * FROM encounters WHERE id = %s", (encounter_id,))
    if not enc or enc["status"] != "active":
        raise ValueError("This interview is no longer active.")
    state = enc["state"]
    ctx = load_patient(str(enc["patient_id"]))
    pend = _pending(encounter_id)
    text = (text or "").strip()

    # 1. Safety: screening answers are judged by code; everything else is scanned.
    if pend and pend["q_type"] == "SAFETY_SCREEN":
        flag = state.get("pending_screen")
        status, rf = safety.evaluate_screen(flag, text, ctx["profile"])
        db.exe("UPDATE interview_turns SET answer = %s WHERE id = %s", (text, pend["id"]))
        if status == "positive":
            return _stop(enc, state, rf)
        if status == "unclear":
            state["screen_unclear"] = state.get("screen_unclear", 0) + 1
            if state["screen_unclear"] >= 2:
                return _stop(enc, state, safety.force_flag(flag, ctx["profile"]))
            q = {"question": "Sorry, I need a clear answer for safety: " + safety.SCREENING_QUESTIONS[flag] + " (yes or no)",
                 "q_type": "SAFETY_SCREEN", "slot": "safety", "rationale": "Re-asking unclear safety answer", "options": ["Yes", "No"]}
            _ask(encounter_id, state, q)
            _save_state(encounter_id, state)
            enc["state"] = state
            return public_view(enc, q)
        state["screen_unclear"] = 0
        state.setdefault("screens_negative", []).append(flag)
        state.pop("pending_screen", None)
    else:
        rf = safety.check_message(text, ctx["profile"])
        if rf:
            if pend:
                db.exe("UPDATE interview_turns SET answer = %s WHERE id = %s", (text, pend["id"]))
            return _stop(enc, state, rf)
        if pend:
            db.exe("UPDATE interview_turns SET answer = %s WHERE id = %s", (text, pend["id"]))

    # 2. Record what we learned.
    slot = pend["slot"] if pend else None
    if slot == "chief_complaint":
        state["slots"]["chief_complaint"] = triage.tidy_complaint(text)
        state["category"] = triage.categorise(text)
        db.exe("UPDATE encounters SET chief_complaint = %s WHERE id = %s", (triage.tidy_complaint(text), encounter_id))
        if state["category"] == "mood":
            state["topics"] = list(set(state.get("topics", [])) | {"mood"})
    elif slot in SCREENER_ITEMS:
        idx = _option_index(text)
        state.setdefault("screeners", {})[slot] = idx
    elif slot in SLOTS and state["mode"] == "offline":
        if slot == "negatives" and safety.NO.search(safety._normalise(text)) and pend:
            asked = re.sub(r"^(any|have you had any)\s+", "", pend["question"].rstrip("?").strip(), flags=re.I)
            state["slots"][slot] = f"Denies {asked}"[:120]
        else:
            state["slots"][slot] = text[:120]

    # 3. Next question.
    q = _next_question(encounter_id, state, ctx)
    if q is None:
        _save_state(encounter_id, state, status="complete")
        enc["state"] = state
        return public_view(enc, None, done=True)
    _ask(encounter_id, state, q)
    _save_state(encounter_id, state)
    enc["state"] = state
    return public_view(enc, q)


def _option_index(text: str) -> int:
    t = text.strip().lower()
    for i, o in enumerate(PHQ_OPTIONS):
        if t == o.lower():
            return i
    if re.match(r"^[0-3]$", t):
        return int(t)
    if "nearly" in t or "every day" in t:
        return 3
    if "more than half" in t:
        return 2
    if "several" in t or "some" in t:
        return 1
    return 0


def _next_question(encounter_id: str, state: dict, ctx: dict) -> dict | None:
    asked = len(state.get("asked_questions", []))
    if asked >= MAX_QUESTIONS + 4:      # hard ceiling including screeners
        return None

    # Validated screeners are inserted by code (fixed wording, fixed options) when mood topics appear.
    if "mood" in set(state.get("topics", [])) or state.get("category") == "mood":
        for key in ("phq2_1", "phq2_2", "gad2_1", "gad2_2"):
            if key not in state.get("screeners", {}) and SCREENER_ITEMS[key] not in state.get("asked_questions", []):
                return {"question": SCREENER_ITEMS[key], "q_type": "STANDARD", "slot": key,
                        "rationale": "Validated screener (PHQ-2 / GAD-2) — fixed wording", "options": PHQ_OPTIONS}

    if asked >= MAX_QUESTIONS:
        return None

    if state["mode"] == "gemini":
        out = _gemini_next(encounter_id, state, ctx)
        if out is not None:
            for s in out.slots_filled:
                if s.slot != "other":
                    state["slots"][s.slot] = s.summary
            if out.considerations:
                state["considerations"] = [c.model_dump() for c in out.considerations]
            state["topics"] = sorted(set(state.get("topics", [])) | {t.lower() for t in out.topics})
            if out.screen_red_flag and out.screen_red_flag not in state.get("screens_negative", []):
                state["pending_screen"] = out.screen_red_flag
                return {"question": safety.SCREENING_QUESTIONS[out.screen_red_flag], "q_type": "SAFETY_SCREEN",
                        "slot": "safety", "rationale": f"AI requested a safety screen ({out.screen_red_flag}); code judges the answer.",
                        "options": ["Yes", "No"]}
            required_left = [s for s in required_for(state.get("category")) if s not in state["slots"]]
            if out.done and not required_left:
                return None
            if out.done and required_left:
                pass  # fall through: Gemini thought it was done but a required slot is empty → ask it anyway
            else:
                if out.next_question.strip() not in state.get("asked_questions", []):
                    return {"question": out.next_question.strip(), "q_type": out.question_type, "slot": out.slot,
                            "rationale": out.rationale}
        state["mode_fallbacks"] = state.get("mode_fallbacks", 0) + 1
    # offline path (or Gemini failure on this turn)
    return _offline_next(state, ctx)


def _gemini_next(encounter_id: str, state: dict, ctx: dict) -> InterviewerOut | None:
    turns = [t for t in _turns(encounter_id) if t["answer"] is not None]
    transcript = "\n".join(f"Q ({t['q_type']}, {t['slot']}): {t['question']}\nA: {t['answer']}" for t in turns)
    complaint = state["slots"].get("chief_complaint", "")
    # Retrieve patient memory once per interview (an embedding call each turn adds ~1s)
    if "memory" not in state:
        state["memory"] = memory(ctx["id"], query=complaint)
    mem = state["memory"]
    remaining = MAX_QUESTIONS - len(state.get("asked_questions", []))
    prompt = (
        f"PATIENT CONTEXT (JSON):\n{compact(ctx, mem)}\n\n"
        f"SLOTS ALREADY FILLED: {state.get('slots', {})}\n"
        f"REQUIRED SLOTS STILL MISSING: {[s for s in required_for(state.get('category')) if s not in state.get('slots', {})]}\n"
        f"SAFETY SCREENS ALREADY NEGATIVE: {state.get('screens_negative', [])}\n"
        f"PHOTOS/VIDEOS THE PATIENT SHARED (objective descriptions): {[m['description'] for m in state.get('media', [])]}\n"
        f"MUST ASK FOR THIS PATIENT (if not already answered): {must_ask(ctx, state.get('category'))}\n"
        f"QUESTIONS REMAINING BUDGET: {remaining}\n\n"
        f"TRANSCRIPT SO FAR:\n{transcript}\n\n"
        f"{ddx_hint(encounter_id)}\n"
        "Return the next question JSON."
    )
    return gemini.generate_json(INTERVIEWER_SYSTEM, prompt, InterviewerOut, temperature=0.4)


def transcript(encounter_id: str) -> list[dict]:
    return [{"question": t["question"], "answer": t["answer"], "type": t["q_type"], "slot": t["slot"],
             "rationale": t["rationale"], "ts": t["ts"].isoformat()} for t in _turns(encounter_id)]
