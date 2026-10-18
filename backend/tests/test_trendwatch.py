from datetime import date, timedelta

from app.trendwatch import evaluate, explain_offline

END = date(2026, 10, 17)


def make_daily(steps_fn, rhr_fn=lambda i: 68, sleep_fn=lambda i: 420, days=30):
    rows = []
    for i in range(days):
        d = END - timedelta(days=days - 1 - i)
        rows += [{"day": d, "code": "steps", "value": steps_fn(i)},
                 {"day": d, "code": "rhr", "value": rhr_fn(i)},
                 {"day": d, "code": "sleep_min", "value": sleep_fn(i)}]
    return rows


def test_stable_is_ok():
    r = evaluate(make_daily(lambda i: 4000 + (i % 3) * 100), [], END)
    assert r.status == "ok" and not r.signals


def test_margaret_decline_alerts_with_reasons():
    daily = make_daily(lambda i: 4200 if i < 25 else 2300)   # last 5 days ~45% down
    checkins = [
        {"day": END - timedelta(days=3), "ate_meals": False},
        {"day": END - timedelta(days=1), "ate_meals": False},
        {"day": END - timedelta(days=2), "confused": True, "note": "feels muddled this morning"},
    ]
    r = evaluate(daily, checkins, END, name="Margaret Ellis")
    keys = {s.key for s in r.signals}
    assert r.status == "alert"
    assert {"mobility_down", "intake_down", "cognition"} <= keys
    assert "falls" in r.risks and "delirium" in r.risks
    mob = next(s for s in r.signals if s.key == "mobility_down")
    assert mob.evidence["drop_pct"] >= 40
    text = explain_offline(r, "Margaret Ellis")
    assert "Margaret was flagged because" in text and "muddled" in text


def test_single_signal_is_watch():
    daily = make_daily(lambda i: 4000, rhr_fn=lambda i: 66 if i < 27 else 80)
    r = evaluate(daily, [], END)
    assert r.status == "watch" and r.signals[0].key == "rhr_up"


def test_insufficient_baseline_no_false_alarm():
    daily = make_daily(lambda i: 500, days=4)
    assert evaluate(daily, [], END).status == "ok"
