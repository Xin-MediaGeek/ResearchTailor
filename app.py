import streamlit as st
import yaml
import os
import subprocess
import sys
import time
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

def load_config():
    load_dotenv(Path(__file__).parent / ".env")
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    config.setdefault("deepseek", {})
    config["deepseek"]["api_key"] = os.getenv("DEEPSEEK_API_KEY", "")
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
    if not os.getenv("DEEPSEEK_API_KEY", "").strip():
        errors.append("`DEEPSEEK_API_KEY` is missing or empty in .env file")
    if not ds.get("base_url", "").strip():
        errors.append("`deepseek.base_url` is missing in config.yaml")
    if not ds.get("model", "").strip():
        errors.append("`deepseek.model` is missing in config.yaml")
    return errors


try:
    CONFIG = load_config()
    _CONFIG_ERROR: str | None = None
except Exception as e:
    CONFIG = {}
    _CONFIG_ERROR = str(e)

ROOT = Path(__file__).parent
PROJECTS_DIR = ROOT / CONFIG.get("paths", {}).get("projects_dir", "projects")
MODULE_POOL_DIR = ROOT / CONFIG.get("paths", {}).get("module_pool_dir", "module_pool")


# ─────────────────────────────────────────────
# Initialization
# ─────────────────────────────────────────────

def init_dirs():
    PROJECTS_DIR.mkdir(exist_ok=True)
    MODULE_POOL_DIR.mkdir(exist_ok=True)
    for module in CONFIG.get("extraction", {}).get("modules", []):
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
    if _CONFIG_ERROR:
        st.error(f"Failed to load config.yaml: {_CONFIG_ERROR}")
        st.stop()
    config_errors = validate_config(CONFIG)
    if config_errors:
        for msg in config_errors:
            st.error(f"Configuration error: {msg}")
        st.stop()
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
    if _CONFIG_ERROR:
        st.error(f"Failed to load config.yaml: {_CONFIG_ERROR}")
        st.stop()
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
    if pdfs:
        if st.button("Confirm collection and proceed to Stage 2", type="primary"):
            st.session_state[f"{run_path.name}_stage1_done"] = True
            st.success("Stage 1 confirmed.")


# ─────────────────────────────────────────────
# Stage 2: Structured Extraction
# ─────────────────────────────────────────────

def _parse_module_content(text: str, module, all_modules) -> str:
    """Extract the content for one module from a paper's extraction Markdown."""
    header = f"## {module['label']}"
    start = text.find(header)
    if start == -1:
        return "Not reported"
    start += len(header)
    end = len(text)
    for other in all_modules:
        if other["id"] == module["id"]:
            continue
        pos = text.find(f"## {other['label']}", start)
        if pos != -1 and pos < end:
            end = pos
    content = text[start:end].strip()
    return content if content else "Not reported"


def render_extraction_review(run_path: Path):
    """Review panel between 2b and 2c: per-module include/exclude toggles with inline editing."""
    import json as _json
    module_dir = run_path / "module_extractions"
    review_path = module_dir / "extraction_review.json"
    modules = CONFIG["extraction"]["modules"]

    extraction_files = sorted(module_dir.glob("*_extraction.md"))
    if not extraction_files:
        return

    st.markdown("#### Step 2b-Review — Review Extracted Modules")
    st.caption(
        "Review each paper's extracted modules before consolidation. "
        "Uncheck a module to exclude it, or edit its content directly. "
        "Edited content will be used in the consolidated file."
    )

    raw = _json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {}

    new_decisions = {}
    for idx, md_file in enumerate(extraction_files, start=1):
        paper_id = md_file.stem.replace("_extraction", "")
        text = md_file.read_text(encoding="utf-8")
        paper_existing = raw.get(paper_id, {})

        with st.expander(f"P{idx}: {paper_id}", expanded=False):
            new_decisions[paper_id] = {}
            for m in modules:
                original = _parse_module_content(text, m, modules)

                prev = paper_existing.get(m["id"], {})
                if isinstance(prev, bool):
                    default_include = prev
                    default_content = original
                elif isinstance(prev, dict):
                    default_include = prev.get("include", True)
                    default_content = prev.get("content") or original
                else:
                    default_include = True
                    default_content = original

                include = st.checkbox(
                    m["label"],
                    value=default_include,
                    key=f"review_{run_path.name}_{paper_id}_{m['id']}",
                )
                edited = st.text_area(
                    f"edit_{m['id']}",
                    value=default_content,
                    height=180,
                    key=f"review_content_{run_path.name}_{paper_id}_{m['id']}",
                    label_visibility="collapsed",
                    disabled=not include,
                )
                new_decisions[paper_id][m["id"]] = {
                    "include": include,
                    "content": edited,
                }
                st.divider()

    if st.button(
        "Save review decisions",
        key=f"save_review_{run_path.name}",
        use_container_width=True,
    ):
        review_path.write_text(
            _json.dumps(new_decisions, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        st.success("Review decisions saved.")


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

    available_models = ["deepseek-v4-flash", "deepseek-v4-pro"]
    legacy_map = {"deepseek-chat": "deepseek-v4-flash", "deepseek-reasoner": "deepseek-v4-pro"}

    default_model = CONFIG["deepseek"].get("model", "deepseek-v4-flash")
    default_model = legacy_map.get(default_model, default_model)
    if default_model not in available_models:
        default_model = available_models[0]

    col_m1, col_m2 = st.columns(2)
    with col_m1:
        selected_model = st.selectbox(
            "分块提取模型",
            available_models,
            index=available_models.index(default_model),
            help="每个分块的逐段提取使用此模型。推荐 deepseek-v4-flash：速度快、成本低。"
        )
    with col_m2:
        selected_merge_model = st.selectbox(
            "合并模型（长文多块合并）",
            available_models,
            index=available_models.index(default_model),
            help="论文超长时，多块结果的最终合并使用此模型。如需更强推理可选 deepseek-v4-pro。短文只有一块时此选项无效。"
        )
    st.caption(
        f"Configured default max_tokens: {CONFIG['deepseek']['max_tokens']}. "
        "单块论文仅调用分块提取模型；多块论文额外调用合并模型一次。"
    )

    existing_md = [f for f in module_dir.glob("*_extraction.md")]
    if existing_md:
        st.info(f"{len(existing_md)} module extraction file(s) already present.")
        with st.expander("View extracted files"):
            for md_file in existing_md:
                st.markdown(f"**{md_file.name}**")
                st.code(md_file.read_text(encoding="utf-8"), language="markdown")

    fulltext_json_files = list((run_path / "extracted_text").glob("*_fulltext.json"))
    existing_md_ids = {f.stem.replace("_extraction", "") for f in module_dir.glob("*_extraction.md")}
    pending_count = sum(
        1 for f in fulltext_json_files
        if f.stem.replace("_fulltext", "") not in existing_md_ids
    )
    if pending_count > 0:
        st.caption(f"{pending_count} paper(s) pending extraction.")

    if st.button("Run module extraction (2b)", use_container_width=True):
        progress_path = run_path / "2b_progress.json"
        if progress_path.exists():
            progress_path.unlink()

        script_path = ROOT / "scripts" / "extract_modules.py"
        proc = subprocess.Popen(
            [
                "python", str(script_path), str(run_path),
                "--model", selected_model,
                "--merge-model", selected_merge_model,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        bar_placeholder = st.empty()
        eta_placeholder = st.empty()

        while proc.poll() is None:
            if progress_path.exists():
                try:
                    prog = json.loads(progress_path.read_text(encoding="utf-8"))
                    total = prog.get("total", 0)
                    done = prog.get("done", 0)
                    skipped = prog.get("skipped", 0)
                    elapsed = prog.get("elapsed_per_paper", [])
                    current = prog.get("current_paper", "")
                    processed = done + skipped
                    if total > 0:
                        bar_placeholder.progress(
                            min(processed / total, 1.0),
                            text=f"Paper {processed} / {total}" + (f" — {current}" if current else ""),
                        )
                    if elapsed and total > 0:
                        avg = sum(elapsed) / len(elapsed)
                        remaining = max(total - processed, 0)
                        eta_sec = avg * remaining
                        mins, secs = divmod(int(eta_sec), 60)
                        eta_str = f"{mins} min {secs:02d} sec" if mins else f"{secs} sec"
                        eta_placeholder.caption(
                            f"Avg {avg:.0f} s/paper — est. **{eta_str}** remaining"
                        )
                    elif total > 0:
                        eta_placeholder.caption("Estimating time — waiting for first paper to complete...")
                except Exception:
                    pass
            time.sleep(2)

        stdout, stderr = proc.communicate()
        bar_placeholder.empty()
        eta_placeholder.empty()
        if progress_path.exists():
            progress_path.unlink()

        if proc.returncode == 0:
            st.success("Module extraction complete.")
            st.rerun()
        else:
            st.error(f"Error: {stderr or stdout}")

    st.divider()
    render_extraction_review(run_path)

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
            open_path_in_file_explorer(module_dir)
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
                use_container_width=True,
                key="dl_consolidated_stage2c"
            )


# ─────────────────────────────────────────────
# Stage 3: Recombination — prompt module helpers
# ─────────────────────────────────────────────

_MODULE_ORDER = ["task_intro", "source_constraint", "quality_rules", "hard_filters", "output_format"]

_MODULE_LABELS = {
    "task_intro":        "模块一：任务说明",
    "source_constraint": "模块二：来源约束",
    "quality_rules":     "模块三：质量要求",
    "hard_filters":      "模块四：硬性筛选条件",
    "output_format":     "模块五：输出格式",
}

_MODULE_HEIGHTS = {
    "task_intro": 120,
    "source_constraint": 120,
    "quality_rules": 100,
    "hard_filters": 160,
    "output_format": 280,
}


def default_prompt_modules() -> dict:
    cfg = CONFIG.get("filters", {})
    labels = [m["label"] for m in CONFIG.get("extraction", {}).get("modules", [])]
    labels_str = "、".join(labels) if labels else "各模块"

    required = "\n".join(f"   - {i}" for i in cfg.get("required_instruments", []))
    excluded_inst = "\n".join(f"   - {i}" for i in cfg.get("excluded_instruments", []))
    excluded_pop = "\n".join(f"   - {i}" for i in cfg.get("excluded_populations", []))

    return {
        "task_intro": (
            f"你将收到多篇研究论文的结构化提取内容。每篇论文已按以下模块进行总结：{labels_str}。\n\n"
            "你的任务是通过组合不同论文中的模块，生成候选研究方向。请用中文输出所有结果。"
        ),
        "source_constraint": (
            "每个候选方向的所有模块来源论文数必须大于1且不超过3篇。不同模块可以来自同一论文。"
            "不是每一篇论文都必须做出贡献。Paper ID必须使用输入文档中已有的编号，"
            "不得由推理模型自行命名或重新编号。"
        ),
        "quality_rules": (
            "只输出各模块真的能配合成一个新研究的候选方向，宁缺毋滥，不能为了得到结果而强行缝合。"
            "最多输出10个候选方向，按内部一致性分数从高到低排列。"
        ),
        "hard_filters": (
            "应用以下硬性筛选条件，任何一条不满足则丢弃该候选方向：\n"
            f"1. 实验测量方法必须至少包含以下之一：\n{required}\n"
            f"2. 实验测量方法不得包含以下任何内容：\n{excluded_inst}\n"
            f"3. 参与者要求不得涉及以下任何内容：\n{excluded_pop}"
        ),
        "output_format": (
            "对于每个通过筛选的候选方向，按以下格式输出：\n\n"
            "**Candidate [N]**\n"
            "- Research question: [一句话概括该组合所暗示的研究问题]\n"
            "- Source papers: [列出paper IDs]\n"
            "- Research Directions: [来自哪篇论文的Future Research Directions，具体内容]\n"
            "- Innovation method: [来自哪篇论文，什么内容]\n"
            "- Application Scenario: [哪篇论文，什么内容]\n"
            "- Evaluation Metrics: [哪篇论文，什么内容]\n"
            "- Experimental Measurement Methods: [哪篇论文，什么内容]\n"
            "- Internal consistency check: [一句话说明各组合模块是否逻辑兼容，如有张力请指出]，并输出分数（作为候选排序依据）"
        ),
    }


_GLOBAL_PROMPT_MODULES_PATH = ROOT / "prompt_modules_default.yaml"


def load_prompt_modules(run_path: Path) -> dict:
    defaults = default_prompt_modules()
    for path in [run_path / "recombination_prompt_modules.yaml", _GLOBAL_PROMPT_MODULES_PATH]:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return {k: data.get(k, defaults[k]) for k in _MODULE_ORDER}
    return defaults


def save_prompt_modules(run_path: Path, modules: dict):
    for path in [run_path / "recombination_prompt_modules.yaml", _GLOBAL_PROMPT_MODULES_PATH]:
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(modules, f, allow_unicode=True, default_flow_style=False)


def assemble_prompt(modules: dict) -> str:
    return "\n\n".join(modules[k] for k in _MODULE_ORDER)


def render_prompt_module_editor(run_path: Path, key_prefix: str) -> dict:
    saved = load_prompt_modules(run_path)
    result = {}
    for key in _MODULE_ORDER:
        result[key] = st.text_area(
            _MODULE_LABELS[key],
            value=saved[key],
            height=_MODULE_HEIGHTS[key],
            key=f"{key_prefix}_{key}_{run_path.name}",
        )
    return result


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
        "下载整合提取文件，并将合并后的提示词一起提交给 Claude。"
        "完成后将 Claude 的完整输出粘贴到 Stage 4。"
    )

    with open(consolidated_path, "rb") as f:
        st.download_button(
            "Download consolidated_extractions.md",
            f,
            file_name="consolidated_extractions.md",
            mime="text/markdown",
            use_container_width=True,
            key="dl_consolidated_stage3"
        )

    st.divider()
    st.markdown("#### Recombination Prompt — 模块化编辑")
    st.caption('按需修改各模块内容，点击"保存提示词配置"后在下方查看合并结果并复制。')

    modules = render_prompt_module_editor(run_path, key_prefix="s3")

    if st.button("保存提示词配置", use_container_width=True, key="save_prompt_s3"):
        save_prompt_modules(run_path, modules)
        st.success("提示词配置已保存。")

    st.divider()
    st.markdown("**合并后的完整提示词**")
    st.caption("使用右上角复制按钮将提示词连同整合文件一起提交给 Claude。")
    st.code(assemble_prompt(modules), language="text")


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

        st.divider()
        st.markdown("#### Step 4d — 精炼 Recombination Prompt")
        st.caption(
            "根据本轮评估结果，修改并保存下一轮的 Recombination Prompt。"
            "保存后，Stage 3 的提示词将自动更新。"
        )
        modules_4d = render_prompt_module_editor(run_path, key_prefix="s4d")
        if st.button("保存精炼后的提示词", type="primary", use_container_width=True, key="save_prompt_4d"):
            save_prompt_modules(run_path, modules_4d)
            st.success("提示词已保存，Stage 3 将在下次加载时使用更新后的配置。")
        st.markdown("**合并预览**")
        st.code(assemble_prompt(modules_4d), language="text")


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
