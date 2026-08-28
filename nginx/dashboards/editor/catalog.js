// Katalog operasi VN Video Editor — sumber kebenaran: tool-appium/docs/vn-automation-map.md
// Ditranskripsi manual (2026-08-28) dari §8/§20-21/§27/§29 (VN 2.17.0, versionCode 6989).
// Label di sini SENGAJA sama persis dengan yang tampil di UI VN, supaya .vn-recipe.md
// bisa dibaca apa-adanya sebagai instruksi tap-per-tap oleh editor manusia.
//
// gating: "free"   = client-side, tanpa login/kredit, aman dipakai kapan saja.
//         "pro"    = sebagian/seluruh item butuh akun VN Pro (👑) — cek dulu sebelum pakai.
//         "credit" = AI generatif server-side, dipotong dari saldo kredit VN (mis. Zoom In=75).
//         "flag"   = ketersediaan tool ITU SENDIRI tergantung status akun (bukan cuma item di dalamnya).

const VN_CATALOG = {
  meta: {
    sumber: "tool-appium/docs/vn-automation-map.md §8, §20-21, §27, §29",
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
  }
};

if (typeof module !== "undefined") module.exports = VN_CATALOG;
