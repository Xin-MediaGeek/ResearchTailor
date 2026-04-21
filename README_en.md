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

Run this in the project root:

```bash
pip install -r requirements.txt
```

---

## Configuration

Open [config.yaml](E:\Xin_Tool\ResearchTailor\config.yaml) and fill in your DeepSeek API key:

```yaml
deepseek:
  api_key: "YOUR_DEEPSEEK_API_KEY"
```

Other settings are also centralized in `config.yaml`, including:

- DeepSeek model and parameters
- six extraction modules
- Stage 3 hard filters
- project and module-pool paths

The current default configuration uses:

- `model: deepseek-chat`
- `max_tokens: 4096`

Recommended usage:

- use `deepseek-chat` as the default extraction model for speed, cost, and stable structured extraction
- use `deepseek-reasoner` when module boundaries are harder and you want stronger reasoning

---

## Launch

Run this in the project root:

```bash
streamlit run app.py
```

The app opens as a local web UI.

---

## Directory Structure

```text
LitRecombine/
├── app.py
├── config.yaml
├── requirements.txt
├── README.md
├── README_en.md
├── research_direction_workflow.md
├── scripts/
│   ├── extract_text.py
│   ├── extract_modules.py
│   ├── format_consolidated.py
│   └── parse_candidates.py
├── module_pool/
│   ├── core_method/
│   ├── experimental_scenario/
│   ├── unresolved_questions/
│   ├── acknowledged_limitations/
│   ├── evaluation_metrics/
│   └── measurement_instruments/
└── projects/
    └── YYYY-MM-DD_HHMMSS_label/
        ├── papers/
        ├── extracted_text/
        ├── module_extractions/
        └── candidates/
```

Notes:

- `projects/` stores the full output of each run
- new run folders use the format `YYYY-MM-DD_HHMMSS[_label]`
- `module_pool/` stores reusable module snippets across runs

---

## Workflow

### Stage 1: Literature Collection

Create a new run in the UI. You can provide a custom label or use the auto-generated timestamp only.

The app will:

- create the run folder structure
- provide a button to open the `papers/` folder

Place the PDFs for the current run into `papers/`.

About 10 papers per run is a practical size.

---

### Stage 2: Structured Extraction

Stage 2 has three steps.

#### 2a: Full-Text Extraction

Run [scripts\extract_text.py](E:\Xin_Tool\ResearchTailor\scripts\extract_text.py) to convert each PDF into a JSON full-text backup saved in:

- `extracted_text/`

Example output:

- `paper01_fulltext.json`

These JSON files are backups for downstream processing rather than the main human-readable artifacts.

#### 2b: Six-Module Extraction

Run [scripts\extract_modules.py](E:\Xin_Tool\ResearchTailor\scripts\extract_modules.py) to extract six modules from each paper:

1. Core Innovation
2. Application Scenario
3. Future Research Directions
4. Acknowledged Limitations
5. Evaluation Metrics
6. Experimental Measurement Methods

Each paper produces one Markdown file in:

- `module_extractions/`

The Stage 2b UI now lets you choose the extraction model directly:

- `deepseek-chat`
- `deepseek-reasoner`

so you do not have to edit `config.yaml` just to switch models.

For long papers, the current implementation does not hard-truncate the first 60,000 characters anymore. Instead it:

1. splits the full text into overlapping chunks
2. extracts modules from each chunk separately
3. merges the chunk-level outputs into one final extraction

This reduces the risk of missing information from later sections, especially:

- limitations
- unresolved questions
- evaluation metrics

#### 2c: Consolidated Extraction

Run [scripts\format_consolidated.py](E:\Xin_Tool\ResearchTailor\scripts\format_consolidated.py) to merge all per-paper extractions into:

- `module_extractions/consolidated_extractions.md`

This file is organized by module rather than by paper, which makes cross-paper comparison easier during recombination.

Current output structure example:

```md
# Consolidated Extractions

Papers included: paper01, paper02

---
## Module: Core Innovation

**[paper01]**
...

**[paper02]**
...
```

If `module_pool/` contains historical high-quality module snippets, the UI lets you:

- inspect available files by module
- select only the specific pool entries to include in the current run

It no longer forces all pool files in at once.

---

### Stage 3: Recombination

In Stage 3, you:

1. download `consolidated_extractions.md`
2. copy the recombination prompt shown in the UI
3. submit both to Claude

The prompt is displayed in a native text area. The recommended way is:

- select the text
- copy it manually with `Ctrl+C` or `Cmd+C`

The project no longer relies on a fragile browser-script clipboard solution.

#### Current Hard Filters

The recombination prompt includes these hard filters:

- Measurement Instruments must include at least one of:
  - eye tracking
  - heart rate measurement
  - head movement tracking
  - hand movement tracking
  - validated self-report questionnaires
- Measurement Instruments must not include EEG
- participants must not involve clinical populations or diagnosed conditions

---

### Stage 4: Candidate Parsing And Evaluation

#### 4a: Candidate Parsing

Paste the full Claude output back into the UI. The app will:

- save the raw text to `candidates/candidates_raw.md`
- split it into candidate files such as:
  - `candidate_001.md`
  - `candidate_002.md`
  - ...

The parser currently supports both heading styles:

- `**Candidate [1]**`
- `**Candidate 1**`

#### 4b: Evaluation Record

After candidates are created, the UI provides:

- Decision
- Rationale

and saves the result to:

- `candidates/evaluation_record.md`

Example:

```md
## Candidate 001
- Decision: Keep
- Rationale: ...
```

#### 4c: Reuse Evaluation Records Later

After multiple runs, historical `evaluation_record.md` files can be sent back to Claude as additional context for improving:

- module design
- recombination prompts
- candidate filtering strategy

---

## Module Pool

`module_pool/` is a cross-run reuse pool for module text.

You can manually place high-quality module snippets from earlier runs into subfolders such as:

- `module_pool/core_method/`
- `module_pool/experimental_scenario/`
- `module_pool/unresolved_questions/`

In Stage 2c, the UI displays those files and lets you select specific entries to include in the consolidated file.

Included pool content is marked with `[pool]` in the merged output.

---

## Key Scripts

- [app.py](E:\Xin_Tool\ResearchTailor\app.py)
  - Streamlit entry point
  - coordinates the four workflow stages

- [scripts\extract_text.py](E:\Xin_Tool\ResearchTailor\scripts\extract_text.py)
  - PDF to JSON full-text backup

- [scripts\extract_modules.py](E:\Xin_Tool\ResearchTailor\scripts\extract_modules.py)
  - DeepSeek-based six-module extraction
  - chunk-based extraction and merge for long papers
  - supports UI-based switching between `deepseek-chat` and `deepseek-reasoner`

- [scripts\format_consolidated.py](E:\Xin_Tool\ResearchTailor\scripts\format_consolidated.py)
  - merges per-paper module outputs
  - supports per-module selection from `module_pool`

- [scripts\parse_candidates.py](E:\Xin_Tool\ResearchTailor\scripts\parse_candidates.py)
  - splits Claude output into individual candidate files
  - supports both `Candidate [N]` and `Candidate N`

---

## Notes

- PDF extraction quality depends on whether the PDF contains selectable text; scanned PDFs often need OCR first
- Stage 2a and Stage 2b skip existing outputs by default to avoid redundant work
- re-running Stage 4a removes old `candidate_*.md` files and writes the newly parsed set
- DeepSeek usage incurs token cost, so setting usage limits is a good idea
- Stage 3 is still manual; it is not automated in the current implementation

---

## Related Document

- [research_direction_workflow.md](E:\Xin_Tool\ResearchTailor\research_direction_workflow.md)
  - design-oriented workflow definition
