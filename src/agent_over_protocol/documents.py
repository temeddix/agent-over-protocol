# Copyright (c) 2026 Danny Kim
"""Document text extraction for workspace files."""

from __future__ import annotations

import csv
import re
import zipfile
from html.parser import HTMLParser
from io import StringIO
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

if TYPE_CHECKING:
    from pathlib import Path

WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DRAWING_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
SPREADSHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
OFFICE_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

TEXT_SUFFIXES = {
    ".cfg",
    ".conf",
    ".css",
    ".csv",
    ".env",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".log",
    ".md",
    ".py",
    ".rst",
    ".text",
    ".toml",
    ".tsv",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
OOXML_SUFFIXES = {".docx", ".pptx", ".xlsx", ".xlsm"}
LEGACY_OFFICE_SUFFIXES = {".doc", ".ppt", ".xls"}
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | OOXML_SUFFIXES


class DocumentReadError(RuntimeError):
    """Raised when a document cannot be extracted as text."""


def read_document(path: Path, *, max_chars: int) -> str:
    """Read a file or document as plain text."""
    suffix = path.suffix.lower()
    if suffix in LEGACY_OFFICE_SUFFIXES:
        message = (
            f"{suffix} is a legacy binary Office format. Save it as an OOXML "
            "file such as .docx, .xlsx, or .pptx first."
        )
        raise DocumentReadError(message)
    if suffix == ".docx":
        return _truncate(_read_docx(path), max_chars)
    if suffix == ".pptx":
        return _truncate(_read_pptx(path), max_chars)
    if suffix in {".xlsx", ".xlsm"}:
        return _truncate(_read_xlsx(path), max_chars)
    if suffix in TEXT_SUFFIXES or not suffix:
        return _truncate(_read_text_file(path), max_chars)
    message = f"Unsupported file type: {suffix or 'no extension'}"
    raise DocumentReadError(message)


def is_supported_document(path: Path) -> bool:
    """Return whether the reader can extract text from this path."""
    suffix = path.suffix.lower()
    return suffix in SUPPORTED_SUFFIXES or not suffix


def _read_text_file(path: Path) -> str:
    data = path.read_bytes()
    text = _decode_text(data)
    suffix = path.suffix.lower()
    if suffix in {".html", ".xml"}:
        return _strip_html(text)
    if suffix in {".csv", ".tsv"}:
        return _read_delimited_text(text, delimiter="\t" if suffix == ".tsv" else ",")
    return text


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp949"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _read_delimited_text(text: str, *, delimiter: str) -> str:
    reader = csv.reader(StringIO(text), delimiter=delimiter)
    lines: list[str] = []
    for index, row in enumerate(reader, start=1):
        values = " | ".join(cell.strip() for cell in row)
        lines.append(f"{index}: {values}")
    return "\n".join(lines)


def _strip_html(text: str) -> str:
    parser = _TextHTMLParser()
    parser.feed(text)
    return parser.text


class _TextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    @property
    def text(self) -> str:
        return "\n".join(part for part in self._parts if part)

    def handle_data(self, data: str) -> None:
        stripped = data.strip()
        if stripped:
            self._parts.append(stripped)


def _read_docx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            names = [
                "word/document.xml",
                *sorted(
                    name
                    for name in archive.namelist()
                    if name.startswith(("word/header", "word/footer", "word/footnotes"))
                    and name.endswith(".xml")
                ),
            ]
            parts: list[str] = []
            for name in names:
                if name in archive.namelist():
                    parts.extend(_word_paragraphs(archive.read(name)))
    except zipfile.BadZipFile as exc:
        message = "Invalid .docx file"
        raise DocumentReadError(message) from exc
    return "\n".join(parts)


def _word_paragraphs(data: bytes) -> list[str]:
    root = _parse_xml(data)
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{WORD_NS}p"):
        parts: list[str] = []
        for child in paragraph.iter():
            if child.tag == f"{WORD_NS}t" and child.text:
                parts.append(child.text)
            elif child.tag == f"{WORD_NS}tab":
                parts.append("\t")
            elif child.tag == f"{WORD_NS}br":
                parts.append("\n")
        text = "".join(parts).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def _read_pptx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            slide_names = sorted(
                (
                    name
                    for name in archive.namelist()
                    if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
                ),
                key=_slide_number,
            )
            slides: list[str] = []
            for index, name in enumerate(slide_names, start=1):
                lines = _drawing_text_lines(archive.read(name))
                if lines:
                    rendered_lines = "\n".join(f"- {line}" for line in lines)
                    slides.append(f"Slide {index}\n{rendered_lines}")
    except zipfile.BadZipFile as exc:
        message = "Invalid .pptx file"
        raise DocumentReadError(message) from exc
    return "\n\n".join(slides)


def _slide_number(name: str) -> int:
    match = re.search(r"slide(\d+)\.xml$", name)
    if match is None:
        return 0
    return int(match.group(1))


def _drawing_text_lines(data: bytes) -> list[str]:
    root = _parse_xml(data)
    return [
        text.text.strip()
        for text in root.iter(f"{DRAWING_NS}t")
        if text.text and text.text.strip()
    ]


def _read_xlsx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            shared_strings = _xlsx_shared_strings(archive)
            sheets = _xlsx_sheets(archive)
            sections: list[str] = []
            for sheet_name, sheet_path in sheets:
                if sheet_path not in archive.namelist():
                    continue
                rows = _xlsx_rows(archive.read(sheet_path), shared_strings)
                if rows:
                    sections.append(f"Sheet: {sheet_name}\n" + _format_xlsx_rows(rows))
    except zipfile.BadZipFile as exc:
        message = "Invalid .xlsx file"
        raise DocumentReadError(message) from exc
    return "\n\n".join(sections)


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = _parse_xml(archive.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root.iter(f"{SPREADSHEET_NS}si"):
        parts = [text.text or "" for text in item.iter(f"{SPREADSHEET_NS}t")]
        strings.append("".join(parts))
    return strings


def _xlsx_sheets(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    if "xl/workbook.xml" not in archive.namelist():
        return []
    relationships = _xlsx_relationships(archive)
    root = _parse_xml(archive.read("xl/workbook.xml"))
    sheets: list[tuple[str, str]] = []
    for sheet in root.iter(f"{SPREADSHEET_NS}sheet"):
        name = sheet.attrib.get("name", "Sheet")
        relationship_id = sheet.attrib.get(f"{OFFICE_REL_NS}id")
        target = relationships.get(relationship_id or "")
        if target is not None:
            sheets.append((name, f"xl/{target.lstrip('/')}"))
    if sheets:
        return sheets
    worksheet_names = sorted(
        (
            name
            for name in archive.namelist()
            if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
        ),
        key=_worksheet_number,
    )
    return [
        (f"Sheet {index}", name) for index, name in enumerate(worksheet_names, start=1)
    ]


def _xlsx_relationships(archive: zipfile.ZipFile) -> dict[str, str]:
    if "xl/_rels/workbook.xml.rels" not in archive.namelist():
        return {}
    root = _parse_xml(archive.read("xl/_rels/workbook.xml.rels"))
    relationships: dict[str, str] = {}
    for relationship in root.iter(f"{REL_NS}Relationship"):
        relationship_id = relationship.attrib.get("Id")
        target = relationship.attrib.get("Target")
        if relationship_id is not None and target is not None:
            relationships[relationship_id] = target
    return relationships


def _worksheet_number(name: str) -> int:
    match = re.search(r"sheet(\d+)\.xml$", name)
    if match is None:
        return 0
    return int(match.group(1))


def _xlsx_rows(
    data: bytes,
    shared_strings: list[str],
) -> list[tuple[int, list[tuple[str, str]]]]:
    root = _parse_xml(data)
    rows: list[tuple[int, list[tuple[str, str]]]] = []
    for row in root.iter(f"{SPREADSHEET_NS}row"):
        row_index = _int_or_zero(row.attrib.get("r"))
        values: list[tuple[str, str]] = []
        for cell in row.iter(f"{SPREADSHEET_NS}c"):
            value = _xlsx_cell_value(cell, shared_strings)
            if value:
                values.append((_cell_column(cell.attrib.get("r", "")), value))
        if values:
            rows.append((row_index, values))
    return rows


def _xlsx_cell_value(element: ET.Element, shared_strings: list[str]) -> str:
    cell_type = element.attrib.get("t")
    if cell_type == "inlineStr":
        inline_parts = [text.text or "" for text in element.iter(f"{SPREADSHEET_NS}t")]
        return "".join(inline_parts).strip()
    value = element.find(f"{SPREADSHEET_NS}v")
    if value is None or value.text is None:
        return ""
    raw = value.text.strip()
    if cell_type == "s":
        index = _int_or_zero(raw)
        if 0 <= index < len(shared_strings):
            return shared_strings[index].strip()
    return raw


def _format_xlsx_row(row_index: int, values: list[tuple[str, str]]) -> str:
    rendered = " | ".join(f"{column}={value}" for column, value in values)
    return f"{row_index}: {rendered}"


def _format_xlsx_rows(rows: list[tuple[int, list[tuple[str, str]]]]) -> str:
    return "\n".join(_format_xlsx_row(row_index, values) for row_index, values in rows)


def _cell_column(cell_reference: str) -> str:
    match = re.match(r"([A-Z]+)", cell_reference)
    if match is None:
        return "?"
    return match.group(1)


def _int_or_zero(value: str | None) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except ValueError:
        return 0


def _truncate(content: str, max_chars: int) -> str:
    stripped = content.strip()
    if max_chars <= 0 or len(stripped) <= max_chars:
        return stripped
    return (
        f"{stripped[:max_chars].rstrip()}\n\n"
        f"[Document truncated to {max_chars} characters.]"
    )


def _parse_xml(data: bytes) -> ET.Element:
    # OOXML files are user-controlled local documents; keep XML parsing isolated.
    return ET.fromstring(data)  # noqa: S314
