from __future__ import annotations

from pathlib import Path

import structlog

logger = structlog.get_logger()


class XlsxParser:
    """Excel XLSX parser using openpyxl."""

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() in {".xlsx", ".xls"}

    def parse(self, path: Path) -> str | None:
        try:
            from openpyxl import load_workbook

            wb = load_workbook(str(path), read_only=True, data_only=True)
            sheets: list[str] = []

            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                rows = []
                for row in ws.iter_rows(values_only=True):
                    cells = [str(c) if c is not None else "" for c in row]
                    if any(c.strip() for c in cells):
                        rows.append(" | ".join(cells))
                if rows:
                    sheets.append(f"## {sheet_name}\n\n" + "\n".join(rows))

            wb.close()
            text = "\n\n".join(sheets)
            if len(text.strip()) < 20:
                logger.warning("xlsx_parse_empty", path=str(path))
                return None
            return text.strip()
        except Exception:
            logger.warning("xlsx_parse_failed", path=str(path))
            return None
