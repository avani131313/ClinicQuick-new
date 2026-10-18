"""Validated clinical scores, computed in plain Python.

Gemini never computes a number. It can suggest which score applies and help
extract inputs from a transcript; the arithmetic and the citation live here.
Every function returns a ScoreResult so the UI and the clinician note can show
inputs, value, band, and source the same way.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import date


@dataclass
class ScoreResult:
    name: str
    version: str
    value: float | int | None
    band: str            # e.g. "low", "moderate", "high", "positive screen", "not applicable"
    severity: int        # 0 = fine, 1 = watch, 2 = act — used for colours and sorting
    summary: str         # one plain-language line, written by code
    inputs: dict
    citation: str
    citation_url: str
    applicable: bool = True
    missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def age_from_dob(dob: str | date, today: date | None = None) -> int:
    d = date.fromisoformat(dob) if isinstance(dob, str) else dob
    t = today or date.today()
    return t.year - d.year - ((t.month, t.day) < (d.month, d.day))


# ---------------------------------------------------------------------------
# BMI
# ---------------------------------------------------------------------------
def bmi(height_cm: float | None, weight_kg: float | None) -> ScoreResult:
    if not height_cm or not weight_kg:
        return ScoreResult("BMI", "WHO", None, "unknown", 0, "Height or weight missing.",
                           {"height_cm": height_cm, "weight_kg": weight_kg},
                           "WHO BMI classification", "https://www.who.int/data/gho/data/themes/topics/topic-details/GHO/body-mass-index",
                           missing=["height_cm" if not height_cm else "weight_kg"])
    v = round(weight_kg / (height_cm / 100) ** 2, 1)
    if v < 18.5:
        band, sev = "underweight", 1
    elif v < 25:
        band, sev = "healthy range", 0
    elif v < 30:
        band, sev = "overweight", 1
    else:
        band, sev = "obesity range", 1
    return ScoreResult("BMI", "WHO", v, band, sev, f"BMI {v} ({band}).",
                       {"height_cm": height_cm, "weight_kg": weight_kg},
                       "WHO BMI classification", "https://www.who.int/data/gho/data/themes/topics/topic-details/GHO/body-mass-index")


# ---------------------------------------------------------------------------
# CANRISK — Canadian Diabetes Risk Questionnaire (PHAC). Validated for ages 40–74.
# Point values taken from the published questionnaire form.
# ---------------------------------------------------------------------------
CANRISK_URL = "https://canadiantaskforce.ca/tools-resources/type-2-diabetes-2/type-2-diabetes-canrisk/"
CANRISK_ETHNICITY_POINTS = {
    "white": 0, "aboriginal": 3, "indigenous": 3, "black": 5, "east_asian": 10,
    "south_asian": 11, "other_non_white": 3, "prefer_not_to_say": 0, None: 0,
}
CANRISK_EDUCATION_POINTS = {
    "some_high_school_or_less": 5, "high_school": 1, "some_college": 0, "degree": 0,
    "prefer_not_to_say": 0, None: 0,
}


def canrisk(p: dict) -> ScoreResult:
    """p keys: age, sex ('male'|'female'), bmi, waist_cm, active_30min_daily (bool),
    fruit_veg_daily (bool), high_bp (bool), high_blood_sugar (bool), baby_over_4kg (bool),
    family_diabetes (list of 'mother','father','sibling','child','other'),
    parent_ethnicities (list), education (str)."""
    age = p.get("age")
    inputs = {k: p.get(k) for k in (
        "age", "sex", "bmi", "waist_cm", "active_30min_daily", "fruit_veg_daily", "high_bp",
        "high_blood_sugar", "baby_over_4kg", "family_diabetes", "parent_ethnicities", "education")}
    if age is None or age < 40 or age > 74:
        return ScoreResult("CANRISK", "PHAC 2011", None, "not applicable", 0,
                           "CANRISK is validated for adults aged 40 to 74.", inputs,
                           "Canadian Diabetes Risk Questionnaire (CANRISK), PHAC", CANRISK_URL,
                           applicable=False)
    pts = 0
    pts += 0 if age < 45 else 7 if age < 55 else 13 if age < 65 else 15
    male = (p.get("sex") or "").lower() == "male"
    pts += 6 if male else 0
    b = p.get("bmi")
    missing: list[str] = []
    if b is None:
        missing.append("bmi")
    else:
        pts += 0 if b < 25 else 4 if b < 30 else 9 if b < 35 else 14
    w = p.get("waist_cm")
    if w is None:
        missing.append("waist_cm")
    else:
        lo, hi = (94, 102) if male else (80, 88)
        pts += 0 if w < lo else 4 if w <= hi else 6
    pts += 0 if p.get("active_30min_daily", True) else 1
    pts += 0 if p.get("fruit_veg_daily", True) else 2
    pts += 4 if p.get("high_bp") else 0
    pts += 14 if p.get("high_blood_sugar") else 0
    pts += 1 if (not male and p.get("baby_over_4kg")) else 0
    fam = {f for f in (p.get("family_diabetes") or []) if f in ("mother", "father", "sibling", "child")}
    pts += min(8, 2 * len(fam))
    eth = p.get("parent_ethnicities") or []
    if not eth:
        missing.append("parent_ethnicities")
    pts += max([CANRISK_ETHNICITY_POINTS.get(e, 3) for e in eth] or [0])
    edu = p.get("education")
    if edu is None:
        missing.append("education")
    pts += CANRISK_EDUCATION_POINTS.get(edu, 0)

    if pts < 21:
        band, sev = "low", 0
    elif pts <= 32:
        band, sev = "moderate", 1
    else:
        band, sev = "high", 2
    summary = f"Type 2 diabetes risk: {band} (CANRISK {pts})."
    if band != "low":
        summary += " A fasting glucose or HbA1c test is commonly recommended."
    if missing:
        summary += " Some answers were missing, so the score may be underestimated."
    return ScoreResult("CANRISK", "PHAC 2011", pts, band, sev, summary, inputs,
                       "Canadian Diabetes Risk Questionnaire (CANRISK), PHAC", CANRISK_URL,
                       missing=missing)


# ---------------------------------------------------------------------------
# PHQ-2 / GAD-2  (each item 0–3: not at all, several days, more than half, nearly every day)
# ---------------------------------------------------------------------------
def _two_item(name, version, items, cutoff, topic, url, cite):
    if items is None or len(items) != 2 or any(i is None for i in items):
        return ScoreResult(name, version, None, "not asked", 0, f"{name} not completed.",
                           {"items": items}, cite, url, applicable=False)
    if any(not 0 <= int(i) <= 3 for i in items):
        raise ValueError(f"{name} items must be 0-3")
    v = int(items[0]) + int(items[1])
    if v >= cutoff:
        return ScoreResult(name, version, v, "positive screen", 2,
                           f"{name} score {v}: positive screen for {topic}. A fuller assessment is suggested.",
                           {"items": items}, cite, url)
    return ScoreResult(name, version, v, "negative screen", 0,
                       f"{name} score {v}: negative screen for {topic}.", {"items": items}, cite, url)


def phq2(items: list[int] | None) -> ScoreResult:
    return _two_item("PHQ-2", "Kroenke 2003", items, 3, "depression",
                     "https://www.hiv.uw.edu/page/mental-health-screening/phq-2",
                     "Patient Health Questionnaire-2 (Kroenke, Spitzer & Williams, 2003)")


def gad2(items: list[int] | None) -> ScoreResult:
    return _two_item("GAD-2", "Kroenke 2007", items, 3, "anxiety",
                     "https://www.hiv.uw.edu/page/mental-health-screening/gad-2",
                     "Generalized Anxiety Disorder-2 (Kroenke et al., 2007)")


# ---------------------------------------------------------------------------
# AUDIT-C (3 items, each 0–4). Positive: >=4 men, >=3 women.
# ---------------------------------------------------------------------------
AUDIT_C_URL = "https://www.hepatitis.va.gov/alcohol/treatment/audit-c.asp"


def audit_c(items: list[int] | None, sex: str | None) -> ScoreResult:
    cite = "AUDIT-C (Bush et al., 1998)"
    if items is None or len(items) != 3 or any(i is None for i in items):
        return ScoreResult("AUDIT-C", "Bush 1998", None, "not asked", 0, "AUDIT-C not completed.",
                           {"items": items, "sex": sex}, cite, AUDIT_C_URL, applicable=False)
    if any(not 0 <= int(i) <= 4 for i in items):
        raise ValueError("AUDIT-C items must be 0-4")
    v = sum(int(i) for i in items)
    cutoff = 4 if (sex or "").lower() == "male" else 3
    if v >= cutoff:
        return ScoreResult("AUDIT-C", "Bush 1998", v, "positive screen", 1,
                           f"AUDIT-C {v}: alcohol use above the screening threshold.",
                           {"items": items, "sex": sex}, cite, AUDIT_C_URL)
    return ScoreResult("AUDIT-C", "Bush 1998", v, "negative screen", 0,
                       f"AUDIT-C {v}: below the screening threshold.", {"items": items, "sex": sex}, cite, AUDIT_C_URL)


# ---------------------------------------------------------------------------
# CDC STEADI "Stay Independent" fall-risk checklist (12 yes/no items, >=4 = at risk)
# ---------------------------------------------------------------------------
STEADI_URL = "https://www.cdc.gov/steadi/media/pdfs/STEADI-Brochure-StayIndependent-508.pdf"
STEADI_ITEMS = [
    ("fallen_past_year", "I have fallen in the past year.", 2),
    ("cane_or_walker", "I use or have been advised to use a cane or walker to get around safely.", 2),
    ("unsteady_walking", "Sometimes I feel unsteady when I am walking.", 1),
    ("holds_furniture", "I steady myself by holding onto furniture when walking at home.", 1),
    ("worried_falling", "I am worried about falling.", 1),
    ("push_to_stand", "I need to push with my hands to stand up from a chair.", 1),
    ("trouble_curb", "I have some trouble stepping up onto a curb.", 1),
    ("rush_toilet", "I often have to rush to the toilet.", 1),
    ("lost_feeling_feet", "I have lost some feeling in my feet.", 1),
    ("meds_lightheaded", "I take medicine that sometimes makes me feel light-headed or more tired than usual.", 1),
    ("meds_sleep_mood", "I take medicine to help me sleep or improve my mood.", 1),
    ("often_sad", "I often feel sad or depressed.", 1),
]


def steadi(answers: dict | None) -> ScoreResult:
    cite = "CDC STEADI — Stay Independent brochure"
    if not answers:
        return ScoreResult("STEADI", "CDC 2017", None, "not asked", 0, "Fall-risk checklist not completed.",
                           {}, cite, STEADI_URL, applicable=False)
    v = sum(pts for key, _, pts in STEADI_ITEMS if answers.get(key))
    yes = [label for key, label, _ in STEADI_ITEMS if answers.get(key)]
    if v >= 4:
        return ScoreResult("STEADI", "CDC 2017", v, "at risk of falling", 2,
                           f"Fall-risk checklist {v}/14: at risk. A clinician fall-risk assessment is suggested.",
                           {"answers": answers, "yes_items": yes}, cite, STEADI_URL)
    return ScoreResult("STEADI", "CDC 2017", v, "lower risk", 0,
                       f"Fall-risk checklist {v}/14: below the at-risk threshold.",
                       {"answers": answers, "yes_items": yes}, cite, STEADI_URL)


# ---------------------------------------------------------------------------
# Which scores apply to this person? (deterministic; Gemini can only add suggestions)
# ---------------------------------------------------------------------------
def applicable_scores(profile: dict, topics: set[str] | None = None) -> list[str]:
    topics = topics or set()
    age = profile.get("age") or 0
    out = ["BMI"]
    if 40 <= age <= 74:
        out.append("CANRISK")
    if profile.get("audit_c"):
        out.append("AUDIT-C")
    if age >= 65 or profile.get("walking_aid"):
        out.append("STEADI")
    if topics & {"mood", "sleep", "fatigue", "stress", "anxiety", "low_mood"}:
        out += ["PHQ-2", "GAD-2"]
    return out


def compute_profile_scores(profile: dict) -> list[ScoreResult]:
    """Compute everything we can from the stored profile alone."""
    b = bmi(profile.get("height_cm"), profile.get("weight_kg"))
    results = [b]
    age = profile.get("age")
    if age is not None and 40 <= age <= 74:
        results.append(canrisk({**profile, "bmi": b.value}))
    if profile.get("audit_c"):
        results.append(audit_c(profile["audit_c"], profile.get("sex")))
    if profile.get("steadi"):
        results.append(steadi(profile["steadi"]))
    if profile.get("phq2"):
        results.append(phq2(profile["phq2"]))
    if profile.get("gad2"):
        results.append(gad2(profile["gad2"]))
    return results
