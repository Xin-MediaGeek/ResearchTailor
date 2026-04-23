"""
Stage 2c: Merge all per-paper module extractions into a single consolidated file.
Organized by module rather than by paper.
Optionally includes entries from the cross-run module pool.

Usage:
  python format_consolidated.py <run_path>
  python format_consolidated.py <run_path> --pool-entry <module_id::filename>
  python format_consolidated.py <run_path> --pool-entry <module_id::filename> --pool-entry <module_id::filename>
"""

import sys
import yaml
from pathlib import Path


# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

def load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────

def parse_extraction_file(md_path: Path, modules: list[dict]) -> dict:
    """
    Parse a per-paper extraction Markdown file into a dict keyed by module id.
    """
    text = md_path.read_text(encoding="utf-8")
    result = {m["id"]: "Not reported" for m in modules}

    # Map of module id → old Chinese labels used before the rename to English
    _LEGACY_LABELS = {"core_method": "核心创新"}

    for i, m in enumerate(modules):
        header = f"## {m['label']}"
        start = text.find(header)
        if start == -1:
            legacy = _LEGACY_LABELS.get(m["id"])
            if legacy:
                header = f"## {legacy}"
                start = text.find(header)
        if start == -1:
            continue
        start += len(header)

        end = len(text)
        for j in range(i + 1, len(modules)):
            next_label = modules[j]['label']
            next_pos = text.find(f"## {next_label}", start)
            if next_pos == -1:
                legacy_j = _LEGACY_LABELS.get(modules[j]["id"])
                if legacy_j:
                    next_pos = text.find(f"## {legacy_j}", start)
            if next_pos != -1:
                end = min(end, next_pos)
                break

        content = text[start:end].strip()
        result[m["id"]] = content if content else "Not reported"

    return result


def load_review_decisions(module_dir: Path) -> dict:
    """Load per-module inclusion decisions from extraction_review.json.
    Returns {paper_id: {module_id: bool}} where True = include.
    Returns empty dict if file is absent (all included by default)."""
    import json
    review_path = module_dir / "extraction_review.json"
    if not review_path.exists():
        return {}
    with open(review_path, encoding="utf-8") as f:
        return json.load(f)


def load_pool_entries(
    module_pool_dir: Path,
    module_id: str,
    selected_files: set[str] | None = None
) -> list[tuple[str, str]]:
    """
    Load all files from the module pool subfolder for a given module.
    Returns list of (label, content) tuples.
    """
    pool_sub = module_pool_dir / module_id
    entries = []
    if not pool_sub.exists():
        return entries
    for f in sorted(pool_sub.iterdir()):
        if f.is_file():
            if selected_files is not None and f.name not in selected_files:
                continue
            try:
                content = f.read_text(encoding="utf-8").strip()
                entries.append((f"[pool] {f.stem}", content))
            except Exception:
                pass
    return entries


# ─────────────────────────────────────────────
# Rendering
# ─────────────────────────────────────────────

def _resolve_module_decision(mod_dec) -> tuple[bool, str | None]:
    """Return (include, edited_content) from a review decision value.

    Handles both old format (bool) and new format (dict with include/content).
    edited_content is None when no override was recorded.
    """
    if isinstance(mod_dec, bool):
        return mod_dec, None
    if isinstance(mod_dec, dict):
        include = mod_dec.get("include", True)
        content = mod_dec.get("content") or None
        return include, content
    return True, None


def render_consolidated(
    modules: list[dict],
    paper_ids: list[str],
    all_extractions: dict,
    pool_entries: dict,
    review_decisions: dict | None = None,
) -> str:
    """
    Render consolidated Markdown organized by module.
    all_extractions: {paper_id: {module_id: content}}
    pool_entries: {module_id: [(label, content)]}
    review_decisions: {paper_id: {module_id: bool | {include, content}}}
    """
    lines = ["# Consolidated Extractions\n"]

    # Paper index
    lines.append("## Paper Index\n")
    for idx, paper_id in enumerate(paper_ids, start=1):
        lines.append(f"- P{idx}: {paper_id}")
    lines.append("")

    for m in modules:
        lines.append(f"---\n## Module: {m['label']}\n")

        for idx, paper_id in enumerate(paper_ids, start=1):
            include = True
            edited_content = None
            if review_decisions:
                paper_dec = review_decisions.get(paper_id, {})
                mod_dec = paper_dec.get(m["id"], True)
                include, edited_content = _resolve_module_decision(mod_dec)

            if not include:
                continue

            content = edited_content if edited_content else all_extractions.get(paper_id, {}).get(m["id"], "Not reported")
            lines.append(f"**[P{idx}]**")
            lines.append(content)
            lines.append("")

        for label, content in pool_entries.get(m["id"], []):
            lines.append(f"**{label}**")
            lines.append(content)
            lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python format_consolidated.py <run_path> [--pool-entry <module_id::filename> ...]")
        sys.exit(1)

    run_path = Path(sys.argv[1])
    selected_pool_files: dict[str, set[str]] = {}
    extra_args = sys.argv[2:]
    i = 0
    while i < len(extra_args):
        if extra_args[i] == "--pool-entry":
            if i + 1 >= len(extra_args):
                print("Missing value after --pool-entry")
                sys.exit(1)
            raw_value = extra_args[i + 1]
            if "::" not in raw_value:
                print(f"Invalid pool entry selector: {raw_value}")
                sys.exit(1)
            module_id, filename = raw_value.split("::", 1)
            selected_pool_files.setdefault(module_id, set()).add(filename)
            i += 2
        else:
            print(f"Unknown argument: {extra_args[i]}")
            sys.exit(1)

    config = load_config()
    modules = config["extraction"]["modules"]

    module_dir = run_path / "module_extractions"
    output_path = module_dir / "consolidated_extractions.md"

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

    all_extractions = {}
    paper_ids = []
    for f in extraction_files:
        paper_id = f.stem.replace("_extraction", "")
        paper_ids.append(paper_id)
        all_extractions[paper_id] = parse_extraction_file(f, modules)
        print(f"  [parsed] {f.name}")

    pool_entries = {m["id"]: [] for m in modules}
    if selected_pool_files:
        module_pool_dir = Path(__file__).parent.parent / config["paths"]["module_pool_dir"]
        for m in modules:
            entries = load_pool_entries(
                module_pool_dir,
                m["id"],
                selected_pool_files.get(m["id"], set())
            )
            pool_entries[m["id"]] = entries
            if entries:
                print(f"  [pool]   {m['label']}: {len(entries)} entry/entries included")

    review_decisions = load_review_decisions(module_dir)
    if review_decisions:
        edited_count = sum(
            1
            for paper_dec in review_decisions.values()
            for v in paper_dec.values()
            if isinstance(v, dict) and v.get("content")
        )
        print(f"[info] Applying extraction review decisions ({edited_count} module(s) with edited content)")

    consolidated = render_consolidated(modules, paper_ids, all_extractions, pool_entries, review_decisions)
    output_path.write_text(consolidated, encoding="utf-8")
    print(f"\nConsolidated file written to: {output_path}")


if __name__ == "__main__":
    main()
