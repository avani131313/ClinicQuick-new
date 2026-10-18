"""Navigation rules: where should this person go? Plain code.

The AI may suggest an urgency, but the final level is max(rules, AI): AI can raise
urgency, never lower it below what the rules require.
"""
from __future__ import annotations

import re

from .context import modifiers
from .safety import _find_positive, _normalise

URGENCY = {
    "self_care":         {"rank": 0, "colour": "green",  "label": "Self-care at home",
                          "where": "Home care", "when": "Monitor at home"},
    "pharmacist":        {"rank": 1, "colour": "yellow", "label": "See a pharmacist",
                          "where": "Pharmacist (minor ailment service)", "when": "In the next day or two"},
    "primary_care_soon": {"rank": 2, "colour": "yellow", "label": "See a doctor or nurse practitioner soon",
                          "where": "Family doctor, NP, or walk-in clinic", "when": "Within 1–3 days"},
    "walk_in_today":     {"rank": 3, "colour": "orange", "label": "Be seen today",
                          "where": "Walk-in or urgent care clinic", "when": "Today"},
    "er":                {"rank": 4, "colour": "red",    "label": "Go to the emergency department",
                          "where": "Emergency department", "when": "Now"},
    "emergency_911":     {"rank": 5, "colour": "red",    "label": "Call 911",
                          "where": "911", "when": "Now"},
}

# Ontario pharmacist minor ailments (O. Reg. 256/24 Sched. 4, as of July 1 2026) — keyword → ailment
MINOR_AILMENTS = [
    (r"dandruff|flak\w* scalp|scalp\b.*\b(flak|itch|scal)|itch\w* scalp|seborrh", "Dandruff (seborrheic dermatitis)"),
    (r"pink ?eye|conjunctivitis|eye\b.*\b(goopy|crust|discharge)", "Conjunctivitis"),
    (r"cold sore|fever blister", "Cold sores"),
    (r"canker|mouth ulcer", "Canker sores"),
    (r"\bacne\b|pimples?|breakouts?", "Acne (mild)"),
    (r"hay ?fever|seasonal allerg|allergic rhinitis|sneez\w*.*itchy eyes", "Allergic rhinitis"),
    (r"heartburn|acid reflux|\bgerd\b", "GERD (heartburn)"),
    (r"hives|insect bite|bug bite|mosquito", "Insect bites and hives"),
    (r"tick bite", "Tick bite (Lyme prevention)"),
    (r"eczema|dermatitis|itchy rash", "Dermatitis (eczema, contact)"),
    (r"sprain|strain|pulled (a )?muscle", "Sprains and strains"),
    (r"hemorrhoid|haemorrhoid", "Hemorrhoids"),
    (r"menstrual cramp|period pain|dysmenorrh", "Painful periods"),
    (r"oral thrush|white patches in (my )?mouth", "Oral thrush"),
    (r"pinworm|threadworm", "Pinworms"),
    (r"impetigo", "Impetigo"),
    (r"head lice|\blice\b", "Head lice"),
    (r"ringworm", "Ringworm"),
    (r"jock itch", "Jock itch"),
    (r"\bwarts?\b|verruca", "Warts"),
    (r"callus|\bcorns?\b", "Calluses and corns"),
    (r"dry eyes?", "Dry eye"),
    (r"stuffy nose|nasal congestion|blocked nose|sinus congestion", "Nasal congestion"),
    (r"burn\w* (when|while) (i )?(pee|urinat)|pain(ful)? (when )?urinat|\buti\b|bladder infection", "Uncomplicated UTI"),
    (r"tension headache", "Mild tension headache"),
]

CATEGORIES = [
    ("hematuria", r"blood in (my )?(urine|pee)|bloody (urine|pee)|(pee|urine) (is |looks )?(red|pink|brown)|hematuria|haematuria"),
    ("skin_scalp", r"scalp|dandruff"),
    ("skin", r"rash|itch|skin|eczema|acne|hives|spots?\b|bumps?|blister|mole|lesion|flak"),
    ("urinary", r"\bpee\b|urinat|bladder|\buti\b|burning when"),
    ("headache", r"headache|migraine|head hurts|head pain"),
    ("respiratory", r"cough|sore throat|cold\b|flu\b|congest|sinus|wheez|short(ness)? of breath"),
    ("abdominal", r"stomach|abdom|belly|nause|vomit|diarr|constipat|heartburn"),
    ("musculoskeletal", r"back pain|knee|shoulder|joint|sprain|strain|ankle|hip|neck pain|muscle"),
    ("mood", r"depress|anxi|stress|low mood|sad\b|panic|can'?t sleep|insomnia|overwhelm|burn(ed|t)? out"),
    ("fever", r"fever|temperature|chills"),
]


_FILLER = re.compile(r"^(?:(?:um+|uh+|er+|hmm+|so|well|okay|ok|yeah|yes|hi|hello|hey|like|actually|basically|i mean|lena)[\s,.!-]*)+", re.I)
_LEAD = re.compile(r"^(?:i(?:'m| am)? (?:think|guess|feel like)\s+)?(?:i(?:'ve| have)? (?:been )?(?:got|have|has|had|having|see|saw|seen|noticed|noticing|am having|'m having)|"
                   r"i'?m (?:having|getting|seeing|noticing|dealing with)|there(?:'s| is| are)(?: been)?|"
                   r"i came in (?:for|because of)|i'?m here (?:for|because of)|my (?:problem|concern|issue) is)\s+", re.I)


def tidy_complaint(text: str) -> str:
    """'Um, I see blood in urine.' -> 'Blood in urine'. Deterministic; keeps the patient's meaning."""
    t = re.sub(r"\s+", " ", (text or "")).strip()
    t = _FILLER.sub("", t)
    t = _LEAD.sub("", t)
    t = re.sub(r"\b(um+|uh+|you know|kind of|sort of)\b[,]?\s*", "", t, flags=re.I)
    t = re.sub(r"\bmy urine\b", "urine", t, flags=re.I)
    t = re.sub(r"^(?:a|an|some|the)\s+", "", t, flags=re.I).strip(" ,.!?-")
    t = re.split(r"(?<=[.!?])\s", t)[0].strip(" ,.!?")
    if len(t) > 90:
        t = t[:90].rsplit(" ", 1)[0] + "…"
    return (t[:1].upper() + t[1:]) if t else (text or "").strip()


def categorise(text: str) -> str:
    t = (text or "").lower()
    for name, pat in CATEGORIES:
        if re.search(pat, t):
            return name
    return "general"


def match_minor_ailment(text: str) -> str | None:
    t = (text or "").lower()
    for pat, name in MINOR_AILMENTS:
        if re.search(pat, t):
            return name
    return None


def _severity(answers_text: str) -> int | None:
    m = re.findall(r"\b(10|[0-9])\s*(/|out of)\s*10\b", answers_text) or re.findall(r"^\s*(10|[0-9])\s*$", answers_text, re.M)
    if not m:
        return None
    vals = [int(x[0] if isinstance(x, tuple) else x) for x in m]
    return max(vals)


def rule_urgency(ctx: dict, category: str, complaint: str, all_answers: str, severity: int | None) -> tuple[str, list[str]]:
    """Minimum urgency the rules require, with reasons."""
    reasons: list[str] = []
    level = "primary_care_soon"
    sev = severity if severity is not None else _severity(all_answers)
    text = f"{complaint}\n{all_answers}".lower()
    ailment = match_minor_ailment(complaint)
    age = ctx["age"]
    prof = ctx["profile"]

    ntext = _normalise(text)
    if category == "hematuria":
        level = "primary_care_soon"
        reasons.append("Visible blood in urine always needs a urine test and clinician review.")
        if _find_positive(ntext, [r"can'?t (pee|urinate)", r"unable to (pee|urinate)", r"can ?not (pee|urinate)"]):
            level = "er"
            reasons.append("Being unable to pass urine needs emergency care.")
        elif _find_positive(ntext, [r"\bclots?\b", r"\bfever\w*\b", r"\bflank\b", r"\bside pain\b", r"\bback pain\b"]):
            level = "walk_in_today"
            reasons.append("Blood in urine with clots, fever, or flank pain should be seen today.")
        if level == "primary_care_soon" and any(m["key"] == "anticoagulant" for m in modifiers(ctx)):
            level = "walk_in_today"
            reasons.append("You take a blood thinner, so new bleeding should be checked the same day.")
    elif ailment:
        exclusions = []
        if prof.get("pregnant"):
            exclusions.append("pregnancy")
        if sev is not None and sev >= 8:
            exclusions.append("severe symptoms")
        if _find_positive(ntext, [r"\bfever\w*", r"\bspreading\b", r"worse fast", r"\bmonths\b", r"over a year"]):
            exclusions.append("fever, spreading, or long duration")
        if ailment == "Uncomplicated UTI" and (ctx["sex"] != "female" or age < 16 or _find_positive(ntext, [r"\bblood\b", r"\bflank\b", r"\bfever"])):
            exclusions.append("UTI outside pharmacist criteria")
        if not exclusions:
            level = "pharmacist"
            reasons.append(f"'{ailment}' is on Ontario's pharmacist minor-ailment list, so a pharmacist can assess and prescribe.")
        else:
            reasons.append(f"Could be a minor ailment ({ailment}) but {', '.join(exclusions)} means a clinician should assess.")
    if sev is not None and sev >= 8 and URGENCY[level]["rank"] < URGENCY["walk_in_today"]["rank"]:
        level = "walk_in_today"
        reasons.append(f"Severity reported as {sev}/10.")
    if age >= 75 and category in ("fever", "abdominal", "respiratory") and URGENCY[level]["rank"] < 3:
        level = "walk_in_today"
        reasons.append("Older adults with these symptoms should be seen the same day.")
    if prof.get("pregnant") and URGENCY[level]["rank"] < 2:
        level = "primary_care_soon"
        reasons.append("Pregnancy: check with your prenatal provider.")
    if not reasons:
        reasons.append("A clinician should review this; no emergency features were reported.")
    return level, reasons


def combine(rule_level: str, ai_level: str | None) -> str:
    if ai_level in URGENCY and URGENCY[ai_level]["rank"] > URGENCY[rule_level]["rank"] and ai_level != "emergency_911":
        return ai_level
    return rule_level


# ---------------------------------------------------------------------------
# Offline considerations (used only when Gemini is unavailable). Clinician-facing only.
# ---------------------------------------------------------------------------
def offline_considerations(ctx: dict, category: str, text: str) -> list[dict]:
    mods = {m["key"]: m["value"] for m in modifiers(ctx)}
    age = ctx["age"]
    out: list[dict] = []
    t = text.lower()
    if category == "hematuria":
        if age < 40:
            if "menstruating_age" in mods:
                out.append({"name": "Menstrual contamination of the sample", "likelihood": "higher" if re.search(r"period|menstrua", t) else "consider",
                            "because": ["↑ female of menstruating age", "confirm timing against last period; repeat urinalysis mid-cycle"]})
            out += [
                {"name": "Exercise-induced hematuria", "likelihood": "higher", "because": [f"↑ age {age}", "↑ recent intense exercise" if re.search(r"train|run|soccer|game|exercise|practice", t) else "consider if recent exertion"]},
                {"name": "Urinary tract infection", "likelihood": "moderate", "because": ["check for dysuria/frequency"]},
                {"name": "Glomerular cause (e.g. post-infectious, IgA nephropathy)", "likelihood": "consider", "because": ["↑ if cola-coloured urine or recent sore throat", "BP and urine protein advised"]},
                {"name": "Renal trauma / stone", "likelihood": "consider", "because": ["↑ if contact sport injury or colicky flank pain"]},
            ]
        else:
            why = [f"↑ age {age}"] + (["↑ smoking history"] if "smoking" in mods else [])
            out += [
                {"name": "Urothelial malignancy (bladder / upper tract)", "likelihood": "must rule out", "because": why + ["visible hematuria in adults ≥ 35–40 warrants imaging and cystoscopy referral per urology guidance"]},
                {"name": "Urinary tract infection", "likelihood": "moderate", "because": ["check urinalysis and culture"]},
                {"name": "Benign prostatic enlargement" if ctx["sex"] == "male" else "Urinary stone", "likelihood": "moderate", "because": ["↑ male, older age" if ctx["sex"] == "male" else "↑ if colicky pain"]},
            ]
        if "anticoagulant" in mods:
            out.append({"name": "Anticoagulant-associated bleeding", "likelihood": "contributing", "because": ["↑ takes an anticoagulant", "does NOT explain away hematuria — full workup still indicated"]})
    elif category == "skin_scalp":
        out += [
            {"name": "Seborrheic dermatitis (dandruff)", "likelihood": "higher", "because": ["↑ greasy/yellow flakes, eyebrows or nasal folds" if re.search(r"greas|yellow|oily|eyebrow|nose", t) else "common cause of flaky, itchy scalp"]},
            {"name": "Scalp psoriasis", "likelihood": "consider", "because": ["↑ thick silvery plaques, elbows/knees, family history"]},
            {"name": "Tinea capitis", "likelihood": "lower" if age >= 18 else "consider", "because": ["↓ adult" if age >= 18 else "↑ child", "↑ if patchy hair loss"]},
            {"name": "Contact / irritant dermatitis", "likelihood": "consider", "because": ["↑ new shampoo, dye or product" if re.search(r"shampoo|dye|product|new", t) else "ask about new products"]},
        ]
    elif category == "skin":
        warm = re.search(r"warm|hot|spreading|fever|swollen|red streak", t)
        out += [
            {"name": "Contact or irritant dermatitis", "likelihood": "higher" if re.search(r"soap|detergent|cream|plant|new|product|metal|watch", t) else "moderate", "because": ["↑ new product or exposure" if re.search(r"soap|detergent|cream|plant|new|product", t) else "ask about new exposures"]},
            {"name": "Eczema (atopic dermatitis)", "likelihood": "moderate", "because": ["↑ itch, dry patches, flexures" if re.search(r"itch|dry", t) else "check history of eczema or asthma"]},
            {"name": "Urticaria (hives)", "likelihood": "consider", "because": ["↑ raised, comes and goes within hours" if re.search(r"come and go|comes and goes|hives|welts", t) else "ask if lesions move or fade within 24 h"]},
            {"name": "Cellulitis / skin infection", "likelihood": "must rule out" if warm else "lower", "because": ["↑ warmth, spreading or fever" if warm else "↓ no warmth, spread or fever reported"]},
        ]
    else:
        out.append({"name": "Clinician assessment needed", "likelihood": "—", "because": ["offline mode: AI considerations unavailable for this complaint"]})
    return out


_FILLER = re.compile(r"^\s*(?:(?:um+|uh+|erm+|hmm+|so|well|okay|ok|yeah|like|basically|actually|honestly|hi|hello|hey)[\s,.!-]+)+", re.I)
_LEAD = re.compile(r"^\s*(?:i'm\s+(?:having|getting|seeing|feeling)?\s*|i(?:'ve|\s+have)?\s+(?:been\s+)?(?:see|seeing|saw|noticed|noticing|got|have|having|had|feel|feeling|am|get|getting)\s+|"
                   r"there(?:'s| is| has been)\s+|i\s+think\s+(?:i\s+have\s+)?|my\s+(?:main\s+)?(?:concern|problem|issue)\s+is\s+(?:that\s+)?)", re.I)


def tidy_complaint(text: str) -> str:
    """'Um, I see blood in urine.' → 'Blood in urine'. Offline fallback; the report AI rewrites it properly."""
    t = (text or "").strip()
    for _ in range(3):
        t2 = _LEAD.sub("", _FILLER.sub("", t))
        if t2 == t:
            break
        t = t2
    t = re.sub(r"\s*\b(?:um+|uh+|erm+)\b,?\s*", " ", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" .,!?-")
    t = re.sub(r"^(?:a|an|some)\s+", "", t, flags=re.I)
    t = re.sub(r"\b(in|on|of|from) my\b", r"\1", t, flags=re.I)
    return (t[:1].upper() + t[1:])[:140] if t else (text or "").strip()
