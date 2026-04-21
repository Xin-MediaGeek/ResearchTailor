# Design: Token-Aware Chunking Config + Robustness Fixes

**Date:** 2026-04-21  
**Scope:** `config.yaml`, `scripts/extract_modules.py`, `scripts/extract_text.py`, `scripts/parse_candidates.py`, `app.py`  
**Approach:** Method B — Smart token budget, config-driven chunking, targeted robustness fixes

---

## 1. config.yaml — New `chunking` Block

Add a top-level `chunking:` section to `config.yaml`:

```yaml
chunking:
  max_tokens: 12000        # token budget per chunk (estimated)
  overlap_tokens: 500      # overlap between adjacent chunks (in tokens)
  chars_per_token: 2.5     # estimation ratio (2.5 for English-dominant; 2.0 for mixed CN/EN)
  min_paragraph_tokens: 50 # paragraphs shorter than this merge with the next one
```

**Rationale:**
- DeepSeek-chat has a 64K context window; extraction prompt consumes ~1–2K; 12K leaves ample room per chunk while keeping API calls efficient.
- `chars_per_token` is exposed as a user-tunable parameter rather than using `tiktoken` (avoids adding a dependency; estimation error <10% for academic English).
- Users switching to `deepseek-reasoner` can safely raise `max_tokens` to ~20000.

---

## 2. `scripts/extract_modules.py` — Rewritten `split_text_into_chunks()`

### 2.1 New Helper: `estimate_tokens()`

```python
def estimate_tokens(text: str, chars_per_token: float) -> int:
    return int(len(text) / chars_per_token)
```

### 2.2 New Helper: `split_into_paragraphs()`

Splits raw text into a list of paragraph strings using a four-level boundary hierarchy:

1. `\n\n` — standard blank line (dominant in English papers)
2. `\n　` or `\n\t` — CJK indent-style paragraph start
3. `。\n` or `.\n` — sentence-ending newline (degraded PDF extraction)
4. Hard character-limit fallback — if a single "paragraph" still exceeds `max_tokens`, force-split it

### 2.3 New Core: `pack_paragraphs_into_chunks()`

Greedy bin-packing algorithm:
- Accumulate paragraphs into the current chunk until adding the next paragraph would exceed `max_tokens`
- At that point, close the chunk and start a new one
- Prepend the new chunk with the tail paragraphs of the previous chunk until their total reaches `overlap_tokens` (overlap is paragraph-granular, not character-slice)
- Paragraphs smaller than `min_paragraph_tokens` are merged with the following paragraph before packing

### 2.4 Updated Signature

```python
def split_text_into_chunks(full_text: str, chunking_cfg: dict) -> list[str]:
    ...
```

Caller in `extract_modules.py` passes `config["chunking"]` — one-line change at the call site.

### 2.5 Comparison with Current Implementation

| Dimension | Before | After |
|-----------|--------|-------|
| Unit | characters | estimated tokens |
| Boundary detection | `\n\n` only | 4-level hierarchy, CJK-aware |
| Overlap unit | characters | tokens (paragraph-granular) |
| Parameter source | function default values | `config.yaml` |

---

## 3. Robustness Fixes

### 3.1 API Retry with Exponential Backoff (`extract_modules.py`)

Wrap `call_model()` with retry logic:
- Max 3 attempts
- Delays: 2s → 4s → 8s
- On final failure: log error and **skip the paper** (continue processing remaining papers rather than crashing)
- Current behavior: unhandled exception aborts the entire run

### 3.2 Empty Text Guard (`extract_text.py` + `extract_modules.py`)

**`extract_text.py`:** After extraction, if `full_text` is empty or whitespace-only, write `{"error": "empty_text", "full_text": ""}` to the JSON output and print a warning.

**`extract_modules.py`:** On loading a JSON file, check for the `error` field or an empty `full_text` before calling the API. If found, skip and print a clear reason message.

Current behavior: empty prompt is sent to DeepSeek, wasting API quota and potentially producing garbage output.

### 3.3 Failure Sentinel Files (`extract_modules.py`)

On extraction failure (after retries exhausted), write `<paper_id>_extraction_FAILED.md` containing:
- Error message and traceback
- Timestamp
- Chunk index that failed (if multi-chunk)

`format_consolidated.py` will detect `_FAILED.md` files, print a warning listing them, and skip them without aborting the consolidation.

Current behavior: failed papers are silently skipped; Stage 2c cannot distinguish "not yet processed" from "processing failed."

### 3.4 `parse_candidates.py` — Regex Robustness

Extend the candidate header regex to match additional formats Claude may produce:

| Format | Example |
|--------|---------|
| Current: bold bracket | `**Candidate [1]**` |
| Current: bold plain | `**Candidate 1**` |
| New: Markdown heading | `## Candidate 1` |
| New: colon suffix | `Candidate 1:` |

On zero candidates parsed: print a warning directing the user to inspect the raw file, rather than silently writing zero output files.

### 3.5 `config.yaml` Load Validation (`app.py`)

Replace bare dict-key access with `config.get()` calls with safe defaults throughout `app.py`. For mandatory fields (`deepseek.api_key`, `deepseek.base_url`, `deepseek.model`), perform an explicit presence check at startup and display a red Streamlit error banner if any are missing — instead of crashing with a `KeyError`.

---

## 4. Files Changed

| File | Change Type | Summary |
|------|-------------|---------|
| `config.yaml` | Addition | New `chunking:` block |
| `scripts/extract_modules.py` | Rewrite (chunking fn) + addition (retry, sentinel) | Token-aware chunking, API retry, sentinel file |
| `scripts/extract_text.py` | Addition | Empty-text guard |
| `scripts/parse_candidates.py` | Fix | Regex extension, zero-match warning |
| `scripts/format_consolidated.py` | Fix | Detect and skip `_FAILED.md` sentinel files with warning |
| `app.py` | Fix | Config validation with user-facing error messages |

---

## 5. Out of Scope

- Page-aware chunking (deferred to a future iteration)
- `tiktoken` integration (estimation is sufficient; avoids dependency)
- Per-model parameter presets in the UI
- Incremental re-extraction of modified PDFs
