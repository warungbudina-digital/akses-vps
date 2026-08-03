# viral-pipeline — analisa video viral, ON-DEMAND

Rantai: **browser (.60) → antrean URL (DB-VPS) → orchestrator (akses-vps) → analyzer (.50) → hasil JSON (DB-VPS)**.

Dijalankan **saat diminta**, bukan terjadwal, karena analyzer hidup di Cloud Shell `.50`
yang ephemeral — VM di-recycle dan home terhapus, jadi tak ada yang bisa "selalu nyala".

## Pembagian peran node

| Node | IP | Peran |
|---|---|---|
| akses-vps (host repo ini) | 10.122.31.250 / 10.66.66.1 | Orchestrator + gateway. Satu-satunya node yang bisa menjangkau DB-VPS **dan** .50 sekaligus. |
| DB-VPS | 10.122.31.251 | Postgres `scraper` (antrean `media.video_ingest` + hasil `media.video_analysis`) **dan** tempat download (yt-dlp + cookies; IP-nya sudah lolos de-risk YouTube/FB/IG). |
| Cloud Shell .50 | 10.66.66.50 | Analyzer `viral_analyzer` (container, `127.0.0.1:9021`). Ephemeral. |
| Cloud Shell .60 | 10.66.66.60 | `full-tool-browser` — hulu penghasil URL. Ephemeral. |

Cloud Shell **tak bisa** menghubungi Postgres DB-VPS langsung (`pg_hba` tak mengizinkan
`10.66.66.0/24`), itulah sebabnya orchestrator duduk di akses-vps sebagai jembatan.

## Isi direktori

| File | Jalan di | Fungsi |
|---|---|---|
| `orchestrator.py` | akses-vps | Kuras antrean: claim → download → stream → analisa → tulis hasil → bersihkan. |
| `enqueue.py` | akses-vps | Masukkan URL berkategori ke antrean (auto-deteksi platform + `external_id`, dedup). |
| `browser_enqueue.py` | akses-vps | Jembatan HULU: scrape URL video dari profil via browser API (.60) → pipe ke `enqueue.py`. Guard gagal-senyap (CAPTCHA/login-wall → exit 4). |
| `schema-queue.sql` | DB-VPS | DDL antrean + kolom `category` pada hasil. **Sudah diterapkan** — berisi `DROP TABLE`, jangan dijalankan ulang pada antrean hidup. |
| `validate-queue.sql` | DB-VPS | Uji perilaku antrean (dedup, dua claim paralel, cleanup). Aman: membersihkan seed-nya sendiri. |
| `bring-up-analyzer.sh` | .50 | Siapkan analyzer di VM fresh (clone + build + up), idempoten. |
| `ir_to_vn.py` | akses-vps | **Penerjemah IR → cetak-biru reproduksi VN** (Infinix): SRT importable + blueprint JSON + recipe.md (langkah VN + storyboard fase). Fidelity struktural. |

Repo ini adalah **sumber kebenaran**; `~/viral-pipeline` di akses-vps adalah symlink ke sini.
Salinan di node lain (DB-VPS, .50) adalah salinan-jalan — sinkronkan dari sini, jangan sebaliknya.

## Cara menjalankan satu putaran

1. **Aktifkan .50**: user buka Cloud Shell `warungbudina` → paste bootstrap (WireGuard + admin key + watchdog).
2. **Siapkan analyzer** di .50: `bash ~/bring-up-analyzer.sh v1` (atau `v2` untuk whisper/CLIP).
3. **Isi antrean** dari akses-vps:
   ```
   python3 ~/viral-pipeline/enqueue.py viral_video "<url>" ["<url>" ...]
   python3 ~/viral-pipeline/enqueue.py --dry-run viral_video "<url>"   # cek deteksi saja
   ```
   Kategori sah: `viral_video`, `menuju_viral_video`.
4. **Kuras antrean** dari akses-vps:
   ```
   python3 ~/viral-pipeline/orchestrator.py          # semua job
   MAX_JOBS=1 python3 ~/viral-pipeline/orchestrator.py
   ```

Orchestrator berhenti dengan pesan jelas kalau analyzer .50 belum healthy — preflight
memeriksa `/healthz`, DB-VPS, dan kelengkapan tools/cookies sebelum menyentuh antrean.

## Status

Teruji end-to-end 2026-08-02 dengan satu reel Instagram nyata: download di DB-VPS →
stream ke .50 → `/analyze` → `media.video_analysis` terisi (bpm 117.45, 1 scene,
semantic "reaction face") → `video_ingest` jadi `analyzed` → file bersih di kedua sisi.

**Integrasi hulu browser(.60) → antrean: ADA** (`browser_enqueue.py`, 2026-08-03):
```
python3 ~/viral-pipeline/browser_enqueue.py <category> <platform> <profil-url> [--limit N] [--dry-run]
# contoh: python3 ~/viral-pipeline/browser_enqueue.py viral_video instagram https://www.instagram.com/gogobud13/
```
Alur: `POST /scraper/jobs` di .60 → poll sampai `done`/`failed` → ambil `posts[].postUrl`
→ pipe `<category> <url>` ke `enqueue.py` (satu sumber deteksi+dedup).

**Kendala hulu tetap berlaku:** TikTok menyajikan slider CAPTCHA ke IP datacenter dan IG
publik kena login-wall → job **`done` tapi `posts=[]`** (gagal senyap). `browser_enqueue.py`
**tidak menelan ini**: exit **4** + pesan + saran fallback. **Jalur fallback andal = suplai
URL manual** → `enqueue.py --stdin` (baris `<category> <url>`). Teruji 2026-08-03: scrape IG
gogobud13 → `done`, 0 post → exit 4 (guard bekerja).

**Belum ada:** pemicu/cron on-demand (menjalankan `orchestrator.py` otomatis saat .50 aktif).

## Jebakan yang sudah dibayar mahal (jangan diulang)

- Separator non-printable (`chr(30)`) di `RETURNING` **hilang** melewati rantai
  psql → ssh → python. Pakai `json_build_object` + `json.loads`.
- Template output yt-dlp `-o 'job.%(ext)s'` **wajib dikutip** — `()` ditafsirkan shell
  remote sebagai subshell dan yt-dlp tak pernah jalan (log kosong, gagal senyap).
- `~` di dalam `shlex.quote()` **tak di-expand**. Pola yang benar: `cd ~/dir && cat relpath`.
- Disk DB-VPS dan akses-vps sama-sama ~93% penuh. Video di-stream lewat pipe supaya tak
  mendarat di disk akses-vps, dan dihapus di kedua sisi setelah analisa.
