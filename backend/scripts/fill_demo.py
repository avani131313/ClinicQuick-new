"""Fill the demo patients' health profiles and medication histories WITHOUT wiping anything else.

    python -m scripts.fill_demo        # from backend/
"""
from datetime import datetime, timedelta, timezone

from app import db
from app.context import invalidate
from scripts.demo_data import apply_meds, apply_profile

EMAILS = {"aisha": "aisha@prelude.demo", "robert": "robert@prelude.demo"}


def main():
    db.init_schema()
    today = datetime.now(timezone(timedelta(hours=-4))).date()
    for key, email in EMAILS.items():
        row = db.q1("SELECT p.id FROM patients p JOIN users u ON u.id = p.user_id WHERE u.email=%s", (email,))
        if not row:
            print(f"skip {email}: not found (run python -m scripts.seed first)")
            continue
        pid = str(row["id"])
        apply_profile(pid, key)
        apply_meds(pid, key, today)
        invalidate(pid)
        print(f"filled {email}")
    db.close()


if __name__ == "__main__":
    main()
