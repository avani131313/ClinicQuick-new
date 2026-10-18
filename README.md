# ClinicQuick

ClinicQuick gets your story ready before you see the doctor. **Lena**, an AI intake assistant, does the nurse's interview by voice or text, asks the follow-up questions a nurse would, stops for emergencies using fixed safety rules, and hands the clinician one clear page. Around that sits a patient app for booking or walking in, medicines, health data from your watch, physio exercises with a camera coach, and a fall alert, plus a clinician portal for the day's visits.

Built for Hack the Valley 11. **All people and records are synthetic.**

## What's in it

**For patients**
- **Check-in with Lena**: live voice, turn-based talk, or typing. Attach a photo or short video. Red-flag symptoms stop the interview and show what to do now.
- **Summary and next step**: plain-language summary and where to go (pharmacist, walk-in, family doctor or ER), shareable with the clinic as a link, QR code or FHIR file.
- **Book & walk-in**: book an appointment, or see nearby walk-in clinics on a map with how many people are waiting and when everyone will be seen. Join a line remotely and watch your place in it.
- **Health data**: a 3D anatomy figure (muscle or point-cloud view) with an anatomical heart beating at your heart rate, plus Apple Health trends: resting heart rate, HRV, sleep, steps, blood oxygen, blood pressure. A button fills in realistic demo watch data.
- **Medications**: current and past medicines, doses, and a timeline.
- **Physio**: exercises your clinician assigned. The camera coach draws your skeleton over the live video, shows a guide figure doing the movement, counts reps from joint angles and gives form tips out loud. Tracking runs in the browser; no video is uploaded.
- **Safety (fall alert)**: on a phone, motion sensors watch for a hard fall followed by stillness. Then three buzzes asking "Are you okay?", then an alarm with a spoken countdown, then a call to a medical help line (Health811 in the demo, never 911).
- Records vault, appointment notifications, dark and light mode, and a **phone view** toggle that shows the whole app in a phone frame.

**For clinicians**
- **Today**: the next visit's intake summary up front, past visits a click away.
- **Patients**: a dashboard per patient with health trends, medications (prescribe or stop), physio exercises to assign, visit history, and uploads of previous records.

## Stack

```
frontend/   Next.js 15 (App Router, TypeScript, CSS modules)
  three.js            3D body, heart, and Lena's wireframe
  Leaflet + OSM       walk-in clinic map (no API key)
  MediaPipe Pose      physio camera coach, loaded from a CDN at runtime
  scripts/body/       Python generators for the 3D models in public/models
backend/    FastAPI (Python 3.12+), Postgres (Tiger Cloud / TimescaleDB, or plain Postgres), Gemini
  app/safety.py       hard-coded red flags (negation-aware, tested)
  app/interview.py    intake slot state machine; Gemini picks the next question, offline fallback
  app/live.py         live voice with Gemini Live, safety-checked transcript
  app/report.py       patient summary + clinician note (AI can raise urgency, never lower it)
  app/scores.py       CANRISK, PHQ-2, GAD-2, AUDIT-C, STEADI, BMI with sources
  app/accounts.py     accounts, profiles, booking, clinician views, record uploads
  app/meds.py, app/physio.py, app/walkin.py, app/notifications.py, app/health.py
  app/fhir.py         FHIR R4 export;  app/vault.py  document upload and Apple Health import
  db/schema.sql       tables (applied on startup)
  scripts/seed.py     demo patients, clinician, visits, watch data
docker-compose.yml + deploy/Caddyfile   one-box deploy with HTTPS
```

## Run it locally

**1. Database.** Create a free service on [Tiger Cloud](https://console.cloud.timescale.com) and copy its URL, or use local Postgres (Tiger-only features switch off automatically).

**2. Backend**
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add DATABASE_URL and GEMINI_API_KEY
python -m scripts.seed        # demo accounts and data (wipes existing demo data)
uvicorn app.main:app --reload --port 8000
python -m pytest -q           # tests
```
http://localhost:8000/health shows whether the database extensions and Gemini are active.

**3. Frontend**
```bash
cd frontend
npm install
echo 'NEXT_PUBLIC_API_URL=http://localhost:8000' > .env.local
npm run dev                   # http://localhost:3000
```

**Demo logins** (password `demo1234`)

| Login | Who |
|---|---|
| aisha@prelude.demo | Aisha, 23. Healthy student with a new symptom |
| robert@prelude.demo | Robert, 68. Heart rhythm condition, on a blood thinner |
| dr.chen@prelude.demo | Clinician. Today's visits, patient dashboards, records |

Red-flag demo: start a check-in and type *"crushing chest pressure going down my arm"*.

**On a real phone.** Motion sensors (fall alert) and the camera (physio) need the site to open over https, and the phone must be able to reach the backend. Run the frontend with `npx next dev --experimental-https -H 0.0.0.0`, set `NEXT_PUBLIC_API_URL` to an address the phone can reach, and open it on the same Wi-Fi. On a laptop, use **Simulate a fall** and **Practice with the guide**.

## Without a Gemini key

Everything still runs. The interview uses a built-in question set per complaint type and notes are written by rules; the app shows which mode is active. With a key, Gemini writes each question, fills the intake, writes the summary and clinician note, reads uploaded lab PDFs and photos, and powers live voice. The rules still decide emergencies, scores and minimum urgency.

## 3D models

The body, heart and Lena are generated, not downloaded. To rebuild them (needs numpy, scikit-image, scipy, pyfqmr), see `frontend/scripts/body/README.md`.

## Deploy

```bash
git clone https://github.com/avani131313/ClinicQuick-new.git && cd ClinicQuick-new
cp backend/.env.example backend/.env   # fill in
DOMAIN=yourdomain.ca docker compose up -d --build
docker compose exec api python -m scripts.seed
```
Caddy gets HTTPS certificates automatically. The API is served at `https://yourdomain/api`.

## Safety notes

ClinicQuick is pre-visit intake, navigation and decision support. It does not diagnose and does not replace a clinician. Walk-in clinics and wait times are simulated. In an emergency, call 911.
