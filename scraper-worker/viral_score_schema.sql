-- Tabel hasil Viral Scorecard (lapisan keputusan) di DB-VPS db `scraper`, schema `trend`.
-- Idempoten. Pakai: cat viral_score_schema.sql | ssh db-vps 'sudo -n -u postgres psql -d scraper -v ON_ERROR_STOP=1 -f -'
SET ROLE scraper;
CREATE SCHEMA IF NOT EXISTS trend;

CREATE TABLE IF NOT EXISTS trend.viral_score (
  id          bigserial PRIMARY KEY,
  run_id      text        NOT NULL,
  video_id    text        NOT NULL REFERENCES trend.tiktok_video(video_id) ON DELETE CASCADE,
  scored_at   timestamptz NOT NULL DEFAULT now(),
  -- sub-skor 1..5 (NULL = pending, mis. analyzer belum jalan)
  s_hook      real, s_pacing real, s_rewatch real,      -- G1 (analyzer .50)
  s_emosi     real, s_relate real, s_share  real,       -- G2 (analyzer / Gemini / scraper)
  s_trend     real, s_universal real,                   -- G3 (scraper / Gemini)
  s_speed     real, s_roi   real,                        -- G4 (heuristik)
  -- rata-rata grup + total tertimbang
  g1 real, g2 real, g3 real, g4 real,
  total       real,
  zone        text,        -- green | yellow | red   (provisional kalau !complete)
  complete    boolean      NOT NULL DEFAULT false,      -- true = 10 dimensi terisi
  sources     jsonb,       -- {dim: "scraper|analyzer|gemini|heuristik|pending"}
  notes       text
);
CREATE INDEX IF NOT EXISTS viral_score_video_idx ON trend.viral_score (video_id, scored_at DESC);
CREATE INDEX IF NOT EXISTS viral_score_run_idx   ON trend.viral_score (run_id, total DESC);
