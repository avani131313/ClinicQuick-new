"""Turns everything ClinicQuick knows about a patient into DDX evidence codes.

Three sources, each code remembers where it came from (shown to the doctor):
  profile      structured profile, conditions, medications, family history, last period
  health data  Apple / Samsung Health observations (activity, resting HR, SpO2, temperature, sleep, labs)
  conversation Lena's interview (Gemini reads it against the question catalogue; keyword rules offline)
Codes follow DDXPlus: 'E_302' = yes, 'E_301_@_V_301' = an option, 'E_56_@_6' = a 0-10 answer.
"""
from __future__ import annotations

import json
import re
import statistics
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

DATA = Path(__file__).resolve().parent / "data"


# ----------------------------------------------------------------- catalogue
@lru_cache(maxsize=1)
def catalog() -> dict:
    ev = json.loads((DATA / "ddx_evidences.json").read_text(encoding="utf-8"))
    co = json.loads((DATA / "ddx_conditions.json").read_text(encoding="utf-8"))
    return {"evidences": {e["code"]: e for e in ev}, "conditions": {c["name"]: c for c in co}}


def label(token: str) -> str:
    ev = catalog()["evidences"]
    base, _, val = token.partition("_@_")
    e = ev.get(base)
    if not e:
        return token
    if not val:
        return e.get("label") or e["question_en"]
    if val.startswith("V_"):
        return f'{e.get("label") or e["question_en"]}: {e["values"].get(val, val)}'
    return f'{e.get("label") or e["question_en"]}: {val}/10'


def valid(token: str) -> bool:
    ev = catalog()["evidences"]
    base, _, val = token.partition("_@_")
    e = ev.get(base)
    if not e:
        return False
    if not val:
        return e["data_type"] == "B"
    if val.startswith("V_"):
        return val in (e.get("values") or {})
    return e["data_type"] == "C" and not e.get("values") and val.isdigit() and 0 <= int(val) <= 10


def is_antecedent(token: str) -> bool:
    e = catalog()["evidences"].get(token.partition("_@_")[0])
    return bool(e and e["is_antecedent"])


# ----------------------------------------------------------------- profile
NOAC = r"apixaban|rivaroxaban|dabigatran|edoxaban|eliquis|xarelto|pradaxa|lixiana|savaysa"
MED_RULES = [
    (NOAC, "E_146"),
    (r"ibuprofen|naproxen|diclofenac|celecoxib|advil|aleve|motrin|nsaid|ketorolac|meloxicam", "E_10"),
    (r"prednison|prednisolon|dexamethason|hydrocortison|methylprednisolon|budesonide tablet", "E_44"),
    (r"methotrexate|tacrolimus|cyclosporin|azathioprin|mycophenol|biologic", "E_227"),
    (r"estradiol|estrogen|progest|levonorgestrel|contracept|birth control|\bpill\b|testosteron|hormone", "E_100"),
    (r"amlodipin|diltiazem|verapamil|nifedipin|felodipin", "E_149"),
    (r"lisinopril|ramipril|perindopril|enalapril|losartan|valsartan|irbesartan|candesartan|hydrochlorothiazide|"
     r"chlorthalidone|indapamide|amlodipin|metoprolol|bisoprolol|atenolol", "E_104"),
    (r"atorvastatin|rosuvastatin|simvastatin|pravastatin|lipitor|crestor|ezetimib", "E_71"),
    (r"metformin|insulin|empagliflozin|dapagliflozin|semaglutide|sitagliptin|gliclazide|glyburide|ozempic|jardiance", "E_69"),
    (r"nitroglycerin|isosorbide|nitrate|sildenafil|tadalafil", "E_184"),
    (r"salbutamol|albuterol|ventolin|fluticason|symbicort|advair|inhaler|montelukast|tiotropium", "E_124"),
    (r"pseudoephedrin|phenylephrin|decongest", "E_213"),
]
CONDITION_RULES = [
    (r"hypertension|high blood pressure", "E_104"), (r"diabet", "E_69"),
    (r"cholesterol|hyperlipid|dyslipid", "E_71"), (r"\basthma", "E_124"), (r"\bcopd|emphysema|chronic bronchitis", "E_123"),
    (r"heart failure", "E_106"), (r"angina|heart attack|myocardial infarction|coronary", "E_105"),
    (r"kidney failure|chronic kidney|\bckd\b|renal failure", "E_113"), (r"dialysis", "E_8"),
    (r"stroke|\btia\b", "E_107"), (r"\bhiv\b", "E_2"), (r"cirrhosis", "E_126"), (r"crohn|ulcerative colitis", "E_47"),
    (r"reflux|\bgerd\b", "E_125"), (r"sleep apn", "E_186"), (r"depress", "E_80"), (r"anxiety", "E_81"),
    (r"migraine", "E_99"), (r"anemi|anaemi", "E_24"), (r"deep vein|\bdvt\b", "E_109"), (r"osteoporos", "E_153"),
    (r"rheumatoid", "E_20"), (r"hyperthyroid|graves", "E_19"), (r"kidney stone|renal stone|nephrolith", "E_313"),
    (r"pneumothorax", "E_21"), (r"chronic sinusitis", "E_119"), (r"heart valve|valvular|mitral|aortic stenosis", "E_22"),
    (r"heart defect|congenital heart", "E_139"), (r"parkinson", "E_95"), (r"fibromyalgia", "E_138"),
    (r"cystic fibrosis", "E_18"), (r"pericarditis", "E_3"), (r"hiatal hernia", "E_98"), (r"nephrotic", "E_197"),
    (r"pancreatitis", "E_6"), (r"metastat", "E_37"), (r"\bcancer|lymphoma|leukemia|carcinoma", "E_34"),
    (r"immunosuppress|transplant", "E_227"), (r"endocrin|hormone (disorder|dysfunction)", "E_158"),
    (r"allerg", "E_226"),
]
FAMILY_RULES = [
    (r"asthma", "E_87"), (r"allerg|hay fever|eczema", "E_86"), (r"lung cancer", "E_224"),
    (r"pancreatic cancer", "E_223"), (r"anemi|anaemi", "E_26"), (r"migraine", "E_99"), (r"pneumothorax", "E_165"),
    (r"cluster headache", "E_25"), (r"myasthenia", "E_28"), (r"psychiatr|schizo|bipolar|depress", "E_29"),
    (r"croup", "E_4"),
]
OCCUPATION_RULES = [
    (r"agricultur|farm", "E_198"), (r"\bmin(e|ing|er)\b", "E_200"), (r"construction", "E_199"),
    (r"daycare|day care|childcare|early childhood", "E_49"),
    (r"\bdye|rubber|leather|paint|chemical|textile|solvent|hairdress|printing", "E_312"),
]


def _rules(text: str, rules) -> set[str]:
    t = (text or "").lower()
    return {code for pat, code in rules if re.search(pat, t)}


def from_profile(ctx: dict, today: date | None = None) -> dict[str, str]:
    """-> {code: why}"""
    today = today or date.today()
    prof = ctx.get("profile") or {}
    out: dict[str, str] = {}

    def add(code, why):
        out.setdefault(code, why)

    smoking = (prof.get("smoking") or "").lower()
    if smoking == "current":
        add("E_79", "profile: smokes")
    elif smoking == "former":
        add("E_191", "profile: former smoker")
    if prof.get("pregnant"):
        add("E_167", "profile: pregnant or may be")
    if prof.get("high_bp"):
        add("E_104", "profile: high blood pressure")
    if prof.get("high_blood_sugar"):
        add("E_69", "profile: high blood sugar")
    if prof.get("active_30min_daily"):
        add("E_143", "profile: active 30 min daily")
    if (prof.get("vaccines_up_to_date") or "").lower() == "yes":
        add("E_209", "profile: vaccines up to date")
    h, w = prof.get("height_cm"), prof.get("weight_kg")
    if h and w:
        bmi = w / (h / 100) ** 2
        if bmi >= 30:
            add("E_70", f"profile: BMI {bmi:.0f}")
        elif bmi < 18.5:
            add("E_208", f"profile: BMI {bmi:.1f}")
    audit = prof.get("audit_c") or []
    if audit and sum(audit) >= 6:
        add("E_78", f"profile: AUDIT-C {sum(audit)}")
    for c in ctx.get("conditions") or []:
        for code in _rules(c, CONDITION_RULES):
            add(code, f"condition: {c}")
    for m in ctx.get("medications") or []:
        for code in _rules(m, MED_RULES):
            add(code, f"medication: {m}")
    for f in (prof.get("family_history") or []) + (prof.get("family_diabetes") or []):
        for code in _rules(f, FAMILY_RULES):
            add(code, f"family history: {f}")
    for mh in prof.get("mental_health_history") or []:
        for code in _rules(mh, [(r"depress", "E_80"), (r"anxiety|panic", "E_81")]):
            add(code, f"mental health history: {mh}")
    for code in _rules(prof.get("occupation") or "", OCCUPATION_RULES):
        add(code, f"occupation: {prof.get('occupation')}")
    drugs = (prof.get("recreational_drugs") or "").lower()
    if re.search(r"cocaine|amphetamin|meth|stimulant|mdma", drugs):
        add("E_62", "profile: stimulant use")
    if re.search(r"inject|\biv\b|heroin", drugs):
        add("E_61", "profile: injection drug use")
    lmp = prof.get("last_menstrual_period")
    if lmp and ctx.get("sex") == "female":
        lmp = lmp if isinstance(lmp, date) else date.fromisoformat(str(lmp)[:10])
        if 0 <= (today - lmp).days <= 7:
            add("E_306", f"profile: period started {lmp.isoformat()}")
    return out


# ----------------------------------------------------------------- health data (Apple / Samsung)
def from_health_data(observations: list[dict], now: datetime | None = None) -> tuple[dict[str, str], list[str]]:
    """observations: [{ts, code, value, source}] -> ({code: why}, [context facts for the doctor]).
    Only defensible mappings become model inputs; everything else is shown to the doctor as context."""
    now = now or datetime.now(timezone.utc)
    codes: dict[str, str] = {}
    facts: list[str] = []
    by: dict[str, list] = {}
    for o in observations:
        by.setdefault(o["code"], []).append(o)
    src = sorted({o.get("source") or "" for o in observations if o.get("source")})

    steps = by.get("steps", [])
    if steps:
        daily: dict[date, float] = {}
        for o in steps:
            d = o["ts"].astimezone(timezone.utc).date()
            daily[d] = daily.get(d, 0) + float(o["value"])
        recent = [v for d, v in daily.items() if (now.date() - d).days <= 1]
        base = [v for d, v in daily.items() if 2 <= (now.date() - d).days <= 30]
        if base:
            med = statistics.median(base)
            peak = max(recent) if recent else 0
            if med >= 10000:
                codes["E_143"] = f"health data: median {med:,.0f} steps/day"
            if peak and peak >= max(15000, 1.8 * med):
                codes["_intense_activity"] = f"health data: {peak:,.0f} steps in the last 48 h (usual {med:,.0f})"
                facts.append(f"Unusually high activity in the last 48 h: {peak:,.0f} steps (usual {med:,.0f}/day).")
            else:
                yday = daily.get(now.date() - timedelta(days=1))  # a full day (today is still in progress)
                if yday is not None and med and yday < 0.5 * med:
                    facts.append(f"Activity well below usual yesterday ({yday:,.0f} vs {med:,.0f} steps/day).")

    rhr = sorted(by.get("rhr", []), key=lambda o: o["ts"])
    if len(rhr) >= 7:
        last = [float(o["value"]) for o in rhr if (now - o["ts"]).days <= 3]
        prior = [float(o["value"]) for o in rhr if 4 <= (now - o["ts"]).days <= 30]
        if last and prior and statistics.mean(last) - statistics.median(prior) >= 8:
            facts.append(f"Resting heart rate up {statistics.mean(last) - statistics.median(prior):.0f} bpm vs baseline "
                         f"({statistics.mean(last):.0f} vs {statistics.median(prior):.0f}).")

    spo2 = [float(o["value"]) for o in by.get("spo2", []) if (now - o["ts"]).days <= 3]
    if spo2 and min(spo2) < 94:
        facts.append(f"Lowest SpO2 in the last 3 days: {min(spo2):.0f}%.")

    temps = [float(o["value"]) for c in ("temp", "body_temp", "temperature") for o in by.get(c, [])
             if (now - o["ts"]).total_seconds() <= 48 * 3600]
    if temps and max(temps) >= 38.0:
        codes["E_91"] = f"health data: temperature {max(temps):.1f} °C"
        facts.append(f"Measured temperature {max(temps):.1f} °C in the last 48 h.")

    bp = [float(o["value"]) for o in by.get("bp_sys", []) if (now - o["ts"]).days <= 30]
    if len(bp) >= 3 and statistics.median(bp) >= 140:
        codes["E_104"] = f"health data: median systolic BP {statistics.median(bp):.0f} mmHg (last 30 days)"
        facts.append(f"Blood pressure running high: median systolic {statistics.median(bp):.0f} mmHg over {len(bp)} readings.")

    rr = [float(o["value"]) for o in by.get("resp_rate", []) if (now - o["ts"]).days <= 3]
    if rr and statistics.mean(rr) >= 20:
        facts.append(f"Breathing rate raised: {statistics.mean(rr):.0f}/min on average in the last 3 days.")

    sleep = sorted(by.get("sleep_min", []), key=lambda o: o["ts"])
    if len(sleep) >= 7:
        last = [float(o["value"]) for o in sleep if (now - o["ts"]).days <= 3]
        prior = [float(o["value"]) for o in sleep if 4 <= (now - o["ts"]).days <= 30]
        if last and prior and statistics.mean(last) < 0.75 * statistics.median(prior):
            facts.append(f"Sleep down to {statistics.mean(last) / 60:.1f} h/night (usual {statistics.median(prior) / 60:.1f} h).")

    weights = sorted(by.get("weight", []), key=lambda o: o["ts"])
    if len(weights) >= 2:
        first, lastw = float(weights[0]["value"]), float(weights[-1]["value"])
        if first and abs(lastw - first) / first >= 0.05:
            facts.append(f"Weight changed {lastw - first:+.1f} kg over the recorded period.")

    labs = {}
    for c, rows in by.items():
        if c.startswith("lab:"):
            r = max(rows, key=lambda o: o["ts"])
            labs[c[4:]] = r
    for name, r in sorted(labs.items())[:8]:
        facts.append(f"Lab {name}: {r['value']:g} {r.get('unit') or ''} ({r['ts'].date().isoformat()}).".replace(" )", ")"))
    if src and (codes or facts):
        facts.append("Sources: " + ", ".join(src) + ".")
    return codes, facts


# ----------------------------------------------------------------- conversation
NEG = re.compile(r"\b(no|not|never|don'?t|doesn'?t|didn'?t|haven'?t|hasn'?t|without|denies|nothing|none)\b")

CONVO_RULES: list[tuple[str, list[str]]] = [
    (r"blood in (my |the )?(urine|pee|wee)|bloody (urine|pee)|peeing blood|hematuria|haematuria|"
     r"(urine|pee|wee)\b.{0,25}\b(red|pink|brown|bloody|dark|cola|tea[- ]colou?r)|(red|pink|brown)(dish)? (urine|pee)", ["E_300"]),
    (r"(burn|sting)\w*.{0,25}(pee|urinat|wee)|(pee|urinat\w*|wee)\w*.{0,25}(burn|sting)|"
     r"hurts? (when|to) (pee|urinat)|painful (urination|peeing)|dysuria|it (burns|stings)", ["E_302"]),
    (r"(pee|urinat\w*|wee)\w* (a lot|more|more often|all the time|frequently)|frequen\w* urinat|urgen|can'?t hold it|rush to the (toilet|bathroom)", ["E_303"]),
    (r"(up|wake up|waking up|get up)\b.{0,25}\bnight\b.{0,25}(pee|urinat|toilet|bathroom)|(pee|urinat|toilet|bathroom).{0,25}at night|nocturia", ["E_304"]),
    (r"weak (stream|flow)|(stream|flow) is (weak|slow)|hard to (start|get going)|dribbl|hesitan|trouble (starting|peeing|getting started)", ["E_305"]),
    (r"(on|having|started|got) my period|period (started|now|just ended|ended)|menstruat", ["E_306"]),
    (r"irregular (period|cycle)|bleed\w* between periods|spotting", ["E_307"]),
    (r"(after|following|since) (a |my |the |our )?(hard |long |intense |big |tough )?(practice|training|workout|game|run|race|marathon|match|exercise|gym session|tournament)", ["E_308"]),
    (r"(sore throat|strep|tonsillitis|throat infection|skin infection|impetigo).{0,40}(week|weeks|ago|recently|last)|"
     r"(last week|weeks ago|recently).{0,40}(sore throat|strep|skin infection)", ["E_309"]),
    (r"foam|froth|bubbly (urine|pee)|puffy (eyes|face)|swollen (ankles|eyes|face|feet)", ["E_310"]),
    (r"(lost|losing) (some |a lot of )?weight|weight loss", ["E_311", "E_162"]),
    (r"kidney stones? before|had (a )?kidney stone|history of (kidney )?stones", ["E_313"]),
    (r"fever|temperature of 3[89]|feel(ing)? (hot|feverish)", ["E_91"]),
    (r"chills|shiver|rigors", ["E_94"]),
    (r"\bpain|ache|aching|hurts?|sore\b|cramp|discomfort|tender", ["E_53"]),
    (r"cough", ["E_201"]), (r"(phlegm|mucus|sputum).{0,20}(green|yellow)|(green|yellow) (phlegm|mucus|sputum)", ["E_77"]),
    (r"cough\w* (up )?blood", ["E_45"]),
    (r"short(ness)? of breath|out of breath|breathless|can'?t catch my breath|hard to breathe|trouble breathing", ["E_66"]),
    (r"wheez", ["E_214"]), (r"runny nose|stuffy|congest|blocked nose", ["E_181"]), (r"sore throat", ["E_97"]),
    (r"hoarse|lost my voice", ["E_212"]), (r"(muscle|body) ach|myalgia", ["E_144"]), (r"nause|queasy", ["E_148"]),
    (r"vomit|throw(ing)? up|threw up", ["E_211"]), (r"diarrh|loose stool", ["E_51"]),
    (r"tired|fatigue|exhaust|no energy", ["E_89"]), (r"dizz|light-?headed", ["E_76"]),
    (r"faint|passed out|blacked out", ["E_159"]), (r"palpitat|racing heart|heart (is )?(racing|pounding)", ["E_155"]),
    (r"heartburn|acid reflux|acid in my throat", ["E_173"]), (r"\brash\b|hives", ["E_129"]),
    (r"lost (my )?(sense of )?smell|can'?t smell", ["E_103"]), (r"sweat", ["E_50"]),
    (r"worse when (i )?(breathe|take a deep breath)|hurts to breathe", ["E_220"]),
    (r"swollen (legs|leg|ankle)", ["E_151"]),
]
LOCATION_RULES = [
    (r"lower (belly|abdomen|tummy|stomach)|bladder|pelvi|pubic|above my pubic", ["E_55_@_V_153"]),
    (r"belly|tummy|stomach|abdom", ["E_55_@_V_187"]),
    (r"lower back", ["E_55_@_V_40"]),
    (r"(right|r) (side|flank)|right kidney", ["E_55_@_V_84"]),
    (r"(left|l) (side|flank)|left kidney", ["E_55_@_V_85"]),
    (r"\bflank|\bside\b|kidney area", ["E_55_@_V_84"]),
    (r"urethra|when i pee", ["E_55_@_V_185"]),
    (r"chest", ["E_55_@_V_29"]), (r"throat", ["E_55_@_V_148"]),
]
COLOUR_RULES = [(r"clot", "V_302"), (r"cola|tea|brown|dark", "V_303"), (r"pink", "V_300"), (r"red", "V_301")]


def _clauses(text: str) -> list[str]:
    return [c.strip() for c in re.split(r"[.;!?\n]|,\s*but\b|\bbut\b", text.lower()) if c.strip()]


def _negated(clause: str, match_start: int) -> bool:
    return bool(NEG.search(clause[max(0, match_start - 40):match_start]))


def from_conversation_rules(turns: list[dict]) -> tuple[dict[str, str], set[str]]:
    """Keyword fallback (no Gemini). -> ({code: why}, denied codes)"""
    present: dict[str, str] = {}
    denied: set[str] = set()
    answers = [t["answer"] for t in turns if t.get("answer")]
    for ans in answers:
        for clause in _clauses(ans):
            for pat, codes in CONVO_RULES:
                m = re.search(pat, clause)
                if m:
                    (denied.update(codes) if _negated(clause, m.start()) else
                     [present.setdefault(c, f'conversation: "{ans[:80]}"') for c in codes])
    text = " ".join(a.lower() for a in answers)
    if "E_53" in present:
        for pat, codes in LOCATION_RULES:
            if re.search(pat, text):
                present.setdefault(codes[0], "conversation: pain location")
                break
        if re.search(r"(spread|radiat|goes|moves|shoot)\w*.{0,30}groin", text):
            present.setdefault("E_57_@_V_16", "conversation: pain spreads to the groin")
        m = re.search(r"\b(10|[0-9])\s*(/|out of)\s*10\b", text) or re.search(r"\b(?:about|around|maybe|a)\s+(10|[0-9])\b", text)
        if m:
            present.setdefault(f"E_56_@_{m.group(1)}", "conversation: pain severity")
    if "E_300" in present:
        for pat, v in COLOUR_RULES:
            if re.search(pat, text):
                present.setdefault(f"E_301_@_{v}", "conversation: urine colour")
                break
    if not re.search(r"travel|trip|abroad|overseas|vacation|holiday", text):
        present.setdefault("E_204_@_V_10", "conversation: no recent travel mentioned")
    for c in denied:
        present.pop(c, None)
    return present, denied


class _Extracted(BaseModel):
    present: list[str]
    denied: list[str] = []


EXTRACT_SYSTEM = """You map a patient's intake interview to a fixed catalogue of clinical question codes.
Rules:
- Return in `present` only codes the PATIENT clearly affirmed or described in their answers. Do not guess.
- Formats: yes/no question -> "E_302". Option question -> "E_301_@_V_301" (one entry per chosen option; for pain
  location E_55 or radiation E_57 pick the closest body sites). 0-10 question -> "E_56_@_6" (an integer).
- Put codes the patient clearly said NO to in `denied`.
- If the patient did not mention travel, add "E_204_@_V_10" (no travel).
- Use only codes and option ids that exist in the catalogue. Respond with JSON only."""


@lru_cache(maxsize=1)
def _catalog_text() -> str:
    lines = []
    for e in catalog()["evidences"].values():
        opts = ""
        if e.get("values"):
            opts = " OPTIONS: " + "; ".join(f"{k}={v}" for k, v in e["values"].items())
        elif e["data_type"] == "C":
            opts = " (answer 0-10)"
        lines.append(f'{e["code"]}: {e["question_en"]}{opts}')
    return "\n".join(lines)


def from_conversation_gemini(turns: list[dict], extra: str = "") -> tuple[dict[str, str], set[str]] | None:
    try:
        from app import gemini
    except Exception:  # noqa: BLE001
        return None
    if not gemini.enabled():
        return None
    tx = "\n".join(f"Q: {t['question']}\nA: {t['answer']}" for t in turns if t.get("answer"))
    prompt = f"CATALOGUE:\n{_catalog_text()}\n\n{extra}\nINTERVIEW:\n{tx}\n\nReturn {{present, denied}}."
    out = gemini.generate_json(EXTRACT_SYSTEM, prompt, _Extracted, temperature=0.0)
    if out is None:
        return None
    present = {t: "conversation (Gemini)" for t in out.present if valid(t)}
    return present, {t for t in out.denied if valid(t)}


# ----------------------------------------------------------------- everything together
def build(ctx: dict, turns: list[dict], observations: list[dict], media_notes: list[str] | None = None,
          use_gemini: bool = True) -> dict:
    sources: dict[str, str] = {}
    prof = from_profile(ctx)
    health, facts = from_health_data(observations)
    convo = None
    if use_gemini:
        extra = f"PHOTO/VIDEO DESCRIPTIONS: {media_notes}\n" if media_notes else ""
        convo = from_conversation_gemini(turns, extra)
    rules, denied_rules = from_conversation_rules(turns)
    if convo:
        present, denied = convo
        for c, why in rules.items():  # keyword rules add recall, unless Gemini heard a clear "no"
            if c not in denied:
                present.setdefault(c, why)
        mode = "gemini"
    else:
        present, denied, mode = rules, denied_rules, "keyword rules"

    for d in (prof, present):
        for c, why in d.items():
            if valid(c):
                sources.setdefault(c, why)
    intense = health.pop("_intense_activity", None)
    for c, why in health.items():
        if valid(c) and c not in denied:
            sources.setdefault(c, why)
    if intense and "E_300" in sources and "E_308" not in denied:
        sources.setdefault("E_308", intense)  # blood after intense exercise, from the step count

    symptoms = [c for c in sources if not is_antecedent(c) and not c.startswith(("E_204", "E_53", "E_56", "E_55", "E_57"))]
    return {"codes": sorted(sources), "sources": sources, "denied": sorted(denied), "facts": facts,
            "in_scope": bool(symptoms), "extraction": mode, "chief": chief_complaint(turns, sources)}


GENERIC = {"E_53", "E_54", "E_55", "E_56", "E_57", "E_58", "E_59", "E_204"}  # pain details, travel


def chief_complaint(turns: list[dict], sources: dict[str, str]) -> list[str]:
    """The patient's main complaint as question codes (e.g. ['E_300'] for blood in urine).
    DDXPlus builds every case so that the condition explains the opening complaint; ranking uses this to keep
    conditions that cannot cause it (e.g. hay fever for blood in urine) off the list."""
    first = from_conversation_rules(turns[:1])[0] if turns else {}
    chief = {c.partition("_@_")[0] for c in first if valid(c) and not is_antecedent(c)} - GENERIC
    if not chief:  # opening complaint not caught by the keyword rules: use every reported symptom
        chief = {c.partition("_@_")[0] for c in sources
                 if not is_antecedent(c) and not sources[c].startswith("profile")} - GENERIC
    return sorted(chief)
