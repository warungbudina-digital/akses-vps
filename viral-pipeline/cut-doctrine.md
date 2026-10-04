# Doktrin Potong (EDL) — pesan utuh, bukan fragmen

Keputusan **range mana yang dipotong** dibuat saat menulis EDL (transkrip → pilih
start/end → render.py mengeksekusi). Doktrin ini mencegah kesalahan paling sering:
**memotong terlalu pendek demi skor, sampai pesannya hilang.**

## Prinsip inti: potong UNIT-PIKIRAN UTUH

Satu reel harus memuat satu pikiran yang **selesai**, bukan cuplikan paling nendang saja:

1. **SETUP** — konteks singkat supaya penonton paham ini soal apa.
2. **KLAIM / momen** — inti pernyataan atau aksi.
3. **PAYOFF** — konsekuensi / kesimpulan / "jleb"-nya.

Buang SETUP atau PAYOFF = penonton tak dapat makna. Hook kuat tanpa payoff = clickbait kosong.

## Aturan

- **Akhiri di kalimat yang tuntas**, jangan di tengah frasa. Batas akhir = setelah ide selesai.
- **Durasi mengikuti PESAN, bukan sebaliknya.** Jangan pernah memotong payoff demi menurunkan durasi.
- **Pad batas 30–200 ms** (Hard Rule 7 video-use) untuk menyerap drift timestamp.
- Kalau arc penuh butuh 2 beat terpisah (mis. pertanyaan di menit 3 + jawaban di menit 7), pakai **2 range** di EDL (render.py menyambungnya), jangan paksa satu window.

## Target durasi per jenis konten

| Jenis | Target | Alasan |
|---|---|---|
| Edukasi / penjelasan / **podcast** (ada narasi) | **25–45 dtk** | butuh setup+klaim+payoff |
| Cerita / sebelum-sesudah / demo beralur | 20–35 dtk | ada perkembangan |
| Umum / kutipan tunggal | 15–25 dtk | satu poin |
| Visual / meme / b-roll tanpa narasi | 8–18 dtk | tak ada pesan verbal |

**12–16 dtk hanya untuk konten tanpa pesan verbal.** Untuk konten berisi narasi, ini terlalu pendek.

## Soal skor (jangan dikejar membabi-buta)

Scorecard `viral_scorecard.py` adalah **pemandu, bukan majikan**. Window re-watch sudah
dilebarkan (≤30 dtk tetap 5.0) agar klip-pesan tak dihukum. Tapi tetap:

- Untuk konten pesan, **🟡 dengan pesan UTUH lebih baik daripada 🟢 yang terpotong.**
- Jangan menaikkan skor dengan membuang SETUP/PAYOFF. Naikkan dengan memilih beat yang
  lebih kuat, bukan dengan memperpendek sampai hampa.

## Checklist sebelum render

- [ ] Ada SETUP + KLAIM + PAYOFF di dalam range?
- [ ] Berakhir di kalimat tuntas (bukan terpotong)?
- [ ] Durasi sesuai tabel jenis konten?
- [ ] Kalau dibuang 3 dtk terakhir, maknanya hilang? (kalau ya = payoff-nya memang di situ, pertahankan)
