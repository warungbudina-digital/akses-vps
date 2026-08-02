SET ROLE scraper;

\echo '=== 1. SEED (4 baris: 2 viral + 2 menuju, 4 platform) ==='
INSERT INTO media.video_ingest (category, platform, source_url, external_id, enqueued_by) VALUES
  ('viral_video','facebook','https://www.facebook.com/reel/1664405718127701','1664405718127701','seed-test'),
  ('viral_video','instagram','https://www.instagram.com/reel/DbaFp0rtCZl/','DbaFp0rtCZl','seed-test'),
  ('menuju_viral_video','youtube','https://www.youtube.com/watch?v=jNQXAC9IVRw','jNQXAC9IVRw','seed-test'),
  ('menuju_viral_video','tiktok','https://www.tiktok.com/@u/video/7300000000000000000','7300000000000000000','seed-test')
ON CONFLICT (source_url) DO NOTHING;
SELECT id, category, platform, status, attempts FROM media.video_ingest ORDER BY id;

\echo '=== 2. DEDUP: insert ulang URL FB yang sama -> harus DIABAIKAN ==='
INSERT INTO media.video_ingest (category, platform, source_url, enqueued_by) VALUES
  ('viral_video','facebook','https://www.facebook.com/reel/1664405718127701','dup-test')
ON CONFLICT (source_url) DO NOTHING;
SELECT count(*) AS total_baris_harus_4 FROM media.video_ingest;

\echo '=== 3. CLAIM #1 (FOR UPDATE SKIP LOCKED) ==='
UPDATE media.video_ingest SET status='processing', claimed_at=now(), attempts=attempts+1, updated_at=now()
WHERE id = (SELECT id FROM media.video_ingest WHERE status='pending' AND attempts < max_attempts
            ORDER BY priority DESC, created_at FOR UPDATE SKIP LOCKED LIMIT 1)
RETURNING id, category, platform, status, attempts;

\echo '=== 4. CLAIM #2 (harus ambil baris LAIN) ==='
UPDATE media.video_ingest SET status='processing', claimed_at=now(), attempts=attempts+1, updated_at=now()
WHERE id = (SELECT id FROM media.video_ingest WHERE status='pending' AND attempts < max_attempts
            ORDER BY priority DESC, created_at FOR UPDATE SKIP LOCKED LIMIT 1)
RETURNING id, category, platform, status, attempts;

\echo '=== 5. STATE AKHIR (harus 2 processing + 2 pending) ==='
SELECT id, category, platform, status, attempts, (claimed_at IS NOT NULL) AS claimed FROM media.video_ingest ORDER BY id;

\echo '=== 6. CLEANUP seed -> antrean kosong lagi ==='
DELETE FROM media.video_ingest WHERE enqueued_by IN ('seed-test','dup-test');
SELECT count(*) AS sisa_harus_0 FROM media.video_ingest;
