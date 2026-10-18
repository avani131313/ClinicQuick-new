# ClinicQuick — handoff notes (for a teammate or another AI assistant)

Hack the Valley 11 project. Pre-visit AI intake ("Lena") plus a patient app and clinician portal. Formerly called Prelude. All data synthetic.
Read README.md first for setup. This file explains the current state and what's next.

## Stack
- backend/ — FastAPI (Python 3.12+), Postgres on **Tiger Cloud** (TimescaleDB hypertables, continuous aggregate `daily_obs`, pgvector memory), **Gemini** via `google-genai`.
- frontend/ — Next.js 15 (App Router, TypeScript, CSS modules, no Tailwind). Talks to the API at `NEXT_PUBLIC_API_URL`.
- Secrets live only in `backend/.env` (never commit): DATABASE_URL, GEMINI_API_KEY, GEMINI_FAST_MODEL=gemini-3.5-flash-lite, JWT_SECRET.

## Key backend files
| File | What it does |
|---|---|
| app/safety.py | Hard-coded red flags (negation-aware). Runs on every patient message. 40+ tests. |
| app/scores.py | CANRISK, PHQ-2, GAD-2, AUDIT-C, STEADI, BMI in plain Python with citations. |
| app/trendwatch.py, app/care.py | Care-home Trend Watch: per-resident baselines → signals → "why flagged". |
| app/interview.py | Typed/turn-based interview: slot state machine, Gemini picks next question, offline fallback. |
| app/live.py | **Live voice** WebSocket `/live/{encounter_id}?t=TOKEN` ⇄ Gemini Live (`GEMINI_LIVE_MODEL`, default gemini-3.8-live). Safety check on live transcript; background "intake sheet" tagging. |
| app/report.py | Patient report (no disease list) + clinician note. AI can raise urgency, never lower (triage.py). |
| app/accounts.py | Register patient/clinician, profile CRUD, doctors + booking, doctor views, interview media, /tts, connections. |
| app/gemini.py | Gemini wrapper: JSON schemas, thinking-level fallback ladder, 12 s cap per question. |
| app/tts.py | Gemini text-to-speech for the turn-based talk mode. |

## Key frontend files
| File | What it does |
|---|---|
| app/page.tsx + components/PulseField.tsx | Dark scroll-story landing with morphing point-cloud heart. |
| app/signup, app/login, components/AuthShell.tsx | Minimal split-screen auth; role choice Patient / Clinician. |
| app/start/page.tsx | One-time health profile questionnaire (after sign-up). |
| app/visit/[id]/page.tsx | Check-in: chooser (Talk/Type) → **LiveMode** (live voice) → falls back to **TalkMode** (turn-based voice) → typed chat. |
| components/LiveMode.tsx + public/pcm-capture.js | Live voice client: mic → 16 kHz PCM over WebSocket; plays 24 kHz audio; interruptions; orb. |
| components/TalkMode.tsx, components/VoiceOrb.tsx, lib/voice.ts | Turn-based voice mode and the animated orb. |
| app/visit/[id]/report/page.tsx | Report: "Book an appointment" / "Find care near me"; share link, FHIR. |
| app/doctor/*, app/care/*, app/connect, app/profile, app/vault | Doctor dashboard, care-home dashboard, connected data, profile editing, records. |

## Demo accounts (password demo1234)
Reset everything with `python -m scripts.seed --reset` (from backend/, WIPES ALL DATA):
- aisha@prelude.demo: 23F, healthy, past UTI. Say "blood in my urine": asked about her period, see-soon urgency.
- robert@prelude.demo: 68M, former smoker, AF on apixaban. Same complaint: asked about other bleeding, same-day urgency, malignancy must be ruled out.
- dr.chen@prelude.demo: Dr. Maya Chen. Upcoming + past appointments, patient history page (/doctor/patient/[id]).

## Status
- Working and tested: everything except the items below.
- **Live voice:** backend tested with a simulated Gemini Live session; browser side type-checks but has NOT been run against real Gemini Live yet. First real test needed.
  - If the live model ID errors, check https://ai.google.dev/gemini-api/docs/live-guide and set `GEMINI_LIVE_MODEL` / `GEMINI_LIVE_VOICE` in .env.
  - Watch the backend log for `live session failed` — the browser then falls back to TalkMode automatically.
- Not built: Vultr deploy (docker-compose.yml + deploy/Caddyfile are ready), GoDaddy domain, Devpost write-up.

## Next steps (in order)
1. Test live voice with real Gemini (Chrome, headphones). Fix any SDK/model errors in app/live.py.
2. Run the demo script in README / spec; record a backup demo video.
3. Deploy to Vultr with docker compose; point a GoDaddy domain at it.
4. Devpost: list Tiger Data (hypertables, continuous aggregate, compression, pgvector), Gemini (live voice, TTS, structured interview, multimodal lab extraction), Vultr, GoDaddy.

## Rules the code follows (keep them)
- Never diagnose to patients; "conditions to consider" are clinician-only.
- Emergencies are decided by code (safety.py), not the AI.
- Scores are computed in code; the AI only explains.
- Never commit backend/.env.
