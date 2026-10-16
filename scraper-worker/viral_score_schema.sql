-- Tabel hasil Viral Scorecard (lapisan keputusan) di DB-VPS db `scraper`, schema `trend`.
-- Idempoten. Pakai: cat viral_score_schema.sql | ssh db-vps 'sudo -n -u postgres psql -d scraper -v ON_ERROR_STOP=1 -f -'
--
-- ⛔ 2026-10-16: FK ke trend.tiktok_video DIHAPUS (migrasi LIVE sudah dijalankan di
-- DB-VPS, lihat project_viral_analyzer.md) -- TikTok dibuang dari sistem riset tren,
-- video_id sekarang post_id Instagram/YouTube (trend.social_post), bukan lagi
-- selalu TikTok. Kolom `platform` DITAMBAH (backfill historis = 'tiktok', 491 baris
-- lama sebelum migrasi). CREATE TABLE IF NOT EXISTS di bawah TAK akan menjalankan
-- ulang migrasi itu kalau tabel sudah ada -- file ini cuma benar utk DEPLOY BARU
-- dari nol; kalau perlu re-apply ke instance lain, jalankan ALTER manual juga.
SET ROLE scraper;
CREATE SCHEMA IF NOT EXISTS trend;

CREATE TABLE IF NOT EXISTS trend.viral_score (
  id          bigserial PRIMARY KEY,
  run_id      text        NOT NULL,
  platform    text,        -- instagram | youtube (video_id tak lagi exclusive TikTok)
  video_id    text        NOT NULL,
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
CREATE INDEX IF NOT EXISTS viral_score_video_idx ON trend.viral_score (platform, video_id, scored_at DESC);
CREATE INDEX IF NOT EXISTS viral_score_run_idx   ON trend.viral_score (run_id, total DESC);
