---
id: "scrape-example/_index"
title: "TEMPLATE — Domain Hasil Scrape (contoh, bukan pengetahuan nyata)"
slug: "_index"
domain: "scrape-example"
status: "draft"
corpus: false
category: "meta"
tags: ["index", "moc", "convention", "scrape"]
keywords: ["template domain scrape", "contoh catatan scrape", "placeholder"]
summary: >
  Placeholder/template domain di ogis-vault — TIDAK berisi pengetahuan
  nyata. Salin pola di sini saat domain scrape-<nama-profil> sesungguhnya
  dibuat. Lihat _meta/frontmatter-schema.md untuk aturan lengkap.
related: ["_meta/frontmatter-schema", "_meta/tag-taxonomy"]
last_updated: "2026-08-29"
---

# TEMPLATE — Domain Hasil Scrape (ogis-vault)

⚠️ **Ini template, bukan domain nyata.** Jangan jalankan
`ingest-append.py scrape-example` dan berharap ada pengetahuan berguna.

## Cara pakai

1. `cp -r ~/ogis-vault/wiki/scrape-example ~/ogis-vault/wiki/scrape-<nama-profil>`
2. Ganti `domain: "scrape-example"` → `domain: "scrape-<nama-profil>"` di
   SEMUA file (termasuk file ini).
3. Ganti `corpus: false` → `corpus: true` di catatan isi (00-template.md),
   TETAP `corpus: false` untuk `_index.md` ini.
4. `python3 ~/ogis-vault/ingest-append.py scrape-<nama-profil>`

## Catatan dalam domain ini (template)

| Catatan | Kategori |
|---------|----------|
| `00-template.md` | contoh 1 catatan isi |
