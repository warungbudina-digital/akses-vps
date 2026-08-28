// Katalog operasi VN Video Editor — sumber kebenaran: tool-appium/docs/vn-automation-map.md
// Ditranskripsi manual (2026-08-28) dari §8/§20-21/§27/§29 (VN 2.17.0, versionCode 6989).
// Label di sini SENGAJA sama persis dengan yang tampil di UI VN, supaya .vn-recipe.md
// bisa dibaca apa-adanya sebagai instruksi tap-per-tap oleh editor manusia.
//
// gating: "free"    = client-side, tanpa login/kredit, aman dipakai kapan saja.
//         "pro"     = sebagian/seluruh item butuh akun VN Pro (👑) — cek dulu sebelum pakai.
//         "credit"  = AI generatif server-side, dipotong dari saldo kredit VN (mis. Zoom In=75).
//         "flag"    = ketersediaan tool ITU SENDIRI tergantung status akun (bukan cuma item di dalamnya).
//         "unclear" = dokumentasi belum tuntas/bertentangan antar-sesi — WAJIB cek live sebelum pakai.

const VN_CATALOG = {
  meta: {
    sumber: "tool-appium/docs/vn-automation-map.md §8 (termasuk sub-Musik), §8a-8h, §13-15, §20-21, §27, §29",
    versi_vn: "2.17.0 (versionCode 6989)",
    catatan: "Speed (editor_toolbar_speed) pernah tercatat TIDAK ADA sama sekali pada akun " +
      "tamu/non-login (§8e), lalu TERBUKTI ADA pada akun login+VN Pro (§21g). Verifikasi " +
      "keberadaan tool di toolbar device tujuan SEBELUM eksekusi resep — feature-flag, bukan bug."
  },

  aspectRatio: ["16:9", "9:16", "1:1"],

  babakDefault: [
    { label: "Hook", durasi: 3 },
    { label: "Isi", durasi: 10 },
    { label: "Penutup", durasi: 4 }
  ],

  cameraMovement: {
    selector: "editor_toolbar_clipZoom",
    label_ui: "Perbesar",
    gating: "free",
    pilihan: ["Tidak ada", "Perkecil", "Perbesar", "Pindah ke kanan", "Pindah ke kiri", "Pindah ke bawah", "Pindah ke atas"]
  },

  speed: {
    selector: "editor_toolbar_speed",
    gating: "flag",
    catatan: "Cek dulu apakah editor_toolbar_speed muncul di toolbar (§21g) — kalau tidak ada, lewati babak ini.",
    tabs: {
      Regular: { label_ui: "Peraturan", pilihan: ["0.1x", "0.5x", "1.0x", "1.5x", "2x", "3x", "(geser bebas 0.1x-4x)"] },
      Curve: { label_ui: "Kurva", pilihan: ["Asli", "Kustom", "Montage", "Hero Time", "Bullet Time", "Jump Cut", "Fast In"] }
    }
  },

  filter: {
    selector: "editor_toolbar_filter",
    kategori: {
      Aesthetic: { gating: "free", contoh: ["A1", "A2", "A3", "A4"] },
      Create: { gating: "free", contoh: ["C5", "C6", "C7"] },
      Vivid: { gating: "pro", contoh: ["VI1", "VI2", "VI3"], catatan: "SELURUH item Vivid 👑 Pro-gated" },
      Original: { gating: "free", contoh: ["Original (tanpa filter)"] },
      Favorites: { gating: "free", contoh: ["(tergantung riwayat device)"] }
    },
    intensity: { selector: "sbIntensity", rentang: [0, 100] }
  },

  fx: {
    selector: "editor_toolbar_FX",
    catatan: "Mayoritas client-side; item bertanda 👑 di bawah = Pro-gated, hindari di eksekusi otonom.",
    kategori: {
      Original: { gating: "free", pilihan: ["None"] },
      Basic: { gating: "free", pilihan: ["Spin 01", "Spin 02", "Spin 03", "Spin 04", "Drop 01", "Drop 02", "Drop 03", "Drop 04", "Zoom 01", "Shake In", "Zoom Out", "Zoom In", "Move Right", "Move Left", "Move Down", "Move Up"] },
      Beats: { gating: "free", pilihan: ["Beats", "Soul", "Black", "White", "Jitter up", "Jitter down", "Expand"] },
      Glitch: { gating: "free", pilihan: ["Glitch 01", "Glitch 02", "Fuzzy", "Cut", "Noise 01", "Noise 02 👑"] },
      RGB: { gating: "free", pilihan: ["RGB 01", "RGB 02", "Chroma Zoom", "Shake"] },
      Blur: { gating: "free", pilihan: ["Fuzzy Opening", "Dreamy Glow", "Camera Focus 👑"] },
      Rotation: { gating: "free", pilihan: ["Spin in", "Spin out", "Rotary 01", "Rotary 02"] },
      Nature: { gating: "free", pilihan: ["Snowing", "Snowflake 01", "Snowflake 02"] },
      Light: { gating: "free", pilihan: ["Light 01", "Light 02", "Light 03", "Leak 👑"] },
      Split: { gating: "free", pilihan: ["(belum dienum penuh — cek live)"] },
      Retro: { gating: "free", pilihan: ["(belum dienum penuh — cek live)"] },
      Decor: { gating: "free", pilihan: ["(belum dienum penuh — cek live)"] },
      Stylize: { gating: "free", pilihan: ["(belum dienum penuh — cek live)"] }
    }
  },

  transisi: {
    selector: "titik sambung antar-klip (tap di batas dua klip saat playhead berhenti di sana, §29)",
    tabs: {
      Base: {
        label_ui: "Base", gating: "free", durasi_rentang_detik: [0.2, 3.0],
        pilihan: ["None", "Black", "White", "Zoom 1", "Zoom 2", "Dissolve 1", "Dissolve 2", "Shake 1", "Shake 2", "Light", "Blur", "Pixelate", "Circle", "Push", "Rotate 1", "Rotate 2", "Slide", "Wipe", "Blink", "Vertical", "Horizontal"]
      },
      Matte: {
        label_ui: "Matte", gating: "free", durasi_rentang_detik: [0.2, 3.0],
        pilihan: ["None", "Circle 1", "Circle 2", "Line 1", "Line 2", "Line 3", "Hexagon", "Square 1", "Square 2", "Square 3", "Ink 1", "Ink 2", "Paint 1", "Paint 2", "Sea", "Swirl", "Zebra", "Memory", "Lens", "Glitch"]
      },
      Effect: {
        label_ui: "Effect", gating: "credit", durasi_tetap_detik: 5,
        catatan: "AI generatif server-side, dipotong dari saldo kredit VN (mis. Zoom In = 75 kredit). Skip jika saldo/otonom.",
        pilihan: ["None", "Custom", "Zoom In", "Zoom Out", "Push", "Pull", "Fly Through"]
      }
    }
  },

  voiceEffect: {
    selector: "editor_toolbar_voiceEffect",
    gating: "free",
    pilihan: ["None", "Child", "Man", "Woman", "Robot", "Alien"]
  },

  textStyle: {
    selector: "editor_toolbar_textStyle",
    catatan: "Sebagian aset kategori ini di-stream dari cloud (ikon unduh) — pastikan device online.",
    kategori: {
      Default: { gating: "free", jumlah: 14 },
      Penutup: { gating: "free", jumlah: 12 },
      Judul: { gating: "free", jumlah: 12 },
      "Judul Tambahan": { gating: "free", jumlah: null },
      Dekoratif: { gating: "free", pilihan: ["TITLE/SUBTITLE", "VIDEO TITLE", "LINE", "Mask", "Frame", "Film"] }
    }
  },

  animasiTeksKlip: {
    catatan: "TIDAK ADA panel preset in/out/loop di build ini (§27i). Satu-satunya jalur animasi " +
      "kustom = Keyframe ◇ (posisi/skala/rotasi/opacity) manual per titik waktu — tulis sebagai " +
      "instruksi bebas di field 'catatan animasi', bukan dropdown."
  },

  // ---- Footage-prep (struktur klip) — §8h, §21h/§28a ----
  trim: {
    selector: "etTotalRangeTimeS (VideoTrimActivity)",
    gating: "free",
    pilihan: ["Tidak diubah", "Asli", "0.1s", "0.3s", "1s", "2.5s", "Kustom (ketik manual)"]
  },
  crop: {
    selector: "editor_toolbar_crop (buka CropActivity)",
    gating: "free",
    pilihan: ["Tidak diubah", "Asli", "Bebas", "9:16", "1:1", "16:9"]
  },
  rotateFlipFill: {
    selector: "editor_toolbar_rotate / flipHorizontal / flipVertical / fill (tanpa content-desc)",
    gating: "free",
    catatan: "Semua AKSI INSTAN tanpa panel (langsung ketuk, tak ada pilihan lanjutan). Rotate " +
      "+90° tiap ketuk memicu panel Background otomatis (area kosong). fill = toggle Mengisi(Fill)/Cocok(Fit)."
  },

  // ---- Komposisi & efek gambar — §8f/§8g ----
  background: {
    selector: "editor_toolbar_background",
    gating: "free",
    catatan: "Dipakai utk latar saat klip tak memenuhi frame (manual, atau otomatis muncul pasca-Rotate).",
    tabs: ["Gambar", "Warna", "Gradien"]
  },
  mask: {
    selector: "editor_toolbar_mask",
    gating: "free",
    catatan: "Ada di toolbar (§27c) tapi jenis mask belum dienum detail di dokumentasi — cek live di device sebelum eksekusi."
  },
  mosaic: {
    selector: "editor_toolbar_mosaic",
    gating: "free",
    pilihan: ["Tidak dipakai", "Mosaik", "Segitiga", "Segi enam", "Blur"],
    size: { selector: "sbSize", default: 20 }
  },
  magnifier: {
    selector: "editor_toolbar_magnifier",
    gating: "free",
    pilihan: ["Tidak dipakai", "Bulat", "Persegi 1", "Persegi 2", "Gaya 1", "Gaya 2"],
    zoom: { selector: "sbZoom", default: 25 },
    border: { selector: "sbBorder", default: 40 }
  },
  imageBorder: {
    selector: "editor_toolbar_imageBorder",
    gating: "free",
    label_ui: "Berbatasan",
    width: { selector: "sbBorderWidth", default: 0 }
  },
  imageBlur: {
    selector: "editor_toolbar_imageBlur",
    gating: "free",
    pilihan: ["Tidak dipakai", "Dasar", "Horizontal", "Vertikal", "Radioaktif"],
    intensity: { selector: "sbBlur/etBlurSize", default: 30, satuan: "%" }
  },
  alpha: {
    selector: "editor_toolbar_alpha",
    gating: "free",
    label_ui: "Kegelapan",
    default: 100
  },
  overlayPiP: {
    selector: "editor_toolbar_toPiP",
    gating: "free",
    catatan: "Mengetuknya TIDAK membuka panel — langsung memindahkan klip terpilih ke trek overlay/PiP baru (posisi/skala diatur via gestur di pratinjau)."
  },

  // ---- Elements / Stiker — §27k ----
  elements: {
    selector: "editor_track_sticker_add (sheet Insert -> Elements)",
    tabs: ["Elements", "Imports", "Favorites"],
    graphics: {
      gating: "free",
      catatan: "Client-side instan. Item ber-crown 👑 di kategori Social = Pro-gated, skip.",
      kategori: ["Shapes (36)", "Lines & Frames (323)", "Social Media Logo (77)", "Social (275, sebagian 👑)"]
    },
    frames: {
      gating: "free",
      catatan: "Cloud tapi berhasil load (~5s) tanpa login — beda dari musik cloud yang gagal.",
      kategori: ["Basic (16)", "Shapes (24)", "Square (40)", "Circle (27)"]
    }
  },

  // ---- Audio klip — §27c ----
  audio: {
    volume: { selector: "editor_toolbar_volume (=volumeFade)", gating: "free", catatan: "Volume + fade in/out, tanpa preset diskrit — tulis kebutuhan sbg catatan." },
    denoise: { selector: "editor_toolbar_denoise", gating: "free" },
    extractAudio: { selector: "editor_toolbar_extractAudio", gating: "free" },
    reverse: { selector: "editor_toolbar_reverse", gating: "free", catatan: "Aksi instan, balik arah putar klip." }
  },

  // ---- Gated / status tak pasti — WAJIB diverifikasi live sebelum eksekusi ----
  autoCaption: {
    selector: "editor_toolbar_autoCaption",
    gating: "unclear",
    catatan: "Kemungkinan server-gated (§27f), belum tuntas diuji. Jangan andalkan di eksekusi otonom sampai diverifikasi."
  },
  freezeFrame: {
    selector: "editor_toolbar_freezeFrame",
    gating: "unclear",
    catatan: "⚠️ DOKUMENTASI BERTENTANGAN: §8e (2026-07-28, Infinix) menyimpulkan freeze frame TIDAK ADA " +
      "sebagai fitur diskrit setelah penelusuran menyeluruh; tapi §27c DAN temuan terpisah 'BONUS toolbar " +
      "late RN7 MOD' (2026-08-13/16, RN7) DUA-DUANYA mencatat content-desc editor_toolbar_freezeFrame ADA " +
      "di inventaris toolbar. Pola sama dgn kasus Speed (§8e vs §21g) — kemungkinan beda per akun/build/" +
      "device (Infinix vs RN7 MOD), bukan cuma 1 sesi keliru. CEK LANGSUNG DI DEVICE TUJUAN, jangan asumsi."
  },

  // ---- Subtitle/caption — 2 JALUR BERBEDA, §8d/§23a/§27b ----
  subtitle: {
    selector: "editor_track_subtitle_add (trek T+ di rail-kanan, sheet 'Insert')",
    catatan: "Sheet Insert selalu tampil 2 opsi: Text (manual) dan SRT Files (impor). " +
      "Keduanya menulis ke trek subtitle YANG SAMA — bisa dicampur (sebagian manual, sebagian impor).",
    manual: {
      selector: "flAddSubtitle",
      gating: "free",
      catatan: "Buka picker template teks (lihat VN_CATALOG.textStyle) → ketik isi teks langsung di keyboard."
    },
    importSrt: {
      selector: "flAddAddSubtitlesFormSRT",
      gating: "free",
      catatan: "Alur: ketuk baris trek subtitle (tanpa klip terpilih) → popup rlAddTextMenu → " +
        "'SRT Files' → dialog 'Impor File SRT' → tvFile 'Impor dari Aplikasi File' → SAF picker " +
        "(com.google.android.documentsui) → file .srt muncul di 'FILE TERBARU' kalau sudah di-push " +
        "ke /sdcard/Download/ (untuk otomasi: adb push lalu `am broadcast` MEDIA_SCANNER_SCAN_FILE " +
        "supaya ke-index). Hasil: caption+timing dari SRT langsung masuk trek, total_textView " +
        "proyek ikut meluas mengikuti durasi SRT."
    }
  },

  // ---- Teks — detail warna/format/ukuran/font/layer, §27b/§27i ----
  textColor: {
    selector: "roda-warna in-keyboard",
    gating: "free",
    target: ["Text", "Stroke", "Shadow", "Background"],
    catatan: "4 target warna terpisah + opacity per-target. Tulis warna yang diinginkan sbg catatan bebas (mis. kode hex) — picker tak bisa diwakili dropdown."
  },
  textFormat: {
    selector: "editor_toolbar_textFormat (A≡)",
    gating: "free",
    listStyle: ["Tidak ada", "Bullet", "Nomor"],
    boldItalic: ["Bold", "Italic"],
    alignment: ["Kiri", "Tengah", "Kanan"],
    caseOption: ["Tidak diubah", "AG (kapital semua)", "Ag (kapital awal)", "ag (huruf kecil semua)"]
  },
  textSize: {
    selector: "editor_toolbar_textFontSize (AA)",
    gating: "free",
    pilihan: ["Tidak diubah", "Title (36)", "Subtitle (28)", "Content (24)", "Kustom"]
  },
  textFont: {
    selector: "editor_toolbar_textFont (Ff, in-keyboard) / editor_toolbar_textFont (klip terpilih)",
    gating: "flag",
    catatan: "Search Font (bawaan) + 'Add font' (impor lokal) = free. Dropdown 'Brand Kit' " +
      "di panel yang sama = LOGIN-GATED (Pro), tampil 'No styles available' kalau belum login."
  },
  textSpacing: {
    selector: "editor_toolbar_textSpacing (ikon spasi, in-keyboard)",
    gating: "free",
    catatan: "Letter/line spacing — nilai slider belum dienum detail di dokumentasi, tulis kebutuhan sbg catatan."
  },
  blendMode: {
    selector: "editor_toolbar_blendMode",
    gating: "free",
    catatan: "Mode blend klip teks/overlay terhadap layer di bawahnya — daftar mode belum dienum di dokumentasi, cek live lalu tulis kebutuhan."
  },
  layerPosition: {
    selector: "editor_toolbar_layerPosition",
    gating: "free",
    catatan: "Urutan Z (depan/belakang) antar-layer teks/overlay — kontrol pasti belum dienum di dokumentasi, cek live."
  },

  // ---- Project-level: musik latar & storyline — §Musik, §8g ----
  musik: {
    selector: "editor_track_music_add (MusicManageActivity)",
    gating: "free",
    catatan: "Tab Musik (katalog bawaan)/Favorit/Milikmu (file sendiri). Katalog cloud kadang 'Loading failed' — siapkan file sendiri sbg cadangan.",
    genre: ["Tidak pakai musik", "Vlog", "Pop", "Dynamic", "Fresh", "Acoustic", "Electronic", "Hip-Hop", "File sendiri (tab Milikmu)"]
  },
  storyline: {
    selector: "editor_toolbar_story (buka StorylineComposeActivity penuh)",
    gating: "free",
    catatan: "Composer storyboard terpisah: per-klip ada deskripsi teks (etMediaDescription) + toggle " +
      "'judul sebagai transisi'. Berguna sbg bahan narasi/AI, BUKAN wajib utk hasil edit akhir."
  }
};

if (typeof module !== "undefined") module.exports = VN_CATALOG;
