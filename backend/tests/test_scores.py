from datetime import date

from app import scores


def test_age():
    assert scores.age_from_dob("2010-10-18", date(2026, 10, 17)) == 15
    assert scores.age_from_dob("2010-10-17", date(2026, 10, 17)) == 16


def test_bmi():
    r = scores.bmi(170, 72.25)
    assert r.value == 25.0 and r.band == "overweight"
    assert scores.bmi(None, 70).value is None


def test_canrisk_not_applicable_under_40():
    r = scores.canrisk({"age": 19, "sex": "female"})
    assert not r.applicable and r.band == "not applicable"


def test_canrisk_low():
    r = scores.canrisk({"age": 42, "sex": "female", "bmi": 22, "waist_cm": 72, "active_30min_daily": True,
                        "fruit_veg_daily": True, "parent_ethnicities": ["white"], "education": "degree"})
    assert r.value == 0 and r.band == "low"


def test_canrisk_high_example():
    # 68 (15) + male (6) + BMI 31 (9) + waist 105 (6) + inactive (1) + no fruit daily (2)
    # + high BP (4) + father diabetic (2) + south asian (11) + high school (1) = 57
    r = scores.canrisk({"age": 68, "sex": "male", "bmi": 31, "waist_cm": 105, "active_30min_daily": False,
                        "fruit_veg_daily": False, "high_bp": True, "high_blood_sugar": False,
                        "family_diabetes": ["father"], "parent_ethnicities": ["white", "south_asian"],
                        "education": "high_school"})
    assert r.value == 57 and r.band == "high" and r.severity == 2


def test_canrisk_moderate_and_family_cap():
    # 50 (7) + female (0) + BMI 27 (4) + waist 85 (4) + family 5 relatives capped at 8 = 23
    r = scores.canrisk({"age": 50, "sex": "female", "bmi": 27, "waist_cm": 85,
                        "family_diabetes": ["mother", "father", "sibling", "child", "other"],
                        "parent_ethnicities": ["white"], "education": "degree"})
    assert r.value == 23 and r.band == "moderate"


def test_phq2_gad2():
    assert scores.phq2([1, 1]).band == "negative screen"
    assert scores.phq2([2, 1]).band == "positive screen"
    assert scores.gad2([3, 3]).value == 6
    assert not scores.gad2(None).applicable


def test_audit_c_sex_cutoffs():
    assert scores.audit_c([1, 1, 1], "female").band == "positive screen"
    assert scores.audit_c([1, 1, 1], "male").band == "negative screen"
    assert scores.audit_c([2, 1, 1], "male").band == "positive screen"


def test_steadi():
    r = scores.steadi({"fallen_past_year": True, "worried_falling": True, "push_to_stand": True})
    assert r.value == 4 and r.band == "at risk of falling"
    assert scores.steadi({"often_sad": True}).band == "lower risk"


def test_applicable():
    assert "STEADI" in scores.applicable_scores({"age": 81})
    assert "CANRISK" not in scores.applicable_scores({"age": 19})
    assert "PHQ-2" in scores.applicable_scores({"age": 30}, {"mood"})
