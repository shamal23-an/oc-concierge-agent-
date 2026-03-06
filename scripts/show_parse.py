"""Show full parsed content + chunks for a single PDF.

Usage:
    uv run python scripts/show_parse.py "path/to/file.pdf"
    uv run python scripts/show_parse.py --list              # list all KB PDFs
    uv run python scripts/show_parse.py --pick N            # pick Nth PDF from list
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ingestion.parsers.pdf import PdfParser
from src.ingestion.chunker import chunk_text

KB_ROOT = Path(__file__).resolve().parent.parent.parent / "knowldge_base" / "Concierge"

BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def hr(char="-", width=100):
    print(f"{DIM}{char * width}{RESET}")


def list_pdfs():
    pdfs = sorted(KB_ROOT.rglob("*.pdf"))
    print(f"\n{BOLD}Knowledge Base PDFs ({len(pdfs)} total){RESET}\n")
    for i, p in enumerate(pdfs, 1):
        rel = p.relative_to(KB_ROOT)
        print(f"  {CYAN}{i:3d}{RESET}  {rel}")
    print(f"\n  Usage: uv run python scripts/show_parse.py --pick <number>")
    return pdfs


def show_pdf(pdf_path: Path):
    parser = PdfParser()

    print(f"\n{BOLD}{'=' * 100}{RESET}")
    print(f"{BOLD}FILE: {CYAN}{pdf_path.name}{RESET}")
    print(f"{DIM}{pdf_path}{RESET}")
    print(f"{BOLD}{'=' * 100}{RESET}\n")

    if not pdf_path.exists():
        print(f"{RED}File not found!{RESET}")
        return

    # ── STEP 1: Raw parsed output ──────────────────────────────────────────
    text = parser.parse(pdf_path)
    if not text:
        print(f"{RED}FAILED — parser returned None (likely image-based PDF){RESET}")
        return

    print(f"{BOLD}{YELLOW}STEP 1: PARSED CONTENT{RESET}")
    print(f"{DIM}({len(text)} chars){RESET}\n")
    hr()

    # Print with line numbers, highlight tables and markers
    for i, line in enumerate(text.split("\n"), 1):
        num = f"{DIM}{i:4d}{RESET} "
        if line.strip().startswith("|"):
            print(f"{num}{GREEN}{line}{RESET}")
        elif "<!-- TABLE:" in line or "<!-- PAGE:" in line:
            print(f"{num}{YELLOW}{line}{RESET}")
        elif line.strip().startswith("##"):
            print(f"{num}{CYAN}{BOLD}{line}{RESET}")
        else:
            print(f"{num}{line}")

    hr()
    table_rows = sum(1 for l in text.split("\n") if l.strip().startswith("|"))
    table_markers = text.count("<!-- TABLE:")
    page_markers = text.count("<!-- PAGE:")
    print(f"\n  {BOLD}Stats:{RESET} {len(text)} chars | "
          f"{GREEN}{table_rows} table rows{RESET} | "
          f"{YELLOW}{table_markers} TABLE markers{RESET} | "
          f"{YELLOW}{page_markers} PAGE markers{RESET}")

    # ── STEP 2: Section-aware chunks ───────────────────────────────────────
    print(f"\n\n{BOLD}{YELLOW}STEP 2: SECTION-AWARE CHUNKS{RESET}\n")

    chunks = chunk_text(text, metadata={"source_file": pdf_path.name})
    print(f"  {BOLD}{len(chunks)} chunks{RESET} generated\n")

    for i, c in enumerate(chunks):
        sec = c.section_title or "(no section)"
        pg = f"page {c.page_number}" if c.page_number else "page ?"
        has_table = "| " in c.text and "---" in c.text

        # Chunk header
        hr("=")
        badge = f"{GREEN} [TABLE]{RESET}" if has_table else ""
        print(f"{BOLD}{CYAN}CHUNK {i}{RESET}  "
              f"section={BOLD}'{sec}'{RESET}  "
              f"{pg}  "
              f"len={len(c.text)}{badge}")
        hr("─")

        # Chunk content with highlighting
        for line in c.text.split("\n"):
            if line.strip().startswith("|"):
                print(f"  {GREEN}{line}{RESET}")
            elif line.strip().startswith("##"):
                print(f"  {CYAN}{BOLD}{line}{RESET}")
            else:
                print(f"  {line}")
        print()

    # ── Summary ────────────────────────────────────────────────────────────
    hr("=")
    table_chunks = sum(1 for c in chunks if "|" in c.text and "---" in c.text)
    sections = set(c.section_title for c in chunks if c.section_title)
    print(f"\n{BOLD}SUMMARY{RESET}")
    print(f"  Chunks: {len(chunks)}")
    print(f"  Chunks with tables: {GREEN}{table_chunks}{RESET}")
    print(f"  Unique sections: {len(sections)}")
    for s in sorted(sections):
        print(f"    {CYAN}• {s}{RESET}")
    print()


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  uv run python scripts/show_parse.py <path.pdf>")
        print("  uv run python scripts/show_parse.py --list")
        print("  uv run python scripts/show_parse.py --pick <N>")
        return

    if sys.argv[1] == "--list":
        list_pdfs()
        return

    if sys.argv[1] == "--pick":
        pdfs = sorted(KB_ROOT.rglob("*.pdf"))
        n = int(sys.argv[2]) - 1
        if 0 <= n < len(pdfs):
            show_pdf(pdfs[n])
        else:
            print(f"Invalid pick. Range: 1-{len(pdfs)}")
        return

    show_pdf(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
