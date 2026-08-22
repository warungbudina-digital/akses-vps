# Wiki: Fitur Gratis & Hack Penggunaan Optimal Hugging Face

> Riset 2026-08-22, akun teruji: **"warungbudina"** (non-Pro, lihat memori `project_huggingface_api_key`). Sumber utama = dokumentasi resmi `huggingface.co/docs/...` + `huggingface.co/pricing` (di-fetch langsung via curl, bukan cuma cache Google/blog SEO — beberapa blog SEO yang muncul di pencarian ternyata memuat angka BASI/salah, sudah disaring). Angka kuota HF berubah cepat (halaman pricing sendiri bilang "subject to change") — cek ulang sebelum mengandalkan untuk keputusan jangka panjang. Semua harga USD.

---

## 0. Ringkasan eksekutif (yang paling penting)

| Fitur gratis | Kuota free-tier | Kunci hack |
|---|---|---|
| **ZeroGPU** (GPU beneran, RTX Pro 6000 Blackwell 48-96GB) | **5 menit/hari** (akun login), 2 menit/hari (anonim) | reset = 24 jam SETELAH pakai pertama (bukan jam tetap); pakai size `large` default (1×) bukan `xlarge` (2×) |
| **Private storage** | **100 GB gratis** | dataset repo privat = "database"/backup gratis, bukan cuma buat model |
| **Public storage** | "Best-effort" (praktis tak terbatas) | asal "berguna utk komunitas" (like/download) |
| **Inference Providers credit** | **$0.10/bulan** (kecil!) | jangan andalkan ini utk beban besar — pakai ZeroGPU Space sbg gantinya |
| **Static Space** | HTML/JS statis, tanpa server | **GRATIS tanpa syarat, tier apa pun** — satu-satunya hosting-Space yg genuinely gratis |
| **CPU Basic (Docker/Gradio)** | 2vCPU/16GB, 50GB disk | hardware-nya $0/jam, TAPI ⚠️ **membuatnya WAJIB PRO $9/bln** (kebijakan diperketat ~Juli 2026) — bukan gratis lagi |
| **Static Space** | **gratis tanpa batas kompute** | cocok utk frontend/dashboard statis |
| **Rate limit API Hub** | Free login 2× lipat drpd anonim | **SELALU pasang `HF_TOKEN`** meski akses publik — alasan #1 orang kena rate-limit |
| **HuggingChat** | chat gratis 110+ model open-weight | tak ada API resmi gratis-nya — utk otomasi tetap lewat Inference Providers (kena kredit kecil di atas) |
| **Community GPU Grant** | gratis, kasus-per-kasus | apply dari Space Settings → bagian "sleep time settings" (pojok kiri-bawah) |
| **Xet storage backend** | otomatis aktif, gratis | `hf_transfer`/`HF_HUB_ENABLE_HF_TRANSFER` **SUDAH DEPRECATED** — pakai `HF_XET_HIGH_PERFORMANCE=1` |

---

## 1. ZeroGPU — GPU beneran gratis (fitur paling bertenaga di tier gratis)

**Cara kerja:** ZeroGPU adalah GPU bersama (`NVIDIA RTX Pro 6000 Blackwell`) yang dialokasikan dinamis HANYA selagi fungsi Python yg didekorasi `@spaces.GPU` benar-benar dieksekusi, lalu dilepas lagi — jadi Space-mu bisa "punya" GPU tanpa membayar/menahan GPU saat idle. Support multi-GPU per aplikasi. **Hanya kompatibel dgn Gradio SDK** (PyTorch-based, Gradio 4+, Python 3.10/3.12).

**Kuota harian per tier (dari dokumentasi resmi, `docs/hub/spaces-zerogpu`):**

| Tipe akun | Kuota GPU harian | Prioritas antrean |
|---|---|---|
| Tak login (anonim) | 2 menit | Rendah |
| **Akun gratis (login)** | **5 menit** | Sedang |
| PRO | 40 menit (bisa diperpanjang beli kredit) | Tertinggi |
| Team org member | 40 menit (bisa diperpanjang) | Tertinggi |
| Enterprise org member | 60 menit (bisa diperpanjang) | Tertinggi |

- ⚠️ **Kuota reset TEPAT 24 JAM setelah pemakaian GPU PERTAMAmu, bukan jam 00:00 tetap.** Hack: kalau kamu tahu jam pipeline harian akan jalan, picu 1 panggilan kecil di jam itu supaya jendela reset "terkunci" konsisten — jangan pakai sporadis di jam acak, nanti window-nya ikut geser tiap hari.
- **Dua ukuran GPU** (di dekorator `@spaces.GPU(size=...)`): `large` (default, SETENGAH GPU = 48GB VRAM, **biaya kuota 1×**) vs `xlarge` (GPU PENUH = 96GB, **biaya kuota 2×** — 45 detik kerja = 90 detik kuota terpakai). **Hack: JANGAN pakai `xlarge` kecuali model benar-benar butuh >48GB** — boros kuota 2× dan antrean lebih lama.
- **Durasi fungsi default 60 detik.** Kalau tugasmu > 60 detik, WAJIB set `@spaces.GPU(duration=120)` dsb, kalau tidak fungsi akan dipotong paksa. Sebaliknya kalau tugasmu SELALU pendek (mis. 5 detik), set duration pendek eksplisit — ini **memperbaiki prioritas antrean** buat semua pengunjung Space-mu (bukan cuma kuotamu sendiri). Bisa juga pakai `duration=callable` (dihitung dinamis dari parameter, mis. jumlah `steps` generate gambar).
- **Optimasi kecepatan:** `torch.compile` **TIDAK didukung** di ZeroGPU, tapi **ahead-of-time (AOT) compilation** (butuh torch ≥2.8) didukung dan bisa signifikan mempercepat — ada blog resmi "Make your ZeroGPU Spaces go brrr with ahead-of-time compilation". Kombinasikan dgn flash-attention 3 utk model besar.
- **Batas hosting:** akun gratis (email terverifikasi + umur akun >30 hari) boleh HOST maksimal **2 Space ZeroGPU** gratis; PRO s/d 10; organisasi Team/Enterprise s/d 50.
- **Hack terpenting:** ZeroGPU Space **BOLEH DIPAKAI GRATIS OLEH SIAPA SAJA**, bukan cuma pemiliknya — jadi kalau kamu cuma butuh INFERENSI (bukan bangun produk sendiri), cari dulu di daftar kurasi Space ZeroGPU yg sudah menjalankan model yg kamu mau (Flux image-gen, Whisper, Llama-chat, dst) dan pakai langsung — kuota 5 menit/hari-mu terpakai di situ, TANPA perlu install/hosting apa pun sendiri.

## 2. Storage gratis

| Tipe akun | Storage publik | Storage privat |
|---|---|---|
| **Gratis** | "Best-effort" — de facto besar, asal berguna bagi komunitas (dinilai dari like/download) | **100 GB** |
| PRO | s/d 10TB + bisa nambah add-on | 1TB + bayar kelebihan |
| Team | 12TB dasar + 1TB/seat | 1TB/seat + bayar kelebihan |

- **Tak ada batas per-repo** utk model/dataset — yg dibatasi kuota TOTAL akun. Batas keras cuma **file tunggal maks 500GB** (disarankan pecah <200GB/file demi kecepatan unduh+CDN cache).
- Rekomendasi struktur repo besar: <100rb file/repo, <10rb file/folder (pakai subfolder), <100 file/commit (pakai `upload_folder`/`hf upload` yg auto-split).
- **Hack backup gratis:** dataset PRIVAT sampai 100GB itu bisa dipakai sbg tempat backup/arsip pribadi apa saja (bukan cuma dataset ML) — mirip menyewa 100GB cloud storage privat gratis, asal format file wajar (bukan dipakai jadi file-hosting arbitrer skala besar, itu melanggar semangat kebijakan).
- **Cara bebaskan storage kalau mepet:** hapus file LFS individual lewat Settings→"List LFS files"; hapus ref Pull Request yg sudah closed/merged (PR menyimpan commit historis sendiri, bisa makan storage signifikan kalau PR itu pernah punya file besar); atau **super-squash** seluruh histori git jadi 1 commit via `huggingface_hub` (destruktif, efek ke kuota baru terlihat dlm 36 jam).
- **Storage grant:** utk kerja open-source berdampak tinggi yg PRO/Team pun tak cukup, HF membuka permintaan grant storage kasus-per-kasus — kontak `datasets@huggingface.co` / `models@huggingface.co` dgn bukti dampak (jumlah download/citation/adopsi komunitas).

## 3. Inference: hf-inference vs Inference Providers

HF sekarang punya SATU sistem billing kredit terpadu bernama **Inference Providers** (dulu "Inference API (serverless)" jadi provider bernama `hf-inference` di dalamnya):

| Tipe akun | Kredit bulanan | Bisa dipakai utk |
|---|---|---|
| **Free** | **$0.10/bulan** (kecil, bisa berubah) | Inference Providers saja |
| PRO | **$2.00/bulan** | SEMUA compute HF: Inference Providers, Inference Endpoints, upgrade CPU/GPU Spaces (termasuk ZeroGPU lebih dari kuota), Jobs |
| Team/Enterprise | $2.00/bulan/seat | sama seperti PRO, dibagi rata anggota |

- ⚠️ **$0.10/bulan itu SANGAT KECIL** — cukup utk beberapa ratus panggilan model kecil (embedding/klasifikasi CPU), TIDAK cukup utk pemakaian rutin model besar. **Kalau kena tembok kredit, jalur gratis yg lebih besar = ZeroGPU Space (poin 1), BUKAN nambah lewat Inference Providers** (itu sudah masuk mode bayar).
- Provider `hf-inference` (bekas "serverless API gratis") sejak Juli 2025 **fokus ke CPU inference** (embedding, text-classification, model kecil bersejarah spt BERT/GPT-2) — model generatif besar sekarang lewat provider eksternal (Together, Fireworks, dst) yg di-routing HF, semua tetap potong kredit yg sama.
- **2 mode billing:** "Routed by Hugging Face" (default — tanpa akun provider terpisah, kredit bulanan otomatis kepakai, simpel) vs "Custom Provider Key" (pasang API key provider sendiri di Settings, HF cuma jadi jalur, TAK potong kredit HF — cocok kalau kamu sudah py akun provider lain dgn kuota gratis sendiri).

## 4. HuggingChat & WebLLM

- **HuggingChat** (`huggingface.co/chat` / app "Open HuggingChat" — sudah terlihat di RN7) = chat UI gratis dgn **110+ model open-weight** (Llama, Mistral, Qwen, Command R+, Gemma dst), termasuk fitur "Assistants" custom (system-prompt + RAG + tools sendiri, bisa dibagikan via link) dan analisis gambar + speech-to-text (Whisper). **Tak ada API resmi gratis terpisah utk HuggingChat** — utk otomasi/scripting tetap lewat Inference Providers biasa (poin 3), jadi kredit kecil tetap berlaku kalau mau dipakai programatik, bukan manual di browser.
- **Local Browser Inference (WebLLM):** utk model kecil, HuggingChat bisa jalankan inferensi LANGSUNG DI BROWSER (device viewer sendiri) — nol biaya server, cocok kalau HP/laptop lokal ada yg mau dipakai iseng tanpa menyentuh kredit apa pun.

## 5. Spaces (hosting gratis + hack biaya)

> ⚠️ **KOREKSI (2026-08-22, ditemukan SETELAH riset awal):** versi awal doc ini keliru bilang "CPU Basic = hosting Docker/Gradio gratis selamanya". **ITU SALAH untuk akun baru sekarang.** Kutipan resmi `docs/hub/spaces-overview` (di-fetch ulang): *"Gradio and Docker Spaces run on compute and **require a paid plan to create: PRO for personal accounts**, Team or Enterprise for organizations. Free personal accounts in good standing can still host up to 2 Gradio Spaces running on **ZeroGPU**."* — kebijakan ini tampaknya baru diperketat sekitar **Juli 2026** (ada thread forum resmi HF soal "New free accounts cannot create CPU Basic Gradio Spaces" & "Docker SDK now marked as Paid"), jadi banyak tutorial/artikel lama (termasuk sumber yg tercampur di riset awal saya) memuat info basi era-lama saat ini masih benar-benar gratis tanpa syarat.

| Jenis Space | Butuh paid plan utk MEMBUAT? | Harga hardware/jam |
|---|---|---|
| **Static** (HTML/JS murni, tanpa backend) | **TIDAK — gratis tanpa syarat, tier apa pun** | — (tak ada kompute) |
| **Gradio di atas ZeroGPU** | Tidak, akun gratis boleh s/d 2 Space | GRATIS (kuota lihat poin 1) |
| **Gradio atau Docker di CPU Basic/hardware lain** | **YA — wajib PRO ($9/bln) personal, atau Team/Enterprise utk organisasi** | CPU Basic sendiri $0/jam, TAPI gerbang pembuatannya yg dikunci paid |
| CPU Upgrade / T4 / L4 / A10G / A100 dst | (sama, perlu paid dulu utk bisa bikin Space compute) | $0.03–$20/jam |

- **Implikasi nyata:** kalau mau host layanan sendiri (dashboard, API kecil, bot) via Docker/Gradio Space, **jalan gratis tanpa PRO cuma tersedia lewat SDK Static** — artinya HARUS pure client-side (HTML/CSS/JS statis + `window.huggingface.variables` utk baca variable publik), tanpa proses server/backend berjalan di sisi Space. Kalau butuh backend (nginx proxy, API, bot listener dst), itu genuinely butuh bayar PRO $9/bulan dulu — bukan lagi gratis murni spt anggapan umum lama.
- **Space gratis (kalau berhasil dibuat, mis. via ZeroGPU-exception atau setelah upgrade PRO) otomatis tidur kalau nganggur ~48 jam, dan BANGUN LAGI otomatis begitu ada pengunjung** — pola mirip "keepalive ping" yg sudah dipakai utk Cloud Shell (`.50/.60/.61`), tanpa risiko VM-recycle kehilangan kode (kode Space permanen di git repo Space itu sendiri).
- **Hardware BERBAYAR (yg sudah di-upgrade) justru DEFAULT jalan terus 24 jam (terus dibayar) kecuali kamu set "sleep time" custom** di Space settings — begitu di-set, Space jadi idle/stopped saat nganggur dan TAK dibayar selama tidur, bangun otomatis saat dikunjungi. **Kalau pernah upgrade Space ke hardware berbayar, WAJIB set sleep time, kalau tidak tagihan jalan terus meski tak dipakai.**
- **Tak ada biaya selama fase "build"** (cuma dibayar saat status Starting/Running) — bebas iterasi Dockerfile tanpa nambah tagihan build lamanan.
- Space yg CRASH otomatis di-suspend & billing berhenti sendiri (tak ada risiko tagihan membengkak akibat crash-loop).
- **Community GPU Grant:** kalau proyek/demo cukup menarik tapi butuh GPU berbayar, form aplikasi ada di **Space Settings → bagian "sleep time settings" (pojok kiri-bawah)** — "Building something cool as a side project? We also offer community GPU grants" (kutipan resmi halaman pricing). Dinilai kasus-per-kasus, tak ada kriteria pasti dipublikasikan — makin jelas nilai/dampak proyeknya, makin besar peluang.
- **Storage Buckets (fitur BARU, per Agustus 2026):** disk Space itu sendiri tetap ephemeral, tapi sekarang bisa **mount model/dataset/Space lain sbg volume READ-ONLY** langsung via `huggingface_hub` API — termasuk dataset PRIVAT milikmu sendiri (gratis s/d 100GB, poin 2). **Hack: pakai dataset privat sbg "penyimpanan referensi" gratis yg di-mount ke Space** (mis. bobot model/aset besar) tanpa perlu bayar Storage Buckets ($8-12/TB) atau add-on Persistent Storage ($5/bln); utk arah tulis-balik (persist output), commit periodik via API ke dataset repo yg sama (bukan tulis langsung ke disk Space) — efektif jadi "database" gratis sepanjang di bawah 100GB.

## 6. Rate limit API Hub — hack termudah & termurah

Semua kuota dihitung per jendela 5 menit (data resmi, per September 2025):

| Tier | API | Resolver (download file) | Pages |
|---|---|---|---|
| Anonim (per IP) | 500 | 3.000 | 100 |
| **Free (login)** | **1.000** | **5.000** | **200** |
| PRO | 2.500 | 12.000 | 400 |
| Team | 3.000 | 20.000 | 400 |
| Enterprise | 6.000 | 50.000 | 600 |

- **Hack #1 (gratis, instan):** "Alasan #1 orang kena rate-limit = TIDAK memasang `HF_TOKEN`" (kutipan resmi) — akun gratis dapat **2× lipat** kuota dibanding anonim, TANPA bayar apa pun, cukup selalu set env `HF_TOKEN` di semua tool (`huggingface_hub`, `transformers`, `datasets`, curl manual dst). Kalau ada skrip di pipeline (`viral-pipeline`, `tool-analisa-video`) yg download model/dataset dari HF tanpa token, ini quick-win gratis.
- Hack #2: endpoint **Resolver** (unduh file langsung, ada `/resolve/` di path) py kuota JAUH lebih tinggi drpd endpoint **API** (search/metadata) — kalau bisa, ganti panggilan API list/search jadi akses langsung by path resolver.
- `huggingface_hub` versi ≥1.2.0 sudah auto-retry cerdas saat kena HTTP 429 (baca header `RateLimit` utk tahu persis kapan boleh coba lagi) — pastikan versi lib selalu terbaru drpd bikin retry-logic manual.

## 7. Kecepatan upload/download — Xet (⚠️ koreksi info basi)

- **PENTING, KOREKSI:** banyak tutorial lama (termasuk kemungkinan pengetahuan lama saya sendiri) menyebut `HF_HUB_ENABLE_HF_TRANSFER=1` + paket `hf_transfer` utk percepat download 2×. **Env var ini SEKARANG DIABAIKAN/DEPRECATED** karena seluruh Hub sudah pindah ke backend storage baru **Xet** (dedup di level BYTE/chunk, bukan file — jauh lebih hemat transfer utk file yg cuma berubah sebagian, mis. checkpoint model iteratif).
- **Cara benar sekarang:** pasang `hf_xet` (otomatis terpasang bareng `huggingface_hub` versi baru) dan set **`HF_XET_HIGH_PERFORMANCE=1`** utk performa maksimal. Semua repo baru per 23 Mei 2025 otomatis Xet-enabled.
- Dampak nyata: upload folder besar sekarang jalan sbg pipeline streaming paralel (cek-dedup-upload-commit sekaligus), bukan lagi upload-file-demi-file berurutan spt Git LFS lama.

## 8. Program lain (relevan tapi bukan prioritas solo-user)

- **Academia Hub:** institusi (bukan individu) dgn kesepakatan mulai $10/seat/bulan, **minimum 250 seat/tahun** — TIDAK relevan utk akun personal single-user spt ini, sebutkan saja utk lengkap.
- **Startup credits / promo PRO gratis 1-6 bulan:** beberapa program partner (mis. lewat direktori promo pihak ketiga) menawarkan PRO gratis sementara utk startup terdaftar — sifatnya berubah-ubah & syarat ketat verifikasi entitas bisnis, tidak dievaluasi lebih lanjut di riset ini karena bukan fokus permintaan.

## 9. Rekomendasi konkret ke infra proyek ini (belum dieksekusi, usulan)

1. **Whisper/CLIP di `viral_analyzer` (.50, CPU-only, whisper bisa >10 menit/video panjang per catatan lama) → pindahkan inferensi ke Space ZeroGPU pribadi.** Bungkus fungsi whisper+CLIP jadi Gradio app kecil di Space ZeroGPU akun `warungbudina` (gratis, kuota 5 menit/hari — cukup utk klip pendek yg jadi mayoritas volume kerja), panggil dari orchestrator `.50`/akses-vps via `gradio_client`/HTTP biasa. Whisper yg tadinya 13 menit CPU bisa jadi hitungan detik di GPU — potensi percepatan besar utk `orchestrator.py`/`run-drain.sh`. **Syarat: kuota 5 menit/hari cukup ketat kalau volume tinggi** — cek dulu total durasi video/hari sebelum commit ke jalur ini.
2. **Selalu pasang `HF_TOKEN` (akun `warungbudina`) di skrip mana pun yg download dari HF** (kalau ada) — quick-win rate-limit 2× tanpa biaya.
3. **Ganti kebiasaan `HF_HUB_ENABLE_HF_TRANSFER` (kalau pernah dipakai) ke `HF_XET_HIGH_PERFORMANCE=1`** — env lama sudah tak berefek.
4. **Pertimbangkan dataset privat HF (gratis 100GB) sbg lapis backup tambahan** utk artefak pipeline (IR JSON, blueprint, dsb dari `viral-pipeline`) — alternatif/pelengkap Gdrive yg sudah dipakai, di luar ekosistem Google (diversifikasi risiko akun/kuota Gdrive yg sudah lumayan padat dgn 3 remote berbeda per memori `project_redmi_vn_node`/`project_viral_analyzer`).
5. **Dashboard analitik `project_browser_automation`** (sekarang di-host manual via nginx:alpine di Cloud Shell `.60` ephemeral, hilang tiap VM recycle) — dashboard-nya sendiri sudah berupa **HTML self-contained hasil generate** (bukan app server), jadi kandidat realistis = **Static Space (genuinely gratis, tanpa perlu PRO)**: cron di hub `git push`/`huggingface_hub.upload_file` file HTML baru ke repo Static Space itu tiap regen, auto-rebuild sendiri. Ini MENGGANTIKAN opsi "Docker Space gratis" yg ternyata sudah tak berlaku (lihat koreksi §5) — menghapus kebutuhan `selfhost-setup.sh` pasca-recycle TANPA perlu bayar apa pun, asal dashboard tetap murni statis (tak ada query live/backend).

---

## Sumber (di-fetch langsung 2026-08-22, bukan cuma cache pencarian)

- [huggingface.co/pricing](https://huggingface.co/pricing) — tabel resmi PRO/Team/Enterprise/hardware Spaces/Inference Endpoints/Storage
- [huggingface.co/docs/hub/spaces-zerogpu](https://huggingface.co/docs/hub/spaces-zerogpu) — kuota, size, duration, AOT compile
- [huggingface.co/docs/hub/storage-limits](https://huggingface.co/docs/hub/storage-limits) — kuota storage, cara bebaskan ruang
- [huggingface.co/docs/hub/spaces-gpus](https://huggingface.co/docs/hub/spaces-gpus) — hardware Spaces, community grant, sleep-time billing
- [huggingface.co/docs/hub/spaces-storage](https://huggingface.co/docs/hub/spaces-storage) — Storage Buckets & mount dataset/model sbg volume
- [huggingface.co/docs/inference-providers/pricing](https://huggingface.co/docs/inference-providers/pricing) — kredit gratis $0.10/$2.00, mekanisme billing
- [huggingface.co/docs/hub/rate-limits](https://huggingface.co/docs/hub/rate-limits) — tabel rate limit API/Resolver/Pages per tier
- [huggingface.co/docs/hub/academia-hub](https://huggingface.co/docs/hub/academia-hub) — syarat 250 seat
- WebSearch pendukung (Xet/hf_transfer deprecation, HuggingChat model count) — hasil disilangkan dgn dok resmi di atas, blog SEO dgn angka kontradiktif (mis. klaim "100K kredit/bulan gratis") DIABAIKAN krn tak cocok halaman pricing resmi.
