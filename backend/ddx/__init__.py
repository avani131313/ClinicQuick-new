"""DDX: symptom-model decision support for ClinicQuick (doctor-only rankings, hidden hints for Lena).

Hooks used by the rest of the app:
  from ddx.router import router            # app.include_router(router) in app/main.py
  from ddx.service import lena_hint        # extra line in interview._gemini_next() prompt
  from ddx.service import patient_next_steps  # optional: safe next steps in report.generate()
"""
