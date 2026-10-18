-- Tiger Data (TimescaleDB + pgvector) features. Applied by app/db.py only when the
-- extensions are available, so the app still runs on plain Postgres for local dev.

-- 1. Hypertables: wearable vitals and daily check-ins partitioned by time.
SELECT create_hypertable('observations', by_range('ts'), if_not_exists => TRUE, migrate_data => TRUE);
SELECT create_hypertable('checkins',     by_range('ts'), if_not_exists => TRUE, migrate_data => TRUE);

-- 2. Continuous aggregate: per-person daily rollups that power baselines + sparklines.
--    steps & sleep are summed per day, heart rate is averaged.
CREATE MATERIALIZED VIEW IF NOT EXISTS daily_obs
WITH (timescaledb.continuous) AS
SELECT patient_id,
       code,
       time_bucket('1 day', ts) AS day,
       sum(value) AS sum_v,
       avg(value) AS avg_v,
       min(value) AS min_v,
       max(value) AS max_v,
       count(*)   AS n
FROM observations
GROUP BY patient_id, code, time_bucket('1 day', ts)
WITH NO DATA;

SELECT add_continuous_aggregate_policy('daily_obs',
  start_offset => INTERVAL '90 days', end_offset => INTERVAL '1 hour',
  schedule_interval => INTERVAL '15 minutes', if_not_exists => TRUE);

-- 3. Columnstore compression for older raw vitals (90%+ smaller on the free tier).
ALTER TABLE observations SET (timescaledb.compress, timescaledb.compress_segmentby = 'patient_id, code');
SELECT add_compression_policy('observations', INTERVAL '14 days', if_not_exists => TRUE);

-- 4. pgvector: semantic memory of past visits, conditions and labs.
ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS embedding vector(768);
CREATE INDEX IF NOT EXISTS memory_chunks_embedding ON memory_chunks USING hnsw (embedding vector_cosine_ops);
