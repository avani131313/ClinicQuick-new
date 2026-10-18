-- Used only when TimescaleDB is NOT available (local dev on plain Postgres).
-- Same shape as the Tiger continuous aggregate so the app code doesn't change.
CREATE OR REPLACE VIEW daily_obs AS
SELECT patient_id, code, date_trunc('day', ts) AS day,
       sum(value) AS sum_v, avg(value) AS avg_v, min(value) AS min_v, max(value) AS max_v, count(*) AS n
FROM observations
GROUP BY patient_id, code, date_trunc('day', ts);
