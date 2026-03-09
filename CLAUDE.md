# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a data extraction and analysis pipeline for Roberto Bolaño's novel **荒野侦探 (The Savage Detectives)** (Chinese translation). It uses PaddleOCR to extract text from a PDF, then calls the Claude API to extract structured literary entities (characters, locations, events, relationships, quotes, testimonies) into a SQLite database.

## Running the Scripts

All scripts use absolute Windows paths and are run from the repo root:

```bash
# 1. OCR the PDF → data/ocr_output.txt  (requires PaddleOCR + PyMuPDF)
python scripts/run_ocr.py

# 2. Extract entities from OCR text → savage_detectives.db  (resumable)
python scripts/extract.py

# 3. Extract Part 2 testimony sections specifically
python scripts/extract_testimonies.py

# 4. Find and merge duplicate character entries (fuzzy match + Claude confirm)
python scripts/dedup_narrators.py

# 5. Generate CSV for human review of suspicious duplicate pairs
python scripts/gen_review_csv.py
# → edit review/review_pairs.csv, fill verdict column

# 6. Execute merges from dedup_report.json (handles chains & canonical conflicts)
python scripts/run_merges2.py

# Refresh CONTEXT.md with current DB schema and sample data
python dump_context.py
```

## Architecture

**Pipeline flow:**
```
PDF → run_ocr.py (PaddleOCR) → data/ocr_output.txt
                                       ↓
                              extract.py (Claude API, chunked 4000 chars)
                                       ↓
                         data/savage_detectives.db (SQLite)
                                       ↓
              extract_testimonies.py  (targeted Part 2 pass)
                                       ↓
                dedup_narrators.py → review/dedup_report.json
                                       ↓
                           run_merges2.py (executes merges)
```

**Key files:**
- `data/savage_detectives.db` — the SQLite database (primary artifact)
- `data/ocr_output.txt` — OCR output with `=== Page N ===` markers between pages
- `logs/extraction_progress.json` — tracks completed chunks for resumable extraction
- `review/dedup_report.json` — Claude-confirmed merge plan consumed by `run_merges2.py`
- `review/review_pairs.csv` — human-review sheet (fill `verdict` column: SAME/DIFFERENT/UNSURE)
- `CONTEXT.md` — DB schema + sample data snapshot (regenerate with `dump_context.py`)

**Database schema** — see `CONTEXT.md` for full schema. Key quirks:
- `quotes.event_id` is always NULL; quotes link to characters only
- `testimonies.interview_year` is unreliable (LLM often defaults to 1976)
- `locations.lat/lng` are mostly NULL; geocoding not yet done
- `event_characters` is the join table linking events ↔ characters with an optional `role`

## Claude API Usage

Scripts use `anthropic` Python SDK with `claude-haiku-4-5`. The model is called to:
- Extract characters/locations/events/relationships/quotes from OCR chunks (`extract.py`)
- Summarize testimony sections and extract metadata (`extract_testimonies.py`)
- Confirm whether fuzzy-matched character pairs are duplicates (`dedup_narrators.py`)

All prompts request plain JSON responses (no markdown fences). Scripts strip accidental fences with `re.sub(r'^```[a-z]*\n?', '', raw)` before `json.loads()`.

## Data Notes

- All text is UTF-8; Chinese character names must be preserved as-is from the OCR text
- The novel has three parts; Part 2 ("第二部 荒野侦探") contains the testimony monologue sections, detected by regex for `Chinese name, location, 19xxYear` header pattern
- Main protagonists: Arturo Belano (阿图罗·贝拉诺) and Ulises Lima (乌里塞斯·利马)
- Character deduplication is an ongoing issue: the LLM extracts short-form names (e.g. "贝拉诺", "利马") as separate entries from full names; `gen_review_csv.py` + `run_merges2.py` handle this
- `rapidfuzz` is required for `gen_review_csv.py`
