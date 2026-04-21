"""
Stage 2a: Extract full text from PDFs and save as JSON.
Usage: python extract_text.py <run_path>
"""

import sys
import json
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("pdfplumber not installed. Run: pip install pdfplumber")
    sys.exit(1)


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


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_text.py <run_path>")
        sys.exit(1)

    run_path = Path(sys.argv[1])
    papers_dir = run_path / "papers"
    output_dir = run_path / "extracted_text"
    output_dir.mkdir(exist_ok=True)

    pdfs = sorted(papers_dir.glob("*.pdf"))
    if not pdfs:
        print("No PDFs found in papers/")
        sys.exit(1)

    print(f"Found {len(pdfs)} PDF(s). Extracting...")

    errors = []
    for pdf_path in pdfs:
        out_path = output_dir / f"{pdf_path.stem}_fulltext.json"
        if out_path.exists():
            print(f"  [skip] {pdf_path.name} (already extracted)")
            continue
        try:
            data = extract_pdf_text(pdf_path)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if data.get("error") == "empty_text":
                print(f"  [warn] {pdf_path.name}: no text extracted (possibly a scanned/image PDF). JSON saved.")
            else:
                print(f"  [ok]   {pdf_path.name} -> {out_path.name}")
        except Exception as e:
            errors.append((pdf_path.name, str(e)))
            print(f"  [err]  {pdf_path.name}: {e}")

    if errors:
        print(f"\nCompleted with {len(errors)} error(s):")
        for name, msg in errors:
            print(f"  {name}: {msg}")
        sys.exit(1)
    else:
        print("\nAll PDFs extracted successfully.")


if __name__ == "__main__":
    main()
