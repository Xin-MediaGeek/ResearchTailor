"""
Stage 4a: Parse Claude's recombination output into individual candidate Markdown files.
Reads candidates_raw.md from the candidates/ folder and writes candidate_NNN.md per candidate.

Usage: python parse_candidates.py <run_path>
"""

import sys
import re
from pathlib import Path


# ─────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────

# Matches lines like: **Candidate 1**, **Candidate [1]**, Candidate 12, etc.
CANDIDATE_HEADER = re.compile(
    r"^\*{0,2}Candidate\s+\[?(\d+)\]?\*{0,2}\s*$",
    re.IGNORECASE
)


def split_candidates(raw_text: str) -> list[tuple[int, str]]:
    """
    Split raw text into (candidate_number, content) tuples.
    Each candidate block starts at a Candidate N header.
    """
    lines = raw_text.splitlines()
    candidates = []
    current_number = None
    current_lines = []

    for line in lines:
        match = CANDIDATE_HEADER.match(line.strip())
        if match:
            if current_number is not None:
                content = "\n".join(current_lines).strip()
                if content:
                    candidates.append((current_number, content))
            current_number = int(match.group(1))
            current_lines = [line]
        else:
            if current_number is not None:
                current_lines.append(line)

    if current_number is not None:
        content = "\n".join(current_lines).strip()
        if content:
            candidates.append((current_number, content))

    return candidates


def render_candidate_markdown(number: int, content: str) -> str:
    return f"# Candidate {number:03d}\n\n{content}\n"


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python parse_candidates.py <run_path>")
        sys.exit(1)

    run_path = Path(sys.argv[1])
    candidates_dir = run_path / "candidates"
    raw_path = candidates_dir / "candidates_raw.md"

    if not raw_path.exists():
        print(f"candidates_raw.md not found at {raw_path}")
        sys.exit(1)

    raw_text = raw_path.read_text(encoding="utf-8")
    if not raw_text.strip():
        print("candidates_raw.md is empty.")
        sys.exit(1)

    candidates = split_candidates(raw_text)

    if not candidates:
        print(
            "No candidates found. Check that Claude's output uses "
            "'**Candidate N**' or '**Candidate [N]**' as section headers."
        )
        sys.exit(1)

    # Remove any previously parsed individual files to avoid stale data
    for old_file in candidates_dir.glob("candidate_*.md"):
        old_file.unlink()

    written = []
    for number, content in candidates:
        out_path = candidates_dir / f"candidate_{number:03d}.md"
        out_path.write_text(
            render_candidate_markdown(number, content),
            encoding="utf-8"
        )
        written.append(out_path.name)
        print(f"  [ok] {out_path.name}")

    print(f"\n{len(written)} candidate(s) parsed and saved.")

    # Initialize evaluation record with empty entries if it does not exist
    eval_path = candidates_dir / "evaluation_record.md"
    if not eval_path.exists():
        lines = ["# Evaluation Record\n"]
        for number, _ in candidates:
            lines.append(f"## Candidate {number:03d}")
            lines.append("- Decision: Pending")
            lines.append("- Rationale: \n")
        eval_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"Evaluation record initialized: {eval_path.name}")


if __name__ == "__main__":
    main()
