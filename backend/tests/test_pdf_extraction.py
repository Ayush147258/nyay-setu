from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.document_intelligence.models import (
    BlockKind,
    DocumentBlock,
    ParseStatus,
)
from app.document_intelligence.parsers import ParserRouter
from app.document_intelligence.pdf_pipeline import (
    OcrPageResult,
    PdfExtractionError,
    PdfExtractionLimits,
    PdfExtractionPipeline,
    normalize_block_text,
    score_text_quality,
)


def write_pdf(path: Path, pages: list[str], *, rotation: int = 0):
    fitz = pytest.importorskip("fitz")
    document = fitz.open()
    for text in pages:
        page = document.new_page(width=595, height=842)
        if rotation:
            page.set_rotation(rotation)
        if text:
            page.insert_textbox(
                fitz.Rect(48, 56, 545, 790),
                text,
                fontsize=11,
            )
    document.save(path)
    document.close()


def fake_ocr_block(page_number: int, version_id: str) -> OcrPageResult:
    text = "OCR recovered FIR No. 123 of 2024 and filing date 12/03/2024."
    return OcrPageResult(
        blocks=[
            DocumentBlock(
                block_id="temporary",
                page_number=page_number,
                sequence=0,
                kind=BlockKind.IMAGE_TEXT,
                text=text,
                confidence=0.88,
            )
        ],
        confidence=0.88,
        orientation_correction=90,
        deskew_angle=-2.0,
    )


def test_text_quality_scores_legal_text_above_noise():
    legal = (
        "IN THE HIGH COURT OF DELHI\n"
        "W.P.(C) 1234/2024\n"
        "The petitioner challenges the order dated 12 March 2024."
    )
    noisy = "@@@@@ #### ????? \ufffd\ufffd\ufffd"

    assert score_text_quality(legal).score >= 0.75
    assert score_text_quality(noisy).score < 0.55
    assert normalize_block_text("A\x00  B\r\n\r\n C") == "A B\n\nC"


def test_digital_pdf_skips_ocr_and_validates_source_blocks(tmp_path, monkeypatch):
    path = tmp_path / "judgment.pdf"
    write_pdf(
        path,
        [
            "IN THE HIGH COURT OF DELHI\n"
            "Judgment in W.P.(C) 1234 of 2024. "
            "The petition was decided after hearing both parties. "
            "The complete factual record and reasons are set out below."
        ],
    )
    pipeline = PdfExtractionPipeline(PdfExtractionLimits())

    def unexpected_ocr(*_args, **_kwargs):
        raise AssertionError("OCR must not run for a strong digital page")

    monkeypatch.setattr(pipeline, "_ocr_page", unexpected_ocr)
    result = pipeline.extract(path, "version-digital")

    assert result.status == ParseStatus.READY
    assert result.pages[0].extraction_method == "digital"
    assert result.pages[0].confidence >= 0.55
    assert result.pages[0].metadata["detected_as_scanned"] is False
    assert result.metadata["digital_pages"] == 1
    assert result.metadata["ocr_pages"] == 0
    assert result.metadata["incremental_page_processing"] is True
    assert all(
        block.metadata["source_span_validated"]
        for block in result.pages[0].blocks
    )


def test_weak_page_uses_ocr_and_surfaces_rotation_deskew(tmp_path, monkeypatch):
    path = tmp_path / "scan.pdf"
    write_pdf(path, [""])
    pipeline = PdfExtractionPipeline(PdfExtractionLimits())
    calls = []

    def fake_ocr(_page, page_number, version_id, _width, _height):
        calls.append(page_number)
        return fake_ocr_block(page_number, version_id)

    monkeypatch.setattr(pipeline, "_ocr_page", fake_ocr)
    result = pipeline.extract(path, "version-scan")
    page = result.pages[0]

    assert calls == [1]
    assert result.status == ParseStatus.READY
    assert page.extraction_method == "ocr"
    assert page.metadata["detected_as_scanned"] is True
    assert page.metadata["orientation_correction"] == 90
    assert page.metadata["deskew_angle"] == -2.0
    assert page.confidence == pytest.approx(0.88)


def test_mixed_pdf_ocr_runs_only_for_weak_page(tmp_path, monkeypatch):
    path = tmp_path / "mixed.pdf"
    write_pdf(
        path,
        [
            "SUPREME COURT OF INDIA judgment with sufficient digital text. "
            "The appeal concerns a final order and contains complete reasons.",
            "",
        ],
    )
    pipeline = PdfExtractionPipeline(PdfExtractionLimits())
    calls = []

    def fake_ocr(_page, page_number, version_id, _width, _height):
        calls.append(page_number)
        return fake_ocr_block(page_number, version_id)

    monkeypatch.setattr(pipeline, "_ocr_page", fake_ocr)
    result = pipeline.extract(path, "version-mixed")

    assert calls == [2]
    assert [page.extraction_method for page in result.pages] == [
        "digital",
        "ocr",
    ]
    assert result.metadata["digital_pages"] == 1
    assert result.metadata["ocr_pages"] == 1


def test_pdf_page_limit_has_machine_readable_state(tmp_path):
    path = tmp_path / "too-many-pages.pdf"
    write_pdf(path, ["one", "two", "three"])
    result = ParserRouter(
        PdfExtractionLimits(max_pages=2)
    ).parse(path, path.name, "application/pdf", "version-limit")

    assert result.status == ParseStatus.LIMIT_EXCEEDED
    assert result.metadata["error_code"] == "pdf_page_limit"
    assert result.metadata["page_count"] == 3


def test_corrupt_pdf_has_explicit_error_state(tmp_path):
    path = tmp_path / "corrupt.pdf"
    path.write_bytes(b"%PDF-1.7\nthis is not a valid PDF")
    result = ParserRouter().parse(
        path,
        path.name,
        "application/pdf",
        "version-corrupt",
    )

    assert result.status == ParseStatus.CORRUPTED
    assert result.metadata["error_code"] == "pdf_corrupted"


def test_password_protected_pdf_has_explicit_error_state(tmp_path):
    fitz = pytest.importorskip("fitz")
    path = tmp_path / "protected.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Protected legal record")
    document.save(
        path,
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner-secret",
        user_pw="user-secret",
    )
    document.close()

    result = ParserRouter().parse(
        path,
        path.name,
        "application/pdf",
        "version-protected",
    )
    assert result.status == ParseStatus.PASSWORD_PROTECTED
    assert result.metadata["error_code"] == "pdf_password_protected"


def test_embedded_image_decompression_limit_is_enforced():
    limits = PdfExtractionLimits(max_embedded_image_pixels=100)
    pipeline = PdfExtractionPipeline(limits)
    page = SimpleNamespace(
        rect=SimpleNamespace(width=595.0, height=842.0),
        rotation=0,
        get_images=lambda full=True: [(1, 0, 20, 20)],
        get_text=lambda *_args, **_kwargs: [],
    )
    counters = {
        "ocr_pixels": 0,
        "embedded_image_pixels": 0,
        "digital_pages": 0,
        "ocr_pages": 0,
        "mixed_pages": 0,
        "failed_pages": 0,
    }

    with pytest.raises(PdfExtractionError) as caught:
        pipeline._process_page(
            None,
            page,
            1,
            "version-images",
            counters,
        )
    assert caught.value.status == ParseStatus.LIMIT_EXCEEDED
    assert caught.value.error_code == "pdf_decompression_limit"


def test_rotated_pixel_limit_is_not_downgraded_to_ocr_warning(monkeypatch):
    pipeline = PdfExtractionPipeline(PdfExtractionLimits(max_page_pixels=100))
    page = SimpleNamespace(
        get_pixmap=lambda **_kwargs: SimpleNamespace(
            width=10,
            height=10,
            samples=bytes(300),
        )
    )

    def reject_expanded_image(_image, _pytesseract):
        raise PdfExtractionError(
            "Rotated OCR image is too large",
            status=ParseStatus.LIMIT_EXCEEDED,
            error_code="pdf_rotated_pixel_limit",
        )

    monkeypatch.setattr(pipeline, "prepare_ocr_image", reject_expanded_image)

    with pytest.raises(PdfExtractionError) as caught:
        pipeline._ocr_page(page, 1, "version-rotation", 10, 10)

    assert caught.value.status == ParseStatus.LIMIT_EXCEEDED
    assert caught.value.error_code == "pdf_rotated_pixel_limit"


def test_standalone_image_pixel_limit_is_enforced(tmp_path, monkeypatch):
    image_module = pytest.importorskip("PIL.Image")
    path = tmp_path / "oversized.png"
    image_module.new("RGB", (15, 10), "white").save(path)
    limits = PdfExtractionLimits(
        max_page_pixels=100,
        max_total_ocr_pixels=1_000,
    )
    monkeypatch.setattr(
        PdfExtractionLimits,
        "from_settings",
        classmethod(lambda cls: limits),
    )
    monkeypatch.setattr(image_module, "MAX_IMAGE_PIXELS", 100)

    with pytest.warns(image_module.DecompressionBombWarning):
        result = ParserRouter().parse(
            path,
            path.name,
            "image/png",
            "version-image-limit",
        )

    assert result.status == ParseStatus.LIMIT_EXCEEDED
    assert result.metadata["error_code"] == "image_pixel_limit"


def test_table_rows_and_cells_are_structured():
    class FakeTable:
        bbox = (10, 20, 300, 180)

        def extract(self):
            return [
                ["Section", "Finding"],
                ["154 CrPC", "FIR registration"],
            ]

    class FakePage:
        def find_tables(self):
            return SimpleNamespace(tables=[FakeTable()])

    blocks, boxes, warnings = PdfExtractionPipeline(
        PdfExtractionLimits()
    )._extract_tables(FakePage(), 1, "version-table")

    assert warnings == []
    assert len(boxes) == 1
    assert len(blocks) == 1
    table = blocks[0].table
    assert table is not None
    assert table.rows[0].cells[0].text == "Section"
    assert table.rows[1].cells[1].text == "FIR registration"
    assert blocks[0].kind == BlockKind.TABLE


def test_render_pixel_limit_is_checked_before_ocr(tmp_path):
    path = tmp_path / "huge-page.pdf"
    fitz = pytest.importorskip("fitz")
    document = fitz.open()
    document.new_page(width=2000, height=2000)
    document.save(path)
    document.close()

    result = ParserRouter(
        PdfExtractionLimits(
            ocr_dpi=200,
            max_page_pixels=1_000_000,
        )
    ).parse(path, path.name, "application/pdf", "version-pixels")

    assert result.status == ParseStatus.LIMIT_EXCEEDED
    assert result.metadata["error_code"] == "pdf_page_pixel_limit"
