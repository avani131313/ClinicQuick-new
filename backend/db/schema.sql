-- Prelude schema. Runs on any Postgres; Tiger-specific features live in tiger.sql
-- and are applied automatically when the timescaledb / vector extensions exist.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email         text UNIQUE NOT NULL,
  password_hash text NOT NULL,
  role          text NOT NULL DEFAULT 'patient' CHECK (role IN ('patient','clinician','care_team')),
  display_name  text,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS patients (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid REFERENCES users(id) ON DELETE SET NULL,
  name        text NOT NULL,
  dob         date NOT NULL,
  sex         text CHECK (sex IN ('female','male','intersex')),
  gender      text,
  facility    text,              -- e.g. 'Maple Grove Retirement Residence' for care-team residents
  room        text,
  synthetic   boolean NOT NULL DEFAULT true,
  source      text NOT NULL DEFAULT 'app',   -- app | synthea | persona
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS profiles (
  patient_id        uuid PRIMARY KEY REFERENCES patients(id) ON DELETE CASCADE,
  height_cm         real,
  weight_kg         real,
  waist_cm          real,
  pregnant          boolean,
  smoking           text,          -- never | former | current | vape
  audit_c           int[],         -- 3 items 0-4
  active_30min_daily boolean,
  fruit_veg_daily   boolean,
  high_bp           boolean,
  high_blood_sugar  boolean,
  baby_over_4kg     boolean,
  family_diabetes   text[],
  family_history    text[],        -- free list: 'heart disease (father)', ...
  parent_ethnicities text[],
  education         text,
  lives_alone       boolean,
  walking_aid       boolean,
  steadi            jsonb,
  consent_at        timestamptz,
  updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS conditions (
  id serial PRIMARY KEY, patient_id uuid REFERENCES patients(id) ON DELETE CASCADE,
  name text NOT NULL, code text, onset date, status text DEFAULT 'active', source text DEFAULT 'self');
CREATE TABLE IF NOT EXISTS medications (
  id serial PRIMARY KEY, patient_id uuid REFERENCES patients(id) ON DELETE CASCADE,
  name text NOT NULL, dose text, source text DEFAULT 'self');
CREATE TABLE IF NOT EXISTS allergies (
  id serial PRIMARY KEY, patient_id uuid REFERENCES patients(id) ON DELETE CASCADE,
  substance text NOT NULL, reaction text, source text DEFAULT 'self');

CREATE TABLE IF NOT EXISTS encounters (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id      uuid REFERENCES patients(id) ON DELETE CASCADE,
  started_at      timestamptz NOT NULL DEFAULT now(),
  ended_at        timestamptz,
  chief_complaint text,
  status          text NOT NULL DEFAULT 'active',  -- active | complete | stopped_red_flag
  state           jsonb NOT NULL DEFAULT '{}'::jsonb, -- slots, considerations, pending screen
  urgency         text
);

CREATE TABLE IF NOT EXISTS interview_turns (
  id           serial PRIMARY KEY,
  encounter_id uuid REFERENCES encounters(id) ON DELETE CASCADE,
  ts           timestamptz NOT NULL DEFAULT now(),
  question     text NOT NULL,
  answer       text,
  q_type       text NOT NULL,     -- STANDARD | AI_PERSONALISED | SAFETY_SCREEN
  slot         text,
  rationale    text
);

CREATE TABLE IF NOT EXISTS red_flag_events (
  id serial PRIMARY KEY, encounter_id uuid REFERENCES encounters(id) ON DELETE CASCADE,
  ts timestamptz NOT NULL DEFAULT now(), flag text, label text, matched_text text, action text);

CREATE TABLE IF NOT EXISTS risk_scores (
  id serial PRIMARY KEY, patient_id uuid REFERENCES patients(id) ON DELETE CASCADE,
  encounter_id uuid REFERENCES encounters(id) ON DELETE CASCADE,
  name text, version text, inputs jsonb, value real, band text, severity int, summary text,
  citation text, citation_url text, computed_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS reports (
  encounter_id  uuid PRIMARY KEY REFERENCES encounters(id) ON DELETE CASCADE,
  patient_json  jsonb, clinician_json jsonb, fhir_bundle jsonb,
  generated_by  text, created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id uuid REFERENCES patients(id) ON DELETE CASCADE,
  uploaded_by text, kind text, filename text, mime text, content bytea,
  extracted jsonb, confirmed boolean DEFAULT false, ts timestamptz NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS shares (
  token text PRIMARY KEY, patient_id uuid REFERENCES patients(id) ON DELETE CASCADE,
  encounter_id uuid REFERENCES encounters(id) ON DELETE CASCADE,
  expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS audit_log (
  id serial PRIMARY KEY, ts timestamptz NOT NULL DEFAULT now(),
  actor text, action text, patient_id uuid, detail jsonb);

CREATE TABLE IF NOT EXISTS alerts (
  id serial PRIMARY KEY, patient_id uuid REFERENCES patients(id) ON DELETE CASCADE,
  ts timestamptz NOT NULL DEFAULT now(), status text, headline text, risks text[],
  signals jsonb, explanation text, acknowledged_by text, acknowledged_at timestamptz);

-- Time series. On Tiger these become hypertables (tiger.sql).
CREATE TABLE IF NOT EXISTS observations (
  patient_id uuid NOT NULL, ts timestamptz NOT NULL, code text NOT NULL,
  value double precision, unit text, source text);
CREATE INDEX IF NOT EXISTS observations_pid_code_ts ON observations (patient_id, code, ts DESC);

CREATE TABLE IF NOT EXISTS checkins (
  patient_id uuid NOT NULL, ts timestamptz NOT NULL,
  ate_meals boolean, slept_ok boolean, dizzy boolean, fell boolean, confused boolean,
  pain int, note text, recorded_by text);
CREATE INDEX IF NOT EXISTS checkins_pid_ts ON checkins (patient_id, ts DESC);

-- Patient memory (text always; embedding column added by tiger.sql when pgvector exists)
CREATE TABLE IF NOT EXISTS memory_chunks (
  id serial PRIMARY KEY, patient_id uuid REFERENCES patients(id) ON DELETE CASCADE,
  ts timestamptz NOT NULL DEFAULT now(), kind text, text text NOT NULL);

-- v2: expanded history, doctors, appointments, interview media -------------------------
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS surgeries text[];
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS hospitalized_past_year boolean;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS occupation text;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS sleep_hours real;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS recreational_drugs text;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS vaccines_up_to_date text;   -- yes | no | not_sure
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS last_menstrual_period date;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS blood_type text;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS emergency_contact text;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS mental_health_history text[];

CREATE TABLE IF NOT EXISTS clinicians (
  user_id    uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  name       text NOT NULL,
  clinic     text,
  specialty  text,
  city       text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS appointments (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id    uuid REFERENCES patients(id) ON DELETE CASCADE,
  clinician_id  uuid REFERENCES clinicians(user_id) ON DELETE CASCADE,
  encounter_id  uuid REFERENCES encounters(id) ON DELETE SET NULL,
  starts_at     timestamptz NOT NULL,
  minutes       int NOT NULL DEFAULT 20,
  reason        text,
  status        text NOT NULL DEFAULT 'booked',   -- booked | cancelled | completed
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS appointments_slot ON appointments (clinician_id, starts_at) WHERE status = 'booked';

ALTER TABLE documents ADD COLUMN IF NOT EXISTS encounter_id uuid REFERENCES encounters(id) ON DELETE SET NULL;

-- v3: medication history (doses, dates, reasons), walk-in queue -----------------------
ALTER TABLE medications ADD COLUMN IF NOT EXISTS frequency text;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS route text;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS reason text;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS prescriber text;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS start_date date;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS end_date date;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS stop_reason text;
ALTER TABLE medications ADD COLUMN IF NOT EXISTS notes text;

CREATE TABLE IF NOT EXISTS walkin_checkins (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id  uuid REFERENCES patients(id) ON DELETE CASCADE,
  clinic_id   text NOT NULL,
  clinic_name text,
  joined_at   timestamptz NOT NULL DEFAULT now(),
  ahead_at_join int NOT NULL,
  minutes_per_patient real NOT NULL,
  status      text NOT NULL DEFAULT 'waiting'   -- waiting | seen | left
);

-- v4: home exercises (physio) a clinician assigns; the camera coach in the app tracks them
CREATE TABLE IF NOT EXISTS exercise_plans (
  id          serial PRIMARY KEY,
  patient_id  uuid REFERENCES patients(id) ON DELETE CASCADE,
  exercise    text NOT NULL,              -- key the app knows how to coach: squat | arm_raise | knee_raise
  sets        int NOT NULL DEFAULT 2,
  reps        int NOT NULL DEFAULT 10,
  notes       text,
  assigned_by text,
  active      boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now()
);
