"""Hard-coded red-flag safety layer.

This module is deliberately plain Python with no AI in it. It runs on every
patient message *before* Gemini sees it. If it fires, the interview stops and
the patient is sent to 911 / 988 / the ER. Gemini can ask a screening question,
but only this code decides what the answer means.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

# ---------------------------------------------------------------------------
# Actions shown to the patient
# ---------------------------------------------------------------------------
ACTIONS = {
    "CALL_911": {
        "title": "Call 911 now",
        "message": "What you've described can be a medical emergency. Call 911 or have someone take you to the nearest emergency department right away. Don't drive yourself.",
        "resources": [{"label": "Call 911", "href": "tel:911"}],
    },
    "CALL_988": {
        "title": "You don't have to go through this alone",
        "message": "Thank you for telling us. Please call or text 9-8-8 (Suicide Crisis Helpline, 24/7, free) to talk to someone now. If you are in immediate danger, call 911.",
        "resources": [
            {"label": "Call 9-8-8", "href": "tel:988"},
            {"label": "Text 9-8-8", "href": "sms:988"},
            {"label": "Call 911", "href": "tel:911"},
        ],
    },
    "GO_TO_ER": {
        "title": "Go to the emergency department now",
        "message": "What you've described needs to be checked in an emergency department today, not tomorrow. If it gets worse or you feel faint, call 911.",
        "resources": [{"label": "Call 911", "href": "tel:911"}],
    },
}


@dataclass
class Rule:
    flag: str
    label: str
    action: str
    patterns: list[str]
    # every group must match somewhere in the text (used for combos like fever + stiff neck)
    requires_all: list[list[str]] = field(default_factory=list)
    requires_pregnant: bool = False


RULES: list[Rule] = [
    Rule("suicide_risk", "Suicidal thoughts or self-harm", "CALL_988", [
        r"\bkill(ing)? myself\b", r"\bend(ing)? (it all|my life)\b", r"\bsuicid(e|al)\b",
        r"\b(want|wanna|going) to die\b", r"\bdon'?t want to (live|be alive|be here)\b",
        r"\bhurt(ing)? myself\b", r"\bself[- ]?harm\b", r"\bcut(ting)? myself\b",
        r"\bno reason to live\b", r"\bbetter off dead\b", r"\bbetter off without me\b",
        r"\boverdose on purpose\b",
    ]),
    Rule("chest_pain", "Chest pain or pressure", "CALL_911", [
        r"\bchest (pain|pressure|tightness|heaviness|discomfort)\b",
        r"\b(pain|pressure|tightness|heaviness|squeezing|crushing)\b[^.?!]{0,25}\bchest\b",
        r"\bchest\b[^.?!]{0,20}\b(hurts?|aches?|tight|heavy|crushing|squeez\w*)\b",
        r"\bheart attack\b",
    ]),
    Rule("stroke", "Possible stroke signs", "CALL_911", [
        r"\bface (is )?(droop\w*|drooping|numb)\b", r"\b(droop\w*|drooping) face\b",
        r"\bslurr(ed|ing) (speech|words)\b", r"\bcan'?t (speak|talk|get (my )?words out)\b",
        r"\b(sudden(ly)?|one side)[^.?!]{0,30}\b(weak\w*|numb\w*|paraly\w*)\b",
        r"\b(arm|leg)[^.?!]{0,15}\b(went|is|feels?) (weak|numb|dead)\b",
        r"\bstroke\b",
    ]),
    Rule("breathing", "Severe trouble breathing", "CALL_911", [
        r"\bcan'?t breathe\b", r"\bcan ?not breathe\b", r"\bstruggling to breathe\b",
        r"\bgasping\b", r"\b(blue|grey|gray) lips\b", r"\blips (are |look )?(turning |going )?(blue|grey|gray)\b",
        r"\bchoking\b", r"\bsevere(ly)? (short(ness)? of breath|breathless)\b",
    ]),
    Rule("anaphylaxis", "Possible severe allergic reaction", "CALL_911", [
        r"\b(throat|tongue|lips?) (is |are |feels? )?(swell\w*|swollen|closing)\b",
        r"\bswell\w* (of|in) (my )?(throat|tongue|lips?)\b",
        r"\bthroat (is )?closing\b", r"\banaphyla\w*\b",
    ]),
    Rule("thunderclap_headache", "Sudden worst-ever headache", "CALL_911", [
        r"\bworst headache\b", r"\bthunderclap\b",
        r"\bsudden\w*[^.?!]{0,20}\b(severe|explosive|excruciating) headache\b",
    ]),
    Rule("meningitis", "Fever with stiff neck", "GO_TO_ER", [], requires_all=[
        [r"\bfever\w*\b", r"\bfebrile\b", r"\bhigh temp\w*\b"],
        [r"\bstiff neck\b", r"\bneck (is |feels? )?stiff\b", r"\bcan'?t (bend|touch chin)\b"],
    ]),
    Rule("major_bleeding", "Heavy bleeding", "CALL_911", [
        r"\b(vomit\w*|throwing up|coughing up) blood\b", r"\bblood in (my )?vomit\b",
        r"\bwon'?t stop bleeding\b", r"\bbleeding (won'?t|will not|doesn'?t) stop\b",
        r"\b(heavy|severe|uncontrolled|a lot of) bleeding\b", r"\bblack,? tarry stool\w*\b",
    ]),
    Rule("loss_of_consciousness", "Fainting or unresponsive", "CALL_911", [
        r"\b(passed|blacked) out\b", r"\bfaint(ed|ing)\b", r"\bunconscious\b", r"\bunresponsive\b",
        r"\bseizure\b", r"\bconvuls\w*\b",
    ]),
    Rule("pregnancy_emergency", "Pregnancy with bleeding or severe pain", "GO_TO_ER", [
        r"\bbleed\w*\b", r"\bsevere (abdominal|stomach|belly) pain\b", r"\bspotting\b",
    ], requires_pregnant=True),
]

NEGATION_CUES = re.compile(
    r"\b(no|not|never|without|denies|deny|none|nor|neither|"
    r"don'?t have|do not have|didn'?t have|haven'?t had|isn'?t|aren'?t|wasn'?t|"
    r"no longer|free of|ruled out)\b"
)
# Clause boundaries stop a negation from reaching across ("no fever, but chest pain")
CLAUSE_SPLIT = re.compile(r"[.;!?\n]|\bbut\b|\bhowever\b|\bthough\b|\balthough\b|,")


@dataclass
class RedFlagResult:
    flag: str
    label: str
    action: str
    title: str
    message: str
    matched_text: str
    resources: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


def _normalise(text: str) -> str:
    t = text.lower()
    t = t.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", t).strip()


def _negated(clause: str, match_start: int) -> bool:
    """True if a negation cue appears in the same clause, within ~5 words before the match."""
    before = clause[:match_start]
    window = " ".join(before.split()[-5:])
    return bool(NEGATION_CUES.search(window))


def _find_positive(text: str, patterns: list[str]) -> str | None:
    for clause in CLAUSE_SPLIT.split(text):
        for pat in patterns:
            m = re.search(pat, clause)
            if m and not _negated(clause, m.start()):
                return m.group(0)
    return None


def check_message(text: str, profile: dict | None = None) -> RedFlagResult | None:
    """Return the first red flag found in a patient message, or None."""
    if not text or not text.strip():
        return None
    t = _normalise(text)
    pregnant = bool((profile or {}).get("pregnant"))
    for rule in RULES:
        if rule.requires_pregnant and not pregnant:
            continue
        matched: str | None = None
        if rule.patterns:
            matched = _find_positive(t, rule.patterns)
            if not matched:
                continue
        if rule.requires_all:
            hits = [_find_positive(t, group) for group in rule.requires_all]
            if not all(hits):
                continue
            matched = " + ".join(h for h in hits if h)
        a = ACTIONS[rule.action]
        return RedFlagResult(rule.flag, rule.label, rule.action, a["title"], a["message"],
                             matched or "", a["resources"])
    return None


# ---------------------------------------------------------------------------
# Screening questions. Gemini may ask for one by name; code judges the answer.
# ---------------------------------------------------------------------------
SCREENING_QUESTIONS = {
    "chest_pain": "Quick safety check: are you having any chest pain, pressure or tightness right now?",
    "stroke": "Quick safety check: any sudden weakness or numbness on one side, a drooping face, or trouble speaking?",
    "breathing": "Quick safety check: are you struggling to breathe right now?",
    "suicide_risk": "Some people feeling this way have thoughts of ending their life. Have you had thoughts like that?",
    "meningitis": "Quick safety check: do you have a fever together with a stiff neck?",
    "major_bleeding": "Quick safety check: is there heavy bleeding that won't stop, or are you vomiting blood?",
    "anaphylaxis": "Quick safety check: is your throat, tongue or lips swelling, or does your throat feel like it's closing?",
}
SCREEN_TO_FLAG_TEXT = {
    "chest_pain": "chest pain",
    "stroke": "stroke",
    "breathing": "can't breathe",
    "suicide_risk": "suicidal",
    "meningitis": "fever and stiff neck",
    "major_bleeding": "heavy bleeding",
    "anaphylaxis": "throat closing",
}

YES = re.compile(r"^\s*(y|yes|yeah|yep|yup|sure|i am|i do|i have|it is|correct|right|kind of|sort of|a bit|a little|sometimes|maybe)\b")
NO = re.compile(r"^\s*(n|no|nope|nah|not really|never|none|i'?m not|i am not|i don'?t|i do not|i haven'?t|it'?s not|it isn'?t|negative)\b")


def evaluate_screen(flag: str, answer: str, profile: dict | None = None) -> tuple[str, RedFlagResult | None]:
    """Judge a reply to a screening question.

    Returns ("positive", result) | ("negative", None) | ("unclear", None).
    The caller re-asks once on "unclear" and treats a second unclear answer as positive.
    """
    if flag not in SCREENING_QUESTIONS:
        return "negative", None
    direct = check_message(answer, profile)
    if direct:
        return "positive", direct
    a = _normalise(answer)
    if NO.search(a):
        return "negative", None
    if YES.search(a):
        return "positive", check_message(SCREEN_TO_FLAG_TEXT[flag], profile)
    return "unclear", None


def force_flag(flag: str, profile: dict | None = None) -> RedFlagResult | None:
    """Raise a flag directly (used when a screen stays unclear twice)."""
    return check_message(SCREEN_TO_FLAG_TEXT.get(flag, ""), profile)
