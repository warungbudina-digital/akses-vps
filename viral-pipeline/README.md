# viral-pipeline — analisa video viral + reproduksi ke VN, ON-DEMAND

**Analisa:** browser (.60) → antrean URL (DB-VPS) → orchestrator (akses-vps) → analyzer (.50) → hasil IR JSON (DB-VPS).

**Reproduksi (opsional):** IR → `ir_to_vn.py` → cetak-biru (SRT + musik + titik-cut) → **VN editor di HP Infinix** (via Appium). Target = **fidelity struktural** (rasio/durasi/ritme-cut/beat/caption/hook), BUKAN pixel-identik.

Dijalankan **saat diminta**, bukan terjadwal, karena analyzer hidup di Cloud Shell `.50`
yang ephemeral — VM di-recycle dan home terhapus, jadi tak ada yang bisa "selalu nyala".

## Pembagian peran node

| Node | IP | Peran |
|---|---|---|
| akses-vps (host repo ini) | 10.122.31.250 / 10.66.66.1 | Orchestrator + gateway. Satu-satunya node yang bisa menjangkau DB-VPS **dan** .50 sekaligus. Juga host Appium (container `tool-appium`) ke HP Infinix (10.66.66.2). |
| DB-VPS | 10.122.31.251 | Postgres `scraper` (antrean `media.video_ingest` + hasil `media.video_analysis`) **dan** tempat download (yt-dlp + cookies; IP-nya sudah lolos de-risk YouTube/FB/IG). 24GB disk bebas. |
| Cloud Shell .50 | 10.66.66.50 | Analyzer `viral_analyzer` (container, `127.0.0.1:9021`). Ephemeral, disk ketat (~3-9GB). |
| Cloud Shell .60 | 10.66.66.60 | `full-tool-browser` — hulu penghasil URL. Ephemeral. Scraper sosial tak andal (CAPTCHA/login-wall). |
| HP Infinix | 10.66.66.2 (WG) | VN editor (`com.frontrow.vlog`, login Pro) — target reproduksi. ADB via WireGuard, port ganti tiap toggle. |

Cloud Shell **tak bisa** menghubungi Postgres DB-VPS langsung (`pg_hba` tak mengizinkan
`10.66.66.0/24`), itulah sebabnya orchestrator duduk di akses-vps sebagai jembatan.

## Isi direktori

| File | Jalan di | Fungsi |
|---|---|---|
| `orchestrator.py` | akses-vps | Kuras antrean: claim → download → stream → analisa → tulis hasil → bersihkan. Timeout analyze `ANALYZE_TIMEOUT` (default 1200s), per-job try/except. |
| `enqueue.py` | akses-vps | Masukkan URL berkategori ke antrean (auto-deteksi platform + `external_id`, dedup). |
| `browser_enqueue.py` | akses-vps | Jembatan HULU: scrape URL video dari profil via browser API (.60) → pipe ke `enqueue.py`. Guard gagal-senyap (CAPTCHA/login-wall → exit 4). |
| `run-drain.sh` | akses-vps | **Pemicu on-demand**: pastikan ControlMaster .50 → hitung pending (0 = no-op) → jalankan orchestrator. Aman dari cron poller. |
| `ir_to_vn.py` | akses-vps | **Penerjemah IR → cetak-biru reproduksi VN**. Output 4 berkas (lihat §Reproduksi). |
| `schema-queue.sql` | DB-VPS | DDL antrean + kolom `category` pada hasil. **Sudah diterapkan** — berisi `DROP TABLE`, jangan dijalankan ulang pada antrean hidup. |
| `validate-queue.sql` | DB-VPS | Uji perilaku antrean (dedup, dua claim paralel, cleanup). Aman: membersihkan seed-nya sendiri. |
| `bring-up-analyzer.sh` | .50 | Siapkan analyzer di VM fresh (clone + build + up), idempoten. `v1` (ringan) / `v2` (whisper+CLIP). |
| `pexels_fetch.py` / `pixabay_fetch.py` | akses-vps | (Jalur C, 2026-08-29) sumber footage stok MENTAH per babak dari blueprint IR — dipanggil `orchestrator.py` best-effort stlh job `analyzed`. |
| `push_raw_footage.py` | akses-vps | Push klip stok hasil fetch di atas → `gfootage:RAW-VIDEO/job-<id>/` (BEDA dari raw-footage §bawah — ini stok Pexels/Pixabay, bukan video sumber yg dianalisa). |
| `dashboard_api.py` | akses-vps (systemd `viral-dashboard-api`) | (2026-10-19) Backend form input URL web, dipanggil `input.html` (nginx `pipeline.obc-crypto.com/input.html`). `POST /api/enqueue` → insert `media.video_ingest` (reuse `enqueue.py`), auth Bearer token (`~/.config/viral-dashboard/credentials.env`). Bind `172.19.0.1:8097` (gateway docker, nginx jalan di container). Install/aktifkan: `install-dashboard-api.sh`. |

Repo ini adalah **sumber kebenaran**; `~/viral-pipeline` di akses-vps adalah symlink ke sini.
Salinan di node lain (DB-VPS, .50) adalah salinan-jalan — sinkronkan dari sini, jangan sebaliknya.

## Cara menjalankan satu putaran ANALISA

1. **Aktifkan .50**: user buka Cloud Shell `warungbudina` → paste bootstrap (WireGuard + admin key + watchdog).
2. **Siapkan analyzer** di .50: `bash ~/bring-up-analyzer.sh v1` (atau `v2` untuk whisper/CLIP).
3. **Isi antrean** dari akses-vps:
   ```
   python3 ~/viral-pipeline/enqueue.py viral_video "<url>" ["<url>" ...]
   python3 ~/viral-pipeline/enqueue.py --dry-run viral_video "<url>"   # cek deteksi saja
   ```
   Kategori sah: `viral_video`, `menuju_viral_video`. Hulu otomatis (opsional):
   `browser_enqueue.py <category> <platform> <profil-url>` (cek guard exit 4 = gagal-senyap).
4. **Kuras antrean** dari akses-vps: `bash ~/viral-pipeline/run-drain.sh`
   (atau `MAX_JOBS=1 python3 ~/viral-pipeline/orchestrator.py`).

Orchestrator/run-drain berhenti dengan pesan jelas kalau .50 belum aktif/healthy — preflight
memeriksa `/healthz`, DB-VPS, dan kelengkapan tools/cookies sebelum menyentuh antrean.

**✅ 2026-08-28:** cron poster untuk run-drain SUDAH ADA (permintaan user) — TAPI bukan
langsung `run-drain.sh` polos, ada gerbang tambahan `~/akses-vps/backup/analyzer-pipeline-trigger.sh`
(dijadwalkan `*/10 22-23,0-14 * * *` UTC di HUB) yang cek dulu SEMUA 3 Cloud Shell (.50/.60/.61)
reachable sebelum memanggil `run-drain.sh` — sinyal "node hari ini benar2 hidup semua", bukan
keharusan teknis (`run-drain.sh`/`orchestrator.py` sendiri cuma butuh `.50`+DB-VPS). Log:
`~/analyzer-pipeline-trigger.log` (HUB).

## Reproduksi ke VN (Infinix)

**✅ 2026-08-28: OTOMATIS.** `orchestrator.py` sekarang memanggil `ir_to_vn.py` sendiri
sesudah tiap job sukses tersimpan di DB — tak perlu langkah manual lagi. Hasil mendarat di
`~/viral-pipeline/reproductions/job-<id>/job-<id>.*` (per-job, bukan ditumpuk di satu folder).
Kalau `ir_to_vn.py` gagal utk suatu job, itu cuma log peringatan — analisa di DB tetap aman.

Pemakaian manual (mis. re-generate dari IR lama) tetap bisa:
`python3 ~/viral-pipeline/ir_to_vn.py <ir.json> --out <base>` → **6 berkas**:

| Berkas | Isi | Dipakai untuk |
|---|---|---|
| `<base>.srt` | Caption dari `subtitle_segments` (timecode) | Impor langsung ke VN (`flAddAddSubtitlesFormSRT`) |
| `<base>.cutlist.txt` | Titik-cut (batas antar-scene), satu detik/baris | Otomasi split jump-cut di VN |
| `<base>.vn-blueprint.json` | Rencana machine-readable (format/pacing/beat/captions/hook/phases/cut_points) | Konsumsi program |
| `<base>.vn-recipe.md` | 7 langkah build VN + storyboard fase | Panduan manusia |
| `<base>.segments.json` | Rencana per-segmen: tiap scene → `zoom` (Perbesar/Perkecil) + `adjust` (dari lighting) | Orchestrasi VN berpandu-data |
| `<base>.story-script.md` | Alur cerita babak-per-babak bahasa naratif (bukan teknis) + arahan "apa yang harus direkam" + pesan inti + checklist | Dibaca kreator/AI kreatif utk visualisasi & nulis naskah rekam ulang (WAJIB, lihat memori `feedback_ir_to_vn_story_script`) |

**Dimensi struktural yang SUDAH bisa direproduksi (teruji end-to-end di Infinix via Appium, 2026-08-03):**

| Dimensi | Sumber di IR | Cara di VN | Status |
|---|---|---|---|
| **Rasio** | `aspect_ratio`/`width`/`height` (sejak analyzer `de9f18a`) | `llFrameType` | ✅ di IR |
| **Caption** | `subtitle_segments` → SRT | impor SRT | ✅ teruji (221 caption) |
| **Musik + beat-sync** | `bpm` + `scene.beat_sync` | pustaka VN + Beat Otomatis | ✅ teruji (Discover, 267 beat) |
| **Jump-cut** | `pacing.cut_points_sec` → cutlist | seek + `editor_toolbar_split` | ✅ teruji (18/19 cut) |
| **Zoom in/out** | `camera_movement=zoom_in/zoom_out` (analyzer `734c838`) → `zoom_moments` | `editor_toolbar_clipZoom` Perbesar/Perkecil | ✅ teruji (in+out) |
| **Pencahayaan** | `scene.lighting` (analyzer `d769792`) → blueprint `lighting` | VN **Adjust** (`editor_toolbar_filter`→Menyesuaikan) | ✅ teruji (KECERAHAN +61) |

**Semua 6 dimensi struktural kini ada di IR DAN bisa diotomasi di VN** (rasio·caption·musik/beat·jump-cut·zoom·pencahayaan). Alur selector VN: `tool-appium/docs/vn-automation-map.md` §23.

**Orchestrasi berpandu-data (rangkai segmen):** `<base>.segments.json` (dari `ir_to_vn`) me-wire tiap segmen ke aksi VN (zoom+adjust). Syarat koheren: footage VN = footage yang dianalisa (segmen VN = scene IR). Status: rencana per-segmen SELESAI (commit `8671db2`); orchestrator VN (seek→select→zoom→adjust) tiap operasi tunggal PROVEN, tapi merangkai 3+ segmen dalam satu run masih rapuh (state VN Lynx) — jalankan per-segmen + reset (vn-map §23f).

Catatan pencahayaan: `lighting.py` (deterministik, V1+V2) sample 3 frame/scene → brightness (mean-luminance), contrast (std-luminance), warmth (mean R−B), saturation + label (dark/normal/bright · low/normal/high · warm/neutral/cool). Diverifikasi klip warna terkontrol. IR LAMA tanpa `lighting` → re-analisa.

Catatan zoom: analyzer `734c838` pisah `zoom_in`/`zoom_out` (tanda divergence = arah; divergence>0=aliran keluar=zoom in — diverifikasi numerik cv2). IR LAMA cuma `"zoom"` (arah tak diketahui) → re-analisa untuk dapat arah. Otomasi VN clipZoom (Perbesar=in / Perkecil=out) teruji; toolbar 21-tool dijangkau andal via Appium `UiScrollable(...).scrollIntoView(description("editor_toolbar_clipZoom"))`.

Detail selector VN + jebakan otomasi Appium: lihat memori `project_viral_analyzer` /
`project_infinix_streaming_setup` + repo `tool-appium/docs/vn-automation-map.md`.

## Raw-footage ke Gdrive (✅ 2026-10-17, revisi 19/10 + 21/10, permintaan user)

Setiap job yang sukses `analyzed` otomatis lanjut (best-effort, kegagalan di
sini TAK PERNAH menggagalkan job) ke `split_and_push_raw()` di
`orchestrator.py`: tarik video sumber balik DB-VPS→akses-vps (satu-satunya
node dgn ffmpeg+rclone+kredensial gfootage sekaligus), pisah **video TANPA
audio** (`-an -c:v copy`, nol transcode, tetap kontainer MKV — codec asli
dipertahankan) + **audio-only** (`-vn -c:a pcm_s16le` → **WAV**, revisi 21/10:
semula stream-copy ke `.mka`/Matroska, diganti PCM supaya tak perlu
demux-kontainer/decode-codec-kompresi apa pun → lebih andal terbaca user
maupun tool AI lemah seperti transkripsi/analisa suara; sample rate+channel
asli dipertahankan, cuma codec yang berubah) + **1 thumbnail** representatif
(filter `thumbnail`, bukan frame fixed). Push ke Gdrive `maydualapan8@gmail.com`
(remote rclone `gfootage:`).

**SATU folder per job** (konsolidasi 19/10, semula 3 folder flat terpisah):

| Folder Gdrive | Isi |
|---|---|
| `raw-footage/<judul> [<url>]/` | `video.mkv` + `audio.wav` + `thumbnail.jpg` |
| `RAW-VIDEO/job-<id>/` *(beda pipeline)* | Stok Pexels/Pixabay — Jalur C, BEDA sumber |
| `VN-exports/` *(beda pipeline)* | Hasil EDIT siap-publish (`premiere_pipeline.py`) |

Nama folder = **judul asli video + URL sumber lengkap** (`<judul> [<url>]`,
disanitasi flat) — judul dari sidecar `work/job-<id>.info.json` (`yt-dlp
--write-info-json`, ditambah ke `download()`). Link folder ditulis balik ke
`media.video_ingest.raw_footage_folder` bila minimal 1 aset sukses ter-upload.
Disk-guard `RAW_MIN_DISK_MB=500` (hub pernah 93% penuh) + cleanup temp lokal
di `finally`, apa pun hasilnya. **Diuji live end-to-end** (bukan dry-run):
job nyata #153, lihat `project_viral_analyzer.md` di memori.

## Status analisa

Teruji end-to-end: reel Instagram (bpm 117.45) + reel Facebook long-form (12:16, 234 scene,
221 caption, whisper ~13mnt) → `media.video_analysis` terisi → `analyzed` → file bersih 2 sisi.
Hulu `browser_enqueue.py` teruji (scrape IG → guard exit 4 karena login-wall; fallback = seed manual).

## Jebakan yang sudah dibayar mahal (jangan diulang)

- **`psql -tA` cetak tag `INSERT 0 N` ke stdout** → mencemari hitungan token-digit (enqueue.py sempat lapor "6 baru, -2 duplikat"). Fix: flag `-q` (quiet).
- **Separator non-printable (`chr(30)`) di `RETURNING` hilang** melewati psql → ssh → python. Pakai `json_build_object` + `json.loads`.
- **Template yt-dlp `-o 'job.%(ext)s'` wajib dikutip** — `()` ditafsirkan subshell shell remote, yt-dlp tak jalan (gagal senyap).
- **`~` di `shlex.quote()` tak di-expand**. Pola benar: `cd ~/dir && cat relpath`.
- **Analyze whisper video panjang bisa >5mnt** → timeout hardcoded 300s dulu bikin `TimeoutExpired` tak tertangkap → crash + job tersangkut `processing`. Fix: `ANALYZE_TIMEOUT` 1200s + per-job try/except.
- **Otomasi VN via Appium**: tombol Lynx (mis. "Menggunakan") TAK kena `adb tap`/coordinate-tap saat interleaving ui-map → pakai **satu sesi Appium** berurutan. Item RecyclerView DocumentsUI perlu **Appium `.click()`** (bukan adb tap). Playhead time terbaca sbg node `current_textView` (buat seek feedback-loop). BACK di editor VN = keluar+autosave.
- **Disk**: DB-VPS ~24GB bebas; **.50 ephemeral ketat** (v2 image 5.86GB, sisa ~3.6GB). Video di-stream lewat pipe ke `.50` (TAK mendarat di disk akses-vps utk jalur analisa), dihapus 2 sisi pasca-analisa. ⚠️ **TERKECUALI**: `split_and_push_raw()` (§Raw-footage di atas, 2026-10-17) SENGAJA menarik 1 copy ke disk akses-vps sebentar (ffmpeg+rclone cuma ada di sini) — disk-guard 500MB + cleanup `finally` menjaga ini tak menumpuk.
