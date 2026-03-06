"""Quick validation script for Phase 1 PDF parser + chunker.

Usage:
    uv run python scripts/test_parser.py [path_to_single_pdf]
    uv run python scripts/test_parser.py  # tests all key PDFs
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ingestion.parsers.pdf import PdfParser
from src.ingestion.chunker import chunk_text

KB_ROOT = Path(__file__).resolve().parent.parent.parent / "knowldge_base" / "Concierge"

# Key PDFs to test — rate cards, menus, restaurants (table-heavy)
TEST_PDFS = [
    KB_ROOT / "BHL RACK Rates 2024 & 2025.pdf",
    KB_ROOT / "Avondrood RACK Jan 2023 - 18 Dec 2025.pdf",
    KB_ROOT / "Camp Figtree RATES 2024.pdf",
    KB_ROOT / "Franschhoek" / "Avondrood Spa Menu 2026.pdf",
    KB_ROOT / "Franschhoek" / "Braai Menu Options (2).pdf",
    KB_ROOT / "Cape Town" / "OC Travel & Tours 2024 RACK Rates.pdf",
    KB_ROOT / "Franschhoek" / "Avondrood Recommends 2026.pdf",
    KB_ROOT / "Franschhoek" / "La Fontaine Menu 2026.pdf",
    KB_ROOT / "Cape Town" / "Blackheath Lodge  Recommends Restaurants - 2024_pdf.pdf",
    KB_ROOT / "Addo" / "Camp Figtree Resturaunt Brochure.pdf",
]


def test_pdf(pdf_path: Path) -> None:
    """Parse a single PDF and show results."""
    parser = PdfParser()
    sep = "=" * 80

    print(f"\n{sep}")
    print(f"FILE: {pdf_path.name}")
    print(f"PATH: {pdf_path}")
    print(sep)

    if not pdf_path.exists():
        print("  SKIPPED — file not found")
        return

    # 1. Parse
    text = parser.parse(pdf_path)
    if not text:
        print("  FAILED — parser returned None (empty/image-based PDF)")
        return

    print(f"  Parsed: {len(text)} chars")

    # 2. Check for table markers
    table_count = text.count("<!-- TABLE:")
    page_count = text.count("<!-- PAGE:")
    pipe_lines = sum(1 for line in text.split("\n") if line.strip().startswith("|"))
    print(f"  Tables: {table_count} TABLE markers, {pipe_lines} markdown table rows")
    print(f"  Pages: {page_count} PAGE markers")

    # 3. Show first table if found
    lines = text.split("\n")
    in_table = False
    table_lines = []
    for line in lines:
        if line.strip().startswith("|"):
            in_table = True
            table_lines.append(line)
        elif in_table:
            break
    if table_lines:
        print(f"\n  FIRST TABLE ({len(table_lines)} rows):")
        for tl in table_lines[:8]:
            print(f"    {tl}")
        if len(table_lines) > 8:
            print(f"    ... ({len(table_lines) - 8} more rows)")

    # 4. Chunk
    chunks = chunk_text(text, metadata={"source_file": pdf_path.name})
    print(f"\n  Chunks: {len(chunks)}")
    for i, c in enumerate(chunks[:3]):
        sec = c.section_title or "(no section)"
        pg = c.page_number or "?"
        print(f"    [{i}] section='{sec}' page={pg} len={len(c.text)}")
        # Show first 100 chars
        preview = c.text[:100].replace("\n", " ")
        print(f"        '{preview}...'")
    if len(chunks) > 3:
        print(f"    ... ({len(chunks) - 3} more chunks)")

    # 5. Check for table preservation in chunks
    table_chunks = [c for c in chunks if "|" in c.text and "---" in c.text]
    print(f"\n  Chunks containing tables: {len(table_chunks)}")


def main():
    if len(sys.argv) > 1:
        # Test a single PDF
        test_pdf(Path(sys.argv[1]))
    else:
        # Test all key PDFs
        print("Phase 1 Validation — PDF Parser + Section-Aware Chunker")
        print(f"Knowledge base: {KB_ROOT}")
        found = sum(1 for p in TEST_PDFS if p.exists())
        print(f"Testing {found}/{len(TEST_PDFS)} PDFs\n")

        results = {"ok": 0, "empty": 0, "missing": 0}
        for pdf in TEST_PDFS:
            if not pdf.exists():
                results["missing"] += 1
                print(f"  SKIP: {pdf.name} (not found)")
                continue
            parser = PdfParser()
            text = parser.parse(pdf)
            if text:
                results["ok"] += 1
            else:
                results["empty"] += 1
            test_pdf(pdf)

        print("\n" + "=" * 80)
        print(f"SUMMARY: {results['ok']} parsed, {results['empty']} empty, {results['missing']} missing")


if __name__ == "__main__":
    main()
