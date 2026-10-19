-- =====================================================================
-- Pipeline analisa video viral (ON-DEMAND; orchestrator di akses-vps,
-- analyzer di .50, DB-VPS = antrean + hasil saja).
-- Skema antrean URL + hasil analisa. v1 — 2026-08-02. SUDAH DITERAPKAN di DB-VPS.
-- PERINGATAN: DROP TABLE media.video_ingest CASCADE di bawah = destruktif.
-- Jangan jalankan ulang pada DB berisi antrean hidup.
--   Dedup      : UNIQUE(source_url).
--   Kategori   : viral_video | menuju_viral_video.
--   Saat sukses: baris -> status 'analyzed' (DIPERTAHANKAN utk audit + anti-dobel);
--                file video temp dihapus di DISK (tak ada blob di DB).
-- Terapkan: cat schema-queue.sql | ssh db-vps 'sudo -n -u postgres psql -d scraper -v ON_ERROR_STOP=1'
-- =====================================================================
SET ROLE scraper;

-- ---------- ANTREAN URL (buang desain-blob lama yang kosong) ----------
DROP TABLE IF EXISTS media.video_ingest CASCADE;
CREATE TABLE media.video_ingest (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category      text NOT NULL CHECK (category IN ('viral_video','menuju_viral_video')),
    platform      text,
    source_url    text NOT NULL,
    external_id   text,
    status        text NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','processing','analyzed','failed','dead')),
    attempts      int  NOT NULL DEFAULT 0,
    max_attempts  int  NOT NULL DEFAULT 3,
    last_error    text,
    priority      int  NOT NULL DEFAULT 0,
    video_sha256  text,
    size_bytes    bigint,
    duration_sec  numeric,
    enqueued_by   text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    claimed_at    timestamptz,
    downloaded_at timestamptz,
    analyzed_at   timestamptz,
    updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_video_ingest_url      ON media.video_ingest (source_url);
CREATE INDEX        ix_video_ingest_claim    ON media.video_ingest (status, priority DESC, created_at)
                                              WHERE status = 'pending';
CREATE INDEX        ix_video_ingest_category ON media.video_ingest (category);

-- ---------- HASIL: tambah kategori (tabel dipertahankan) ----------
ALTER TABLE media.video_analysis
    ADD COLUMN IF NOT EXISTS category text
        CHECK (category IN ('viral_video','menuju_viral_video'));
CREATE INDEX IF NOT EXISTS ix_video_analysis_category ON media.video_analysis (category);

-- ---------- KURASI PRIBADI + mirror Sheet via n8n (2026-10-19) ----------
-- Kolom scoring manual (diisi user, dibaca/ditulis n8n saat sync ke/dari
-- Google Sheet) + link folder Gdrive raw-footage hasil split_and_push_raw().
ALTER TABLE media.video_ingest
    ADD COLUMN IF NOT EXISTS user_score int CHECK (user_score BETWEEN 1 AND 10),
    ADD COLUMN IF NOT EXISTS user_notes text,
    ADD COLUMN IF NOT EXISTS decision text CHECK (decision IN ('pilih','tunda','skip')),
    ADD COLUMN IF NOT EXISTS used_in_rn7 boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS raw_footage_folder text;
