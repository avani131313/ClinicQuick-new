"""Turns a ranking into (a) questions that would best separate the leading conditions,
(b) Lena's hidden hint, and (c) safe next steps for the patient that never name a condition."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import runtime
from .evidence import catalog


@lru_cache(maxsize=1)
def condition_symptoms() -> dict[str, list[str]]:
    """Which question codes each condition can produce (DDXPlus knowledge base + the urinary module)."""
    return json.loads((Path(__file__).resolve().parent / "data" / "condition_symptoms.json").read_text(encoding="utf-8"))

MUST_RULE_OUT_SEVERITY = 2      # DDXPlus severity 1-2 = serious; flag if probability >= 5%
MAX_PROBABILITY = 0.80          # never show certainty: no condition is shown above 80%
FEMALE_ONLY = {"E_306", "E_307", "E_145", "E_167", "E_163", "E_141", "E_11"}

# Safe, general next steps by condition. Shown to the patient WITHOUT the condition name.
ADVICE = {
    "Urinary tract infection (cystitis)": ["Drink plenty of water through the day.",
                                           "A pharmacist or clinician can test your urine; in Ontario pharmacists can assess "
                                           "uncomplicated urinary symptoms."],
    "Pyelonephritis (kidney infection)": ["If you get a fever, shaking chills or pain in your back or side, get seen today."],
    "Menstrual or gynecologic bleeding (not from urine)": ["Note the dates of your period; if blood appears outside your period, "
                                                           "tell your clinician."],
    "Kidney or ureteral stone": ["Drink plenty of water.", "Get seen urgently if the pain becomes severe, or you get a fever or vomiting."],
    "Exercise-induced hematuria": ["Rest from hard exercise for 2-3 days and stay well hydrated.",
                                   "If you still see blood after 3 days of rest, see a doctor."],
    "Glomerulonephritis (kidney inflammation)": ["Your clinician may want to check a urine sample and your blood pressure."],
    "Benign prostatic hyperplasia": ["Keep a note of how often you urinate, day and night, to show your clinician."],
    "URTI": ["Rest, fluids and warm drinks can ease symptoms; a pharmacist can suggest symptom relief."],
    "Viral pharyngitis": ["Warm drinks, lozenges and rest can ease a sore throat; a pharmacist can suggest relief."],
    "Influenza": ["Rest and drink fluids; stay home to avoid spreading it.",
                  "Get seen if breathing becomes difficult or you get worse after starting to improve."],
    "Bronchitis": ["Rest and fluids help; avoid smoke.", "See a clinician if the cough lasts more than 3 weeks or you get short of breath."],
    "Acute laryngitis": ["Rest your voice and drink fluids."],
    "Allergic sinusitis": ["Avoiding known triggers may help; a pharmacist can suggest allergy relief."],
    "Acute rhinosinusitis": ["Saline rinses, rest and fluids can help; a pharmacist can suggest relief."],
    "Chronic rhinosinusitis": ["Saline rinses may help; your clinician can discuss longer-term options."],
    "Acute otitis media": ["A pharmacist or clinician can check the ear; get seen if pain or fever is severe."],
    "GERD": ["Smaller meals and not eating within 3 hours of bed may help; a pharmacist can suggest relief."],
    "Panic attack": ["Slow breathing (in for 4, out for 6) can help in the moment.",
                     "If chest pain or breathlessness doesn't settle, get seen urgently."],
    "Anemia": ["Your clinician may want a blood test."],
    "Bronchospasm / acute asthma exacerbation": ["Use your reliever inhaler as prescribed; get urgent help if it isn't helping."],
}
SERIOUS_STEP = "Please see a doctor soon so this can be checked properly. Don't wait for it to go away on its own."


def cap_probabilities(p, cap: float = MAX_PROBABILITY) -> np.ndarray:
    """Clip every probability at `cap` and share the excess among the other conditions in proportion to
    their scores, so the 59 probabilities still add up to 100%."""
    p = np.asarray(p, dtype=float).copy()
    p = p / p.sum() if p.sum() > 0 else np.full(len(p), 1.0 / len(p))
    for _ in range(len(p)):
        excess = np.clip(p - cap, 0, None).sum()
        if excess <= 1e-12:
            break
        p = np.minimum(p, cap)
        room = p < cap
        w = p[room] if p[room].sum() > 0 else np.ones(room.sum())
        p[room] += excess * w / w.sum()
    return p


def rank(age: int, sex: str | None, codes: list[str], top: int = 5, chief: list[str] | None = None) -> list[dict]:
    p = runtime.scores([{"age": age, "sex": sex, "evidences": codes}])[0]
    names = runtime.labels()
    if chief:  # only conditions that can cause the main complaint (as in DDXPlus)
        ok = np.array([bool(set(condition_symptoms().get(n, [])) & set(chief)) for n in names])
        if ok.any() and p[ok].sum() > 0:
            p = np.where(ok, p, 0.0)
    p = cap_probabilities(p)
    conds = catalog()["conditions"]
    out = []
    for i in np.argsort(-p)[:top]:
        c = conds.get(names[i], {})
        sev = c.get("severity")
        out.append({"name": names[i], "probability": round(float(p[i]), 4), "icd10": c.get("icd10"),
                    "severity": sev, "must_rule_out": bool(sev and sev <= MUST_RULE_OUT_SEVERITY and p[i] >= 0.05)})
    return out


def confidence(ranked: list[dict]) -> dict:
    p = [r["probability"] for r in ranked]
    if not p:
        return {"level": "none", "text": "No ranking."}
    top, gap = p[0], p[0] - (p[1] if len(p) > 1 else 0)
    level = "high" if top >= 0.6 and gap >= 0.3 else "moderate" if top >= 0.35 else "low"
    text = {"high": "The model clearly favours one condition.",
            "moderate": "The model leans towards one condition, but others remain plausible.",
            "low": "The model is unsure: several conditions are similarly likely."}[level]
    return {"level": level, "top": top, "gap": round(gap, 4), "text": text}


def discriminating_questions(age: int, sex: str | None, codes: list[str], ranked: list[dict], k: int = 3,
                             exclude: list[str] | None = None) -> list[dict]:
    """Unasked yes/no symptom questions whose 'yes' would most change the leading probabilities."""
    ev = catalog()["evidences"]
    names = runtime.labels()
    lead = [names.index(r["name"]) for r in ranked[:3]]
    have = {c.partition("_@_")[0] for c in codes} | {c.partition("_@_")[0] for c in (exclude or [])}
    female = sex == "F" and 12 <= age <= 52
    # only questions that at least one leading condition actually produces (DDXPlus knowledge base)
    relevant = set().union(*(condition_symptoms().get(r["name"], []) for r in ranked[:3]))
    cands = [c for c in sorted(relevant) if c in ev and ev[c]["data_type"] == "B" and c not in have
             and (female or c not in FEMALE_ONLY)]
    if not cands:
        return []
    rows = [{"age": age, "sex": sex, "evidences": codes}] + [{"age": age, "sex": sex, "evidences": codes + [c]} for c in cands]
    s = runtime.scores(rows)
    base, alt = s[0, lead], s[1:, lead]
    # how much a "yes" re-orders the LEADING candidates among themselves ...
    rel_base = base / max(base.sum(), 1e-12)
    rel_alt = alt / np.maximum(alt.sum(axis=1, keepdims=True), 1e-12)
    shift = np.abs(rel_alt - rel_base).sum(axis=1)
    # ... counting only questions that keep the picture on these candidates (not ones pointing elsewhere)
    shift[alt.sum(axis=1) < 0.5 * base.sum()] = 0
    out = []
    for i in np.argsort(-shift)[:k]:
        if shift[i] < 0.05:
            break
        c = cands[i]
        moved = names[lead[int(np.argmax(rel_alt[i] - rel_base))]]
        out.append({"code": c, "question": ev[c]["question_en"], "shift": round(float(shift[i]), 3), "favours_if_yes": moved})
    return out


def patient_steps(ranked: list[dict]) -> list[str]:
    """Safe next steps for the patient. Never names a condition; never lowers urgency."""
    if any(r["must_rule_out"] or (r["severity"] and r["severity"] <= MUST_RULE_OUT_SEVERITY and r["probability"] >= 0.10)
           for r in ranked[:5]):
        return [SERIOUS_STEP]
    steps: list[str] = []
    for r in ranked[:2]:
        if r["probability"] >= 0.2:
            for s in ADVICE.get(r["name"], []):
                if s not in steps:
                    steps.append(s)
    return steps[:3]


def lena_hint(payload: dict) -> str:
    """Hidden context for Lena's next-question prompt. Never shown to the patient."""
    if not payload or not payload.get("ranked"):
        return ""
    lead = ", ".join(f'{r["name"]} ({r["probability"]:.0%})' for r in payload["ranked"][:3])
    qs = "\n".join(f'  - {q["question"]}' for q in payload.get("questions", []))
    steps = "\n".join(f"  - {s}" for s in payload.get("patient_steps", []))
    serious = any(r["must_rule_out"] for r in payload["ranked"])
    return (
        "\nDECISION-SUPPORT HINT (hidden from the patient; never mention it and never name any condition):\n"
        f"- A symptom model currently ranks for the clinician: {lead}.\n"
        + (f"- Questions that would best tell these apart (ask one in plain words if not already covered):\n{qs}\n" if qs else "")
        + (f"- Practical next steps you may offer near the end, without naming any condition:\n{steps}\n" if steps else "")
        + ("- A serious condition is in the list: encourage seeing a clinician promptly and never reassure.\n" if serious else "")
    )
