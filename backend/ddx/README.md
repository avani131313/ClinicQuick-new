# DDX — symptom-model decision support (clinician-only)

A LightGBM model trained on DDXPlus (49 conditions) plus a generated blood-in-urine module (10 conditions) ranks the
patient's most likely conditions for the **doctor**. Patients never see condition names or probabilities.

- **Doctor visit page and clinician share link:** a "Symptom model: top 5" panel with a probability per condition
  (capped at 80%, never certainty), ICD-10, "must rule out" flags, confidence, the questions that would best separate
  the candidates, and every input the model used, grouped by source.
- **Lena (typed and live voice):** a hidden hint with the leading candidates and the questions to ask. She asks sharper
  questions and can offer safe next steps, but never names a condition. In live voice the hint is sent between turns
  only, so she is never cut off. Set `DDX_LIVE_HINTS=0` in `.env` to turn that off.
- **Patient summary:** extra safe next steps (for example "drink plenty of water"; "see a doctor soon" whenever a
  serious condition is possible). No condition names.

## Inputs (everything ClinicQuick has on the patient)
| Source | Used for |
|---|---|
| Lena conversation (typed or live) | symptoms, "no" answers, pain location and intensity, urine colour, onset after exercise (Gemini extraction plus a keyword fallback) |
| Profile | age, sex, smoking, pregnancy, last period, high BP, high blood sugar, BMI, AUDIT-C, activity, vaccines, occupation, family history |
| Conditions and current medicines | e.g. apixaban → on a blood thinner; ibuprofen → NSAID use (stopped medicines are ignored) |
| Wearables / Apple Health / demo watch | step spike → "after intense exercise"; temperature ≥ 38 °C → fever; home BP ≥ 140 → high BP; resting HR, SpO2, sleep, breathing rate, weight, labs → shown to the doctor as context |

Ranking only includes conditions that can cause the patient's **main complaint** (the opening answer), as in DDXPlus.
So hay fever never ranks for blood in urine, even with a family history of asthma.

## Files
| File | What it does |
|---|---|
| `runtime.py` | loads `model/` and scores patients |
| `evidence.py` | turns all patient data into model inputs |
| `guidance.py` | top 5, 80% cap, flags, confidence, separating questions, patient advice, Lena's hint |
| `service.py` | computes and caches per encounter in the `ddx_predictions` table (a hypertable on Tiger) |
| `router.py` | `GET /ddx/status`, `GET /ddx/doctor/encounters/{id}` (that patient's doctors only, audited), `GET /ddx/share/{token}`, `POST /ddx/wearables/samsung` |
| `samsung.py` | best-effort Samsung Health export import (zip/CSV) into `observations` (no UI yet) |
| `data/` | the 237 questions, 59 conditions, which symptoms belong to which condition |
| `model/` | the trained model: `best_model.pkl`, `train.py`, `prepare.py`, `data/meta.json` (all from one run) |

Check it works: `GET http://localhost:8000/ddx/status` → `{"model_loaded": true, "conditions": 59}`.

## Hooks in the rest of the app (all marked `ddx` / `DDX`)
| File | Hook |
|---|---|
| `app/main.py` | registers the `/ddx` router |
| `app/interview.py` | `ddx_hint(encounter_id)` added to Lena's typed-interview prompt |
| `app/live.py` | `ddx_live_hint` re-ranks after each answer; `ddx_push()` sends the hint to Gemini Live between turns |
| `app/report.py` | `ddx_next_steps(encounter_id)` added to the patient's next steps |
| `frontend/components/DdxPanel.tsx` + `ddx.module.css` | the doctor panel (dark and light themes) |
| `frontend/app/doctor/visit/[id]/page.tsx`, `frontend/app/clinician/[token]/page.tsx` | show the panel above the clinician note |
| `requirements.txt`, `Dockerfile` | numpy, pandas, scikit-learn, lightgbm; `libgomp1`; `COPY ddx ./ddx` |

## Limits
- Knows 59 conditions: mostly breathing, throat and chest, plus blood in urine. Other complaints show "outside what the
  model knows".
- Without a working Gemini key, only the urinary keyword rules extract symptoms, so non-urinary complaints show as
  out of scope.
- Training data is synthetic (DDXPlus) or generated. Probabilities are the model's confidence, not calibrated clinical risk.
