---
id: "_meta/tag-taxonomy"
title: "ogis-vault Tag Taxonomy"
domain: "_meta"
status: "stable"
corpus: false
category: "meta"
tags: ["taxonomy", "tags", "convention", "controlled-vocabulary"]
keywords: ["tag taxonomy", "controlled vocabulary", "canonical tags"]
summary: >
  Controlled tag vocabulary for ogis-vault. Notes may only use tags listed
  here (or add a new one here first).
related: ["_meta/frontmatter-schema", "README"]
last_updated: "2026-08-29"
---

# ogis-vault Tag Taxonomy

Tags are a **controlled vocabulary**. Use the canonical tag; do not invent
synonyms.

## Cross-domain (structural) tags

| Tag | Meaning |
|-----|---------|
| `index` / `moc` | A map-of-content / navigation note (`corpus:false`). |
| `convention` | A vault rule/standard. |
| `rag` | About the RAG/embedding pipeline itself. |

## Cross-domain (scrape-* content) tags

Dipakai lintas SEMUA domain `scrape-<nama-profil>` — sama persis konvensi
yang sudah disepakati di vault Pi4B (`_meta/scrape-domain-convention.md`,
`~/wiki-docs/_meta/tag-taxonomy.md`), supaya istilah konsisten kalau nanti
ada kebutuhan bandingkan lintas kedua vault:

| Canonical | Use for |
|-----------|---------|
| `scrape` | apa pun hasil pengambilan data via browser-automation |
| `viral-analyzer` | terkait pipeline `viral_analyzer` |
| `social-media-content` | konten/metrik dari platform media sosial |
| `browser-profile` | catatan yg spesifik ke satu profil browser |

## Domain-specific tags

Tambah bagian baru `## Domain: scrape-<nama>` di sini begitu domain nyata
dibuat, ikut pola `~/wiki-docs/_meta/tag-taxonomy.md` di Pi4B (per-domain
tag list + definisi singkat).
