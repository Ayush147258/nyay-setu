from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.document_intelligence.models import BlockKind, ParseStatus
from app.document_intelligence.parsers import ParserRouter


ROOT = Path(__file__).parent / "golden_corpus"


def test_golden_corpus_contains_40_verified_documents():
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    checksums = json.loads((ROOT / "checksums.json").read_text(encoding="utf-8"))

    assert manifest["document_count"] == 40
    assert len(manifest["documents"]) == 40
    assert len(checksums) == 40
    for item in manifest["documents"]:
        path = ROOT / "generated" / item["filename"]
        assert path.exists(), item["filename"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == checksums[path.name]


@pytest.mark.parametrize(
    ("filename", "media_type", "expected_format"),
    [
        ("judgment-01.pdf", "application/pdf", "pdf"),
        (
            "legal-memo-01.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "docx",
        ),
        (
            "case-register-01.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "spreadsheet",
        ),
    ],
)
def test_representative_golden_digital_documents_parse(
    filename,
    media_type,
    expected_format,
):
    path = ROOT / "generated" / filename
    result = ParserRouter().parse(
        path,
        filename,
        media_type,
        f"golden-test-{filename}",
    )

    assert result.status == ParseStatus.READY
    assert result.document_format.value == expected_format
    assert result.pages
    assert any(page.blocks for page in result.pages)


def test_golden_pdf_table_has_structured_cells():
    path = ROOT / "generated" / "evidence-table-01.pdf"
    result = ParserRouter().parse(
        path,
        path.name,
        "application/pdf",
        "golden-table",
    )

    assert result.status in {ParseStatus.READY, ParseStatus.PARTIAL}
    tables = [
        block
        for page in result.pages
        for block in page.blocks
        if block.kind == BlockKind.TABLE and block.table is not None
    ]
    assert tables
    assert tables[0].table.rows[0].cells[0].text == "Provision"
