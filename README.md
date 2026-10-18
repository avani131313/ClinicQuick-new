# Prelude

Prelude does the nurse's interview before you see the doctor. It asks the follow-up questions a triage nurse would, stops for emergencies using fixed rules, works out where you should go (pharmacist, walk-in, or ER), and gives the clinician a structured note. For care homes, **Trend Watch** compares each resident with their own baseline and explains why someone is flagged.

Built for Hack the Valley 11. **All data is synthetic.**

```
frontend/   Next.js 15 (TypeScript). Patient app, clinician portal, care-team dashboard
backend/    FastAPI (Python 3.12+). Safety rules, scores, Trend Watch, Gemini interviewer, FHIR export
  app/safety.py      hard-coded red flags (negation-aware, 40+ tests)
  app/scores.py      CANRISK, PHQ-2, GAD-2, AUDIT-C, STEADI, BMI — pure Python, cited
  app/trendwatch.py  per-resident baseline rules + explanations (the PCC piece)
  app/interview.py   slot state machine; Gemini picks the next question, offline protocol as fallback
  app/triage.py      navigation rules incl. Ontario pharmacist minor ailments (July 2026 list)
  app/report.py      patient report (no disease list) + nurse-style clinician note
  app/fhir.py        FHIR R4 transaction bundle + push to HAPI test server
  app/vault.py       document upload, Gemini lab extraction, Apple Health export import
  db/schema.sql      tables;  db/tiger.sql  hypertables, continuous aggregate, compression, pgvector
  scripts/seed.py         demo personas + Maple Grove residents + 60 days of wearable data
  scripts/load_synthea.py load Synthea FHIR bundles
docker-compose.yml + deploy/Caddyfile   one-box deploy on Vultr with HTTPS
```

## Run it locally (10 minutes)

**1. Database.** Create a free service on [Tiger Cloud](https://console.cloud.timescale.com) and copy the service URL. Plain local Postgres also works: Tiger features switch off automatically and a normal view replaces the continuous aggregate.

**2. Backend**
```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # paste DATABASE_URL and GEMINI_API_KEY
.venv/bin/python -m scripts.seed           # personas, residents, wearable data
# optional: real Synthea patients
#   java -jar synthea-with-dependencies.jar -p 25 --exporter.fhir.export=true --exporter.years_of_history=5
#   .venv/bin/python -m scripts.load_synthea output/fhir --accounts 3
.venv/bin/uvicorn app.main:app --reload --port 8000
.venv/bin/python -m pytest -q              # 61 tests
```
Visit http://localhost:8000/health. It shows whether TimescaleDB, pgvector and Gemini are active.

**3. Frontend**
```bash
cd frontend
npm install
echo 'NEXT_PUBLIC_API_URL=http://localhost:8000' > .env.local
npm run dev        # http://localhost:3000
```

**The flow:** landing page → **Sign up** (choose patient or doctor) → patients answer the one-time health profile → straight into the check-in with Lena → summary → **Book an appointment** or **Find care near me**. Doctors see their bookings with the intake note attached, and can upload visit documents back into the patient's record. Patients can edit their profile any time; age is always calculated from date of birth.

**Voice, photo and video:** the mic button uses the browser's speech recognition (Chrome, Edge, Safari; hidden in Firefox). "Read questions aloud" uses the browser's built-in voices. The camera button attaches a photo or a short video (20 MB max). With Gemini on, it's described objectively, and that description shapes the next questions and appears in the clinician note.

**Demo logins** (password `demo1234`)

| Login | Who | Shows |
|---|---|---|
| priya@prelude.demo | Priya, 19 | flaky scalp → **pharmacist** (dandruff is an Ontario minor ailment) |
| jordan@prelude.demo | Jordan, 16, athlete | blood in urine → benign causes lead |
| robert@prelude.demo | Robert, 68, ex-smoker on apixaban | blood in urine → malignancy "must rule out", personalised blood-thinner questions |
| care@maplegrove.demo | Nurse Aisha | Maple Grove dashboard; **Margaret Ellis** flagged |
| dr.chen@clinic.demo | Dr. Maya Chen | doctor's appointments with intake notes (also dr.haddad@, np.singh@) |

Red-flag demo: start any check-in and type *"crushing chest pressure going down my arm"*.

## Without a Gemini key

Everything still works. The interview uses a built-in question set for each complaint type (scalp/skin, blood in urine, headache, generic), and notes are written by rules. The UI shows which mode is running. With a key, Gemini writes each question, fills the intake slots, ranks conditions to consider (with ↑/↓ reasons), writes the report, reads uploaded lab PDFs and photos, and writes the nurse handover text. The rules still decide emergencies, scores and minimum urgency. **AI can raise urgency, never lower it.**

## Deploy (Vultr + GoDaddy)

1. Create a Vultr instance (Ubuntu, Docker marketplace image). Use promo code `MAJORLEAGUEHACKING`.
2. Register a domain through GoDaddy Registry (promo `MLHHTV2689`). Add an **A record** pointing to the instance IP.
3. On the box:
   ```bash
   git clone <repo> && cd prelude
   cp backend/.env.example backend/.env   # fill in
   DOMAIN=yourdomain.ca docker compose up -d --build
   docker compose exec api python -m scripts.seed
   ```
   Caddy gets HTTPS certificates automatically. The API is served at `https://yourdomain/api`.

## How it maps to the judging

| Track | Where |
|---|---|
| **PCC: Catch It Early** | `/care`: per-resident baselines, rule signals, "why flagged", suggested checks, review acknowledgement, staff check-ins that re-run Trend Watch live |
| **Tiger Data** | hypertables (`observations`, `checkins`), continuous aggregate `daily_obs` (baselines + sparklines), compression policy, pgvector memory (`memory_chunks.embedding`), all in one Postgres |
| **Gemini** | interviewer (structured output), report and clinician note, multimodal lab extraction, embeddings for patient memory, care handover text |
| **Vultr / GoDaddy** | compose deploy above |

## Not yet verified (no network access from the build box)

- **Live Gemini calls.** The schemas convert correctly and the Gemini path was exercised with a mocked model. Run one real interview once the key is in. If the model name errors, set `GEMINI_FAST_MODEL` in `.env`.
- **`db/tiger.sql` on a real Tiger service.** It was written against current TimescaleDB syntax but only plain Postgres was available here. Check `/health` after the first start.
- **FHIR push to hapi.fhir.org.** The bundle is built and downloadable; the push needs internet access.
- **Apple Health import** with a real `export.zip`.

## Safety notes for the pitch

Say: pre-visit intake, navigation, decision support, "PHIPA-aware", synthetic data.
Don't say: diagnoses, replaces doctors, PHIPA/HIPAA compliant, "trains on your data". Memory is retrieval: past visits are embedded and pulled into the prompt.

CANRISK point values follow the published PHAC questionnaire. STEADI, PHQ-2, GAD-2 and AUDIT-C use their standard cut-offs. Sources are linked from every score.
