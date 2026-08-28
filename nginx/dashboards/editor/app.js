// Dashboard generator script-editing VN — logic murni client-side (tanpa network call).
// Menyusun .vn-blueprint.json (machine-readable) + .vn-recipe.md (checklist tap-per-tap
// pakai label persis dari VN_CATALOG) dari brief kreatif + pilihan style per babak.
//
// Field per babak dibagi 2 kelompok di UI: "Style dasar" (selalu tampil) dan
// "Detail lanjutan" (dalam <details>, default tertutup) — supaya pemakaian cepat
// tetap ringkas, tapi seluruh tool yang terdokumentasi di vn-automation-map.md
// tetap bisa diatur presisi kalau dibutuhkan.

const STORAGE_KEY = "vn-editor-dashboard:proyek";

function uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}

function slugify(s) {
  return (s || "proyek").toLowerCase().trim()
    .replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || "proyek";
}

function opt(list, selected) {
  return list.map(v => `<option value="${escAttr(v)}" ${v === selected ? "selected" : ""}>${escHtml(v)}</option>`).join("");
}

function escHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function escAttr(s) { return escHtml(s); }

function filterKategoriOptions() { return Object.keys(VN_CATALOG.filter.kategori); }
function fxKategoriOptions() { return Object.keys(VN_CATALOG.fx.kategori); }
function textStyleKategoriOptions() { return Object.keys(VN_CATALOG.textStyle.kategori); }

let babakRows = [];

function defaultBabak(label, durasi) {
  return {
    id: uid(), label, durasi, brief: "", teksTampil: "",
    // -- style dasar --
    camera: "Tidak ada", speedTab: "Regular", speedPilihan: "1.0x",
    filterKategori: "Original", filterPilihan: "Original (tanpa filter)", filterIntensity: 100,
    fxKategori: "Original", fxPilihan: "None",
    voiceEffect: "None",
    textStyleKategori: "Default",
    transisiTab: "Base", transisiPilihan: "None", transisiDurasi: 0.5,
    catatanAnimasi: "",
    // -- detail lanjutan: footage-prep --
    trimPreset: "Tidak diubah", cropRatio: "Tidak diubah",
    rotate90: false, flipH: false, flipV: false, fillMode: "Tidak diubah",
    // -- detail lanjutan: komposisi/efek gambar --
    backgroundFill: "Tidak dipakai", maskCatatan: "",
    mosaicStyle: "Tidak dipakai", mosaicSize: 20,
    magnifierShape: "Tidak dipakai", magnifierZoom: 25, magnifierBorder: 40,
    imageBorderWidth: 0, imageBlurType: "Tidak dipakai", imageBlurIntensity: 30,
    alphaValue: 100, overlayPiP: false, elementsCatatan: "",
    // -- detail lanjutan: audio --
    volumeCatatan: "", denoise: false, extractAudio: false, reverse: false,
    // -- detail lanjutan: gated/tak pasti --
    autoCaption: false, freezeFrame: false,
    // -- detail lanjutan: teks --
    textColorCatatan: "", textAlign: "Tidak diubah", textCase: "Tidak diubah",
    textListStyle: "Tidak ada", textBold: false, textItalic: false, textSizePilihan: "Tidak diubah",
    textFontCatatan: "", textSpacingCatatan: "", blendModeCatatan: "", layerPositionCatatan: ""
  };
}

function seedBabakDefault() {
  babakRows = VN_CATALOG.babakDefault.map(b => defaultBabak(b.label, b.durasi));
}

function renderBabakForm() {
  const wrap = document.getElementById("babak-list");
  wrap.innerHTML = babakRows.map((b, i) => babakRowHtml(b, i)).join("");
}

function chk(f, checked, label) {
  return `<label class="chk"><input type="checkbox" data-f="${f}" ${checked ? "checked" : ""}> ${label}</label>`;
}

function babakRowHtml(b, i) {
  const fxPilihan = VN_CATALOG.fx.kategori[b.fxKategori]?.pilihan || [];
  const filterPilihan = ["Original (tanpa filter)"].concat(VN_CATALOG.filter.kategori[b.filterKategori]?.contoh || []);
  const transisiPilihan = VN_CATALOG.transisi.tabs[b.transisiTab]?.pilihan || [];
  return `
  <fieldset class="babak" data-id="${b.id}">
    <div class="babak-head">
      <input class="babak-label" data-f="label" value="${escAttr(b.label)}" placeholder="Nama babak">
      <label class="dur">Durasi (detik)
        <input type="number" min="0.5" step="0.5" data-f="durasi" value="${b.durasi}">
      </label>
      <button type="button" class="btn-ghost btn-remove" title="Hapus babak">Hapus</button>
    </div>

    <label class="fld">Brief kreatif / ide visualisasi klien
      <textarea data-f="brief" rows="2" placeholder="Mis: buka dengan wajah kaget, kamera goyang cepat, mood energik...">${escHtml(b.brief)}</textarea>
    </label>

    <label class="fld">Teks tampil di layar / subtitle (kata-kata literal, kosongkan kalau tak perlu teks)
      <textarea data-f="teksTampil" rows="1" placeholder="Mis: Promo cuma hari ini!">${escHtml(b.teksTampil)}</textarea>
    </label>

    <h3 class="section-h">Style dasar</h3>
    <div class="grid2">
      <label class="fld">Gerak kamera (clipZoom)
        <select data-f="camera">${opt(VN_CATALOG.cameraMovement.pilihan, b.camera)}</select>
      </label>

      <label class="fld">Speed <span class="tag flag">flag</span>
        <div class="inline">
          <select data-f="speedTab">${opt(Object.keys(VN_CATALOG.speed.tabs), b.speedTab)}</select>
          <select data-f="speedPilihan">${opt(VN_CATALOG.speed.tabs[b.speedTab].pilihan, b.speedPilihan)}</select>
        </div>
      </label>

      <label class="fld">Filter
        <div class="inline">
          <select data-f="filterKategori">${opt(filterKategoriOptions(), b.filterKategori)}</select>
          <select data-f="filterPilihan">${opt(filterPilihan, b.filterPilihan)}</select>
        </div>
        <span class="tag ${VN_CATALOG.filter.kategori[b.filterKategori]?.gating}">${VN_CATALOG.filter.kategori[b.filterKategori]?.gating}</span>
      </label>

      <label class="fld">Intensitas filter (0-100)
        <input type="number" min="0" max="100" data-f="filterIntensity" value="${b.filterIntensity}">
      </label>

      <label class="fld">FX
        <div class="inline">
          <select data-f="fxKategori">${opt(fxKategoriOptions(), b.fxKategori)}</select>
          <select data-f="fxPilihan">${opt(fxPilihan, b.fxPilihan)}</select>
        </div>
      </label>

      <label class="fld">Voice effect
        <select data-f="voiceEffect">${opt(VN_CATALOG.voiceEffect.pilihan, b.voiceEffect)}</select>
      </label>

      <label class="fld">Gaya teks (kategori)
        <select data-f="textStyleKategori">${opt(textStyleKategoriOptions(), b.textStyleKategori)}</select>
      </label>

      <label class="fld">Transisi masuk
        <div class="inline">
          <select data-f="transisiTab">${opt(Object.keys(VN_CATALOG.transisi.tabs), b.transisiTab)}</select>
          <select data-f="transisiPilihan">${opt(transisiPilihan, b.transisiPilihan)}</select>
        </div>
        <span class="tag ${VN_CATALOG.transisi.tabs[b.transisiTab].gating}">${VN_CATALOG.transisi.tabs[b.transisiTab].gating}</span>
      </label>
    </div>

    <label class="fld">Catatan animasi kustom (keyframe posisi/skala/opacity — tanpa preset, lihat catatan katalog)
      <textarea data-f="catatanAnimasi" rows="1" placeholder="Mis: zoom perlahan dari 100% ke 130% sepanjang babak">${escHtml(b.catatanAnimasi)}</textarea>
    </label>

    <details class="adv">
      <summary>Detail lanjutan (crop/rotate, komposisi, audio, teks, dll — ${countAktif(b)} aktif)</summary>

      <h3 class="section-h">Footage-prep</h3>
      <div class="grid3">
        <label class="fld">Trim <span class="tag free">free</span>
          <select data-f="trimPreset">${opt(VN_CATALOG.trim.pilihan, b.trimPreset)}</select>
        </label>
        <label class="fld">Crop rasio
          <select data-f="cropRatio">${opt(VN_CATALOG.crop.pilihan, b.cropRatio)}</select>
        </label>
        <label class="fld">Fill mode
          <select data-f="fillMode">${opt(["Tidak diubah", "Mengisi (Fill)", "Cocok (Fit)"], b.fillMode)}</select>
        </label>
      </div>
      <div class="chk-row">
        ${chk("rotate90", b.rotate90, "Putar 90° (instan)")}
        ${chk("flipH", b.flipH, "Flip horizontal (instan)")}
        ${chk("flipV", b.flipV, "Flip vertikal (instan)")}
      </div>

      <h3 class="section-h">Komposisi & efek gambar</h3>
      <div class="grid3">
        <label class="fld">Background fill (area kosong)
          <select data-f="backgroundFill">${opt(["Tidak dipakai"].concat(VN_CATALOG.background.tabs), b.backgroundFill)}</select>
        </label>
        <label class="fld">Mosaik/blur privasi
          <select data-f="mosaicStyle">${opt(VN_CATALOG.mosaic.pilihan, b.mosaicStyle)}</select>
        </label>
        <label class="fld">Ukuran mosaik (${VN_CATALOG.mosaic.size.default} default)
          <input type="number" min="0" max="100" data-f="mosaicSize" value="${b.mosaicSize}">
        </label>
        <label class="fld">Magnifier/lup
          <select data-f="magnifierShape">${opt(VN_CATALOG.magnifier.pilihan, b.magnifierShape)}</select>
        </label>
        <label class="fld">Magnifier zoom (${VN_CATALOG.magnifier.zoom.default} default)
          <input type="number" min="0" max="100" data-f="magnifierZoom" value="${b.magnifierZoom}">
        </label>
        <label class="fld">Magnifier border (${VN_CATALOG.magnifier.border.default} default)
          <input type="number" min="0" max="100" data-f="magnifierBorder" value="${b.magnifierBorder}">
        </label>
        <label class="fld">Lebar border klip (imageBorder)
          <input type="number" min="0" max="100" data-f="imageBorderWidth" value="${b.imageBorderWidth}">
        </label>
        <label class="fld">Blur klip (imageBlur)
          <select data-f="imageBlurType">${opt(VN_CATALOG.imageBlur.pilihan, b.imageBlurType)}</select>
        </label>
        <label class="fld">Intensitas blur (%)
          <input type="number" min="0" max="100" data-f="imageBlurIntensity" value="${b.imageBlurIntensity}">
        </label>
        <label class="fld">Opacity/Kegelapan (alpha)
          <input type="number" min="0" max="100" data-f="alphaValue" value="${b.alphaValue}">
        </label>
      </div>
      <div class="chk-row">${chk("overlayPiP", b.overlayPiP, "Jadikan klip ini overlay/PiP (toPiP)")}</div>
      <label class="fld">Mask <span class="tag free">free</span> (jenis belum dienum lengkap di dok — tulis kebutuhan)
        <input type="text" data-f="maskCatatan" value="${escAttr(b.maskCatatan)}" placeholder="Mis: mask bulat utk foto profil">
      </label>
      <label class="fld">Elements/Stiker (Graphics: ${VN_CATALOG.elements.graphics.kategori.join(", ")} · Frames: ${VN_CATALOG.elements.frames.kategori.join(", ")})
        <input type="text" data-f="elementsCatatan" value="${escAttr(b.elementsCatatan)}" placeholder="Mis: logo IG di pojok kanan atas">
      </label>

      <h3 class="section-h">Audio klip</h3>
      <div class="chk-row">
        ${chk("denoise", b.denoise, "Denoise")}
        ${chk("extractAudio", b.extractAudio, "Extract audio")}
        ${chk("reverse", b.reverse, "Reverse (putar balik)")}
      </div>
      <label class="fld">Volume/fade — catatan (tanpa preset diskrit)
        <input type="text" data-f="volumeCatatan" value="${escAttr(b.volumeCatatan)}" placeholder="Mis: fade in 0.5s, volume 80%">
      </label>

      <h3 class="section-h">Gated / status tak pasti <span class="tag unclear">unclear</span></h3>
      <div class="chk-row">
        ${chk("autoCaption", b.autoCaption, "AutoCaption (§27f: kemungkinan server-gated)")}
        ${chk("freezeFrame", b.freezeFrame, "Freeze frame (⚠️ dokumentasi bertentangan, cek live)")}
      </div>

      <h3 class="section-h">Teks — detail</h3>
      <div class="grid3">
        <label class="fld">Alignment
          <select data-f="textAlign">${opt(["Tidak diubah"].concat(VN_CATALOG.textFormat.alignment), b.textAlign)}</select>
        </label>
        <label class="fld">Case
          <select data-f="textCase">${opt(VN_CATALOG.textFormat.caseOption, b.textCase)}</select>
        </label>
        <label class="fld">List style
          <select data-f="textListStyle">${opt(VN_CATALOG.textFormat.listStyle, b.textListStyle)}</select>
        </label>
        <label class="fld">Ukuran teks
          <select data-f="textSizePilihan">${opt(VN_CATALOG.textSize.pilihan, b.textSizePilihan)}</select>
        </label>
      </div>
      <div class="chk-row">${chk("textBold", b.textBold, "Bold")} ${chk("textItalic", b.textItalic, "Italic")}</div>
      <label class="fld">Warna teks (4 target: Text/Stroke/Shadow/Background — picker tak terwakili dropdown, tulis kebutuhan)
        <input type="text" data-f="textColorCatatan" value="${escAttr(b.textColorCatatan)}" placeholder="Mis: teks putih, stroke hitam 2px">
      </label>
      <div class="grid2">
        <label class="fld">Font <span class="tag flag">flag</span> (Brand Kit = login-gated)
          <input type="text" data-f="textFontCatatan" value="${escAttr(b.textFontCatatan)}" placeholder="Mis: font impor lokal 'Poppins Bold'">
        </label>
        <label class="fld">Spacing (letter/line)
          <input type="text" data-f="textSpacingCatatan" value="${escAttr(b.textSpacingCatatan)}" placeholder="Mis: line spacing rapat">
        </label>
        <label class="fld">Blend mode
          <input type="text" data-f="blendModeCatatan" value="${escAttr(b.blendModeCatatan)}" placeholder="Mis: Multiply (cek live, belum dienum)">
        </label>
        <label class="fld">Layer position (Z-order)
          <input type="text" data-f="layerPositionCatatan" value="${escAttr(b.layerPositionCatatan)}" placeholder="Mis: bawa teks ke depan overlay">
        </label>
      </div>
    </details>
  </fieldset>`;
}

function countAktif(b) {
  let n = 0;
  if (b.trimPreset !== "Tidak diubah") n++;
  if (b.cropRatio !== "Tidak diubah") n++;
  if (b.rotate90) n++;
  if (b.flipH) n++;
  if (b.flipV) n++;
  if (b.fillMode !== "Tidak diubah") n++;
  if (b.backgroundFill !== "Tidak dipakai") n++;
  if (b.maskCatatan) n++;
  if (b.mosaicStyle !== "Tidak dipakai") n++;
  if (b.magnifierShape !== "Tidak dipakai") n++;
  if (b.imageBorderWidth > 0) n++;
  if (b.imageBlurType !== "Tidak dipakai") n++;
  if (b.alphaValue !== 100) n++;
  if (b.overlayPiP) n++;
  if (b.elementsCatatan) n++;
  if (b.volumeCatatan) n++;
  if (b.denoise) n++;
  if (b.extractAudio) n++;
  if (b.reverse) n++;
  if (b.autoCaption) n++;
  if (b.freezeFrame) n++;
  if (b.textColorCatatan) n++;
  if (b.textAlign !== "Tidak diubah") n++;
  if (b.textCase !== "Tidak diubah") n++;
  if (b.textListStyle !== "Tidak ada") n++;
  if (b.textBold) n++;
  if (b.textItalic) n++;
  if (b.textSizePilihan !== "Tidak diubah") n++;
  if (b.textFontCatatan) n++;
  if (b.textSpacingCatatan) n++;
  if (b.blendModeCatatan) n++;
  if (b.layerPositionCatatan) n++;
  return n;
}

const NUMERIC_FIELDS = new Set(["durasi", "filterIntensity", "transisiDurasi", "mosaicSize", "magnifierZoom", "magnifierBorder", "imageBorderWidth", "imageBlurIntensity", "alphaValue"]);
const CHECKBOX_FIELDS = new Set(["rotate90", "flipH", "flipV", "overlayPiP", "denoise", "extractAudio", "reverse", "autoCaption", "freezeFrame", "textBold", "textItalic"]);

function readBabakFromDom() {
  document.querySelectorAll("#babak-list .babak").forEach(el => {
    const id = el.dataset.id;
    const row = babakRows.find(b => b.id === id);
    if (!row) return;
    el.querySelectorAll("[data-f]").forEach(input => {
      const f = input.dataset.f;
      if (CHECKBOX_FIELDS.has(f)) { row[f] = input.checked; return; }
      let v = input.value;
      if (NUMERIC_FIELDS.has(f)) v = parseFloat(v) || 0;
      row[f] = v;
    });
  });
}

// Field yang mengubah OPSI dropdown lain (kategori -> daftar pilihan) butuh render
// ulang penuh. Field lain (termasuk semua checkbox/select di panel "Detail lanjutan")
// cukup update teks ringkasan di tempat — supaya <details> yang sedang terbuka
// TIDAK ikut tertutup/reset tiap kali user centang satu checkbox (bug UX kalau
// renderBabakForm dipanggil untuk setiap perubahan).
const OPTIONS_DEPENDENT_FIELDS = new Set(["filterKategori", "fxKategori", "speedTab", "transisiTab"]);

function onBabakInput(e) {
  const el = e.target.closest("[data-f]");
  if (!el) return;
  readBabakFromDom();
  const f = el.dataset.f;
  const fieldset = el.closest(".babak");
  const row = babakRows.find(b => b.id === fieldset.dataset.id);
  if (OPTIONS_DEPENDENT_FIELDS.has(f)) {
    if (f === "filterKategori") row.filterPilihan = (VN_CATALOG.filter.kategori[row.filterKategori]?.contoh || ["Original (tanpa filter)"])[0];
    if (f === "fxKategori") row.fxPilihan = (VN_CATALOG.fx.kategori[row.fxKategori]?.pilihan || ["None"])[0];
    if (f === "speedTab") row.speedPilihan = VN_CATALOG.speed.tabs[row.speedTab].pilihan[0];
    if (f === "transisiTab") row.transisiPilihan = VN_CATALOG.transisi.tabs[row.transisiTab].pilihan[0];
    renderBabakForm();
    return;
  }
  const summary = fieldset.querySelector(".adv > summary");
  if (summary) summary.textContent = `Detail lanjutan (crop/rotate, komposisi, audio, teks, dll — ${countAktif(row)} aktif)`;
}

function addBabak() {
  readBabakFromDom();
  babakRows.push(defaultBabak(`Babak ${babakRows.length + 1}`, 5));
  renderBabakForm();
}

function removeBabak(id) {
  readBabakFromDom();
  babakRows = babakRows.filter(b => b.id !== id);
  renderBabakForm();
}

function buildBlueprint(meta) {
  return {
    generator: "editor.obc-crypto.com dashboard",
    dibuat: new Date().toISOString(),
    proyek: meta.proyek,
    klien: meta.klien,
    rasio: meta.rasio,
    instruksi_umum: meta.instruksiUmum,
    musik: meta.musikGenre && meta.musikGenre !== "Tidak pakai musik" ? { selector: VN_CATALOG.musik.selector, genre: meta.musikGenre } : null,
    storyline: meta.storyline ? { selector: VN_CATALOG.storyline.selector, catatan: VN_CATALOG.storyline.catatan } : null,
    subtitle_method: meta.subtitleMethod === "Impor SRT"
      ? { jalur: "Impor SRT", ...VN_CATALOG.subtitle.importSrt }
      : { jalur: "Manual per-babak (in-app)", ...VN_CATALOG.subtitle.manual },
    catalog_sumber: VN_CATALOG.meta.sumber,
    babak: babakRows.map((b, i) => ({
      index: i + 1,
      label: b.label,
      durasi_detik: b.durasi,
      brief_kreatif: b.brief,
      teks_tampil: b.teksTampil || null,
      camera_movement: { selector: VN_CATALOG.cameraMovement.selector, pilihan: b.camera },
      speed: b.speedPilihan === "1.0x" ? null : {
        selector: VN_CATALOG.speed.selector, tab: b.speedTab, pilihan: b.speedPilihan,
        gating: "flag", catatan: VN_CATALOG.speed.catatan
      },
      filter: b.filterPilihan.startsWith("Original") ? null : {
        selector: VN_CATALOG.filter.selector, kategori: b.filterKategori, pilihan: b.filterPilihan,
        intensity: b.filterIntensity, gating: VN_CATALOG.filter.kategori[b.filterKategori]?.gating
      },
      fx: b.fxPilihan === "None" ? null : {
        selector: VN_CATALOG.fx.selector, kategori: b.fxKategori, pilihan: b.fxPilihan
      },
      voice_effect: b.voiceEffect === "None" ? null : { selector: VN_CATALOG.voiceEffect.selector, pilihan: b.voiceEffect },
      text_style: { selector: VN_CATALOG.textStyle.selector, kategori: b.textStyleKategori },
      transisi_masuk: b.transisiPilihan === "None" ? null : {
        tab: b.transisiTab, pilihan: b.transisiPilihan, durasi_detik: b.transisiDurasi,
        gating: VN_CATALOG.transisi.tabs[b.transisiTab].gating
      },
      catatan_animasi_kustom: b.catatanAnimasi || null,

      footage_prep: (b.trimPreset !== "Tidak diubah" || b.cropRatio !== "Tidak diubah" || b.rotate90 || b.flipH || b.flipV || b.fillMode !== "Tidak diubah") ? {
        trim: b.trimPreset !== "Tidak diubah" ? b.trimPreset : null,
        crop_ratio: b.cropRatio !== "Tidak diubah" ? b.cropRatio : null,
        rotate90: b.rotate90, flip_horizontal: b.flipH, flip_vertical: b.flipV,
        fill_mode: b.fillMode !== "Tidak diubah" ? b.fillMode : null
      } : null,

      komposisi: (b.backgroundFill !== "Tidak dipakai" || b.maskCatatan || b.mosaicStyle !== "Tidak dipakai" ||
        b.magnifierShape !== "Tidak dipakai" || b.imageBorderWidth > 0 || b.imageBlurType !== "Tidak dipakai" ||
        b.alphaValue !== 100 || b.overlayPiP || b.elementsCatatan) ? {
        background_fill: b.backgroundFill !== "Tidak dipakai" ? b.backgroundFill : null,
        mask_catatan: b.maskCatatan || null,
        mosaic: b.mosaicStyle !== "Tidak dipakai" ? { style: b.mosaicStyle, size: b.mosaicSize } : null,
        magnifier: b.magnifierShape !== "Tidak dipakai" ? { shape: b.magnifierShape, zoom: b.magnifierZoom, border: b.magnifierBorder } : null,
        image_border_width: b.imageBorderWidth > 0 ? b.imageBorderWidth : null,
        image_blur: b.imageBlurType !== "Tidak dipakai" ? { type: b.imageBlurType, intensity: b.imageBlurIntensity } : null,
        alpha: b.alphaValue !== 100 ? b.alphaValue : null,
        overlay_pip: b.overlayPiP || null,
        elements_catatan: b.elementsCatatan || null
      } : null,

      audio: (b.volumeCatatan || b.denoise || b.extractAudio || b.reverse) ? {
        volume_catatan: b.volumeCatatan || null, denoise: b.denoise || null,
        extract_audio: b.extractAudio || null, reverse: b.reverse || null
      } : null,

      gated_tak_pasti: (b.autoCaption || b.freezeFrame) ? {
        auto_caption: b.autoCaption ? VN_CATALOG.autoCaption.catatan : null,
        freeze_frame: b.freezeFrame ? VN_CATALOG.freezeFrame.catatan : null
      } : null,

      teks_detail: (b.textColorCatatan || b.textAlign !== "Tidak diubah" || b.textCase !== "Tidak diubah" ||
        b.textListStyle !== "Tidak ada" || b.textBold || b.textItalic || b.textSizePilihan !== "Tidak diubah" ||
        b.textFontCatatan || b.textSpacingCatatan || b.blendModeCatatan || b.layerPositionCatatan) ? {
        warna_catatan: b.textColorCatatan || null,
        alignment: b.textAlign !== "Tidak diubah" ? b.textAlign : null,
        case: b.textCase !== "Tidak diubah" ? b.textCase : null,
        list_style: b.textListStyle !== "Tidak ada" ? b.textListStyle : null,
        bold: b.textBold || null, italic: b.textItalic || null,
        ukuran: b.textSizePilihan !== "Tidak diubah" ? b.textSizePilihan : null,
        font_catatan: b.textFontCatatan || null,
        spacing_catatan: b.textSpacingCatatan || null,
        blend_mode_catatan: b.blendModeCatatan || null,
        layer_position_catatan: b.layerPositionCatatan || null
      } : null
    }))
  };
}

function fmtTs(sec) {
  const s = Math.max(0, sec);
  const m = Math.floor(s / 60), r = (s % 60).toFixed(1);
  return `${m}:${r.padStart(4, "0")}`;
}

function buildRecipe(meta, bp) {
  let t = 0;
  const lines = [];
  lines.push(`# Resep edit VN — ${meta.proyek}`);
  lines.push("");
  lines.push(`> Klien: ${meta.klien || "-"} · Rasio: ${meta.rasio} · Dibuat: ${new Date().toLocaleString("id-ID")}`);
  if (meta.instruksiUmum) lines.push(`\n**Instruksi/mood umum:** ${meta.instruksiUmum}`);
  lines.push("\n**Sebelum mulai:** buka proyek baru di VN (rasio " + meta.rasio + "), impor klip sesuai urutan babak di bawah, lalu ikuti tiap babak SECARA BERURUTAN — instruksi ditulis pakai label tombol/tab persis seperti yang tampil di VN.");
  if (bp.musik)
    lines.push(`\n**Musik latar:** trek musik (\`editor_track_music_add\`) → tab Musik → genre **"${bp.musik.genre}"** (kalau katalog cloud gagal load, pakai tab Milikmu dengan file sendiri).`);

  const babakDenganTeks = bp.babak.filter(b => b.teks_tampil);
  if (babakDenganTeks.length && bp.subtitle_method.jalur === "Impor SRT") {
    lines.push(`\n**Subtitle — jalur Impor SRT:** JANGAN ketik teks satu-per-satu di editor. Download file ` +
      `\`.srt\` di bawah halaman ini → \`adb push namafile.srt /sdcard/Download/\` ke device VN → di ` +
      `\`EditorActivity\` (tanpa klip terpilih) ketuk baris trek subtitle → popup **"Insert"** → **"SRT Files"** ` +
      `→ dialog "Impor File SRT" → **"Impor dari Aplikasi File"** → pilih file dari **"FILE TERBARU"** ` +
      `(kalau belum muncul, picu scan media dulu). Timing tiap baris otomatis sesuai timestamp babak.`);
  } else if (babakDenganTeks.length) {
    lines.push(`\n**Subtitle — jalur manual per-babak:** trek T+ (\`editor_track_subtitle_add\`) di tiap babak → sheet Insert → **"Text"** → pilih template gaya (lihat tiap babak di bawah) → ketik isi teks persis seperti tercantum.`);
  }
  lines.push("\n---\n");

  bp.babak.forEach((b, i) => {
    const t0 = t, t1 = t + b.durasi_detik;
    t = t1;
    lines.push(`## Babak ${i + 1} — ${b.label} (${fmtTs(t0)}–${fmtTs(t1)}, ${b.durasi_detik}s)`);
    if (b.brief_kreatif) lines.push(`\n**Ide kreatif:** ${b.brief_kreatif}`);
    if (b.teks_tampil) lines.push(`\n**Teks tampil:** "${b.teks_tampil}"`);
    lines.push("\n**Langkah eksekusi di VN:**");
    const steps = [];
    if (b.teks_tampil && bp.subtitle_method.jalur !== "Impor SRT")
      steps.push(`Trek T+ → Insert → **Text** → pilih template kategori **"${b.text_style.kategori}"** → ketik: **"${b.teks_tampil}"**.`);
    else if (b.teks_tampil)
      steps.push(`(Teks babak ini SUDAH termasuk di file .srt yang di-generate — lihat instruksi Impor SRT di atas, jangan ketik ulang manual.)`);
    if (b.camera_movement.pilihan !== "Tidak ada")
      steps.push(`Pilih klip babak ini → toolbar **Perbesar** (clipZoom) → pilih **"${b.camera_movement.pilihan}"**.`);
    if (b.speed)
      steps.push(`Toolbar **Speed** → tab **"${b.speed.tab === "Curve" ? "Kurva" : "Peraturan"}"** → pilih **"${b.speed.pilihan}"**. ⚠️ ${b.speed.catatan}`);
    if (b.filter)
      steps.push(`Toolbar **Filter** → kategori **"${b.filter.kategori}"** → pilih **"${b.filter.pilihan}"** → set Intensity ke **${b.filter.intensity}**${b.filter.gating === "pro" ? " (⚠️ butuh akun VN Pro)" : ""}.`);
    if (b.fx)
      steps.push(`Toolbar **FX** → kategori **"${b.fx.kategori}"** → pilih **"${b.fx.pilihan}"**${String(b.fx.pilihan).includes("👑") ? " (⚠️ Pro-gated)" : ""}.`);
    if (b.voice_effect)
      steps.push(`Toolbar **voiceEffect** → pilih **"${b.voice_effect.pilihan}"**.`);
    if (b.transisi_masuk)
      steps.push(`Di batas AWAL babak ini: tap titik sambung klip → tab **"${b.transisi_masuk.tab}"** → pilih **"${b.transisi_masuk.pilihan}"** → set durasi **${b.transisi_masuk.durasi_detik}s**${b.transisi_masuk.gating === "credit" ? " (⚠️ AI berbayar kredit — cek saldo dulu)" : ""}.`);
    if (b.catatan_animasi_kustom)
      steps.push(`Animasi kustom (Keyframe ◇): ${b.catatan_animasi_kustom} — set keyframe di awal babak, geser playhead ke akhir babak, ubah properti, VN interpolasi otomatis.`);

    if (b.footage_prep) {
      const fp = b.footage_prep;
      if (fp.trim) steps.push(`Trim (VideoTrimActivity) → preset **"${fp.trim}"**.`);
      if (fp.crop_ratio) steps.push(`Toolbar **Crop** → rasio **"${fp.crop_ratio}"**.`);
      if (fp.rotate90) steps.push(`Toolbar **Rotate** → ketuk 1x (+90°) — panel Background bisa muncul otomatis kalau ada area kosong.`);
      if (fp.flip_horizontal) steps.push(`Toolbar **flipHorizontal** → ketuk (mirror instan).`);
      if (fp.flip_vertical) steps.push(`Toolbar **flipVertical** → ketuk (mirror instan).`);
      if (fp.fill_mode) steps.push(`Toolbar **fill** (tanpa label, di sebelah flipVertical) → toggle ke **"${fp.fill_mode}"**.`);
    }
    if (b.komposisi) {
      const k = b.komposisi;
      if (k.background_fill) steps.push(`Toolbar **Background** → tab **"${k.background_fill}"**.`);
      if (k.mask_catatan) steps.push(`Toolbar **Mask**: ${k.mask_catatan} (cek jenis mask tersedia langsung di device).`);
      if (k.mosaic) steps.push(`Toolbar **Mosaik** → gaya **"${k.mosaic.style}"** → set ukuran ke **${k.mosaic.size}**.`);
      if (k.magnifier) steps.push(`Toolbar **Magnifier** → bentuk **"${k.magnifier.shape}"** → Zoom **${k.magnifier.zoom}**, Border **${k.magnifier.border}**.`);
      if (k.image_border_width) steps.push(`Toolbar **Berbatasan** (imageBorder) → set lebar ke **${k.image_border_width}**.`);
      if (k.image_blur) steps.push(`Toolbar **Blur** (imageBlur) → tipe **"${k.image_blur.type}"** → intensitas **${k.image_blur.intensity}%**.`);
      if (k.alpha) steps.push(`Toolbar **Kegelapan** (alpha) → set ke **${k.alpha}**.`);
      if (k.overlay_pip) steps.push(`Toolbar **Overlay Track** (toPiP) → ketuk — klip langsung pindah ke trek overlay/PiP, atur posisi via gestur di pratinjau.`);
      if (k.elements_catatan) steps.push(`Sheet Insert → **Elements** (atau **Frames**): ${k.elements_catatan}.`);
    }
    if (b.audio) {
      const a = b.audio;
      if (a.volume_catatan) steps.push(`Toolbar **Volume** (volumeFade): ${a.volume_catatan}.`);
      if (a.denoise) steps.push(`Toolbar **Denoise** → aktifkan.`);
      if (a.extract_audio) steps.push(`Toolbar **Extract Audio** → aktifkan.`);
      if (a.reverse) steps.push(`Toolbar **Reverse** → ketuk (aksi instan, balik arah putar).`);
    }
    if (b.gated_tak_pasti) {
      const g = b.gated_tak_pasti;
      if (g.auto_caption) steps.push(`Toolbar **AutoCaption** → aktifkan. ⚠️ ${g.auto_caption}`);
      if (g.freeze_frame) steps.push(`Toolbar **Freeze Frame** → aktifkan. ⚠️ ${g.freeze_frame}`);
    }
    if (b.teks_detail) {
      const td = b.teks_detail;
      const bits = [];
      if (td.alignment) bits.push(`alignment ${td.alignment}`);
      if (td.case) bits.push(`case ${td.case}`);
      if (td.list_style && td.list_style !== "Tidak ada") bits.push(`list style ${td.list_style}`);
      if (td.bold) bits.push("bold");
      if (td.italic) bits.push("italic");
      if (td.ukuran) bits.push(`ukuran ${td.ukuran}`);
      if (bits.length) steps.push(`Toolbar teks **Format** (A≡) / **Size** (AA): ${bits.join(", ")}.`);
      if (td.warna_catatan) steps.push(`Toolbar teks **Color** (roda-warna, 4 target Text/Stroke/Shadow/Background): ${td.warna_catatan}.`);
      if (td.font_catatan) steps.push(`Toolbar teks **Font** (Ff): ${td.font_catatan}.`);
      if (td.spacing_catatan) steps.push(`Toolbar teks **Spacing**: ${td.spacing_catatan}.`);
      if (td.blend_mode_catatan) steps.push(`Toolbar **blendMode**: ${td.blend_mode_catatan}.`);
      if (td.layer_position_catatan) steps.push(`Toolbar **layerPosition**: ${td.layer_position_catatan}.`);
    }

    if (steps.length === 0) steps.push("Tanpa style tambahan — pakai klip apa adanya sesuai brief kreatif di atas.");
    steps.forEach(s => lines.push(`- [ ] ${s}`));
    lines.push("");
  });

  if (bp.storyline) {
    lines.push("---\n");
    lines.push(`## Opsional — Storyline\nBuka toolbar **Cerita** (story) → susun tiap klip dengan deskripsi teks (\`etMediaDescription\`) sesuai brief tiap babak di atas. ${bp.storyline.catatan}`);
  }

  lines.push("\n---\n");
  lines.push(`**Total durasi rencana:** ${fmtTs(t)} (${t.toFixed(1)}s) — cocokkan dengan \`total_textView\` di VN setelah semua klip disusun.`);
  return lines.join("\n");
}

function fmtSrtTs(sec) {
  const s = Math.max(0, sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = Math.floor(s % 60);
  const ms = Math.round((s - Math.floor(s)) * 1000);
  const p2 = n => String(n).padStart(2, "0");
  const p3 = n => String(n).padStart(3, "0");
  return `${p2(h)}:${p2(m)}:${p2(ss)},${p3(ms)}`;
}

// Bangun file .srt standar dari teks_tampil + timing tiap babak (§23a: caption
// impor SRT masuk trek subtitle dgn timing PERSIS sesuai file — jadi babak tanpa
// teks_tampil dilewati, bukan diisi baris kosong).
function buildSrt(bp) {
  let t = 0, idx = 0;
  const blocks = [];
  bp.babak.forEach(b => {
    const t0 = t, t1 = t + b.durasi_detik;
    t = t1;
    if (!b.teks_tampil) return;
    idx++;
    blocks.push(`${idx}\n${fmtSrtTs(t0)} --> ${fmtSrtTs(t1)}\n${b.teks_tampil}\n`);
  });
  return blocks.join("\n");
}

function download(filename, content, mime) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

function loadHistory() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"); }
  catch { return []; }
}
function saveHistory(list) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(list.slice(0, 50))); } catch { /* private mode dsb, abaikan */ }
}

function renderHistory() {
  const list = loadHistory();
  const wrap = document.getElementById("history-list");
  if (!list.length) { wrap.innerHTML = `<p class="muted">Belum ada proyek yang di-generate.</p>`; return; }
  wrap.innerHTML = list.map(item => `
    <div class="hist-item">
      <div>
        <strong>${escHtml(item.proyek)}</strong>
        <span class="muted">— ${new Date(item.dibuat).toLocaleString("id-ID")} (${item.babakCount} babak)</span>
      </div>
      <div class="hist-actions">
        <button type="button" class="btn-ghost" data-open="${item.id}">Buka lagi</button>
      </div>
    </div>`).join("");
}

function openHistoryItem(id) {
  const list = loadHistory();
  const item = list.find(x => x.id === id);
  if (!item) return;
  document.getElementById("f-proyek").value = item.proyek;
  document.getElementById("f-klien").value = item.klien || "";
  document.getElementById("f-rasio").value = item.rasio;
  document.getElementById("f-instruksi").value = item.instruksiUmum || "";
  document.getElementById("f-musik").value = item.musikGenre || "Tidak pakai musik";
  document.getElementById("f-storyline").checked = !!item.storyline;
  document.getElementById("f-subtitle-method").value = item.subtitleMethod || "Manual per-babak (in-app)";
  babakRows = item.babakRows;
  renderBabakForm();
  showOutput(item.blueprint, item.recipe);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function showOutput(bp, recipeMd) {
  document.getElementById("out-json").textContent = JSON.stringify(bp, null, 2);
  document.getElementById("out-md").textContent = recipeMd;
  document.getElementById("output-section").hidden = false;
  window.__lastBlueprint = bp;
  window.__lastRecipe = recipeMd;

  const srt = buildSrt(bp);
  window.__lastSrt = srt;
  const srtCard = document.getElementById("srt-card");
  if (srt) {
    document.getElementById("out-srt").textContent = srt;
    srtCard.hidden = false;
  } else {
    srtCard.hidden = true;
  }
}

function onGenerate(e) {
  e.preventDefault();
  readBabakFromDom();
  const meta = {
    proyek: document.getElementById("f-proyek").value.trim() || "Proyek Tanpa Nama",
    klien: document.getElementById("f-klien").value.trim(),
    rasio: document.getElementById("f-rasio").value,
    instruksiUmum: document.getElementById("f-instruksi").value.trim(),
    musikGenre: document.getElementById("f-musik").value,
    storyline: document.getElementById("f-storyline").checked,
    subtitleMethod: document.getElementById("f-subtitle-method").value
  };
  if (!babakRows.length) { alert("Tambahkan minimal 1 babak dulu."); return; }

  const bp = buildBlueprint(meta);
  const recipe = buildRecipe(meta, bp);
  showOutput(bp, recipe);

  const list = loadHistory();
  list.unshift({
    id: uid(), proyek: meta.proyek, klien: meta.klien, rasio: meta.rasio, instruksiUmum: meta.instruksiUmum,
    musikGenre: meta.musikGenre, storyline: meta.storyline, subtitleMethod: meta.subtitleMethod,
    dibuat: new Date().toISOString(), babakCount: babakRows.length,
    babakRows: JSON.parse(JSON.stringify(babakRows)), blueprint: bp, recipe
  });
  saveHistory(list);
  renderHistory();
  document.getElementById("output-section").scrollIntoView({ behavior: "smooth" });
}

document.addEventListener("DOMContentLoaded", () => {
  seedBabakDefault();
  renderBabakForm();
  renderHistory();

  document.getElementById("babak-list").addEventListener("change", onBabakInput);
  document.getElementById("babak-list").addEventListener("input", (e) => {
    if (e.target.matches('textarea,input[type="text"],input[type="number"]')) readBabakFromDom();
  });
  document.getElementById("babak-list").addEventListener("click", (e) => {
    if (e.target.matches(".btn-remove")) removeBabak(e.target.closest(".babak").dataset.id);
  });
  document.getElementById("btn-add-babak").addEventListener("click", addBabak);
  document.getElementById("gen-form").addEventListener("submit", onGenerate);

  document.getElementById("btn-dl-json").addEventListener("click", () => {
    if (!window.__lastBlueprint) return;
    download(`${slugify(window.__lastBlueprint.proyek)}.vn-blueprint.json`, JSON.stringify(window.__lastBlueprint, null, 2), "application/json");
  });
  document.getElementById("btn-dl-md").addEventListener("click", () => {
    if (!window.__lastRecipe) return;
    download(`${slugify(window.__lastBlueprint.proyek)}.vn-recipe.md`, window.__lastRecipe, "text/markdown");
  });
  document.getElementById("btn-dl-srt").addEventListener("click", () => {
    if (!window.__lastSrt) return;
    download(`${slugify(window.__lastBlueprint.proyek)}.srt`, window.__lastSrt, "text/plain");
  });
  document.getElementById("btn-copy-md").addEventListener("click", async () => {
    if (!window.__lastRecipe) return;
    try { await navigator.clipboard.writeText(window.__lastRecipe); flashCopied("btn-copy-md"); }
    catch { alert("Gagal copy — salin manual dari kotak preview."); }
  });

  document.getElementById("history-list").addEventListener("click", (e) => {
    if (e.target.matches("[data-open]")) openHistoryItem(e.target.dataset.open);
  });
});

function flashCopied(btnId) {
  const btn = document.getElementById(btnId);
  const orig = btn.textContent;
  btn.textContent = "Tersalin ✓";
  setTimeout(() => { btn.textContent = orig; }, 1500);
}
