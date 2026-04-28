# LitRecombine

Research direction generation tool based on structured literature extraction and cross-paper recombination.

---

## Overview

A common workflow in research ideation is to propose a direction first and then search the literature for support. That approach often leads to two problems:

- the idea is weakly grounded in published evidence
- the idea overlaps with existing work without being noticed early enough

`LitRecombine` reverses that order:

1. extract structured modules from published papers
2. recombine those modules across papers
3. generate candidate research directions with clear source traceability

Each candidate direction is grounded in source papers rather than being generated without evidence.

---

## What The Project Does

The current project is a local `Streamlit` workflow with four stages:

1. Literature collection
2. Structured extraction
3. Recombination
4. Candidate evaluation

In practice:

- PDF text extraction is done locally
- six-module extraction is done through the DeepSeek API
- the recombination step is still manual and submitted to Claude
- candidate parsing and evaluation return to the local app

---

## Requirements

- Python 3.10+
- DeepSeek API key

---

## Installation

```bash
pip install -r requirements.txt
```

For the test suite, also install pytest:

```bash
pip install pytest
```

---

## Configuration

**Step 1: Copy the config templates**

```bash
cp config.yaml.example config.yaml
cp .env.example .env
```

**Step 2: Add your API key**

Edit `.env` and fill in your DeepSeek API key:

```
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

> `.env` is gitignored and will never be committed. The API key is no longer stored in `config.yaml`.

**Step 3: Adjust other settings in `config.yaml` as needed**

| Block | Contents |
|-------|----------|
| `deepseek` | model, max_tokens, temperature (API key is in .env) |
| `extraction.modules` | Six module definitions |
| `filters` | Stage 3 hard filters |
| `chunking` | Long-paper chunking parameters (see below) |
| `paths` | projects and module_pool directories |

### Chunking Parameters (`chunking`)

```yaml
chunking:
  max_tokens: 12000         # token budget per chunk (estimated)
  overlap_tokens: 500       # overlap between adjacent chunks (in tokens)
  chars_per_token: 2.5      # 2.5 for English-dominant; 2.0 for mixed CN/EN
  min_paragraph_tokens: 50  # paragraphs shorter than this merge with the next
```

Model guidance:

- `deepseek-v4-flash`: default — fast, cost-efficient, reliable for structured extraction
- `deepseek-v4-pro`: stronger reasoning for papers with complex or ambiguous structure; consider raising `chunking.max_tokens` to `20000`

---

## Launch

```bash
streamlit run app.py
```

The app opens as a local web UI. If `DEEPSEEK_API_KEY` is missing from `.env` or `config.yaml` is missing required fields, a red error banner is shown immediately.

---

## Running Tests

```bash
python -m pytest tests/ -v
```

---

## Directory Structure

```text
LitRecombine/
├── app.py                        # Streamlit entry point
├── config.yaml.example           # Config template (copy to config.yaml)
├── .env.example                  # API key template (copy to .env and fill in)
├── requirements.txt
├── README.md
├── README_en.md
├── research_direction_workflow.md
├── scripts/
│   ├── extract_text.py           # Stage 2a: PDF → JSON full-text extraction
│   ├── extract_modules.py        # Stage 2b: six-module extraction (with chunking)
│   ├── format_consolidated.py    # Stage 2c: merge per-paper extractions
│   └── parse_candidates.py       # Stage 4a: parse Claude output into candidates
├── tests/
│   ├── test_chunking.py          # Unit tests for chunking helpers
│   └── test_parse_candidates.py  # Unit tests for candidate header regex
├── module_pool/
│   ├── core_method/
│   ├── experimental_scenario/
│   ├── unresolved_questions/
│   ├── acknowledged_limitations/
│   ├── evaluation_metrics/
│   └── measurement_instruments/
└── projects/                     # Run outputs (not version-controlled)
    └── YYYY-MM-DD_HHMMSS[_label]/
        ├── papers/
        ├── extracted_text/
        ├── module_extractions/
        └── candidates/
```

---

## Workflow

### Stage 1: Literature Collection

Create a new run in the UI. You can provide a custom label or use the auto-generated timestamp only.

The app creates the run folder structure and provides a button to open the `papers/` folder. Place the PDFs for the current run into `papers/`.

About 10 papers per run is a practical size for cost and recombination complexity.

---

### Stage 2: Structured Extraction

#### 2a: Full-Text Extraction

Converts each PDF to a JSON file saved in `extracted_text/`. The JSON contains the full text and a per-page breakdown.

If a PDF contains no selectable text (e.g. a scanned image), a `[warn]` message is printed and an `"error": "empty_text"` field is written into the JSON. Downstream steps skip these files automatically.

#### 2b: Six-Module Extraction

Extracts six modules from each paper:

1. Core Innovation
2. Application Scenario
3. Future Research Directions
4. Acknowledged Limitations
5. Evaluation Metrics
6. Experimental Measurement Methods

Each paper produces one Markdown file in `module_extractions/`.

**Model selection:** The UI provides two independent model dropdowns:

- **Chunk extraction model**: used for per-chunk module extraction — `deepseek-v4-flash` recommended (fast and cost-efficient)
- **Merge model**: used only for the final merge call when a paper is split into multiple chunks — switch to `deepseek-v4-pro` for stronger reasoning on complex papers

For single-chunk papers, only the extraction model is called; the merge model has no effect.

**Long-paper handling:** When a paper exceeds the token budget, the text is split using a four-level boundary hierarchy (blank lines → sentence-ending newlines → force-split), modules are extracted from each chunk independently, and the results are merged in a final consolidation call. All chunking parameters are configurable in `config.yaml`.

**API fault tolerance:** Each API call is retried up to 3 times with exponential backoff (2 s / 4 s / 8 s). If all retries fail, a `{paper_id}_extraction_FAILED.md` sentinel file is written and the script continues with the remaining papers.

#### 2c: Consolidated Extraction

Merges all per-paper extractions into `module_extractions/consolidated_extractions.md`, organized by module rather than by paper.

If any `_FAILED.md` sentinel files exist, a warning is printed and those papers are excluded from the consolidation.

If `module_pool/` contains historical high-quality snippets, the UI lets you select specific entries to include.

---

### Stage 3: Recombination

In Stage 3, you:

1. download `consolidated_extractions.md`
2. copy the recombination prompt from the UI
3. submit both to Claude

#### Current Hard Filters

The recombination prompt includes the following hard filters (configurable in `config.yaml` under `filters:`):

- Measurement Instruments must include at least one of:
  - eye tracking
  - heart rate measurement
  - head movement tracking
  - hand movement tracking
  - validated self-report questionnaires
- Measurement Instruments must not include CAVE
- participants must not involve clinical populations or diagnosed conditions

---

### Stage 4: Candidate Parsing And Evaluation

#### 4a: Candidate Parsing

Paste the full Claude output back into the UI. The app will:

- save the raw text to `candidates/candidates_raw.md`
- split it into candidate files: `candidate_001.md`, `candidate_002.md`, ...

The parser supports the following header formats:

| Format | Example |
|--------|---------|
| Bold with brackets | `**Candidate [1]**` |
| Bold plain | `**Candidate 1**` |
| Markdown heading | `## Candidate 1`, `### Candidate 1` |
| Colon suffix | `Candidate 1:` |

#### 4b: Evaluation Record

After candidates are created, the UI provides Decision and Rationale fields for each candidate, saved to `candidates/evaluation_record.md`.

#### 4c: Reuse Evaluation Records

After multiple runs, historical `evaluation_record.md` files can be sent back to Claude as context for improving module design, recombination prompts, or candidate filtering strategy.

---

## Module Pool

`module_pool/` is a cross-run reuse pool. Place high-quality module snippets from earlier runs into the appropriate subfolders. In Stage 2c, the UI lets you select specific entries per module to include in the consolidated file. Included pool content is marked with `[pool]` in the output.

---

## Notes

- PDF extraction quality depends on whether the PDF contains selectable text; scanned PDFs need OCR first
- Stage 2a and Stage 2b skip existing outputs by default to avoid redundant processing
- Re-running Stage 4a removes old `candidate_*.md` files and writes the newly parsed set
- DeepSeek usage incurs token cost; setting usage limits in the DeepSeek console is recommended
- Stage 3 is still manual — submitting to Claude is not automated in the current implementation

---

## Related Document

- [research_direction_workflow.md](research_direction_workflow.md): design-oriented workflow definition
