"""
Stage 2b: Extract six modules from each paper via DeepSeek API.
Usage:
  python extract_modules.py <run_path>
  python extract_modules.py <run_path> --model deepseek-chat
  python extract_modules.py <run_path> --model deepseek-reasoner
"""

import json
import sys
import time
from pathlib import Path

import yaml

try:
    from openai import OpenAI
except ImportError:
    print("openai not installed. Run: pip install openai")
    sys.exit(1)


def load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_client(config: dict) -> OpenAI:
    return OpenAI(
        api_key=config["deepseek"]["api_key"],
        base_url=config["deepseek"]["base_url"]
    )


SYSTEM_PROMPT = """You are a research assistant extracting structured information from academic papers.
You extract only what is explicitly stated in the paper.
You never infer, paraphrase beyond what is stated, or fill missing information with plausible content.
If a module has no corresponding content in the paper, you output exactly: Not reported"""


def build_module_blocks(modules: list[dict]) -> str:
    return "\n\n".join(
        f"**Module {i + 1} — {m['label']}**\n{m['description']}"
        for i, m in enumerate(modules)
    )


def get_header_variants(module: dict, index: int) -> list[str]:
    labels = [module["label"], *module.get("aliases", [])]
    variants = []
    for label in labels:
        variants.extend([
            f"**Module {index + 1} — {label}**",
            f"Module {index + 1} — {label}",
            f"**{label}**",
            label + ":",
        ])
    return variants


def split_text_into_chunks(
    full_text: str,
    max_chars: int = 50000,
    overlap_chars: int = 3000
) -> list[str]:
    if len(full_text) <= max_chars:
        return [full_text]

    chunks = []
    start = 0
    text_length = len(full_text)
    while start < text_length:
        end = min(start + max_chars, text_length)
        if end < text_length:
            split_at = full_text.rfind("\n\n", start, end)
            if split_at > start + max_chars // 2:
                end = split_at

        chunk = full_text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= text_length:
            break
        start = max(0, end - overlap_chars)

    return chunks


def build_extraction_prompt(
    paper_id: str,
    full_text: str,
    modules: list[dict],
    chunk_index: int | None = None,
    chunk_total: int | None = None
) -> str:
    chunk_note = ""
    if chunk_index is not None and chunk_total is not None:
        chunk_note = (
            f"\nThis is chunk {chunk_index} of {chunk_total} from the same paper. "
            "Extract module evidence only from this chunk. "
            "If a module is not covered in this chunk, output exactly: Not reported.\n"
        )

    return f"""Extract the following six modules from this research paper.
For each module, provide only information explicitly stated in the paper.
If a module has no corresponding content, output exactly: Not reported

Paper ID: {paper_id}
{chunk_note}

{build_module_blocks(modules)}

---

PAPER TEXT:
{full_text}"""


def build_merge_prompt(paper_id: str, chunk_outputs: list[str], modules: list[dict]) -> str:
    joined = "\n\n---\n\n".join(
        f"### Chunk {idx}\n{content}" for idx, content in enumerate(chunk_outputs, start=1)
    )
    return f"""You will receive module extraction outputs produced from multiple chunks of the same paper.
Merge them into one final extraction for Paper ID: {paper_id}.

Rules:
- Preserve only information explicitly present in the chunk outputs.
- Do not invent, infer, or reconcile contradictions with outside knowledge.
- If a module is Not reported in every chunk, output exactly: Not reported
- When multiple chunks provide compatible details for the same module, combine them concisely into one entry.

Return the final answer using exactly these module headers:

{build_module_blocks(modules)}

CHUNK OUTPUTS:
{joined}"""


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


def parse_module_response(response_text: str, modules: list[dict]) -> dict:
    result = {m["id"]: "Not reported" for m in modules}

    lines = response_text.splitlines()
    current_module_id = None
    current_lines = []

    def flush(mid, collected):
        if mid:
            content = "\n".join(collected).strip()
            result[mid] = content if content else "Not reported"

    for line in lines:
        matched = False
        for i, m in enumerate(modules):
            header_variants = get_header_variants(m, i)
            for variant in header_variants:
                if line.strip().startswith(variant):
                    flush(current_module_id, current_lines)
                    current_module_id = m["id"]
                    current_lines = []
                    matched = True
                    break
            if matched:
                break

        if not matched and current_module_id:
            current_lines.append(line)

    flush(current_module_id, current_lines)
    return result


def render_extraction_markdown(paper_id: str, modules: list[dict], extracted: dict) -> str:
    lines = [f"# Module Extraction: {paper_id}\n"]
    for m in modules:
        content = extracted.get(m["id"], "Not reported")
        lines.append(f"## {m['label']}")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_modules.py <run_path>")
        sys.exit(1)

    run_path = Path(sys.argv[1])
    model_override = None
    extra_args = sys.argv[2:]
    i = 0
    while i < len(extra_args):
        if extra_args[i] == "--model":
            if i + 1 >= len(extra_args):
                print("Missing value after --model")
                sys.exit(1)
            model_override = extra_args[i + 1]
            i += 2
        else:
            print(f"Unknown argument: {extra_args[i]}")
            sys.exit(1)

    fulltext_dir = run_path / "extracted_text"
    output_dir = run_path / "module_extractions"
    output_dir.mkdir(exist_ok=True)

    config = load_config()
    modules = config["extraction"]["modules"]
    client = build_client(config)
    ds_config = config["deepseek"]
    if model_override:
        ds_config = {**ds_config, "model": model_override}

    json_files = sorted(fulltext_dir.glob("*_fulltext.json"))
    if not json_files:
        print("No full-text JSON files found. Run extract_text.py first.")
        sys.exit(1)

    print(f"Found {len(json_files)} paper(s). Extracting modules with {ds_config['model']}...")

    errors = []
    for json_path in json_files:
        paper_id = json_path.stem.replace("_fulltext", "")
        out_path = output_dir / f"{paper_id}_extraction.md"

        if out_path.exists():
            print(f"  [skip] {paper_id} (already extracted)")
            continue

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            full_text = data.get("full_text", "")
            if not full_text.strip():
                print(f"  [warn] {paper_id}: empty full text, skipping.")
                continue

            text_chunks = split_text_into_chunks(full_text)
            chunk_outputs = []
            total_chunks = len(text_chunks)

            for idx, chunk_text in enumerate(text_chunks, start=1):
                prompt = build_extraction_prompt(
                    paper_id,
                    chunk_text,
                    modules,
                    chunk_index=idx if total_chunks > 1 else None,
                    chunk_total=total_chunks if total_chunks > 1 else None
                )
                chunk_outputs.append(call_model(client, ds_config, prompt))
                if total_chunks > 1:
                    print(f"    [chunk] {paper_id}: {idx}/{total_chunks}")
                    time.sleep(1)

            if total_chunks == 1:
                response_text = chunk_outputs[0]
            else:
                merge_prompt = build_merge_prompt(paper_id, chunk_outputs, modules)
                response_text = call_model(client, ds_config, merge_prompt)

            extracted = parse_module_response(response_text, modules)
            markdown = render_extraction_markdown(paper_id, modules, extracted)

            out_path.write_text(markdown, encoding="utf-8")
            print(f"  [ok]   {paper_id} -> {out_path.name}")

            time.sleep(1)

        except Exception as e:
            errors.append((paper_id, str(e)))
            print(f"  [err]  {paper_id}: {e}")

    if errors:
        print(f"\nCompleted with {len(errors)} error(s):")
        for name, msg in errors:
            print(f"  {name}: {msg}")
        sys.exit(1)

    print("\nAll modules extracted successfully.")


if __name__ == "__main__":
    main()
