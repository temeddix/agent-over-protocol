# Copyright (c) 2026 Danny Kim
"""Tests for workspace browsing and document extraction."""

from __future__ import annotations

import zipfile
from typing import TYPE_CHECKING

import pytest

from agent_over_protocol.workspace import Workspace, WorkspaceError

if TYPE_CHECKING:
    from pathlib import Path


async def test_workspace_lists_reads_and_searches_text_files(tmp_path: Path) -> None:
    """The workspace can list, read, and search regular text files."""
    notes = tmp_path / "notes.md"
    notes.write_text("# Notes\nFind this Korean keyword: 문서탐색", encoding="utf-8")
    workspace = _workspace(tmp_path)

    listing = await workspace.list_directory(".")
    content = await workspace.read_file("notes.md")
    matches = await workspace.search_files("문서탐색")

    assert "[FILE] notes.md" in listing
    assert "Find this Korean keyword" in content
    assert "notes.md:" in matches


async def test_workspace_reads_office_ooxml_documents(tmp_path: Path) -> None:
    """The workspace extracts text from docx, pptx, and xlsx files."""
    _write_docx(tmp_path / "report.docx", "Word document body")
    _write_pptx(tmp_path / "deck.pptx", "PowerPoint slide text")
    _write_xlsx(tmp_path / "sheet.xlsx", "Excel cell text")
    workspace = _workspace(tmp_path)

    docx = await workspace.read_file("report.docx")
    pptx = await workspace.read_file("deck.pptx")
    xlsx = await workspace.read_file("sheet.xlsx")

    assert "Word document body" in docx
    assert "PowerPoint slide text" in pptx
    assert "A=Excel cell text" in xlsx


async def test_workspace_blocks_parent_directory_traversal(tmp_path: Path) -> None:
    """Workspace reads cannot escape the configured root."""
    workspace = _workspace(tmp_path)

    with pytest.raises(WorkspaceError, match="Parent directory traversal"):
        await workspace.read_file("../secret.txt")


def _workspace(root: Path) -> Workspace:
    return Workspace(
        root=root,
        max_read_chars=10_000,
        max_list_entries=100,
        max_search_results=10,
        max_search_file_bytes=1_000_000,
    )


def _write_docx(path: Path, text: str) -> None:
    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'
        f"{text}"
        "</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)


def _write_pptx(path: Path, text: str) -> None:
    xml = (
        '<p:sld xmlns:p="http://schemas.openxmlformats.org/'
        'presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/'
        'drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:txBody>'
        f"<a:p><a:r><a:t>{text}</a:t></a:r></a:p>"
        "</p:txBody></p:sp></p:spTree></p:cSld></p:sld>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", xml)


def _write_xlsx(path: Path, text: str) -> None:
    workbook = (
        '<workbook xmlns="http://schemas.openxmlformats.org/'
        'spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships"><sheets><sheet name="Sheet1" '
        'sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    relationships = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        'relationships"><Relationship Id="rId1" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    shared_strings = (
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<si><t>{text}</t></si></sst>"
    )
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/'
        'spreadsheetml/2006/main"><sheetData><row r="1">'
        '<c r="A1" t="s"><v>0</v></c></row></sheetData></worksheet>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/sharedStrings.xml", shared_strings)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
