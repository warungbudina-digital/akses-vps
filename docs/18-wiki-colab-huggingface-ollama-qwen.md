# Wiki: Google Colab + Hugging Face + Ollama + Qwen

> Riset dilakukan Agustus 2026 (WebSearch/WebFetch langsung ke sumber resmi & komunitas). Angka kuota/limit di dunia LLM berubah cepat — setiap klaim di bawah diberi catatan tanggal riset. Selalu cek ulang sebelum mengambil keputusan penting jangka panjang.

---

## 1. Google Colab — Panduan Lengkap

### 1.1 Apa itu Colab & cara pakai dasar

Google Colab (Colaboratory) adalah layanan notebook Jupyter yang jalan di server Google, gratis dengan akses GPU/TPU terbatas. Alurnya:

1. Buka `colab.research.google.com`, buat notebook baru (`.ipynb`, tersimpan otomatis ke Google Drive).
2. Pilih runtime: menu **Runtime → Change runtime type** → pilih CPU / GPU (T4, L4, A100, dst tergantung tier) / TPU.
3. Tiap cell adalah kode Python yang jalan di VM sementara (ephemeral) — begitu sesi berakhir, filesystem lokal VM hilang total (kecuali yang disimpan ke Drive/HF/eksternal).

Tutorial praktis dasar:

```python
# 1. Mount Google Drive agar data/checkpoint persisten
from google.colab import drive
drive.mount('/content/drive')

# 2. Install package (contoh: transformers + ollama-related tooling)
!pip install -q transformers accelerate bitsandbytes huggingface_hub

# 3. Login ke Hugging Face (token dari huggingface.co/settings/tokens)
from huggingface_hub import login
login()  # akan minta token, atau pakai login(token="hf_xxx")

# 4. Jalankan inference/training singkat
from transformers import AutoModelForCausalLM, AutoTokenizer
model_id = "Qwen/Qwen2.5-1.5B-Instruct"
tok = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(model_id, device_map="auto")
```

Cek GPU yang didapat: `!nvidia-smi`.

### 1.2 Batasan aktual (riset Agustus 2026)

**Durasi sesi & idle timeout** — dari FAQ resmi Colab (`research.google.com/colaboratory/faq.html`):
- Tier gratis: runtime maksimum **~12 jam**, "tergantung ketersediaan dan pola pemakaian" — ini plafon, bukan jaminan.
- Idle timeout: sesi terputus jika tab tidak berinteraksi (umum dilaporkan komunitas **~90 menit**; Google sendiri tidak mempublikasikan angka pasti dan bisa berubah).
- Colab Pro+: mendukung eksekusi kontinu hingga **24 jam** selama saldo compute unit masih ada.
- GPU/TPU yang tersedia "bervariasi dari waktu ke waktu" — tidak ada jaminan tipe GPU tertentu, bahkan di tier berbayar ("subject to availability").

**Harga & kuota (Agustus 2026)**:

| Paket | Harga | Kuota | Catatan |
|---|---|---|---|
| Gratis | Rp0 | Tidak ada kuota GPU tetap, akses "dibatasi berat" saat demand tinggi | Sering dilaporkan setara ~15-30 jam T4/minggu, tapi **tidak dijamin/dipublikasikan resmi** |
| Colab Pro | $9.99/bulan | 100 compute units | GPU premium tersedia tergantung ketersediaan |
| Colab Pro+ | $49.99/bulan | 500 compute units | Runtime hingga 24 jam, prioritas lebih tinggi |
| Pay-As-You-Go | $9.99 | 100 compute units (sekali beli) | Compute unit **expired 90 hari** setelah dibeli |

Contoh konsumsi compute unit: GPU T4 ≈ 1,19 CU/jam (100 CU ≈ 84 jam), GPU A100 40GB ≈ 5,40 CU/jam (100 CU ≈ 18 jam) — jadi GPU lebih kuat = kuota habis jauh lebih cepat.

**Larangan ToS penting** (dari `colab.research.google.com/terms` + `research.google.com/colaboratory/tos_v4.html`, dicek langsung Agustus 2026):
- Dilarang: file hosting, media serving, "web service offerings" lain — **artinya Colab TIDAK BOLEH dipakai sebagai server produksi/API permanen**.
- Dilarang: torrent/P2P, remote proxy, crypto mining, DoS attack, password cracking, deepfake, containerization untuk membypass kebijakan.
- Tier gratis khusus tambahan larangan: **SSH shell / remote desktop**, membypass UI notebook lewat web interface lain, worker distributed computing.
- Larangan-larangan ini melonggar sedikit di paket berbayar selama saldo compute positif, tapi larangan "web service offering 24/7" pada dasarnya tetap berlaku secara semangat ToS — resource Colab diprioritaskan untuk *interactive use case*, bukan backend produksi.
- Google mengumpulkan data prompt/kode/output untuk perbaikan produk, disimpan hingga 18 bulan — perlu diperhatikan kalau kerjaan sensitif.

### 1.3 Hacks optimal

- **Checkpoint otomatis**: simpan checkpoint tiap 15-30 menit ke Google Drive (`drive.mount`) atau langsung push ke Hugging Face Hub tiap N step (`trainer.push_to_hub()` / `model.push_to_hub()`), supaya kalau sesi putus tidak kehilangan progres.
- **Cegah idle disconnect**: eksekusi trik JS auto-click di console browser memang beredar luas di komunitas, tapi ini **melanggar ToS** dan berisiko akun ditandai/dibatasi — lebih aman desain training/job supaya selesai dalam batas waktu wajar & checkpoint sering, drpd melawan mekanisme anti-idle Google.
- **Jalankan sebagai job pendek, bukan server**: pola paling aman = "batch job" (convert model, quantize, fine-tune LoRA singkat, generate dataset) lalu keluar — bukan proses yang menunggu request terus-menerus.
- **Tunnel sementara (bukan permanen)**: untuk demo/testing singkat, komunitas memakai `cloudflared` atau `ngrok` untuk mengekspos Ollama/FastAPI yang jalan di Colab ke URL publik sementara (`https://xxxx.trycloudflare.com`). Ini cocok untuk uji coba beberapa jam, **bukan** untuk backend 24/7 — begitu sesi Colab habis/idle, tunnel ikut mati dan URL publik hilang.
- **Hemat compute unit**: pilih GPU seringan cukup (T4 dulu, baru naik ke L4/A100 kalau training benar-benar butuh), matikan runtime manual selesai kerja (`Runtime → Disconnect and delete runtime`) — compute unit hanya terpakai saat runtime aktif.
- **Kaggle Notebooks sebagai alternatif**: Kaggle memberi kuota GPU mingguan (dilaporkan **~30 jam GPU/minggu**, sesi maks ~12 jam, GPU T4/P100 + akses TPU) secara gratis tanpa kartu kredit, dan sekarang **Colab Pro bisa ditautkan ke akun Kaggle untuk menambah kuota GPU mingguan di Kaggle**. Cocok dipakai bergantian dengan Colab kalau kuota salah satu habis.

---

## 2. Hugging Face — Panduan Lengkap

### 2.1 Komponen utama

- **Hub**: registry model + dataset (mirip GitHub untuk model AI), tiap repo punya git + Git LFS untuk file besar.
- **Spaces**: hosting demo/app (Gradio/Streamlit/Docker) gratis (CPU) atau berbayar (GPU dedicated/ZeroGPU).
- **Datasets**: hosting dataset, format sama seperti model repo.
- **Inference API / Inference Endpoints**: API serverless (gratis, rate-limited, untuk testing) vs Endpoints (GPU dedicated berbayar, untuk produksi).

### 2.2 Tutorial praktis

**CLI resmi terbaru** — penting: `huggingface-cli` **sudah deprecated**, di `huggingface_hub` v1.0+ perintah `huggingface-cli download` bahkan sudah dihapus total. Perintah resminya sekarang **`hf`** (riset Agustus 2026, blog resmi "Say hello to `hf`"):

```bash
pip install -U huggingface_hub

hf login                       # login pakai token
hf download Qwen/Qwen2.5-1.5B-Instruct --local-dir ./qwen2.5-1.5b
hf upload myuser/my-repo ./local-folder      # upload single-commit (bisa resumable utk folder besar)
```

(Script lama yang masih pakai `huggingface-cli download` umumnya bisa diganti langsung jadi `hf download` — hampir drop-in replacement.)

**Git LFS manual** (kalau butuh kontrol penuh, mis. repo GGUF besar):

```bash
git lfs install
git clone https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct
cd Qwen2.5-1.5B-Instruct
git lfs pull
```

**Load model via `transformers`**:

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-1.5B-Instruct",
    torch_dtype=torch.bfloat16,
    device_map="auto",       # accelerate otomatis sebar layer ke GPU/CPU/disk sesuai RAM tersedia
)
tok = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-1.5B-Instruct")
```

**Quantization di level `transformers`**:
- **bitsandbytes** 4-bit/8-bit (`load_in_4bit=True`, `bnb_4bit_quant_type="nf4"`, `bnb_4bit_use_double_quant=True`) — cocok untuk fine-tuning QLoRA di GPU terbatas (mis. T4 Colab).
- **GPTQ / AWQ** — quantization pasca-training yang dioptimalkan untuk inference GPU cepat (lebih rumit setup dibanding GGUF, umumnya untuk yang serius pakai vLLM/TGI).
- **GGUF** (lewat `llama.cpp`) — format quantized untuk inference **CPU-friendly**, ini yang dipakai Ollama (dibahas detail di bagian 3-4).

### 2.3 Batasan aktual (riset Agustus 2026, sumber: `huggingface.co/docs/hub/storage-limits`, blog eesel/metacto/klymentiev)

| Item | Free | PRO ($9/bulan) | Team/Enterprise |
|---|---|---|---|
| Storage repo privat | **100GB gratis** | **1TB** + pay-as-you-go di atasnya | 1TB per seat + pay-as-you-go |
| Storage repo publik | Tidak dibatasi ketat (dalam batas wajar) | 10TB publik disebut sbg perk PRO | — |
| Inference API (serverless, gratis) | Rate-limit "beberapa ratus request/jam", model umumnya **<10B parameter**, kena cold-start di model kurang populer | Rate limit naik signifikan + kredit 2 juta token/bulan lintas provider | — |
| ZeroGPU (Spaces, H200 shared) | **~5 menit GPU/hari** | **~25-40 menit/hari** + prioritas antrian | — |
| Spaces CPU Basic | Gratis (2 vCPU / 16GB RAM) | Sama + alokasi 2.000 CPU-jam/bulan gratis (mulai berlaku Juni 2026) utk demo open-source | — |
| Spaces GPU berbayar | — | $0,40/jam (T4 kecil) s.d. $23,50/jam (8x L40S) | — |

Catatan penting: angka rate-limit Inference API **tidak dipublikasikan resmi sebagai angka pasti** oleh HF — bervariasi tergantung popularitas model & beban server saat itu, jadi treat semua angka di atas sebagai estimasi komunitas per Agustus 2026, bukan SLA.

### 2.4 Hacks

- **Convert HF → GGUF untuk Ollama**: pipeline standar pakai `llama.cpp` (detail lengkap di bagian 3.3 & 4).
- **Host Space gratis sebagai API ringan**: bikin Space CPU Basic (gratis) jalankan FastAPI/Gradio yang wrap model kecil atau bahkan cuma proxy ke Ollama lokal — cocok untuk endpoint ringan non-real-time, bukan untuk model besar (CPU Basic cuma 2 vCPU/16GB RAM, jauh lebih lega dari akses-vps tapi tetap bukan untuk model >7B).
- **`device_map="auto"` dari `accelerate`**: otomatis membagi layer model ke GPU→CPU→disk offload sesuai RAM/VRAM yang terdeteksi, berguna kalau load model yang pas-pasan muat.
- **Quantized GGUF siap pakai**: tidak perlu convert sendiri — banyak uploader komunitas terpercaya (bartowski, MaziyarPanahi, TheBloke [legacy], Qwen resmi) sudah upload versi GGUF berbagai quant level untuk hampir semua model populer termasuk Qwen — cukup `hf download` atau langsung `ollama pull hf.co/...`.

---

## 3. Model Qwen — Fokus Khusus

### 3.1 Varian terbaru di HF (riset Agustus 2026)

Temuan mengejutkan: per Agustus 2026 lini Qwen sudah jauh melampaui "Qwen2.5" — ada seri **Qwen3, Qwen3.5, Qwen3.6, bahkan Qwen3.8** yang sudah dirilis Alibaba, dengan context window yang jauh lebih besar dari generasi sebelumnya:

| Model | Ukuran | Context native | Context extended (YaRN) | Lisensi |
|---|---|---|---|---|
| Qwen2.5 series | 0.5B – 72B (termasuk 0.5B/1.5B/3B/7B/14B/32B/72B) | hingga 128K | — | Apache 2.0 (mayoritas) |
| Qwen3-8B / Qwen3-32B | 8B / 32B | 32.768 token | hingga 131.072 token via YaRN | Apache 2.0 |
| Qwen3.5-4B / Qwen3.5-27B | 4B / 27B | 262.144 token | hingga 1.010.000 token | Apache 2.0 |
| Qwen3.6-27B / Qwen3.6-35B-A3B (MoE) | 27B dense / 35B total-3B aktif | 262.144 token (default) | — | Apache 2.0 |
| Qwen3-Coder-Next | 80B total, hanya ~3B aktif (MoE) | 256K | — | — |
| Qwen3.8-Max | ~2,4T total (MoE, ~95B aktif/token) | — | — | Custom (bukan open-weight penuh) |

Untuk kasus CPU-only/RAM kecil (relevan buat infra user), yang paling relevan tetap kelas **kecil**: Qwen2.5-0.5B/1.5B/3B/7B atau Qwen3.5-4B — model besar (27B+) butuh GPU kelas atas atau RAM puluhan GB, di luar jangkauan CPU-only VPS kecil.

GGUF quantized resmi/terpercaya tersedia di HF, misalnya repo seri `bartowski/Qwen2.5-*-GGUF`, `bartowski/Qwen3.8-27B-GGUF`, dan Qwen sendiri juga rilis GGUF resmi untuk sebagian model (lihat `Qwen/Qwen2.5-*-Instruct-GGUF`).

### 3.2 Menjalankan Qwen di Ollama — dua jalur

**Jalur 1 — dari Ollama library resmi** (model sudah dikurasi & di-repackage Ollama):

```bash
ollama pull qwen2.5           # default tag, biasanya ukuran mid-size
ollama pull qwen2.5:1.5b
ollama pull qwen2.5:3b
ollama pull qwen2.5:7b
ollama pull qwen3
ollama run qwen2.5:1.5b
```

Ollama library `qwen2.5` resmi mencakup rentang **0.5B sampai 72B**, dilatih di dataset ~18 triliun token, dukungan multibahasa dan konteks hingga 128K (tergantung ukuran).

**Jalur 2 — langsung dari Hugging Face Hub** (`hf.co/...`), berguna untuk model/quant yang belum ada di Ollama library, termasuk fine-tune komunitas atau model privat sendiri:

```bash
# format: ollama run hf.co/{user}/{repo}[:{quant_tag}]
ollama run hf.co/bartowski/Qwen2.5-7B-Instruct-GGUF
ollama run hf.co/bartowski/Qwen2.5-7B-Instruct-GGUF:Q4_K_M
ollama pull hf.co/bartowski/Qwen2.5-7B-Instruct-GGUF:Q4_K_M
```

Perbedaan kunci dua jalur ini:
- **Ollama library**: sudah dikurasi tim Ollama, biasanya default quant (Q4_0-ish) sudah dipilihkan, gampang, tapi pilihan quant/varian terbatas ke yang mereka publish.
- **`hf.co/...` direct pull**: akses ke **45 ribu+ repo GGUF publik** di HF (per data terbaru komunitas) — termasuk quant custom (Q3_K_XL, Q4_K_L, IQ4_XS, dst dari uploader seperti bartowski), model niche, atau **repo privat milik sendiri** (butuh `ollama login`/token HF). Kalau tidak spesifikasi tag quant, Ollama otomatis ambil Q4_K_M jika tersedia di repo.

### 3.3 Tabel rekomendasi quantization vs RAM

Formula umum yang dipakai komunitas: `RAM (GB) ≈ Parameter(miliar) × bytes-per-bobot × 1.2 (overhead)`, dengan bytes-per-bobot: FP16=2.0, Q8_0=1.0, Q5_K_M≈0.69, Q4_K_M≈0.55, Q3_K_M≈0.41. Tambah 1-2GB lagi untuk KV-cache context + OS.

| Ukuran model | Q4_K_M (RAM ±) | Q5_K_M (RAM ±) | Q8_0 (RAM ±) | Rekomendasi |
|---|---|---|---|---|
| 0.5B | ~0,4 GB | ~0,5 GB | ~0,7 GB | Muat di hampir semua device, termasuk VPS 1-2GB RAM |
| 1.5B | ~1,0 GB | ~1,3 GB | ~1,8 GB | Batas realistis VPS kecil (~2GB RAM) |
| 3B | ~2,0 GB | ~2,5 GB | ~3,5 GB | Butuh ≥4GB RAM total sistem supaya aman |
| 7B | ~4,6-7,9 GB* | ~9,1 GB* | ~7,7-8 GB* | Butuh ≥8GB RAM, idealnya ada GPU |
| 14B | ~9-10 GB | ~11-12 GB | ~15-16 GB | Butuh 16GB+ RAM atau GPU |
| 32B | ~20-22 GB | ~24-26 GB | ~34-36 GB | Praktis butuh GPU dedicated |
| 70B | ~38-42 GB | ~47-50 GB | ~72-75 GB | Server GPU kelas atas / multi-GPU |

\* Angka 7B bervariasi tergantung sumber pengukuran (ada disparitas kecil di data komunitas Q4 vs Q5 untuk 7B) — anggap 5-8GB sebagai rentang aman.

Rekomendasi umum: **Q4_K_M** adalah "sweet spot" default (hemat ~70%+ dibanding FP16, penurunan kualitas minor); **Q5_K_M** kalau task butuh presisi lebih (coding, math, agentic); **Q8_0** nyaris lossless tapi RAM besar — cocok kalau RAM berlimpah dan ingin kualitas maksimal dari GGUF.

---

## 4. Pipeline Penghubung Colab ↔ HF ↔ Ollama

### Pipeline A — Convert & quantize HF → GGUF pakai GPU gratis Colab, lalu jalankan di Ollama

```bash
# --- di Colab (pakai GPU/CPU Colab utk convert, ringan, tak butuh GPU kuat) ---
!git clone https://github.com/ggml-org/llama.cpp
!pip install -r llama.cpp/requirements.txt

# 1) convert model HF (safetensors) -> GGUF F16 (presisi tinggi dulu)
!python llama.cpp/convert_hf_to_gguf.py Qwen/Qwen2.5-3B-Instruct \
    --outtype f16 --outfile qwen2.5-3b-f16.gguf

# 2) build llama-quantize lalu quantize ke Q4_K_M
!cmake -B llama.cpp/build llama.cpp && cmake --build llama.cpp/build --target llama-quantize -j
!llama.cpp/build/bin/llama-quantize qwen2.5-3b-f16.gguf qwen2.5-3b-Q4_K_M.gguf Q4_K_M

# 3) push ke HF Hub (repo privat/publik milik sendiri)
from huggingface_hub import HfApi
HfApi().upload_file(
    path_or_fileobj="qwen2.5-3b-Q4_K_M.gguf",
    path_in_repo="qwen2.5-3b-Q4_K_M.gguf",
    repo_id="myuser/qwen2.5-3b-custom-gguf",
)
```

```bash
# --- di mesin lokal/server (mis. Pi4B atau akses-vps) ---
ollama pull hf.co/myuser/qwen2.5-3b-custom-gguf:Q4_K_M
# atau bikin Modelfile manual dari file GGUF lokal:
cat > Modelfile <<'EOF'
FROM ./qwen2.5-3b-Q4_K_M.gguf
PARAMETER temperature 0.7
EOF
ollama create qwen-custom -f Modelfile
```

### Pipeline B — Fine-tuning/LoRA ringan di Colab → merge → GGUF → Ollama

1. Di Colab (GPU T4 gratis cukup untuk Qwen2.5 0.5B-3B): load model base 4-bit (`bitsandbytes`, `nf4`) + `peft` LoRA (`r=64, lora_alpha=16` umum dipakai) + `trl`/`transformers.Trainer` untuk fine-tune dataset custom (mis. gaya caption personal branding).
2. Push adapter LoRA ke HF (`model.push_to_hub("myuser/qwen2.5-1.5b-caption-lora")`) — ukurannya kecil (puluhan-ratusan MB), cepat.
3. Merge adapter ke base model (`peft` `merge_and_unload()`), lalu convert hasil merge → GGUF (sama seperti Pipeline A) → quantize → push/pull ke Ollama.

Ini pola standar QLoRA: hemat memori drastis di GPU terbatas Colab, tapi tetap perlu Colab (bukan akses-vps) karena butuh GPU untuk fine-tuning yang layak — CPU-only fine-tuning terlalu lambat untuk praktis.

### Pipeline C — HF Spaces/Endpoints sebagai API persisten vs self-host Ollama

Karena Colab **dilarang ToS jadi server 24/7** dan sesi mati otomatis, ada 2 opsi kalau butuh API yang hidup terus:
- **HF Spaces (CPU Basic gratis / ZeroGPU kuota harian / GPU dedicated berbayar)** — cocok kalau butuh endpoint publik tanpa kelola server sendiri, tapi model besar atau traffic tinggi tetap kena biaya/kuota.
- **Self-host Ollama** (di infra sendiri: Pi4B, VPS, laptop) — inference gratis tanpa batas kuota provider, tapi ditanggung sendiri soal kapasitas hardware (RAM/CPU) dan uptime.

Trade-off intinya: Colab = "pinjam GPU sesekali/batch", HF Spaces/Endpoints = "sewa hosting terkelola", Ollama self-host = "beli sekali (hardware sendiri), pakai selamanya tapi terbatas kapasitas".

---

## 5. Keselarasan Optimal Colab + HF untuk Model AI Lokal via Ollama

**Playbook end-to-end** — dari "punya model Qwen di HF" sampai "jalan di Ollama lokal siap automasi":

1. **Pilih model** di HF (Qwen resmi atau varian fine-tune) sesuai kebutuhan (bahasa, ukuran, context).
2. **(Opsional) Fine-tune ringan** di Colab kalau butuh gaya/domain khusus (LoRA/QLoRA, Pipeline B) — pakai GPU gratis Colab, jangan di CPU lokal (terlalu lambat).
3. **Convert & quantize ke GGUF** di Colab (Pipeline A) kalau belum ada GGUF siap pakai di HF — manfaatkan GPU/CPU gratis Colab untuk kerja berat konversi sekali jalan, bukan proses berulang.
4. **Simpan hasil di HF Hub** (repo privat/publik) sebagai "titik distribusi" — bukan di Colab (hilang saat sesi berakhir) dan bukan didorong langsung ke server produksi tiap kali (biar ada riwayat versi + bisa ditarik dari device manapun).
5. **`ollama pull hf.co/...`** dari server produksi (Pi4B/VPS/laptop) — proses ringan, hanya download, tidak butuh GPU.
6. **Ollama jalan sebagai daemon lokal 24/7** di hardware yang MEMANG sanggup (bukan Colab, bukan HF Spaces gratis) — inference CPU-only untuk model kecil (0.5B-3B) itu ranahnya Ollama self-host, bukan Colab/HF gratisan.

Kaidah pembagian peran:
- **Colab** = GPU berat *sesekali/batch* (fine-tune, convert, quantize, eksperimen) — bukan backend, bukan penyimpanan permanen.
- **Hugging Face** = *distribusi* (Hub untuk model/dataset) + *hosting API ringan opsional* (Spaces/Endpoints) — bukan tempat training berat gratis kecuali pakai ZeroGPU kuota kecil.
- **Ollama lokal** = *inference murah 24/7 tanpa GPU* untuk model kecil-menengah yang sudah di-quantize — ini yang paling pas untuk kebutuhan automasi harian yang butuh respons cepat & tanpa biaya per-request.

---

## 6. Relevansi & Rekomendasi Konkret untuk Infra User

### 6.1 Spek riil akses-vps (diukur langsung, Agustus 2026)

```
CPU   : 2 vCPU (nproc = 2)
RAM   : 1,9 GiB total, hanya ~770 MiB "available" saat idle (1,2 GiB sudah dipakai 14 container)
Swap  : 4,0 GiB (3,6 GiB masih bebas, tapi swap = disk, jauh lebih lambat dari RAM)
Disk  : 29 GB total, 11 GB tersisa (63% terpakai)
```

Ini VPS **kecil, CPU-only, RAM sangat mepet** — dan RAM-nya sudah dipakai untuk stack produksi penting (WireGuard hub, nginx, mosquitto, genieacs, freeradius, redis, dst — 14 container). Ini bukan mesin yang "kosong menunggu diisi model AI".

### 6.2 Ukuran Qwen yang REALISTIS di akses-vps

Berdasarkan tabel RAM di bagian 3.3, dibandingkan RAM available riil (~770MB, bukan 1,9GB penuh):

| Model | RAM Q4_K_M | Muat di akses-vps? |
|---|---|---|
| Qwen2.5-0.5B | ~0,4 GB | **Ya, dengan margin tipis** — kandidat paling aman |
| Qwen2.5-1.5B | ~1,0 GB | **Berisiko** — akan makan swap, bisa memicu OOM di container lain (mosquitto/nginx crash-loop seperti insiden pasca-reboot yang sudah pernah terjadi di host ini) |
| Qwen2.5-3B ke atas | ≥2 GB | **Jangan** — RAM available saat ini bahkan tidak cukup untuk model saja, belum lagi KV-cache + OS |

**Rekomendasi tegas: JANGAN jalankan Ollama sebagai daemon permanen di akses-vps.** Alasannya bukan cuma soal "muat atau tidak" secara matematis — host ini adalah **hub kendali akses (WireGuard 10.66.66.1) untuk seluruh infrastruktur**. Kalau proses Ollama+model memicu tekanan memori dan OOM-killer menyasar container yang salah, risiko berulangnya insiden "mosquitto tak restart → nginx crash-loop" (sudah pernah terjadi pasca-reboot di host ini) jadi nyata — dan kali ini bisa memutus akses ke SEMUA node lain (Pi4B, RN7, Cloud Shell .50/.60), bukan cuma satu layanan.

### 6.3 Ke mana Qwen+Ollama seharusnya dijalankan

Selaras dengan pola SOP node terjadwal yang sudah ada (`docs/16-sop-node-terjadwal.md`: akses-vps = hub 24/7 murni kendali, kerja berat ada di node terjadwal lain):

- **Raspberry Pi 4B** — sudah punya Ollama + `nomic-embed` (untuk RAG vault pentest) tapi **belum punya model reasoning/chat**. Ini kandidat paling logis untuk nambah `qwen2.5:0.5b` atau `qwen2.5:1.5b` (cek dulu `free -h` di Pi sebelum pilih ukuran — kalau Pi4B model 4GB/8GB RAM, ruang jauh lebih lega dibanding akses-vps). Dengan itu, RAG vault bisa naik level dari "cuma retrieval embedding" jadi "retrieval + jawaban ter-generate" (baseline RAG lengkap: embed dengan nomic-embed, generate jawaban dengan Qwen).
- **Google Cloud Shell `.50` (viral_analyzer)** — ini yang paling menjanjikan buat langsung dipakai: `ir_to_vn.py` saat ini WAJIB keluarkan `.story-script.md` tapi (sesuai catatan proyek) prosesnya heuristik murni, sengaja tanpa Gemini/API berbayar. **Qwen kecil via Ollama (mis. 1.5B-3B Q4_K_M) bisa jalan di situ** untuk menghasilkan narasi story-script yang lebih natural dibanding heuristik template, TANPA melanggar prinsip "tanpa Gemini/API berbayar" — karena Ollama+Qwen 100% lokal/open-weight, bukan API berbayar. Cloud Shell `.50` kemungkinan punya RAM lebih lega dari akses-vps (perlu dicek `free -h` di sana juga), jadi bisa pertimbangkan naik ke 3B-7B kalau spek mengizinkan.
- **Agen media sosial (personal branding)** — untuk caption generation lebih natural, Qwen kecil (0.5B-1.5B, fine-tuned ringan via Pipeline B kalau mau gaya "Go Go Bud" konsisten) bisa dipasang di Pi4B atau RN7 (kalau RAM RN7 memungkinkan), dipanggil dari akses-vps sebagai *trigger*, bukan dieksekusi di akses-vps.
- **akses-vps tetap berperan sebagai orchestrator/trigger saja** — kalau memang perlu "otak AI" yang bisa dipanggil dari hub, opsi paling aman secara RAM adalah **memanggil Qwen yang jalan di Pi4B/`.50` lewat WireGuard** (akses-vps cukup `curl` ke `http://10.66.66.x:11434/api/generate`), persis pola SOP node terjadwal yang sudah dipakai untuk pipeline video (akses-vps memicu, node lain yang berat kerja).

### 6.4 Peran Colab dalam alur ini

Colab **cocok** dipakai sesekali untuk:
- Quantize model Qwen custom/fine-tune ke GGUF (pakai GPU gratis, jauh lebih cepat dari CPU 2 vCPU akses-vps) → push ke HF → pull dari Pi4B/`.50`.
- Fine-tuning LoRA ringan Qwen 0.5B-3B kalau suatu saat ingin gaya caption/story-script yang benar-benar konsisten dengan brand "Go Go Bud" — QLoRA di T4 gratis Colab realistis untuk model sekecil ini.

Colab **TIDAK cocok** dan **JANGAN dipakai** sebagai:
- Backend API 24/7 untuk agen medsos atau viral_analyzer — sesi mati otomatis (~12 jam maks, idle timeout ~90 menit), dan ini melanggar ToS ("web service offering", larangan hosting server). Kalaupun dipaksa pakai tunnel (cloudflared/ngrok), URL publiknya hilang tiap kali sesi restart — tidak stabil untuk automasi terjadwal yang butuh endpoint tetap.

### 6.5 Ringkasan peringatan realistis

- **VPS kecil CPU-only (akses-vps) = lambat & berisiko untuk model >1.5B** — bahkan model 0.5B pun sebaiknya dites hati-hati dulu (`ollama run` interaktif, monitor `free -h` real-time) sebelum dijadikan proses permanen, karena RAM available saat ini sudah sangat tipis (~770MB).
- **Colab tidak bisa jadi backend produksi 24/7** — cocok untuk kerja berat *sesekali* (convert/quantize/fine-tune), bukan untuk melayani request terus-menerus.
- **HF Spaces gratis (ZeroGPU) juga terbatas** — hanya ~5 menit GPU/hari di tier gratis, tidak cukup untuk beban kerja rutin harian tanpa upgrade PRO.
- **Node yang paling siap untuk "otak" Qwen 24/7 justru bukan akses-vps** — melainkan Pi4B (kalau RAM-nya lebih besar dari akses-vps) atau Cloud Shell `.50`, mengikuti pola arsitektur yang memang sudah dipakai user selama ini (hub ringan + node kerja terpisah).

---

## Daftar sumber yang dipakai riset (Agustus 2026)

- [Google Colab FAQ resmi](https://research.google.com/colaboratory/faq.html)
- [Colab Additional Terms of Service](https://colab.research.google.com/terms)
- [Colab Paid Services Additional ToS](https://research.google.com/colaboratory/tos_v4.html)
- [Google Colab Free Tier Limits 2026 — Joshua Thompson](https://joshthompson.co.uk/ai/google-colab-2026-guide-free-compute-automations-pro-tips/)
- [Kaggle Weekly GPU Quotas dataset](https://www.kaggle.com/datasets/headsortails/kaggle-weekly-gpu-quotas)
- [Kaggle vs Google Colab 2026](https://lalatenduswain.medium.com/kaggle-vs-google-colab-which-cloud-notebook-platform-should-you-choose-in-2026-da053a02fcb7)
- [Hugging Face Storage Limits (docs resmi)](https://huggingface.co/docs/hub/storage-limits)
- [Hugging Face Inference API Free Tier Limits 2026 — Dmytro Klymentiev](https://klymentiev.com/blog/huggingface-inference-api)
- [Hugging Face Pricing 2026 — eesel AI](https://www.eesel.ai/blog/hugging-face-pricing)
- [HuggingFace Spaces CPU tier price change news](https://ai.axisterian.com/news/huggingface-spaces-pricing-change)
- [Use Ollama with any GGUF Model on Hugging Face Hub — docs resmi HF](https://huggingface.co/docs/hub/ollama)
- ["Say hello to `hf`" — blog resmi Hugging Face](https://huggingface.co/blog/hf-cli)
- [llama.cpp quantize README — GitHub ggml-org](https://github.com/ggml-org/llama.cpp/blob/master/tools/quantize/README.md)
- [Qwen — llama.cpp quantization docs resmi](https://qwen.readthedocs.io/en/latest/quantization/llama.cpp.html)
- [bartowski GGUF repos di Hugging Face](https://huggingface.co/bartowski)
- [ollama.com/library/qwen2.5](https://ollama.com/library/qwen2.5)
- [Qwen/Qwen3-8B, Qwen3-32B, Qwen3.5, Qwen3.6, Qwen3.8-Max — Hugging Face model cards](https://huggingface.co/Qwen)
- [GGUF Memory Calculator](https://ggufloader.github.io/gguf-memory-calculator.html)
- [colab-llm — Ollama + Cloudflare Tunnel di Colab (GitHub)](https://github.com/enescingoz/colab-llm)
- [On-Device Qwen2.5 benchmark CPU — arXiv](https://arxiv.org/html/2504.17376v1)
- [Making LLMs more accessible with bitsandbytes 4-bit & QLoRA — blog resmi HF](https://huggingface.co/blog/4bit-transformers-bitsandbytes)
