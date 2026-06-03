# Copyright (c) 2026 Danny Kim
"""Tests for workspace browsing and document extraction."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from openpyxl import Workbook

from agent_over_protocol.documents import DocumentReader, JsonObject
from agent_over_protocol.workspace import Workspace, WorkspaceError

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_httpx import HTTPXMock


async def test_workspace_lists_reads_and_searches_text_files(tmp_path: Path) -> None:
    """The workspace can list, read, and search regular text files."""
    notes = tmp_path / "notes.md"
    notes.write_text("# Notes\nFind this Korean keyword: 문서탐색", encoding="utf-8")
    workspace = _workspace(tmp_path)

    listing = await workspace.list_directory(".")
    content = await workspace.read_file("notes.md")
    matches = await workspace.search_files("문서탐색")

    assert listing["entries"] == [
        {
            "kind": "file",
            "name": "notes.md",
            "path": "notes.md",
            "size_bytes": notes.stat().st_size,
        }
    ]
    document = cast("JsonObject", content["document"])
    assert document["kind"] == "text_document"
    text = document["text"]
    assert isinstance(text, str)
    assert "Find this Korean keyword" in text
    assert matches["results"] == [
        {
            "path": "notes.md",
            "snippet": "Find this Korean keyword: 문서탐색",
        }
    ]


async def test_workspace_reads_excel_as_structured_sheets(tmp_path: Path) -> None:
    """Excel files are returned as sheets, rows, and addressed cells."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Budget"
    sheet["A1"] = "Item"
    sheet["B1"] = "Amount"
    sheet["A2"] = "Hosting"
    sheet["B2"] = 42
    workbook.save(tmp_path / "budget.xlsx")
    workspace = _workspace(tmp_path)

    result = await workspace.read_file("budget.xlsx")

    document = cast("JsonObject", result["document"])
    assert document["kind"] == "spreadsheet"
    assert document["sheets"] == [
        {
            "name": "Budget",
            "rows": [
                {
                    "index": 1,
                    "cells": [
                        {"address": "A1", "row": 1, "column": "A", "value": "Item"},
                        {"address": "B1", "row": 1, "column": "B", "value": "Amount"},
                    ],
                },
                {
                    "index": 2,
                    "cells": [
                        {"address": "A2", "row": 2, "column": "A", "value": "Hosting"},
                        {"address": "B2", "row": 2, "column": "B", "value": 42},
                    ],
                },
            ],
        }
    ]
    text = document["text"]
    assert isinstance(text, str)
    assert "Budget: A2=Hosting | B2=42" in text


async def test_workspace_uses_tika_for_pdf_documents(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    """Non-spreadsheet binary documents are extracted through Tika."""
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-pretend")
    httpx_mock.add_response(
        method="PUT",
        url="http://tika.test/rmeta/text",
        json=[
            {
                "Content-Type": "application/pdf",
                "X-TIKA:content": "Extracted PDF text",
            }
        ],
    )
    workspace = _workspace(tmp_path)

    result = await workspace.read_file("report.pdf")

    assert result["document"] == {
        "kind": "text_document",
        "format": "pdf",
        "metadata": {"Content-Type": "application/pdf"},
        "text": "Extracted PDF text",
    }


async def test_workspace_encodes_non_ascii_tika_filename_header(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    """Tika requests keep non-ASCII filenames out of raw HTTP headers."""
    pdf = tmp_path / "회의록.pdf"
    pdf.write_bytes(b"%PDF-pretend")
    httpx_mock.add_response(
        method="PUT",
        url="http://tika.test/rmeta/text",
        json=[{"X-TIKA:content": "Extracted PDF text"}],
    )
    workspace = _workspace(tmp_path)

    await workspace.read_file("회의록.pdf")

    request = httpx_mock.get_request(
        method="PUT",
        url="http://tika.test/rmeta/text",
    )
    assert request is not None
    disposition = request.headers["Content-Disposition"]
    assert disposition.isascii()
    assert "filename*=UTF-8''%ED%9A%8C%EC%9D%98%EB%A1%9D.pdf" in disposition


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
        document_reader=DocumentReader(
            tika_url="http://tika.test",
            tika_timeout_seconds=5.0,
            max_spreadsheet_rows=100,
            max_spreadsheet_columns=50,
        ),
    )
