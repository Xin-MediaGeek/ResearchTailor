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
import re
import yaml
from pathlib import Path


# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

def load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path, "r") as f:
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

    for i, m in enumerate(modules):
        # Match section from this module header to the next
        next_headers = []
        for j in range(i + 1, len(modules)):
            next_headers.append(f"## {modules[j]['label']}")
            for alias in modules[j].get("aliases", []):
                next_headers.append(f"## {alias}")
        pattern_end = "|".join(re.escape(h) for h in next_headers) if next_headers else None

        possible_headers = [m["label"], *m.get("aliases", [])]
        header_matches = []
        for header_label in possible_headers:
            header = f"## {header_label}"
            start = text.find(header)
            if start != -1:
                header_matches.append((start, len(header)))

        if not header_matches:
            continue

        start, header_len = min(header_matches, key=lambda item: item[0])
        start += header_len
        if pattern_end:
            end_match = re.search(pattern_end, text[start:])
            end = start + end_match.start() if end_match else len(text)
        else:
            end = len(text)

        content = text[start:end].strip()
        result[m["id"]] = content if content else "Not reported"

    return result


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

def render_consolidated(
    modules: list[dict],
    paper_ids: list[str],
    all_extractions: dict,
    pool_entries: dict
) -> str:
    """
    Render consolidated Markdown organized by module.
    all_extractions: {paper_id: {module_id: content}}
    pool_entries: {module_id: [(label, content)]}
    """
    lines = ["# Consolidated Extractions\n"]
    lines.append(
        f"Papers included: {', '.join(paper_ids)}\n"
    )

    for m in modules:
        lines.append(f"---\n## Module: {m['label']}\n")

        for paper_id in paper_ids:
            content = all_extractions.get(paper_id, {}).get(m["id"], "Not reported")
            lines.append(f"**[{paper_id}]**")
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

    consolidated = render_consolidated(modules, paper_ids, all_extractions, pool_entries)
    output_path.write_text(consolidated, encoding="utf-8")
    print(f"\nConsolidated file written to: {output_path}")


if __name__ == "__main__":
    main()
