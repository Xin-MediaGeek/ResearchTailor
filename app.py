import streamlit as st
import yaml
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

def load_config():
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

CONFIG = load_config()
ROOT = Path(__file__).parent
PROJECTS_DIR = ROOT / CONFIG["paths"]["projects_dir"]
MODULE_POOL_DIR = ROOT / CONFIG["paths"]["module_pool_dir"]


# ─────────────────────────────────────────────
# Initialization
# ─────────────────────────────────────────────

def init_dirs():
    PROJECTS_DIR.mkdir(exist_ok=True)
    MODULE_POOL_DIR.mkdir(exist_ok=True)
    for module in CONFIG["extraction"]["modules"]:
        (MODULE_POOL_DIR / module["id"]).mkdir(exist_ok=True)

def create_run_folder(label: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    folder_name = f"{timestamp}_{label}" if label else timestamp
    run_path = PROJECTS_DIR / folder_name
    for sub in ["papers", "extracted_text", "module_extractions", "candidates"]:
        (run_path / sub).mkdir(parents=True, exist_ok=True)
    return run_path

def get_existing_runs() -> list[Path]:
    if not PROJECTS_DIR.exists():
        return []
    return sorted(
        [p for p in PROJECTS_DIR.iterdir() if p.is_dir()],
        reverse=True
    )


# ─────────────────────────────────────────────
# UI Helpers
# ─────────────────────────────────────────────

def stage_header(number: int, title: str, status: str = ""):
    col1, col2 = st.columns([6, 1])
    with col1:
        st.subheader(f"Stage {number}: {title}")
    with col2:
        if status == "done":
            st.success("Done")
        elif status == "running":
            st.info("Running")
        elif status == "pending":
            st.warning("Pending")

def run_script(script_name: str, *args) -> tuple[bool, str]:
    script_path = ROOT / "scripts" / script_name
    result = subprocess.run(
        ["python", str(script_path), *[str(a) for a in args]],
        capture_output=True,
        text=True
    )
    success = result.returncode == 0
    output = result.stdout if success else result.stderr
    return success, output


def open_path_in_file_explorer(path: Path) -> tuple[bool, str]:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return True, ""
    except Exception as e:
        return False, str(e)


# ─────────────────────────────────────────────
# Page: Home
# ─────────────────────────────────────────────

def page_home():
    st.title("LitRecombine")
    st.caption("Literature-Driven Research Direction Generation")
    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Start a New Run")
        label = st.text_input(
            "Run label (optional)",
            placeholder="e.g. scenario_study",
            help="Combined with today's date to name the run folder."
        )
        if st.button("Create Run", type="primary", use_container_width=True):
            run_path = create_run_folder(label.strip())
            st.session_state["active_run"] = str(run_path)
            st.success(f"Run created: `{run_path.name}`")
            st.rerun()

    with col2:
        st.markdown("#### Resume Existing Run")
        runs = get_existing_runs()
        if runs:
            run_names = [r.name for r in runs]
            selected = st.selectbox("Select run", run_names)
            if st.button("Open Run", use_container_width=True):
                st.session_state["active_run"] = str(PROJECTS_DIR / selected)
                st.rerun()
        else:
            st.caption("No existing runs found.")

    st.divider()
    st.markdown("#### Module Pool")
    st.caption(
        "The module pool stores high-quality extractions across runs. "
        "Place files manually into the subfolders below."
    )
    pool_cols = st.columns(3)
    for i, module in enumerate(CONFIG["extraction"]["modules"]):
        with pool_cols[i % 3]:
            pool_sub = MODULE_POOL_DIR / module["id"]
            count = len(list(pool_sub.glob("*")))
            st.metric(module["label"], f"{count} file(s)")
    if st.button("Open Module Pool Folder"):
        success, error = open_path_in_file_explorer(MODULE_POOL_DIR)
        if not success:
            st.error(f"Could not open folder: {error}")


# ─────────────────────────────────────────────
# Page: Run Workflow
# ─────────────────────────────────────────────

def page_run():
    run_path = Path(st.session_state["active_run"])
    st.title(f"Run: `{run_path.name}`")
    if st.button("← Back to Home"):
        del st.session_state["active_run"]
        st.rerun()
    st.divider()

    tabs = st.tabs([
        "Stage 1 — Collection",
        "Stage 2 — Extraction",
        "Stage 3 — Recombination",
        "Stage 4 — Evaluation"
    ])

    with tabs[0]:
        render_stage1(run_path)

    with tabs[1]:
        render_stage2(run_path)

    with tabs[2]:
        render_stage3(run_path)

    with tabs[3]:
        render_stage4(run_path)


# ─────────────────────────────────────────────
# Stage 1: Literature Collection
# ─────────────────────────────────────────────

def render_stage1(run_path: Path):
    stage_header(1, "Literature Collection")

    papers_dir = run_path / "papers"
    pdfs = list(papers_dir.glob("*.pdf"))

    st.markdown(
        "Place your downloaded PDF files into the `papers/` folder for this run, "
        "then confirm below to proceed."
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Open papers/ folder", use_container_width=True):
            success, error = open_path_in_file_explorer(papers_dir)
            if not success:
                st.error(f"Could not open folder: {error}")
    with col2:
        if st.button("Refresh file list", use_container_width=True):
            st.rerun()

    if pdfs:
        st.success(f"{len(pdfs)} PDF(s) detected:")
        for pdf in pdfs:
            st.text(f"  {pdf.name}")
    else:
        st.warning("No PDFs found in papers/ yet.")

    st.divider()
    st.markdown("**Year range guidance for collection**")
    guidance = [
        ("Core Method", "No restriction", "Foundational methods may come from earlier work"),
        ("Experimental Scenario", "Last 3 years", "Scenarios should reflect current VR hardware"),
        ("Unresolved Questions", "Last 3 years", "Should reflect current research frontier"),
        ("Acknowledged Limitations", "Last 3 years", "Should reflect current research frontier"),
        ("Evaluation Metrics", "No restriction", "Established metrics may come from earlier work"),
        ("Measurement Instruments", "Last 5 years", "Balance maturity with technical currency"),
    ]
    for module, year_range, rationale in guidance:
        st.markdown(f"- **{module}**: {year_range} — {rationale}")

    st.divider()
    if pdfs:
        if st.button("Confirm collection and proceed to Stage 2", type="primary"):
            st.session_state[f"{run_path.name}_stage1_done"] = True
            st.success("Stage 1 confirmed.")


# ─────────────────────────────────────────────
# Stage 2: Structured Extraction
# ─────────────────────────────────────────────

def render_stage2(run_path: Path):
    stage_header(2, "Structured Extraction")

    papers_dir = run_path / "papers"
    extracted_dir = run_path / "extracted_text"
    module_dir = run_path / "module_extractions"
    pdfs = list(papers_dir.glob("*.pdf"))
    consolidated_path = module_dir / "consolidated_extractions.md"

    if not pdfs:
        st.warning("No PDFs found. Complete Stage 1 first.")
        return

    st.markdown("#### Step 2a — Full-Text Extraction")
    st.caption("Extract raw text from each PDF and save as JSON backup.")

    existing_json = list(extracted_dir.glob("*.json"))
    if existing_json:
        st.info(f"{len(existing_json)} full-text file(s) already extracted.")

    if st.button("Run full-text extraction (2a)", use_container_width=True):
        with st.spinner("Extracting full text..."):
            success, output = run_script("extract_text.py", str(run_path))
        if success:
            st.success("Full-text extraction complete.")
        else:
            st.error(f"Error: {output}")

    st.divider()
    st.markdown("#### Step 2b — Module Extraction via DeepSeek API")
    st.caption(
        "Each paper's full text is sent to the DeepSeek API. "
        "Results are saved as per-paper Markdown files."
    )

    available_models = ["deepseek-chat", "deepseek-reasoner"]
    default_model = CONFIG["deepseek"]["model"]
    selected_model = st.selectbox(
        "Extraction model",
        available_models,
        index=available_models.index(default_model) if default_model in available_models else 0,
        help="Use deepseek-chat for faster, lower-cost extraction. Use deepseek-reasoner when you want stronger reasoning for harder extraction boundaries."
    )
    st.caption(
        f"Configured default max_tokens: {CONFIG['deepseek']['max_tokens']}. "
        "deepseek-chat is usually the best default for stable structured extraction."
    )

    existing_md = [f for f in module_dir.glob("*_extraction.md")]
    if existing_md:
        st.info(f"{len(existing_md)} module extraction file(s) already present.")
        with st.expander("View extracted files"):
            for md_file in existing_md:
                st.markdown(f"**{md_file.name}**")
                st.code(md_file.read_text(encoding="utf-8"), language="markdown")

    if st.button("Run module extraction (2b)", use_container_width=True):
        with st.spinner("Calling DeepSeek API for each paper..."):
            success, output = run_script("extract_modules.py", str(run_path), "--model", selected_model)
        if success:
            st.success("Module extraction complete.")
            st.rerun()
        else:
            st.error(f"Error: {output}")

    st.divider()
    st.markdown("#### Step 2c — Consolidated Extraction File")
    st.caption(
        "All per-paper extractions are merged into a single file organized by module. "
        "This file is the input for the recombination step."
    )

    selected_pool_entries = []
    pool_files_by_module = {}
    for module in CONFIG["extraction"]["modules"]:
        pool_sub = MODULE_POOL_DIR / module["id"]
        files = [f for f in sorted(pool_sub.iterdir()) if f.is_file()] if pool_sub.exists() else []
        pool_files_by_module[module["id"]] = files

    total_pool_files = sum(len(files) for files in pool_files_by_module.values())
    if total_pool_files:
        st.markdown("**Optional module pool entries**")
        st.caption("Select only the cross-run module snippets you want to include in this run.")
        for module in CONFIG["extraction"]["modules"]:
            files = pool_files_by_module[module["id"]]
            if not files:
                continue
            selected_names = st.multiselect(
                module["label"],
                [f.name for f in files],
                key=f"pool_select_{module['id']}",
                help=f"Choose which {module['label']} pool entries to include."
            )
            for filename in selected_names:
                selected_pool_entries.append(f"{module['id']}::{filename}")

    if st.button("Generate consolidated_extractions.md (2c)", use_container_width=True):
        with st.spinner("Consolidating..."):
            args = [str(run_path)]
            for entry in selected_pool_entries:
                args.extend(["--pool-entry", entry])
            success, output = run_script("format_consolidated.py", *args)
        if success:
            st.success("Consolidated file generated.")
            st.rerun()
        else:
            st.error(f"Error: {output}")

    if consolidated_path.exists():
        st.success("consolidated_extractions.md is ready.")
        with st.expander("Preview consolidated file"):
            st.code(consolidated_path.read_text(encoding="utf-8"), language="markdown")
        with open(consolidated_path, "rb") as f:
            st.download_button(
                "Download consolidated_extractions.md",
                f,
                file_name="consolidated_extractions.md",
                mime="text/markdown",
                use_container_width=True
            )


# ─────────────────────────────────────────────
# Stage 3: Recombination
# ─────────────────────────────────────────────

def render_stage3(run_path: Path):
    stage_header(3, "Recombination (Tailor Step)")

    consolidated_path = run_path / "module_extractions" / "consolidated_extractions.md"

    if not consolidated_path.exists():
        st.warning("consolidated_extractions.md not found. Complete Stage 2c first.")
        return

    st.markdown(
        "Download the consolidated extraction file and the recombination prompt below. "
        "Submit both to Claude. Then paste Claude's full output in Stage 4."
    )

    with open(consolidated_path, "rb") as f:
        st.download_button(
            "Download consolidated_extractions.md",
            f,
            file_name="consolidated_extractions.md",
            mime="text/markdown",
            use_container_width=True
        )

    st.divider()
    st.markdown("#### Recombination Prompt")
    st.caption("Copy this prompt and submit it to Claude together with the consolidated file.")

    prompt = generate_recombination_prompt()
    st.text_area(
        "Recombination prompt",
        value=prompt,
        height=340,
        key=f"recombination_prompt_{run_path.name}",
        help="Click inside the field and use Ctrl+C / Cmd+C to copy the prompt."
    )
    st.info("Use Ctrl+C / Cmd+C after selecting the prompt above. This is more reliable than browser script-based copying.")

    st.divider()
    st.markdown("#### Active Hard Filters")
    st.caption("These filters are embedded in the prompt above.")
    cfg = CONFIG["filters"]
    st.markdown("**Required instruments** (at least one must be present):")
    for item in cfg["required_instruments"]:
        st.markdown(f"- {item}")
    st.markdown("**Excluded instruments**:")
    for item in cfg["excluded_instruments"]:
        st.markdown(f"- {item}")
    st.markdown("**Excluded populations**:")
    for item in cfg["excluded_populations"]:
        st.markdown(f"- {item}")


def generate_recombination_prompt() -> str:
    cfg = CONFIG["filters"]
    labels = [module["label"] for module in CONFIG["extraction"]["modules"]]
    required = "\n".join(f"   - {i}" for i in cfg["required_instruments"])
    excluded_inst = "\n".join(f"   - {i}" for i in cfg["excluded_instruments"])
    excluded_pop = "\n".join(f"   - {i}" for i in cfg["excluded_populations"])

    return f"""You will receive structured extractions from multiple research papers. Each paper has been summarized across six modules: {", ".join(labels)}.

Your task is to generate candidate research directions by combining modules from different papers. Each candidate direction must draw its components from at least two different source papers.

Apply the following hard filters. Discard any candidate that fails any one of them:
1. The Measurement Instruments component must include at least one of the following:
{required}
2. The Measurement Instruments component must not include any of the following:
{excluded_inst}
3. The participant requirements must not involve any of the following:
{excluded_pop}

For each candidate direction that passes all filters, output the following:

**Candidate [N]**
- Source papers: [list paper IDs]
- {labels[0]}: [which paper, what content]
- {labels[1]}: [which paper, what content]
- {labels[2]} being addressed: [which paper, what content]
- {labels[4]}: [which paper, what content]
- {labels[5]}: [which paper, what content]
- Research question: [one concise statement of the research question this combination implies]
- Internal consistency check: [one sentence noting whether the combined components are logically compatible, and flagging any tension if present]

Generate as many candidates as the combinations reasonably support. Do not filter by research type or thematic focus beyond the three hard criteria above."""


# ─────────────────────────────────────────────
# Stage 4: Evaluation
# ─────────────────────────────────────────────

def render_stage4(run_path: Path):
    stage_header(4, "Evaluation")

    candidates_dir = run_path / "candidates"
    raw_path = candidates_dir / "candidates_raw.md"
    eval_path = candidates_dir / "evaluation_record.md"

    st.markdown("#### Step 4a — Paste Claude Output")
    st.caption(
        "Paste Claude's full recombination output below. "
        "The application will parse it into individual candidate files."
    )

    raw_text = st.text_area(
        "Claude output",
        height=300,
        placeholder="Paste Claude's full output here...",
        value=raw_path.read_text(encoding="utf-8") if raw_path.exists() else ""
    )

    if st.button("Parse candidates", type="primary", use_container_width=True):
        if not raw_text.strip():
            st.warning("No content to parse.")
        else:
            raw_path.write_text(raw_text, encoding="utf-8")
            with st.spinner("Parsing..."):
                success, output = run_script("parse_candidates.py", str(run_path))
            if success:
                st.success("Candidates parsed successfully.")
                st.rerun()
            else:
                st.error(f"Error: {output}")

    parsed = sorted(candidates_dir.glob("candidate_*.md"))
    if not parsed:
        return

    st.divider()
    st.markdown(f"#### Step 4b — Evaluation Record ({len(parsed)} candidate(s))")
    st.caption(
        "Review each candidate and record your decision and rationale. "
        "The evaluation record is saved automatically."
    )

    existing_eval = load_evaluation_record(eval_path)

    decisions = {}
    rationales = {}

    for candidate_file in parsed:
        candidate_id = candidate_file.stem
        st.markdown(f"---\n**{candidate_id.replace('_', ' ').title()}**")

        with st.expander("View candidate"):
            st.markdown(candidate_file.read_text(encoding="utf-8"))

        prev = existing_eval.get(candidate_id, {})
        col1, col2 = st.columns([1, 3])
        with col1:
            decisions[candidate_id] = st.selectbox(
                "Decision",
                ["Pending", "Keep", "Discard"],
                index=["Pending", "Keep", "Discard"].index(prev.get("decision", "Pending")),
                key=f"decision_{candidate_id}"
            )
        with col2:
            rationales[candidate_id] = st.text_input(
                "Rationale",
                value=prev.get("rationale", ""),
                key=f"rationale_{candidate_id}"
            )

    if st.button("Save evaluation record", type="primary", use_container_width=True):
        save_evaluation_record(eval_path, decisions, rationales)
        st.success(f"Saved to `{eval_path.name}`")

    if eval_path.exists():
        st.divider()
        st.markdown("#### Step 4c — Use Record as Workflow Input")
        st.caption(
            "After multiple runs, submit accumulated evaluation records to Claude "
            "to refine the extraction modules or recombination prompt."
        )
        with open(eval_path, "rb") as f:
            st.download_button(
                "Download evaluation_record.md",
                f,
                file_name=f"{run_path.name}_evaluation_record.md",
                mime="text/markdown",
                use_container_width=True
            )


def load_evaluation_record(path: Path) -> dict:
    if not path.exists():
        return {}
    result = {}
    current_id = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            current_id = line[3:].strip().lower().replace(" ", "_")
            result[current_id] = {}
        elif line.startswith("- Decision:") and current_id:
            result[current_id]["decision"] = line.split(":", 1)[1].strip()
        elif line.startswith("- Rationale:") and current_id:
            result[current_id]["rationale"] = line.split(":", 1)[1].strip()
    return result

def save_evaluation_record(path: Path, decisions: dict, rationales: dict):
    lines = ["# Evaluation Record\n"]
    for candidate_id in decisions:
        label = candidate_id.replace("_", " ").title()
        lines.append(f"## {label}")
        lines.append(f"- Decision: {decisions[candidate_id]}")
        lines.append(f"- Rationale: {rationales[candidate_id]}\n")
    path.write_text("\n".join(lines), encoding="utf-8")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="LitRecombine",
        page_icon="🔬",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    init_dirs()

    if "active_run" not in st.session_state:
        page_home()
    else:
        page_run()

if __name__ == "__main__":
    main()
