import pytest

from app.safety import check_message, evaluate_screen

POSITIVE = [
    ("I have crushing chest pressure spreading to my left arm", "chest_pain"),
    ("my chest hurts when I breathe", "chest_pain"),
    ("there's a tight squeezing pain in my chest", "chest_pain"),
    ("I think I'm having a heart attack", "chest_pain"),
    ("my face is drooping and my speech is slurred", "stroke"),
    ("suddenly my left arm went numb and weak", "stroke"),
    ("I can't get my words out", "stroke"),
    ("I can't breathe properly", "breathing"),
    ("his lips are turning blue", "breathing"),
    ("my throat is closing after I ate peanuts", "anaphylaxis"),
    ("tongue feels swollen", "anaphylaxis"),
    ("worst headache of my life came on suddenly", "thunderclap_headache"),
    ("I have a fever and a stiff neck", "meningitis"),
    ("high temperature, and my neck is stiff", "meningitis"),
    ("I've been vomiting blood", "major_bleeding"),
    ("the cut won't stop bleeding", "major_bleeding"),
    ("I passed out in the shower", "loss_of_consciousness"),
    ("I want to kill myself", "suicide_risk"),
    ("honestly I don't want to live anymore", "suicide_risk"),
    ("I've been having suicidal thoughts", "suicide_risk"),
    ("everyone would be better off without me", "suicide_risk"),
    ("I keep hurting myself", "suicide_risk"),
    ("No fever, but I do have chest pain", "chest_pain"),          # negation must not cross "but"
    ("I’m having chest pain", "chest_pain"),                       # curly apostrophe
]

NEGATIVE = [
    "I have a flaky itchy scalp",
    "no chest pain at all",
    "I don't have chest pain",
    "denies chest pain or shortness of breath",
    "I'm not suicidal, just tired",
    "no fever",
    "I have a fever and a sore throat",            # fever alone is not a red flag
    "my neck is a bit stiff from sleeping wrong",  # stiff neck alone is not
    "headache since this morning, mild",
    "I noticed some blood in my urine",            # urgent-ish but not an emergency stop
    "I bled a little when I brushed my teeth",
    "I've never fainted",
    "my knee hurts when I climb stairs",
    "",
]


@pytest.mark.parametrize("text,flag", POSITIVE)
def test_positive(text, flag):
    r = check_message(text)
    assert r is not None, text
    assert r.flag == flag, (text, r.flag)


@pytest.mark.parametrize("text", NEGATIVE)
def test_negative(text):
    assert check_message(text) is None, text


def test_suicide_routes_to_988():
    r = check_message("I want to end my life")
    assert r.action == "CALL_988"
    assert any("988" in x["href"] for x in r.resources)


def test_pregnancy_bleeding_only_when_pregnant():
    assert check_message("some spotting today") is None
    r = check_message("some spotting today", {"pregnant": True})
    assert r and r.flag == "pregnancy_emergency" and r.action == "GO_TO_ER"


@pytest.mark.parametrize("answer,status", [
    ("no", "negative"), ("Nope, nothing like that", "negative"), ("i don't", "negative"),
    ("yes", "positive"), ("yeah a bit", "positive"), ("actually my chest feels tight", "positive"),
    ("just the itch on my head", "unclear"),
])
def test_screen(answer, status):
    s, r = evaluate_screen("chest_pain", answer)
    assert s == status, answer
    if status == "positive":
        assert r and r.action == "CALL_911"
