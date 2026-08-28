// Dashboard generator script-editing VN — logic murni client-side (tanpa network call).
// Menyusun .vn-blueprint.json (machine-readable) + .vn-recipe.md (checklist tap-per-tap
// pakai label persis dari VN_CATALOG) dari brief kreatif + pilihan style per babak.

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

function filterKategoriOptions() {
  return Object.keys(VN_CATALOG.filter.kategori);
}
function fxKategoriOptions() {
  return Object.keys(VN_CATALOG.fx.kategori);
}
function textStyleKategoriOptions() {
  return Object.keys(VN_CATALOG.textStyle.kategori);
}

let babakRows = [];

function seedBabakDefault() {
  babakRows = VN_CATALOG.babakDefault.map((b, i) => ({
    id: uid(), index: i + 1, label: b.label, durasi: b.durasi, brief: "",
    camera: "Tidak ada", speedTab: "Regular", speedPilihan: "1.0x",
    filterKategori: "Original", filterPilihan: "Original (tanpa filter)", filterIntensity: 100,
    fxKategori: "Original", fxPilihan: "None",
    voiceEffect: "None",
    textStyleKategori: "Default",
    transisiTab: "Base", transisiPilihan: "None", transisiDurasi: 0.5,
    catatanAnimasi: ""
  }));
}

function renderBabakForm() {
  const wrap = document.getElementById("babak-list");
  wrap.innerHTML = babakRows.map((b, i) => babakRowHtml(b, i)).join("");
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
  </fieldset>`;
}

function readBabakFromDom() {
  document.querySelectorAll("#babak-list .babak").forEach(el => {
    const id = el.dataset.id;
    const row = babakRows.find(b => b.id === id);
    if (!row) return;
    el.querySelectorAll("[data-f]").forEach(input => {
      const f = input.dataset.f;
      let v = input.value;
      if (f === "durasi" || f === "filterIntensity" || f === "transisiDurasi") v = parseFloat(v) || 0;
      row[f] = v;
    });
  });
}

function onBabakInput(e) {
  const el = e.target.closest("[data-f]");
  if (!el) return;
  readBabakFromDom();
  const f = el.dataset.f;
  // re-render kalau field yang berubah mengubah opsi dependen (kategori -> pilihan)
  if (["filterKategori", "fxKategori", "speedTab", "transisiTab"].includes(f)) {
    const id = el.closest(".babak").dataset.id;
    const row = babakRows.find(b => b.id === id);
    if (f === "filterKategori") row.filterPilihan = (VN_CATALOG.filter.kategori[row.filterKategori]?.contoh || ["Original (tanpa filter)"])[0];
    if (f === "fxKategori") row.fxPilihan = (VN_CATALOG.fx.kategori[row.fxKategori]?.pilihan || ["None"])[0];
    if (f === "speedTab") row.speedPilihan = VN_CATALOG.speed.tabs[row.speedTab].pilihan[0];
    if (f === "transisiTab") row.transisiPilihan = VN_CATALOG.transisi.tabs[row.transisiTab].pilihan[0];
    renderBabakForm();
  }
}

function addBabak() {
  readBabakFromDom();
  babakRows.push({
    id: uid(), index: babakRows.length + 1, label: `Babak ${babakRows.length + 1}`, durasi: 5, brief: "",
    camera: "Tidak ada", speedTab: "Regular", speedPilihan: "1.0x",
    filterKategori: "Original", filterPilihan: "Original (tanpa filter)", filterIntensity: 100,
    fxKategori: "Original", fxPilihan: "None",
    voiceEffect: "None",
    textStyleKategori: "Default",
    transisiTab: "Base", transisiPilihan: "None", transisiDurasi: 0.5,
    catatanAnimasi: ""
  });
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
    catalog_sumber: VN_CATALOG.meta.sumber,
    babak: babakRows.map((b, i) => ({
      index: i + 1,
      label: b.label,
      durasi_detik: b.durasi,
      brief_kreatif: b.brief,
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
      catatan_animasi_kustom: b.catatanAnimasi || null
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
  lines.push("\n---\n");

  bp.babak.forEach((b, i) => {
    const t0 = t, t1 = t + b.durasi_detik;
    t = t1;
    lines.push(`## Babak ${i + 1} — ${b.label} (${fmtTs(t0)}–${fmtTs(t1)}, ${b.durasi_detik}s)`);
    if (b.brief_kreatif) lines.push(`\n**Ide kreatif:** ${b.brief_kreatif}`);
    lines.push("\n**Langkah eksekusi di VN:**");
    const steps = [];
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
    if (b.text_style)
      steps.push(`Tambah teks (trek T+) → panel gaya → kategori **"${b.text_style.kategori}"** → tulis narasi/caption babak ini.`);
    if (b.transisi_masuk)
      steps.push(`Di batas AWAL babak ini: tap titik sambung klip → tab **"${b.transisi_masuk.tab}"** → pilih **"${b.transisi_masuk.pilihan}"** → set durasi **${b.transisi_masuk.durasi_detik}s**${b.transisi_masuk.gating === "credit" ? " (⚠️ AI berbayar kredit — cek saldo dulu)" : ""}.`);
    if (b.catatan_animasi_kustom)
      steps.push(`Animasi kustom (Keyframe ◇): ${b.catatan_animasi_kustom} — set keyframe di awal babak, geser playhead ke akhir babak, ubah properti, VN interpolasi otomatis.`);
    if (steps.length === 0) steps.push("Tanpa style tambahan — pakai klip apa adanya sesuai brief kreatif di atas.");
    steps.forEach(s => lines.push(`- [ ] ${s}`));
    lines.push("");
  });

  lines.push("---\n");
  lines.push(`**Total durasi rencana:** ${fmtTs(t)} (${t.toFixed(1)}s) — cocokkan dengan \`total_textView\` di VN setelah semua klip disusun.`);
  return lines.join("\n");
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
}

function onGenerate(e) {
  e.preventDefault();
  readBabakFromDom();
  const meta = {
    proyek: document.getElementById("f-proyek").value.trim() || "Proyek Tanpa Nama",
    klien: document.getElementById("f-klien").value.trim(),
    rasio: document.getElementById("f-rasio").value,
    instruksiUmum: document.getElementById("f-instruksi").value.trim()
  };
  if (!babakRows.length) { alert("Tambahkan minimal 1 babak dulu."); return; }

  const bp = buildBlueprint(meta);
  const recipe = buildRecipe(meta, bp);
  showOutput(bp, recipe);

  const list = loadHistory();
  list.unshift({
    id: uid(), proyek: meta.proyek, klien: meta.klien, rasio: meta.rasio, instruksiUmum: meta.instruksiUmum,
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
    if (e.target.matches('textarea,[data-f="durasi"],[data-f="filterIntensity"]')) readBabakFromDom();
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
