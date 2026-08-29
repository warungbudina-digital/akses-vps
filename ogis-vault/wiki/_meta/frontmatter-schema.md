---
id: "_meta/frontmatter-schema"
title: "ogis-vault Frontmatter Schema"
domain: "_meta"
status: "stable"
corpus: false
category: "meta"
tags: ["schema", "frontmatter", "metadata", "convention"]
keywords: ["frontmatter fields", "yaml metadata", "note schema", "vault convention"]
summary: >
  Required/optional YAML frontmatter fields for every note in ogis-vault.
  Identik aturannya dgn vault Pi4B (~/wiki-docs/_meta/frontmatter-schema.md)
  — disalin apa adanya krn pola sudah teruji, cuma vault-nya fisik terpisah
  (ogis-vault khusus domain scrape-<nama-profil-browser>, bukan gabung Pi4B).
related: ["README", "_meta/tag-taxonomy"]
last_updated: "2026-08-29"
---

# ogis-vault Frontmatter Schema

Every `.md` note MUST start with a YAML frontmatter block using these fields.
Uniformity is mandatory — the RAG pipeline (`ingest.py`/`ingest-append.py`)
treats these as per-chunk metadata.

## Required fields

| Field | Type | Rule |
|-------|------|------|
| `id` | string | **Globally unique**, form `"<domain>/<slug>"` (e.g. `"scrape-tiktok/00-overview"`). |
| `title` | string | Human title of the note. |
| `slug` | string | File slug within the domain (matches filename without `.md`). |
| `domain` | string | The domain folder name — HARUS `scrape-<nama-profil-browser>` (satu profil browser = satu domain). |
| `status` | enum | `draft` \| `stable` \| `deprecated`. |
| `corpus` | bool | `true` = embed this note; `false` = navigation/meta, exclude from embeddings. |
| `category` | string | One coarse bucket within the domain. |
| `tags` | list | From the controlled vocabulary in `_meta/tag-taxonomy.md`. |
| `keywords` | list | Free-text synonyms/search terms to boost retrieval (not controlled). |
| `summary` | string | 1–3 sentences. Used as a retrieval preview and citation blurb. |
| `last_updated` | date | `YYYY-MM-DD`. Re-embed (`ingest-append.py <domain>`) when this changes. |

## Optional fields

| Field | Type | Rule |
|-------|------|------|
| `source_urls` | list | Canonical upstream URLs (halaman yg di-scrape) untuk citation/verification. |
| `related` | list | `id`s of related notes. |
| `audience` | list | e.g. `["ai-rag","user"]`. |
| `service` | string | `"ogis-browser-scraper"` untuk semua domain `scrape-*`. |

## Rules

1. **`id` never changes** once assigned.
2. **`corpus: false`** for `README.md`, every `_index.md`, dan semua isi `_meta/`.
3. **Tags must exist in `_meta/tag-taxonomy.md`.** Tambah di situ dulu kalau perlu tag baru.
4. **Body must be self-contained** — satu chunk (per-H2) bisa diambil tanpa tetangganya.

## Minimal template

```yaml
---
id: "<domain>/<slug>"
title: "..."
slug: "<slug>"
domain: "<domain>"
status: "draft"
corpus: true
category: "..."
tags: ["...", "..."]
keywords: ["...", "..."]
source_urls: ["https://..."]
summary: >
  One to three sentences describing the note for retrieval.
related: []
audience: ["ai-rag", "user"]
service: "ogis-browser-scraper"
last_updated: "YYYY-MM-DD"
---
```
