"""Spreadsheet parsing (spec 10.1): CSV (charset detection, sniffed delimiter), XLSX (openpyxl, formula
results), XLS (xlrd). Spreadsheets are only read, never executed."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

import charset_normalizer
import openpyxl
import xlrd

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_DATA_ROWS = 50_000
KINDS = {".csv": "csv", ".xlsx": "xlsx", ".xls": "xls"}
CSV_DELIMITERS = [",", ";", "\t"]


class ParseError(Exception):
    """`code` is a 14.2 code: FILE_TOO_LARGE, FILE_UNREADABLE, FILE_NO_HEADER, FILE_UNSUPPORTED."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class Sheet:
    name: str
    headers: list[str] = field(default_factory=list)
    rows: list[tuple[int, list[Any]]] = field(default_factory=list)  # (source row number, cells)


def file_kind(filename: str) -> str:
    kind = KINDS.get(Path(filename).suffix.lower())
    if kind is None:
        raise ParseError("FILE_UNSUPPORTED")
    return kind


# ---------------------------------------------------------------- cell normalization
def normalize_cell(value: Any) -> Any:
    """Strings trimmed; dates -> ISO YYYY-MM-DD; numbers kept as numbers; blanks -> None."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == time(0) else value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat(timespec="seconds")
    if isinstance(value, int | float | Decimal):
        return value
    text = str(value).strip()
    return text or None


def number_as_text(value: int | float | Decimal) -> str:
    """Integral numbers without decimals and never in scientific notation (10.1, part_number column)."""
    if isinstance(value, int):
        return str(value)
    d = Decimal(str(value))
    if d == d.to_integral_value():
        return str(int(d))
    return format(d.normalize(), "f")


def _is_empty(cells: list[Any]) -> bool:
    return all(c is None for c in cells)


def _finish(name: str, raw_rows: list[tuple[int, list[Any]]]) -> Sheet:
    """Header row = first non-empty row; fully empty rows are skipped and not counted."""
    non_empty = [(n, cells) for n, cells in raw_rows if not _is_empty(cells)]
    if not non_empty:
        raise ParseError("FILE_NO_HEADER")
    header_row, header_cells = non_empty[0]
    width = max(len(c) for _, c in non_empty)

    def cell(cells: list[Any], col: int) -> Any:
        return cells[col] if col < len(cells) else None

    # Trailing columns with no header and no data are dropped.
    while width > 0 and cell(header_cells, width - 1) is None and all(
            cell(c, width - 1) is None for _, c in non_empty[1:]):
        width -= 1
    if width == 0:
        raise ParseError("FILE_NO_HEADER")
    headers: list[str] = []
    seen: dict[str, int] = {}
    for i in range(width):
        value = cell(header_cells, i)
        h = number_as_text(value) if isinstance(value, int | float | Decimal) else (str(value) if value is not None else "")
        h = h.strip() or f"Column {i + 1}"
        count = seen.get(h.lower(), 0) + 1
        seen[h.lower()] = count
        headers.append(h if count == 1 else f"{h} ({count})")
    data = [(n, (cells + [None] * width)[:width]) for n, cells in non_empty[1:]]
    if len(data) > MAX_DATA_ROWS:
        raise ParseError("FILE_TOO_LARGE")
    return Sheet(name=name, headers=headers, rows=data)


# ---------------------------------------------------------------- CSV
def _decode(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        best = charset_normalizer.from_bytes(data).best()
        if best is None:
            raise ParseError("FILE_UNREADABLE") from None
        return str(best)


def _sniff_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:50])
    try:
        return csv.Sniffer().sniff(sample, delimiters="".join(CSV_DELIMITERS)).delimiter
    except csv.Error:
        first = next((line for line in text.splitlines() if line.strip()), "")
        counts = {d: first.count(d) for d in CSV_DELIMITERS}
        return max(counts, key=lambda d: counts[d]) if max(counts.values()) > 0 else ","


def read_csv(data: bytes) -> list[Sheet]:
    text = _decode(data)
    if "\x00" in text:
        raise ParseError("FILE_UNREADABLE")
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=_sniff_delimiter(text), quotechar='"')
    rows: list[tuple[int, list[Any]]] = []
    try:
        for n, record in enumerate(reader, start=1):
            cells = [normalize_cell(c) for c in record]
            if _is_empty(cells):
                continue
            rows.append((n, cells))
            if len(rows) > MAX_DATA_ROWS + 1:  # + 1 for the header row
                raise ParseError("FILE_TOO_LARGE")
    except csv.Error as exc:
        raise ParseError("FILE_UNREADABLE") from exc
    return [_finish("", rows)]


# ---------------------------------------------------------------- XLSX
def read_xlsx(path: Path, only: str | None = None) -> list[Sheet]:
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises many types for corrupt files
        raise ParseError("FILE_UNREADABLE") from exc
    sheets: list[Sheet] = []
    try:
        for ws in wb.worksheets:
            if only is not None and ws.title != only:
                continue
            rows: list[tuple[int, list[Any]]] = []
            non_empty = 0
            for n, record in enumerate(ws.iter_rows(values_only=True), start=1):
                cells = [normalize_cell(c) for c in record]
                if _is_empty(cells):
                    continue
                rows.append((n, cells))
                non_empty += 1
                if non_empty > MAX_DATA_ROWS + 1:  # + 1 for the header row
                    raise ParseError("FILE_TOO_LARGE")
            try:
                sheets.append(_finish(ws.title, rows))
            except ParseError as err:
                if err.code != "FILE_NO_HEADER":
                    raise
    finally:
        wb.close()
    return sheets


# ---------------------------------------------------------------- XLS
def _xls_value(book: xlrd.book.Book, cell: xlrd.sheet.Cell) -> Any:
    if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
        return None
    if cell.ctype == xlrd.XL_CELL_DATE:
        try:
            return normalize_cell(xlrd.xldate.xldate_as_datetime(cell.value, book.datemode))
        except (xlrd.xldate.XLDateError, ValueError, OverflowError):
            return cell.value
    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
        return "TRUE" if cell.value else "FALSE"
    if cell.ctype == xlrd.XL_CELL_ERROR:
        return None
    if cell.ctype == xlrd.XL_CELL_NUMBER:
        v = float(cell.value)
        return int(v) if v.is_integer() else v
    return normalize_cell(cell.value)


def read_xls(data: bytes, only: str | None = None) -> list[Sheet]:
    try:
        book = xlrd.open_workbook(file_contents=data, on_demand=True)
    except Exception as exc:
        raise ParseError("FILE_UNREADABLE") from exc
    sheets: list[Sheet] = []
    try:
        for name in book.sheet_names():
            if only is not None and name != only:
                continue
            sh = book.sheet_by_name(name)
            if sh.nrows > MAX_DATA_ROWS + 10_000:
                raise ParseError("FILE_TOO_LARGE")
            rows = [(r + 1, [_xls_value(book, sh.cell(r, c)) for c in range(sh.ncols)]) for r in range(sh.nrows)]
            try:
                sheets.append(_finish(name, rows))
            except ParseError as err:
                if err.code != "FILE_NO_HEADER":
                    raise
    finally:
        book.release_resources()
    return sheets


def read_file(path: Path, kind: str, only_sheet: str | None = None) -> list[Sheet]:
    """All non-empty sheets (or just `only_sheet`). Raises ParseError."""
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ParseError("FILE_TOO_LARGE")
    if kind == "csv":
        sheets = read_csv(path.read_bytes())
    elif kind == "xlsx":
        sheets = read_xlsx(path, only_sheet)
    elif kind == "xls":
        sheets = read_xls(path.read_bytes(), only_sheet)
    else:
        raise ParseError("FILE_UNSUPPORTED")
    if not sheets:
        raise ParseError("FILE_NO_HEADER")
    return sheets
