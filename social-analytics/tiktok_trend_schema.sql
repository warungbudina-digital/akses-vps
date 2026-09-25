-- Skema riset tren TikTok (watchlist kreator niche AI/tech) di DB-VPS, db `scraper`.
-- Idempoten: aman dijalankan ulang.
-- Pakai: cat tiktok_trend_schema.sql | ssh db-vps 'sudo -n -u postgres psql -d scraper -v ON_ERROR_STOP=1 -f -'
SET ROLE scraper;
CREATE SCHEMA IF NOT EXISTS trend;

-- Satu baris per percobaan baca profil. `status` membedakan "berhasil tapi
-- kosong" dari "gagal mengukur" (captcha/diblokir/error) — jangan disamakan.
CREATE TABLE IF NOT EXISTS trend.tiktok_account_snapshot (
  id          bigserial PRIMARY KEY,
  run_id      text        NOT NULL,
  handle      text        NOT NULL,
  taken_at    timestamptz NOT NULL DEFAULT now(),
  status      text        NOT NULL,  -- ok | no_videos | captcha | not_found | error
  nickname    text,
  bio         text,
  followers   bigint,
  following   bigint,
  likes       bigint,
  videos      bigint,
  cards_seen  int,
  error       text
);
CREATE INDEX IF NOT EXISTS tiktok_account_snapshot_handle_idx
  ON trend.tiktok_account_snapshot (handle, taken_at DESC);

-- Metadata video (tak berubah).
CREATE TABLE IF NOT EXISTS trend.tiktok_video (
  video_id     text PRIMARY KEY,
  handle       text        NOT NULL,
  url          text        NOT NULL,
  description  text,
  hashtags     text[]      NOT NULL DEFAULT '{}',
  music        text,
  duration_s   int,
  created_at   timestamptz,
  first_seen   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS tiktok_video_handle_idx ON trend.tiktok_video (handle, created_at DESC);

-- Statistik video berulang (time-series) → bisa hitung kecepatan naik.
CREATE TABLE IF NOT EXISTS trend.tiktok_video_snapshot (
  id        bigserial PRIMARY KEY,
  run_id    text        NOT NULL,
  video_id  text        NOT NULL REFERENCES trend.tiktok_video(video_id) ON DELETE CASCADE,
  taken_at  timestamptz NOT NULL DEFAULT now(),
  plays     bigint,
  likes     bigint,
  comments  bigint,
  shares    bigint,
  saves     bigint
);
CREATE INDEX IF NOT EXISTS tiktok_video_snapshot_vid_idx
  ON trend.tiktok_video_snapshot (video_id, taken_at DESC);

-- Kandidat akun baru dari "Suggested accounts" — TIDAK otomatis dipantau,
-- user yang memutuskan (pindahkan ke watchlist.json).
CREATE TABLE IF NOT EXISTS trend.tiktok_candidate (
  handle      text PRIMARY KEY,
  found_via   text        NOT NULL,
  first_seen  timestamptz NOT NULL DEFAULT now(),
  last_seen   timestamptz NOT NULL DEFAULT now(),
  times_seen  int         NOT NULL DEFAULT 1
);

-- 2026-09-25: bedakan video vs carousel foto (Photo Mode; durasi 0 menyesatkan).
ALTER TABLE trend.tiktok_video ADD COLUMN IF NOT EXISTS media_type text;  -- video | photo
ALTER TABLE trend.tiktok_video ADD COLUMN IF NOT EXISTS n_images   int;

-- 2026-09-25: riset lintas platform (instagram / youtube / facebook) — tabel generik.
CREATE TABLE IF NOT EXISTS trend.social_account_snapshot (
  id          bigserial PRIMARY KEY,
  run_id      text        NOT NULL,
  platform    text        NOT NULL,
  handle      text        NOT NULL,
  taken_at    timestamptz NOT NULL DEFAULT now(),
  status      text        NOT NULL,  -- ok | not_found | error
  name        text,
  followers   bigint,
  posts       bigint,
  total_views bigint,
  error       text
);
CREATE INDEX IF NOT EXISTS social_account_snapshot_idx
  ON trend.social_account_snapshot (platform, handle, taken_at DESC);

CREATE TABLE IF NOT EXISTS trend.social_post (
  platform     text        NOT NULL,
  post_id      text        NOT NULL,
  handle       text        NOT NULL,
  url          text,
  caption      text,
  media_type   text,        -- video | short | reel | image | carousel
  hashtags     text[]      NOT NULL DEFAULT '{}',
  created_at   timestamptz,
  first_seen   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (platform, post_id)
);
CREATE INDEX IF NOT EXISTS social_post_handle_idx ON trend.social_post (platform, handle, created_at DESC);

CREATE TABLE IF NOT EXISTS trend.social_post_snapshot (
  id        bigserial PRIMARY KEY,
  run_id    text        NOT NULL,
  platform  text        NOT NULL,
  post_id   text        NOT NULL,
  taken_at  timestamptz NOT NULL DEFAULT now(),
  views     bigint,     -- IG Business Discovery tak memberi views → NULL
  likes     bigint,
  comments  bigint,
  FOREIGN KEY (platform, post_id) REFERENCES trend.social_post (platform, post_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS social_post_snapshot_idx
  ON trend.social_post_snapshot (platform, post_id, taken_at DESC);
