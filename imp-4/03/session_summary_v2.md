# DeepDive Intelligence — Session Summary (2026-04-01, Part 2)

## Overview

This session focused on **3 major upgrades** to the DeepDive Intelligence search engine and data pipeline:

1. **RSS Feed Expansion** — From 3 feeds to 10 global + Indian sources
2. **Search Engine v2.0** — Multi-keyword tokenization, synonym mapping, and entity-priority scoring
3. **Search Engine v2.1** — Topic coherence filtering layer

---

## 1. RSS Feed Expansion

### Problem
The system only had 3 RSS feeds (BBC Business, NYT Business, Reuters Business). Users searching for specific topics like "Hormuz" or "UAE" couldn't find results because those articles weren't being ingested.

### Solution
Updated `.env` `RSS_FEEDS` from 3 to **10 sources**:

| Category | Feed |
|----------|------|
| 🌍 Global World | BBC World News |
| 🌍 Global World | NYT World |
| 🌍 Global World | Al Jazeera |
| 🌍 Global World | Reuters World |
| 💼 Global Business | Reuters Business |
| 💼 Global Business | BBC Business |
| 🇮🇳 India | The Hindu |
| 🇮🇳 India | Indian Express |
| 🇮🇳 India | Times of India |
| 🇮🇳 India | Livemint |

**File changed:** `.env` (line 10)

---

## 2. Search Engine v2.0 — Multi-Keyword & Synergy Scoring

### Problem
The `/event` search used a simple `LIKE '%full query%'` approach. Full sentences like "UAE wants to help US force Hormuz open" returned zero results because no article contained that exact string.

### Solution
Complete overhaul of the search logic in `api/routers/intelligence.py`:

### 2a. Query Tokenization
- Added `_tokenize_query()` function
- Strips punctuation, lowercases, removes stopwords
- Returns two lists: `base_kws` (user's words) and `syn_kws` (expanded synonyms)

### 2b. Stopwords → Low-Weight Words Split
**Before:** Words like "help", "want", "us", "force" were in `_STOPWORDS` (completely ignored)
**After:** Moved to `_LOW_WEIGHT_WORDS` — still searched, but contribute only +0.5 instead of +10.0

### 2c. Synonym Mapping (Entity-Only)
Added `_SYNONYMS` dictionary:
```
"uae" → ["united", "arab", "emirates"]
"us"  → ["united", "states", "america", "usa"]
"uk"  → ["united", "kingdom", "britain"]
"hormuz" → ["strait"]
"eu"  → ["european", "union"]
"un"  → ["united", "nations"]
```
**Critical rule:** Synonyms are expanded in SQL queries ONLY against `Node.entity`, NOT against description or topic (prevents false positives).

### 2d. Entity Priority Scoring
New scoring weights:

| Match Type | Regular Word | Low-Weight Word |
|------------|:---:|:---:|
| Entity hit | +10.0 | +0.5 |
| Topic hit | +5.0 | +0.5 |
| Description hit | +2.0 | +0.2 |
| Exact full query in entity | +30.0 | — |
| Full query substring in entity | +15.0 | — |

### 2e. Synergy Multiplier
If a result matches multiple distinct keywords from the query: `score += matched_kws * 2.0`

### 2f. Minimum Strong Match Filter
If `strong_matches == 0` (only generic words matched): `score *= 0.1` (90% penalty)

---

## 3. Search Engine v2.1 — Topic Coherence Filtering

### Problem
Even with v2.0, results could still be noisy. A query about "Hormuz" might return articles that only mention "help" or "force" in their description — topically irrelevant.

### Solution
Added a coherence filtering layer ON TOP of existing scoring:

### 3a. Core Keyword Extraction
Added `_extract_core_keywords()` function:
- Filters base keywords to find entities/locations/topics (non-low-weight, 3+ chars)
- Example: "UAE wants to help US force Hormuz open" → `["uae", "hormuz"]`
- Has 3-tier fallback: long core words → all non-low-weight → all base keywords

### 3b. Per-Result Core Match Tracking
During the scoring loop, each keyword now tracks WHERE it matched:
- `core_in_entity` — core keyword found in entity field
- `core_in_topic` — core keyword found in cluster topic
- `core_in_desc_only` — core keyword found ONLY in description (not entity/topic)

### 3c. Hard Filter (Most Important)
```python
if total_core_hits == 0:
    continue  # Result is REMOVED — doesn't belong to the query's topic
```
Results that don't match ANY core keyword are completely excluded.

### 3d. Description-Only Penalty
```python
if core_in_entity == 0 and core_in_topic == 0 and core_in_desc_only > 0:
    score *= 0.15  # 85% penalty — weak contextual match
```
If core keywords only appear in the article description (not entity/topic), the result is heavily penalized.

### 3e. Coherence Ratio Boost
```python
coherence_ratio = total_core_hits / len(core_kws)
score += coherence_ratio * 10.0  # Up to +10 for perfect coherence
```
Results matching MORE core keywords from the query get boosted proportionally.

### 3f. Entity Dominance Enforcement
```python
if core_in_entity > 0:
    score += core_in_entity * 8.0
```
Results with core keywords in their entity field ALWAYS outrank generic matches.

---

## 4. Documentation Updates

### `imp-4/03/26.md` (Implementation Log)
- Added **Phase 4: API Search Upgrade (v2.0) & RSS Expansion** section
- Documented all 6 algorithmic improvements
- Updated Next Steps

### `project_analysis_report.md` (Analysis Report)
- Updated API Layer section (4.10) — reflects new search capabilities
- Added "Strengths (Upgraded)" section with 3 new items
- Updated Issues tables — marked 3 issues as ✅ Fixed:
  - Git initialized
  - CORS configured
  - Deprecated APIs fixed

---

## 5. Git Commits

| Commit | Message |
|--------|---------|
| `6126110` | `feat: upgrade search engine v2.0 - add entity synergy, synonym mapping, noise filters, and expand RSS feeds` |
| `4b10a5a` | `feat: add topic coherence filtering layer to search engine v2.1` |

Both commits were pushed to `main` on GitHub.

---

## 6. Files Modified

| File | Change |
|------|--------|
| `.env` | Expanded RSS_FEEDS from 3 → 10 sources |
| `api/routers/intelligence.py` | Search engine v2.0 + v2.1 (tokenization, synonyms, coherence) |
| `imp-4/03/26.md` | Added Phase 4 documentation |
| `project_analysis_report.md` | Updated API section and issue tracker |

---

## 7. Current System State

| Component | Status |
|-----------|--------|
| Backend (uvicorn:8000) | ✅ Running |
| Frontend (vite:5173) | ✅ Running |
| Search Engine | v2.1 (coherence filtering active) |
| RSS Feeds | 10 sources configured |
| Git | All changes committed and pushed |
