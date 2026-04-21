# Token-Aware Chunking Config + Robustness Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make chunking token-aware and config-driven, then fix five robustness issues across the pipeline scripts.

**Architecture:** Add a `chunking:` block to `config.yaml`; replace the character-based `split_text_into_chunks()` in `extract_modules.py` with a token-estimated, paragraph-hierarchy function; wrap `call_model()` with exponential-backoff retry and sentinel-file-on-failure; add guards for empty PDFs, extended candidate-header regex, and Streamlit config validation.

**Tech Stack:** Python 3.10+, PyYAML, pytest (dev), existing openai/pdfplumber/streamlit stack

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `config.yaml` | Modify | Add `chunking:` block |
| `scripts/extract_modules.py` | Modify | Rewrite chunking fns, add retry + sentinel |
| `scripts/extract_text.py` | Modify | Write `error` field on empty extraction |
| `scripts/parse_candidates.py` | Modify | Extend regex, zero-match warning |
| `scripts/format_consolidated.py` | Modify | Detect and warn about `_FAILED.md` files |
| `app.py` | Modify | Config validation with Streamlit error banner |
| `tests/test_chunking.py` | Create | Unit tests for all chunking helpers |
| `tests/test_parse_candidates.py` | Create | Unit tests for extended candidate regex |

---

## Task 1: Add `chunking:` block to config.yaml

**Files:**
- Modify: `config.yaml`

- [ ] **Step 1: Add chunking block at end of config.yaml**

Open `config.yaml` and append after the `filters:` block:

```yaml
# Chunking settings for long-paper processing
chunking:
  max_tokens: 12000         # token budget per chunk (estimated)
  overlap_tokens: 500       # overlap carried from previous chunk (in tokens)
  chars_per_token: 2.5      # estimation ratio (2.5 for English; 2.0 for CN/EN mixed)
  min_paragraph_tokens: 50  # paragraphs shorter than this merge with the next
```

- [ ] **Step 2: Verify the file loads correctly**

```bash
cd e:/Xin_Tool/ResearchTailor
python -c "import yaml; c = yaml.safe_load(open('config.yaml')); print(c['chunking'])"
```

Expected output:
```
{'max_tokens': 12000, 'overlap_tokens': 500, 'chars_per_token': 2.5, 'min_paragraph_tokens': 50}
```

- [ ] **Step 3: Commit**

```bash
git add config.yaml
git commit -m "config: add chunking block with token-budget parameters"
```

---

## Task 2: Token-aware chunking functions (TDD)

**Files:**
- Create: `tests/test_chunking.py`
- Modify: `scripts/extract_modules.py` (lines 62–88, plus call site at line 259)

- [ ] **Step 1: Create tests/test_chunking.py with failing tests**

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from extract_modules import (
    estimate_tokens,
    split_into_paragraphs,
    pack_paragraphs_into_chunks,
    split_text_into_chunks,
)

DEFAULT_CFG = {
    "max_tokens": 100,
    "overlap_tokens": 20,
    "chars_per_token": 2.5,
    "min_paragraph_tokens": 5,
}


class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("", 2.5) == 0

    def test_basic(self):
        assert estimate_tokens("a" * 250, 2.5) == 100

    def test_fractional_rounds_down(self):
        assert estimate_tokens("a" * 251, 2.5) == 100


class TestSplitIntoParagraphs:
    def test_double_newline_splits(self):
        text = "para one\n\npara two\n\npara three"
        result = split_into_paragraphs(text, max_tokens=1000, chars_per_token=2.5)
        assert result == ["para one", "para two", "para three"]

    def test_empty_paragraphs_dropped(self):
        text = "a\n\n\n\nb"
        result = split_into_paragraphs(text, max_tokens=1000, chars_per_token=2.5)
        assert result == ["a", "b"]

    def test_oversized_paragraph_force_split(self):
        long_para = "x" * 600  # 600 chars / 2.5 = 240 tokens > max_tokens=100
        result = split_into_paragraphs(long_para, max_tokens=100, chars_per_token=2.5)
        assert len(result) > 1
        for chunk in result:
            assert estimate_tokens(chunk, 2.5) <= 100

    def test_single_paragraph_under_limit(self):
        text = "short paragraph"
        result = split_into_paragraphs(text, max_tokens=1000, chars_per_token=2.5)
        assert result == ["short paragraph"]


class TestPackParagraphsIntoChunks:
    def test_single_chunk_when_fits(self):
        paras = ["hello world"] * 3
        result = pack_paragraphs_into_chunks(paras, max_tokens=1000, overlap_tokens=10,
                                             chars_per_token=2.5, min_paragraph_tokens=1)
        assert len(result) == 1

    def test_splits_when_overflow(self):
        # Each para ~ 40 tokens (100 chars / 2.5), max=100 → 2 paras per chunk
        paras = ["a" * 100] * 6
        result = pack_paragraphs_into_chunks(paras, max_tokens=100, overlap_tokens=10,
                                             chars_per_token=2.5, min_paragraph_tokens=1)
        assert len(result) >= 3

    def test_overlap_carries_forward(self):
        # Each para: "alpha "*10 = 60 chars = 24 tokens. max=50 fits 2 (48 tok).
        # overlap=25 carries the last para (24 tok) of the closed chunk forward.
        paras = ["alpha " * 10, "beta " * 10, "gamma " * 10, "delta " * 10]
        result = pack_paragraphs_into_chunks(paras, max_tokens=50, overlap_tokens=25,
                                             chars_per_token=2.5, min_paragraph_tokens=1)
        assert len(result) >= 2
        # The last paragraph of chunk 1 should appear at the start of chunk 2
        last_of_chunk1 = result[0].split("\n\n")[-1]
        assert last_of_chunk1 in result[1]

    def test_small_paragraphs_merge(self):
        # 4 tiny paras (< min_paragraph_tokens=5) should merge together
        cfg = {**DEFAULT_CFG, "min_paragraph_tokens": 5}
        paras = ["hi"] * 4
        result = pack_paragraphs_into_chunks(
            paras, max_tokens=cfg["max_tokens"], overlap_tokens=cfg["overlap_tokens"],
            chars_per_token=cfg["chars_per_token"], min_paragraph_tokens=cfg["min_paragraph_tokens"]
        )
        assert len(result) == 1

    def test_empty_input(self):
        result = pack_paragraphs_into_chunks([], max_tokens=100, overlap_tokens=10,
                                             chars_per_token=2.5, min_paragraph_tokens=5)
        assert result == []


class TestSplitTextIntoChunks:
    def test_short_text_single_chunk(self):
        text = "This is a short paper."
        result = split_text_into_chunks(text, DEFAULT_CFG)
        assert result == [text]

    def test_long_text_multiple_chunks(self):
        para = "word " * 60 + "\n\n"  # ~120 tokens per para at chars_per_token=2.5
        text = para * 5
        result = split_text_into_chunks(text, DEFAULT_CFG)
        assert len(result) > 1

    def test_chunks_non_empty(self):
        text = "\n\n".join(["paragraph " * 30] * 10)
        result = split_text_into_chunks(text, DEFAULT_CFG)
        assert all(c.strip() for c in result)

    def test_accepts_chunking_cfg_dict(self):
        cfg = {"max_tokens": 50, "overlap_tokens": 10, "chars_per_token": 2.5, "min_paragraph_tokens": 5}
        text = "a" * 500
        result = split_text_into_chunks(text, cfg)
        assert isinstance(result, list)
```

- [ ] **Step 2: Run tests to verify they all fail**

```bash
cd e:/Xin_Tool/ResearchTailor
python -m pytest tests/test_chunking.py -v 2>&1 | head -40
```

Expected: `ImportError` or multiple `FAILED` — the new functions don't exist yet.

- [ ] **Step 3: Replace chunking functions in extract_modules.py**

Replace lines 62–88 (the old `split_text_into_chunks`) with the following four functions. Also add `import re` at the top of the file (after `import json`):

```python
import re
```

Replace the old `split_text_into_chunks` function block with:

```python
def estimate_tokens(text: str, chars_per_token: float) -> int:
    return int(len(text) / chars_per_token)


def split_into_paragraphs(text: str, max_tokens: int, chars_per_token: float) -> list[str]:
    """Split text into paragraph strings using a 4-level boundary hierarchy."""
    max_chars = int(max_tokens * chars_per_token)

    # Level 1: split on blank lines (handles \n\n, \n \n, \n\t\n)
    raw_paras = re.split(r'\n[ \t]*\n', text)

    paragraphs = []
    for para in raw_paras:
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_chars:
            paragraphs.append(para)
        else:
            # Level 2/3: split on sentence-ending newlines (。\n or .\n)
            sub_paras = re.split(r'(?<=[。.])\n', para)
            for sub in sub_paras:
                sub = sub.strip()
                if not sub:
                    continue
                if len(sub) <= max_chars:
                    paragraphs.append(sub)
                else:
                    # Level 4: force-split at character limit
                    while sub:
                        paragraphs.append(sub[:max_chars])
                        sub = sub[max_chars:]

    return paragraphs


def pack_paragraphs_into_chunks(
    paragraphs: list[str],
    max_tokens: int,
    overlap_tokens: int,
    chars_per_token: float,
    min_paragraph_tokens: int,
) -> list[str]:
    """Greedily pack paragraphs into token-bounded chunks with overlap."""
    if not paragraphs:
        return []

    # Merge paragraphs that are below min_paragraph_tokens into the next one
    merged: list[str] = []
    buf = ""
    for p in paragraphs:
        if buf and estimate_tokens(p, chars_per_token) < min_paragraph_tokens:
            buf = buf + "\n\n" + p
        else:
            if buf:
                merged.append(buf)
            buf = p
    if buf:
        merged.append(buf)

    chunks: list[str] = []
    current_paras: list[str] = []
    current_tokens = 0

    for para in merged:
        para_tok = estimate_tokens(para, chars_per_token)
        if current_tokens + para_tok > max_tokens and current_paras:
            chunks.append("\n\n".join(current_paras))
            # Build overlap from the tail of the closed chunk
            overlap_paras: list[str] = []
            overlap_tok = 0
            for p in reversed(current_paras):
                t = estimate_tokens(p, chars_per_token)
                if overlap_tok + t <= overlap_tokens:
                    overlap_paras.insert(0, p)
                    overlap_tok += t
                else:
                    break
            current_paras = overlap_paras
            current_tokens = overlap_tok
        current_paras.append(para)
        current_tokens += para_tok

    if current_paras:
        chunks.append("\n\n".join(current_paras))

    return chunks


def split_text_into_chunks(full_text: str, chunking_cfg: dict) -> list[str]:
    """Split full paper text into overlapping token-bounded chunks."""
    max_tokens = chunking_cfg["max_tokens"]
    overlap_tokens = chunking_cfg["overlap_tokens"]
    chars_per_token = chunking_cfg["chars_per_token"]
    min_paragraph_tokens = chunking_cfg["min_paragraph_tokens"]

    if estimate_tokens(full_text, chars_per_token) <= max_tokens:
        return [full_text]

    paragraphs = split_into_paragraphs(full_text, max_tokens, chars_per_token)
    return pack_paragraphs_into_chunks(
        paragraphs, max_tokens, overlap_tokens, chars_per_token, min_paragraph_tokens
    )
```

- [ ] **Step 4: Update the call site in extract_modules.py main()**

Find (around line 259 of the original):
```python
            text_chunks = split_text_into_chunks(full_text)
```

Replace with:
```python
            text_chunks = split_text_into_chunks(full_text, config["chunking"])
```

Also update `load_config()` to provide chunking defaults if the block is absent (safety net for users who haven't updated their config.yaml yet):

Find `load_config()` in `extract_modules.py`:
```python
def load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
```

Replace with:
```python
def load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    config.setdefault("chunking", {
        "max_tokens": 12000,
        "overlap_tokens": 500,
        "chars_per_token": 2.5,
        "min_paragraph_tokens": 50,
    })
    return config
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd e:/Xin_Tool/ResearchTailor
python -m pytest tests/test_chunking.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add scripts/extract_modules.py tests/test_chunking.py
git commit -m "feat: token-aware chunking with paragraph hierarchy and config-driven parameters"
```

---

## Task 3: API retry + sentinel file on failure

**Files:**
- Modify: `scripts/extract_modules.py`

- [ ] **Step 1: Add `from datetime import datetime` import**

At the top of `extract_modules.py`, after `import time`, add:

```python
from datetime import datetime
```

- [ ] **Step 2: Replace `call_model()` with retry wrapper**

Find the existing `call_model()` function:

```python
def call_model(client: OpenAI, ds_config: dict, user_prompt: str) -> str:
    request_args = {
        "model": ds_config["model"],
        "max_tokens": ds_config["max_tokens"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]
    }

    # deepseek-reasoner does not support temperature in the same way as deepseek-chat.
    if ds_config["model"] != "deepseek-reasoner":
        request_args["temperature"] = ds_config["temperature"]

    response = client.chat.completions.create(**request_args)
    return response.choices[0].message.content or ""
```

Replace with:

```python
def call_model(client: OpenAI, ds_config: dict, user_prompt: str) -> str:
    request_args = {
        "model": ds_config["model"],
        "max_tokens": ds_config["max_tokens"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]
    }

    # deepseek-reasoner does not support temperature in the same way as deepseek-chat.
    if ds_config["model"] != "deepseek-reasoner":
        request_args["temperature"] = ds_config["temperature"]

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(**request_args)
            return response.choices[0].message.content or ""
        except Exception as e:
            last_exc = e
            wait = 2 ** (attempt + 1)
            print(f"    [retry] API error (attempt {attempt + 1}/3): {e}. Retrying in {wait}s...")
            time.sleep(wait)

    raise last_exc  # type: ignore[misc]
```

- [ ] **Step 3: Write sentinel file in the except block of main()**

Find the existing `except Exception as e:` block in `main()`:

```python
        except Exception as e:
            errors.append((paper_id, str(e)))
            print(f"  [err]  {paper_id}: {e}")
```

Replace with:

```python
        except Exception as e:
            errors.append((paper_id, str(e)))
            print(f"  [err]  {paper_id}: {e}")
            failed_path = output_dir / f"{paper_id}_extraction_FAILED.md"
            failed_path.write_text(
                f"# Extraction Failed: {paper_id}\n\n"
                f"**Error:** {e}\n\n"
                f"**Timestamp:** {datetime.now().isoformat()}\n",
                encoding="utf-8",
            )
```

- [ ] **Step 4: Manual smoke-test (no network needed)**

Verify the retry logic compiles and the sentinel path is correct:

```bash
cd e:/Xin_Tool/ResearchTailor
python -c "from scripts.extract_modules import call_model; print('import ok')"
```

Expected: `import ok`

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_modules.py
git commit -m "feat: add exponential-backoff retry to call_model and sentinel file on extraction failure"
```

---

## Task 4: Empty-text guard in extract_text.py

**Files:**
- Modify: `scripts/extract_text.py`

- [ ] **Step 1: Add empty-text check in `extract_pdf_text()`**

Find:
```python
def extract_pdf_text(pdf_path: Path) -> dict:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            pages.append({"page": i + 1, "text": text.strip()})
    full_text = "\n\n".join(p["text"] for p in pages if p["text"])
    return {
        "paper_id": pdf_path.stem,
        "filename": pdf_path.name,
        "page_count": len(pages),
        "full_text": full_text,
        "pages": pages
    }
```

Replace with:

```python
def extract_pdf_text(pdf_path: Path) -> dict:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            pages.append({"page": i + 1, "text": text.strip()})
    full_text = "\n\n".join(p["text"] for p in pages if p["text"])
    result = {
        "paper_id": pdf_path.stem,
        "filename": pdf_path.name,
        "page_count": len(pages),
        "full_text": full_text,
        "pages": pages,
    }
    if not full_text.strip():
        result["error"] = "empty_text"
    return result
```

- [ ] **Step 2: Add warning print in main() when error field present**

Find in `main()`:
```python
        try:
            data = extract_pdf_text(pdf_path)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"  [ok]   {pdf_path.name} -> {out_path.name}")
```

Replace with:

```python
        try:
            data = extract_pdf_text(pdf_path)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if data.get("error") == "empty_text":
                print(f"  [warn] {pdf_path.name}: no text extracted (possibly a scanned/image PDF). JSON saved.")
            else:
                print(f"  [ok]   {pdf_path.name} -> {out_path.name}")
```

- [ ] **Step 3: Verify extract_modules.py already handles the empty case**

`extract_modules.py` already has at line ~255:
```python
full_text = data.get("full_text", "")
if not full_text.strip():
    print(f"  [warn] {paper_id}: empty full text, skipping.")
    continue
```

This check covers the `error: empty_text` case automatically. No additional change needed in `extract_modules.py`.

- [ ] **Step 4: Verify the script still imports cleanly**

```bash
cd e:/Xin_Tool/ResearchTailor
python -c "from scripts.extract_text import extract_pdf_text; print('import ok')"
```

Expected: `import ok`

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_text.py
git commit -m "fix: write error field in extract_text output when PDF yields no text"
```

---

## Task 5: Extended candidate-header regex (TDD)

**Files:**
- Create: `tests/test_parse_candidates.py`
- Modify: `scripts/parse_candidates.py`

- [ ] **Step 1: Create tests/test_parse_candidates.py with failing tests**

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from parse_candidates import CANDIDATE_HEADER, split_candidates


class TestCandidateHeaderRegex:
    def _match(self, line: str):
        return CANDIDATE_HEADER.match(line.strip())

    # --- formats that already work ---
    def test_bold_bracket(self):
        assert self._match("**Candidate [1]**")

    def test_bold_plain(self):
        assert self._match("**Candidate 1**")

    def test_plain_no_bold(self):
        assert self._match("Candidate 3")

    # --- new formats ---
    def test_markdown_h2(self):
        assert self._match("## Candidate 1"), "## heading not matched"

    def test_markdown_h3(self):
        assert self._match("### Candidate 2"), "### heading not matched"

    def test_colon_suffix(self):
        assert self._match("Candidate 1:"), "colon suffix not matched"

    def test_bold_colon(self):
        assert self._match("**Candidate 1**:"), "bold + colon not matched"

    def test_h2_colon(self):
        assert self._match("## Candidate 3:"), "## + colon not matched"

    def test_captures_number(self):
        m = self._match("## Candidate 42:")
        assert m and m.group(1) == "42"

    def test_does_not_match_random_text(self):
        assert not self._match("This is a sentence about candidates.")

    def test_does_not_match_partial(self):
        assert not self._match("  some text Candidate 1 in middle")


class TestSplitCandidates:
    def test_bold_bracket_format(self):
        raw = "**Candidate [1]**\nContent one.\n\n**Candidate [2]**\nContent two."
        result = split_candidates(raw)
        assert len(result) == 2
        assert result[0][0] == 1
        assert result[1][0] == 2

    def test_markdown_heading_format(self):
        raw = "## Candidate 1\nContent one.\n\n## Candidate 2\nContent two."
        result = split_candidates(raw)
        assert len(result) == 2
        assert result[0][0] == 1

    def test_colon_format(self):
        raw = "Candidate 1:\nBody here.\n\nCandidate 2:\nAnother body."
        result = split_candidates(raw)
        assert len(result) == 2

    def test_empty_raw_returns_empty(self):
        assert split_candidates("") == []

    def test_no_headers_returns_empty(self):
        assert split_candidates("Just some text without any headers.") == []
```

- [ ] **Step 2: Run tests to confirm failures**

```bash
cd e:/Xin_Tool/ResearchTailor
python -m pytest tests/test_parse_candidates.py -v 2>&1 | head -40
```

Expected: `test_markdown_h2`, `test_markdown_h3`, `test_colon_suffix`, `test_bold_colon`, `test_h2_colon`, `test_markdown_heading_format`, `test_colon_format` should FAIL.

- [ ] **Step 3: Replace CANDIDATE_HEADER regex in parse_candidates.py**

Find:
```python
CANDIDATE_HEADER = re.compile(
    r"^\*{0,2}Candidate\s+\[?(\d+)\]?\*{0,2}\s*$",
    re.IGNORECASE
)
```

Replace with:
```python
CANDIDATE_HEADER = re.compile(
    r"^(?:#{1,3}\s*)?\*{0,2}Candidate\s+\[?(\d+)\]?\*{0,2}\s*:?\s*$",
    re.IGNORECASE
)
```

- [ ] **Step 4: Improve the zero-candidates warning message**

Find:
```python
    if not candidates:
        print(
            "No candidates found. Check that Claude's output uses "
            "'**Candidate N**' or '**Candidate [N]**' as section headers."
        )
        sys.exit(1)
```

Replace with:
```python
    if not candidates:
        print(
            "No candidates found in candidates_raw.md.\n"
            "Accepted header formats:\n"
            "  **Candidate 1**    **Candidate [1]**\n"
            "  ## Candidate 1    ### Candidate 1\n"
            "  Candidate 1:      Candidate 1\n"
            "Please inspect the file and ensure Claude's output uses one of these formats."
        )
        sys.exit(1)
```

- [ ] **Step 5: Run tests to confirm all pass**

```bash
cd e:/Xin_Tool/ResearchTailor
python -m pytest tests/test_parse_candidates.py -v
```

Expected: all `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add scripts/parse_candidates.py tests/test_parse_candidates.py
git commit -m "fix: extend candidate header regex to match ## headings and colon suffix formats"
```

---

## Task 6: Detect and skip FAILED sentinel files in format_consolidated.py

**Files:**
- Modify: `scripts/format_consolidated.py`

- [ ] **Step 1: Add FAILED file detection in main()**

Find in `format_consolidated.py`:
```python
    extraction_files = sorted(module_dir.glob("*_extraction.md"))
    if not extraction_files:
        print("No extraction files found. Run extract_modules.py first.")
        sys.exit(1)

    print(f"Found {len(extraction_files)} extraction file(s).")
```

Replace with:
```python
    failed_files = sorted(module_dir.glob("*_extraction_FAILED.md"))
    if failed_files:
        print(f"[warn] {len(failed_files)} paper(s) failed extraction and will be excluded:")
        for ff in failed_files:
            print(f"  - {ff.stem.replace('_extraction_FAILED', '')}")
        print()

    extraction_files = sorted(module_dir.glob("*_extraction.md"))
    if not extraction_files:
        print("No extraction files found. Run extract_modules.py first.")
        sys.exit(1)

    print(f"Found {len(extraction_files)} extraction file(s).")
```

- [ ] **Step 2: Verify the glob patterns don't overlap**

The glob `*_extraction.md` does NOT match `paper_extraction_FAILED.md` (which ends in `_FAILED.md`). Confirm:

```bash
cd e:/Xin_Tool/ResearchTailor
python -c "
from pathlib import Path
import tempfile, os
with tempfile.TemporaryDirectory() as d:
    p = Path(d)
    (p / 'paper_extraction.md').touch()
    (p / 'paper_extraction_FAILED.md').touch()
    print('extraction.md matches:', list(p.glob('*_extraction.md')))
    print('FAILED matches:', list(p.glob('*_extraction_FAILED.md')))
"
```

Expected: the two globs each match exactly one file, with no overlap.

- [ ] **Step 3: Commit**

```bash
git add scripts/format_consolidated.py
git commit -m "fix: detect and warn about _FAILED sentinel files in format_consolidated"
```

---

## Task 7: Config validation in app.py

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Wrap module-level config load with error capture**

Find at the top of `app.py`:
```python
CONFIG = load_config()
ROOT = Path(__file__).parent
PROJECTS_DIR = ROOT / CONFIG["paths"]["projects_dir"]
MODULE_POOL_DIR = ROOT / CONFIG["paths"]["module_pool_dir"]
```

Replace with:
```python
try:
    CONFIG = load_config()
    _CONFIG_ERROR: str | None = None
except Exception as e:
    CONFIG = {}
    _CONFIG_ERROR = str(e)

ROOT = Path(__file__).parent
PROJECTS_DIR = ROOT / CONFIG.get("paths", {}).get("projects_dir", "projects")
MODULE_POOL_DIR = ROOT / CONFIG.get("paths", {}).get("module_pool_dir", "module_pool")
```

- [ ] **Step 2: Add `validate_config()` helper after the `load_config()` function**

Find the end of `load_config()` in app.py:
```python
def load_config():
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
```

Replace with:
```python
def load_config():
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    config.setdefault("chunking", {
        "max_tokens": 12000,
        "overlap_tokens": 500,
        "chars_per_token": 2.5,
        "min_paragraph_tokens": 50,
    })
    return config


def validate_config(config: dict) -> list[str]:
    """Return a list of human-readable error messages for missing required fields."""
    errors = []
    ds = config.get("deepseek", {})
    if not ds.get("api_key", "").strip():
        errors.append("`deepseek.api_key` is missing or empty in config.yaml")
    if not ds.get("base_url", "").strip():
        errors.append("`deepseek.base_url` is missing in config.yaml")
    if not ds.get("model", "").strip():
        errors.append("`deepseek.model` is missing in config.yaml")
    return errors
```

- [ ] **Step 3: Show config errors at the top of every page render**

Find `page_home()`:
```python
def page_home():
    st.title("LitRecombine")
    st.caption("Literature-Driven Research Direction Generation")
    st.divider()
```

Add config error banner just after the title:
```python
def page_home():
    st.title("LitRecombine")
    st.caption("Literature-Driven Research Direction Generation")
    if _CONFIG_ERROR:
        st.error(f"Failed to load config.yaml: {_CONFIG_ERROR}")
        st.stop()
    config_errors = validate_config(CONFIG)
    if config_errors:
        for msg in config_errors:
            st.error(f"Configuration error: {msg}")
        st.stop()
    st.divider()
```

Also add the same guard at the top of `page_run()`. Find:
```python
def page_run():
    run_path = Path(st.session_state["active_run"])
    st.title(f"Run: `{run_path.name}`")
```

Add after the title line:
```python
def page_run():
    run_path = Path(st.session_state["active_run"])
    st.title(f"Run: `{run_path.name}`")
    if _CONFIG_ERROR:
        st.error(f"Failed to load config.yaml: {_CONFIG_ERROR}")
        st.stop()
```

- [ ] **Step 4: Verify Streamlit app starts without error**

```bash
cd e:/Xin_Tool/ResearchTailor
python -c "import ast, pathlib; ast.parse(pathlib.Path('app.py').read_text(encoding='utf-8')); print('syntax ok')"
```

Expected: `syntax ok`

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "fix: catch config.yaml load errors and validate required fields with Streamlit error banners"
```

---

## Task 8: Run full test suite

- [ ] **Step 1: Install pytest if not present**

```bash
cd e:/Xin_Tool/ResearchTailor
pip install pytest
```

- [ ] **Step 2: Run all tests**

```bash
cd e:/Xin_Tool/ResearchTailor
python -m pytest tests/ -v
```

Expected output: all tests `PASSED`, no failures.

- [ ] **Step 3: Final integration check — import all scripts**

```bash
cd e:/Xin_Tool/ResearchTailor
python -c "
import yaml
config = yaml.safe_load(open('config.yaml'))
print('chunking cfg:', config['chunking'])

import sys; sys.path.insert(0, 'scripts')
from extract_modules import split_text_into_chunks, estimate_tokens
text = 'paragraph text. ' * 500
chunks = split_text_into_chunks(text, config['chunking'])
print(f'chunks produced: {len(chunks)}')
for i, c in enumerate(chunks):
    print(f'  chunk {i+1}: ~{estimate_tokens(c, config[\"chunking\"][\"chars_per_token\"])} tokens')
"
```

Expected: prints chunking config + chunk count (should be >1 for 8000+ word text).

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "test: add full test suite for chunking and candidate parsing"
```
