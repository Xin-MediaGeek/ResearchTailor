# LitRecombine: Research Direction Generation Workflow
## Literature-Driven Recombination Method

---

## Overview

This workflow generates candidate research directions by extracting structured information from existing literature and recombining modules across papers. Every component of each candidate direction traces back to a published source, eliminating the problem of generating directions without evidentiary grounding.

The workflow is implemented as a local Streamlit application. All stages are accessible through a step-by-step UI. The user interacts with each stage in sequence; the application handles all file operations and API calls automatically.

---

## File Structure

```
LitRecombine/                               # Workflow root (universal, not domain-specific)
├── app.py                                  # Streamlit application entry point
├── config.yaml                             # API keys and path settings
├── scripts/
│   ├── extract_text.py                     # Stage 2a: PDF to full-text JSON
│   ├── extract_modules.py                  # Stage 2b: full-text to six-module extraction
│   ├── format_consolidated.py              # Stage 2c: merge all extractions into unified input
│   └── parse_candidates.py                 # Stage 4a: parse Claude output into individual candidates
├── module_pool/                            # Cross-run module pool (auto-created, user-populated)
│   ├── core_method/
│   ├── experimental_scenario/
│   ├── unresolved_questions/
│   ├── acknowledged_limitations/
│   ├── evaluation_metrics/
│   └── measurement_instruments/
└── projects/                               # All analysis runs
    ├── 2025-07-01_153045_scenario/         # Run folder (YYYY-MM-DD_HHMMSS + optional user label)
    │   ├── papers/                         # User places source PDFs here
    │   ├── extracted_text/                 # Stage 2a output
    │   │   ├── paper01_fulltext.json
    │   │   └── ...
    │   ├── module_extractions/             # Stage 2b and 2c output
    │   │   ├── paper01_extraction.md       # Per-paper extraction (archive and traceability)
    │   │   ├── paper02_extraction.md
    │   │   └── consolidated_extractions.md # All papers merged by module (tailor step input)
    │   └── candidates/                     # Stage 3 and 4 output
    │       ├── candidates_raw.md           # User pastes Claude output here
    │       ├── candidate_001.md            # Auto-parsed individual candidates
    │       ├── candidate_002.md
    │       └── evaluation_record.md        # Stage 4 evaluation with decisions and rationale
    └── 2025-07-15_locomotion/
        └── ...
```

---

## Stage 1: Literature Collection

**Domain scope**: Virtual reality and motion sickness. All topics within this domain are in scope regardless of subfield or application area.

**Search tool**: Elicit (manual search and selection by researcher). Literature selection is not automated because domain judgment at this stage is critical.

**Papers per run**: Approximately 10 papers per run to keep extraction workload manageable.

**Workflow action**: The user launches the application and either enters a custom label or accepts the auto-generated timestamp-only folder name. The application creates a unique run folder using `YYYY-MM-DD_HHMMSS` plus the optional label, can open the `papers/` directory from the UI, and the user places all downloaded PDFs into `papers/` before confirming in the UI.

**Year range by module**:

| Module | Year Range | Rationale |
|--------|------------|-----------|
| Core Method | No restriction | Foundational methods may come from earlier work |
| Experimental Scenario | Last 3 years | Scenarios should reflect current VR hardware |
| Unresolved Questions | Last 3 years | Should reflect current research frontier |
| Acknowledged Limitations | Last 3 years | Should reflect current research frontier |
| Evaluation Metrics | No restriction | Established metrics may come from earlier work |
| Measurement Instruments | Last 5 years | Balance maturity with technical currency |

Note: Year range guides collection priorities and is not applied as a strict programmatic filter.

---

## Stage 2: Structured Extraction

### Stage 2a: Full-Text Extraction

The application runs `extract_text.py` on all PDFs in `papers/`. Each paper's full text is saved as a JSON file in `extracted_text/`. These files serve as processing backups and are not intended for direct human reading.

### Stage 2b: Module Extraction via DeepSeek API

Each full-text JSON is passed to the DeepSeek API with the extraction prompt below. The result for each paper is saved as a Markdown file in `module_extractions/`.

If a paper is long, the application splits the full text into overlapping chunks, runs extraction on each chunk, and then performs a merge pass to produce one final per-paper extraction. This reduces the risk of missing modules that appear late in the paper.

The UI allows the user to select the extraction model for the current run. The default configuration uses `deepseek-v4-flash`, while `deepseek-v4-pro` can be selected when stronger reasoning is desired.

**Extraction prompt**:

```
You are extracting structured information from a research paper. Extract the following six modules. For each module, provide only information explicitly stated in the paper. If a module has no corresponding content in the paper, output exactly "Not reported". Do not infer, summarize beyond what is stated, or fill gaps with plausible content.

**Paper ID**: [paperID]

**Module 1 — Core Innovation**
The primary technical method, analytical approach, theoretical innovation, or application innovation used in the study, but only when the authors explicitly present it as an innovation.

**Module 2 — Application Scenario**
The specific task type or situational setup used in the experiment, and what problem the study addresses in that scenario.

**Module 3 — Future Research Directions**
Problems the authors explicitly state were not solved in the current study but could be addressed in future work, together with the stated reasons and why the direction is necessary.

**Module 4 — Acknowledged Limitations**
Methodological or design flaws the authors explicitly identified.

**Module 5 — Evaluation Metrics**
The dependent variables or criteria used to measure outcomes.

**Module 6 — Experimental Measurement Methods**
The core data collection methods used in the experiment, including software algorithms and hardware facilities.
```

### Stage 2c: Consolidated Extraction File

After all per-paper extractions are complete, `format_consolidated.py` automatically merges them into `consolidated_extractions.md`. This file is organized by module rather than by paper, allowing the recombination step to compare all papers within the same module without switching between files.

Current structure of `consolidated_extractions.md`:

```
## Module: Core Innovation

**[paper01]**
...

**[paper02]**
...

## Module: Application Scenario
**[paper01]**
...
```

If the user has placed any module-level files into the cross-run `module_pool/`, the application allows the user to select specific pool entries by module for inclusion in the consolidated file for this run. Inclusion is manual and user-confirmed.

---

## Stage 3: Recombination (Tailor Step)

The user downloads `consolidated_extractions.md` from the UI and submits it to Claude together with the recombination prompt below. The prompt is displayed in a text area in the UI for reliable manual copy. This step is performed manually because the reasoning demands involved in evaluating combinatorial validity are high.

**Recombination prompt**:

```
You will receive structured extractions from multiple research papers. Each paper has been summarized across six modules: Core Innovation, Application Scenario, Future Research Directions, Acknowledged Limitations, Evaluation Metrics, and Experimental Measurement Methods.

Your task is to generate candidate research directions by combining modules from different papers. Each candidate direction must draw its components from at least two different source papers.

Apply the following hard filters. Discard any candidate that fails any one of them:
1. The Measurement Instruments component must include at least one of the following: eye tracking, heart rate measurement, head movement tracking, hand movement tracking, or validated self-report questionnaires.
2. The Measurement Instruments component must not include EEG.
3. The participant requirements must not involve clinical populations or individuals with diagnosed conditions.

For each candidate direction that passes all filters, output the following:

**Candidate [N]**
- Source papers: [list paper IDs]
- Core Innovation: [which paper, what content]
- Application Scenario: [which paper, what content]
- Future Research Direction being addressed: [which paper, what content]
- Evaluation Metrics: [which paper, what metrics]
- Experimental Measurement Methods: [which paper, what methods]
- Research question: [one concise statement of the research question this combination implies]
- Internal consistency check: [one sentence noting whether the combined components are logically compatible, and flagging any tension if present]

Generate as many candidates as the combinations reasonably support. Do not filter by research type or thematic focus beyond the three hard criteria above.
```

---

## Stage 4: Evaluation

### Stage 4a: Candidate Parsing

The user copies Claude's full output and pastes it into the designated text area in the UI. `parse_candidates.py` automatically splits the output into individual candidate files (`candidate_001.md`, `candidate_002.md`, etc.) saved in `candidates/`. The raw pasted output is also saved as `candidates_raw.md` for reference. The parser supports both `Candidate [N]` and `Candidate N` heading styles.

### Stage 4b: Evaluation Record

The application generates `evaluation_record.md` in `candidates/` with one entry per candidate. The user reviews each candidate in the UI and records a decision and rationale for each.

Structure of each entry in `evaluation_record.md`:

```
## Candidate 001
- Decision: [Keep / Discard / Pending]
- Rationale: [free text]
```

### Stage 4c: Evaluation Record as Workflow Input

After multiple runs, accumulated evaluation records can be submitted to Claude as additional context to improve extraction module design or refine the recombination prompt. This step is manual and user-initiated.

---

## Constraints Summary

| Constraint | Specification |
|------------|---------------|
| Required instruments | At least one of: eye tracking, heart rate, head or hand movement tracking, validated questionnaires |
| Excluded instruments | EEG |
| Participant population | Healthy adults, university student population |
| Excluded populations | Clinical populations, individuals with diagnosed conditions |
| Contribution type | Methodological (no restriction on specific form) |
| Pre-excluded directions | None |
| Software and algorithms | No restrictions |
