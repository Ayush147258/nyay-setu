"""Measured, bounded PDF extraction with selective OCR fallback."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

from app.document_intelligence.models import (
    BlockKind,
    BoundingBox,
    DocumentBlock,
    DocumentPage,
    ParseStatus,
    StructuredTable,
    TableCell,
    TableRow,
)


_TABLE_EXTRACTION_LOCK = Lock()


@dataclass(frozen=True)
class PdfExtractionLimits:
    text_quality_threshold: float = 0.55
    min_digital_text_chars: int = 24
    ocr_dpi: int = 200
    ocr_languages: str = "eng+hin"
    max_pages: int = 500
    max_page_pixels: int = 40_000_000
    max_total_ocr_pixels: int = 500_000_000
    max_embedded_image_pixels: int = 500_000_000
    max_images_per_page: int = 200
    max_page_text_chars: int = 2_000_000

    @classmethod
    def from_settings(cls) -> "PdfExtractionLimits":
        from app.config import settings

        return cls(
            text_quality_threshold=settings.pdf_text_quality_threshold,
            min_digital_text_chars=settings.pdf_min_digital_text_chars,
            ocr_dpi=settings.pdf_ocr_dpi,
            ocr_languages=settings.document_ocr_languages,
            max_pages=settings.pdf_max_pages,
            max_page_pixels=settings.pdf_max_page_pixels,
            max_total_ocr_pixels=settings.pdf_max_total_ocr_pixels,
            max_embedded_image_pixels=settings.pdf_max_embedded_image_pixels,
            max_images_per_page=settings.pdf_max_images_per_page,
            max_page_text_chars=settings.pdf_max_page_text_chars,
        )


@dataclass(frozen=True)
class TextQuality:
    score: float
    characters: int
    words: int
    printable_ratio: float
    alphanumeric_ratio: float
    replacement_ratio: float


@dataclass
class PdfExtractionResult:
    status: ParseStatus
    parser_name: str
    pages: list[DocumentPage] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OcrPageResult:
    blocks: list[DocumentBlock]
    confidence: float
    orientation_correction: int = 0
    deskew_angle: float = 0.0
    warnings: list[str] = field(default_factory=list)


class PdfExtractionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status: ParseStatus,
        error_code: str,
        metadata: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.error_code = error_code
        self.metadata = metadata or {}


def normalize_block_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = value.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [
        re.sub(r"[\t\f\v ]+", " ", line).strip()
        for line in value.split("\n")
    ]
    normalized: list[str] = []
    blank = False
    for line in lines:
        if line:
            normalized.append(line)
            blank = False
        elif normalized and not blank:
            normalized.append("")
            blank = True
    return "\n".join(normalized).strip()


def score_text_quality(value: str) -> TextQuality:
    text = normalize_block_text(value)
    characters = [character for character in text if not character.isspace()]
    count = len(characters)
    if not count:
        return TextQuality(0.0, 0, 0, 0.0, 0.0, 0.0)

    printable = sum(character.isprintable() for character in characters) / count
    alphanumeric = sum(character.isalnum() for character in characters) / count
    replacements = sum(
        character == "\ufffd" or unicodedata.category(character) == "Cc"
        for character in characters
    ) / count
    words = len(re.findall(r"\w+", text, flags=re.UNICODE))
    lines = max(1, len([line for line in text.splitlines() if line.strip()]))
    punctuation_runs = len(re.findall(r"[^\w\s]{5,}", text, flags=re.UNICODE))

    length_score = min(count / 80.0, 1.0)
    word_score = min(words / 12.0, 1.0)
    line_score = min(lines / 5.0, 1.0)
    alpha_score = min(alphanumeric / 0.45, 1.0)
    noise_penalty = min(
        0.55,
        replacements * 2.5 + punctuation_runs * 0.08,
    )
    score = (
        0.30 * length_score
        + 0.25 * printable
        + 0.20 * alpha_score
        + 0.15 * word_score
        + 0.10 * line_score
        - noise_penalty
    )
    return TextQuality(
        score=max(0.0, min(1.0, round(score, 4))),
        characters=count,
        words=words,
        printable_ratio=round(printable, 4),
        alphanumeric_ratio=round(alphanumeric, 4),
        replacement_ratio=round(replacements, 4),
    )


def _block_id(version_id: str, page_number: int, sequence: int, text: str) -> str:
    encoded = f"{version_id}:{page_number}:{sequence}:{text}".encode(
        "utf-8",
        errors="ignore",
    )
    return "blk_" + hashlib.sha256(encoded).hexdigest()[:20]


def _bbox(values: Any) -> BoundingBox | None:
    try:
        x0, y0, x1, y1 = (float(item) for item in values[:4])
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(item) for item in (x0, y0, x1, y1)):
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    return BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1)


def _overlap_fraction(
    candidate: BoundingBox | None,
    table: BoundingBox | None,
) -> float:
    if candidate is None or table is None:
        return 0.0
    width = max(0.0, min(candidate.x1, table.x1) - max(candidate.x0, table.x0))
    height = max(0.0, min(candidate.y1, table.y1) - max(candidate.y0, table.y0))
    intersection = width * height
    candidate_area = (candidate.x1 - candidate.x0) * (candidate.y1 - candidate.y0)
    return intersection / candidate_area if candidate_area else 0.0


class PdfExtractionPipeline:
    def __init__(self, limits: PdfExtractionLimits | None = None):
        self.limits = limits or PdfExtractionLimits.from_settings()

    def extract(self, path: Path, version_id: str) -> PdfExtractionResult:
        try:
            import fitz
        except ImportError as exc:
            raise PdfExtractionError(
                "PDF support is not installed",
                status=ParseStatus.FAILED,
                error_code="pdf_dependency_missing",
            ) from exc

        try:
            document = fitz.open(str(path))
        except Exception as exc:
            raise PdfExtractionError(
                "PDF is corrupted or unreadable",
                status=ParseStatus.CORRUPTED,
                error_code="pdf_corrupted",
                metadata={"exception_type": type(exc).__name__},
            ) from exc

        try:
            if not document.is_pdf:
                raise PdfExtractionError(
                    "The uploaded file is not a valid PDF",
                    status=ParseStatus.CORRUPTED,
                    error_code="pdf_invalid",
                )
            if document.needs_pass and document.authenticate("") <= 0:
                raise PdfExtractionError(
                    "Password-protected PDF requires manual review",
                    status=ParseStatus.PASSWORD_PROTECTED,
                    error_code="pdf_password_protected",
                )
            if document.page_count == 0:
                raise PdfExtractionError(
                    "PDF contains no pages",
                    status=ParseStatus.CORRUPTED,
                    error_code="pdf_empty",
                )
            if document.page_count > self.limits.max_pages:
                raise PdfExtractionError(
                    f"PDF exceeds the {self.limits.max_pages}-page limit",
                    status=ParseStatus.LIMIT_EXCEEDED,
                    error_code="pdf_page_limit",
                    metadata={
                        "page_count": document.page_count,
                        "max_pages": self.limits.max_pages,
                    },
                )

            warnings: list[str] = []
            if getattr(document, "is_repaired", False):
                warnings.append("PDF cross-reference data was repaired while opening")
            pages: list[DocumentPage] = []
            counters = {
                "ocr_pixels": 0,
                "embedded_image_pixels": 0,
                "digital_pages": 0,
                "ocr_pages": 0,
                "mixed_pages": 0,
                "failed_pages": 0,
            }

            for page_index in range(document.page_count):
                page_number = page_index + 1
                try:
                    page = document.load_page(page_index)
                    parsed = self._process_page(
                        document,
                        page,
                        page_number,
                        version_id,
                        counters,
                    )
                except PdfExtractionError:
                    raise
                except Exception as exc:
                    counters["failed_pages"] += 1
                    parsed = DocumentPage(
                        page_number=page_number,
                        confidence=0.0,
                        extraction_method="none",
                        warnings=[
                            f"Page extraction failed safely: {type(exc).__name__}"
                        ],
                        metadata={"error_code": "pdf_page_failed"},
                    )
                pages.append(parsed)

            missing = [page.page_number for page in pages if not page.blocks]
            low_confidence = [
                page.page_number
                for page in pages
                if page.blocks and page.confidence < 0.60
            ]
            for page in pages:
                warnings.extend(
                    f"Page {page.page_number}: {warning}"
                    for warning in page.warnings
                )

            if len(missing) == len(pages):
                status = ParseStatus.OCR_REQUIRED
            elif missing or low_confidence or counters["failed_pages"]:
                status = ParseStatus.PARTIAL
            else:
                status = ParseStatus.READY

            metadata = {
                "page_count": len(pages),
                "digital_pages": counters["digital_pages"],
                "ocr_pages": counters["ocr_pages"],
                "mixed_pages": counters["mixed_pages"],
                "failed_pages": counters["failed_pages"],
                "ocr_pixels": counters["ocr_pixels"],
                "embedded_image_pixels": counters["embedded_image_pixels"],
                "text_quality_threshold": self.limits.text_quality_threshold,
                "incremental_page_processing": True,
                "source_spans_validated": all(
                    block.metadata.get("source_span_validated")
                    for page in pages
                    for block in page.blocks
                ),
                "missing_pages": missing,
                "low_confidence_pages": low_confidence,
            }
            return PdfExtractionResult(
                status=status,
                parser_name="pymupdf+tesseract-selective",
                pages=pages,
                warnings=warnings,
                metadata=metadata,
            )
        finally:
            document.close()

    def _process_page(
        self,
        document: Any,
        page: Any,
        page_number: int,
        version_id: str,
        counters: dict[str, int],
    ) -> DocumentPage:
        width = float(page.rect.width)
        height = float(page.rect.height)
        if (
            not math.isfinite(width)
            or not math.isfinite(height)
            or width <= 0
            or height <= 0
        ):
            raise PdfExtractionError(
                f"Page {page_number} has invalid dimensions",
                status=ParseStatus.CORRUPTED,
                error_code="pdf_invalid_page_dimensions",
            )

        images = page.get_images(full=True)
        if len(images) > self.limits.max_images_per_page:
            raise PdfExtractionError(
                f"Page {page_number} contains too many embedded images",
                status=ParseStatus.LIMIT_EXCEEDED,
                error_code="pdf_image_count_limit",
                metadata={
                    "page_number": page_number,
                    "image_count": len(images),
                    "max_images_per_page": self.limits.max_images_per_page,
                },
            )
        page_image_pixels = sum(
            max(0, int(item[2])) * max(0, int(item[3]))
            for item in images
            if len(item) > 3
        )
        counters["embedded_image_pixels"] += page_image_pixels
        if (
            counters["embedded_image_pixels"]
            > self.limits.max_embedded_image_pixels
        ):
            raise PdfExtractionError(
                "PDF embedded-image decompression limit exceeded",
                status=ParseStatus.LIMIT_EXCEEDED,
                error_code="pdf_decompression_limit",
                metadata={
                    "embedded_image_pixels": counters["embedded_image_pixels"],
                    "max_embedded_image_pixels": (
                        self.limits.max_embedded_image_pixels
                    ),
                },
            )

        raw_blocks = page.get_text("blocks", sort=True)
        raw_text = "\n".join(
            str(item[4])
            for item in raw_blocks
            if len(item) > 4 and int(item[6] if len(item) > 6 else 0) == 0
        )
        if len(raw_text) > self.limits.max_page_text_chars:
            raise PdfExtractionError(
                f"Page {page_number} text expansion limit exceeded",
                status=ParseStatus.LIMIT_EXCEEDED,
                error_code="pdf_text_expansion_limit",
                metadata={
                    "page_number": page_number,
                    "characters": len(raw_text),
                    "max_page_text_chars": self.limits.max_page_text_chars,
                },
            )

        quality = score_text_quality(raw_text)
        table_blocks, table_boxes, table_warnings = self._extract_tables(
            page,
            page_number,
            version_id,
        )
        digital_blocks = self._digital_blocks(
            raw_blocks,
            table_boxes,
            page_number,
            version_id,
            quality.score,
        )
        needs_ocr = (
            quality.score < self.limits.text_quality_threshold
            or quality.characters < self.limits.min_digital_text_chars
        )
        page_warnings = list(table_warnings)
        rotation = int(page.rotation or 0)

        if not needs_ocr:
            blocks = digital_blocks + table_blocks
            method = "digital"
            confidence = quality.score
            counters["digital_pages"] += 1
            ocr_metadata: dict[str, Any] = {}
        else:
            page_warnings.append(
                "Digital text quality "
                f"{quality.score:.2f} was below the OCR threshold "
                f"{self.limits.text_quality_threshold:.2f}"
            )
            projected_pixels = self._projected_pixels(width, height)
            if projected_pixels > self.limits.max_page_pixels:
                raise PdfExtractionError(
                    f"Page {page_number} exceeds the OCR pixel limit",
                    status=ParseStatus.LIMIT_EXCEEDED,
                    error_code="pdf_page_pixel_limit",
                    metadata={
                        "page_number": page_number,
                        "projected_pixels": projected_pixels,
                        "max_page_pixels": self.limits.max_page_pixels,
                    },
                )
            counters["ocr_pixels"] += projected_pixels
            if counters["ocr_pixels"] > self.limits.max_total_ocr_pixels:
                raise PdfExtractionError(
                    "PDF total OCR pixel limit exceeded",
                    status=ParseStatus.LIMIT_EXCEEDED,
                    error_code="pdf_total_pixel_limit",
                    metadata={
                        "ocr_pixels": counters["ocr_pixels"],
                        "max_total_ocr_pixels": self.limits.max_total_ocr_pixels,
                    },
                )
            ocr = self._ocr_page(
                page,
                page_number,
                version_id,
                width,
                height,
            )
            page_warnings.extend(ocr.warnings)
            if ocr.blocks:
                blocks = ocr.blocks + table_blocks
                method = "mixed" if table_blocks else "ocr"
                confidence = ocr.confidence
                counters[
                    "mixed_pages" if method == "mixed" else "ocr_pages"
                ] += 1
            else:
                blocks = digital_blocks + table_blocks
                method = "digital" if blocks else "none"
                confidence = quality.score if blocks else 0.0
                if blocks:
                    counters["digital_pages"] += 1
            ocr_metadata = {
                "orientation_correction": ocr.orientation_correction,
                "deskew_angle": ocr.deskew_angle,
                "rendered_pixels": projected_pixels,
            }

        self._validate_blocks(blocks, page_number, version_id)
        return DocumentPage(
            page_number=page_number,
            width=width,
            height=height,
            rotation=rotation,
            confidence=max(0.0, min(1.0, confidence)),
            extraction_method=method,
            warnings=page_warnings,
            blocks=blocks,
            metadata={
                "digital_text_quality": quality.score,
                "digital_characters": quality.characters,
                "digital_words": quality.words,
                "printable_ratio": quality.printable_ratio,
                "alphanumeric_ratio": quality.alphanumeric_ratio,
                "replacement_ratio": quality.replacement_ratio,
                "detected_as_scanned": needs_ocr,
                "embedded_images": len(images),
                "embedded_image_pixels": page_image_pixels,
                "tables": len(table_blocks),
                **ocr_metadata,
            },
        )

    def _projected_pixels(self, width: float, height: float) -> int:
        scale = self.limits.ocr_dpi / 72.0
        return int(math.ceil(width * scale) * math.ceil(height * scale))

    def _digital_blocks(
        self,
        raw_blocks: list[Any],
        table_boxes: list[BoundingBox],
        page_number: int,
        version_id: str,
        confidence: float,
    ) -> list[DocumentBlock]:
        blocks: list[DocumentBlock] = []
        for item in raw_blocks:
            if len(item) < 5:
                continue
            block_type = int(item[6] if len(item) > 6 else 0)
            if block_type != 0:
                continue
            text = normalize_block_text(str(item[4]))
            bounds = _bbox(item)
            if not text or any(
                _overlap_fraction(bounds, table) >= 0.55
                for table in table_boxes
            ):
                continue
            words = text.split()
            uppercase = (
                sum(character.isupper() for character in text)
                / max(1, sum(character.isalpha() for character in text))
            )
            kind = (
                BlockKind.HEADING
                if len(words) <= 14 and uppercase >= 0.65
                else BlockKind.PARAGRAPH
            )
            sequence = len(blocks)
            blocks.append(
                DocumentBlock(
                    block_id=_block_id(
                        version_id,
                        page_number,
                        sequence,
                        text,
                    ),
                    page_number=page_number,
                    sequence=sequence,
                    kind=kind,
                    text=text,
                    confidence=max(0.0, min(1.0, confidence)),
                    bbox=bounds,
                    metadata={"extraction_method": "digital"},
                )
            )
        return blocks

    def _extract_tables(
        self,
        page: Any,
        page_number: int,
        version_id: str,
    ) -> tuple[list[DocumentBlock], list[BoundingBox], list[str]]:
        blocks: list[DocumentBlock] = []
        boxes: list[BoundingBox] = []
        warnings: list[str] = []
        finder = getattr(page, "find_tables", None)
        if finder is None:
            return blocks, boxes, warnings
        snapshots: list[tuple[int, Any, list[list[Any]]]] = []
        try:
            # PyMuPDF table discovery uses native shared state in some builds.
            # Keep that narrow section serialized, then normalize in parallel.
            with _TABLE_EXTRACTION_LOCK:
                tables = finder().tables
                for table_index, table in enumerate(tables):
                    try:
                        snapshots.append(
                            (table_index, table.bbox, table.extract())
                        )
                    except Exception:
                        warnings.append(
                            f"Table {table_index + 1} could not be extracted"
                        )
        except Exception as exc:
            return blocks, boxes, [
                f"Table detection failed safely: {type(exc).__name__}"
            ]

        for table_index, table_bbox, values in snapshots:
            normalized_rows = [
                [normalize_block_text(cell or "") for cell in row]
                for row in values
            ]
            if not any(any(cell for cell in row) for row in normalized_rows):
                continue
            bounds = _bbox(table_bbox)
            rows = [
                TableRow(
                    row_index=row_index,
                    cells=[
                        TableCell(
                            row_index=row_index,
                            column_index=column_index,
                            text=cell,
                        )
                        for column_index, cell in enumerate(row)
                    ],
                )
                for row_index, row in enumerate(normalized_rows)
            ]
            text = "\n".join(
                " | ".join(row).rstrip()
                for row in normalized_rows
            ).strip()
            table_id = (
                "tbl_"
                + hashlib.sha256(
                    f"{version_id}:{page_number}:{table_index}:{text}".encode(
                        "utf-8",
                        errors="ignore",
                    )
                ).hexdigest()[:20]
            )
            structured = StructuredTable(
                table_id=table_id,
                page_number=page_number,
                rows=rows,
                bbox=bounds,
            )
            sequence = len(blocks)
            blocks.append(
                DocumentBlock(
                    block_id=_block_id(
                        version_id,
                        page_number,
                        sequence,
                        text,
                    ),
                    page_number=page_number,
                    sequence=sequence,
                    kind=BlockKind.TABLE,
                    text=text,
                    confidence=0.95,
                    bbox=bounds,
                    table=structured,
                    metadata={
                        "extraction_method": "digital_table",
                        "rows": len(rows),
                        "columns": max((len(row.cells) for row in rows), default=0),
                    },
                )
            )
            if bounds is not None:
                boxes.append(bounds)
        return blocks, boxes, warnings

    def _ocr_page(
        self,
        page: Any,
        page_number: int,
        version_id: str,
        page_width: float,
        page_height: float,
    ) -> OcrPageResult:
        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            return OcrPageResult(
                blocks=[],
                confidence=0.0,
                warnings=["OCR dependencies are unavailable on this worker"],
            )

        image = None
        try:
            pixmap = page.get_pixmap(dpi=self.limits.ocr_dpi, alpha=False)
            image = Image.frombytes(
                "RGB",
                (pixmap.width, pixmap.height),
                pixmap.samples,
            )
            image, orientation, deskew = self.prepare_ocr_image(
                image,
                pytesseract,
            )
            try:
                data = pytesseract.image_to_data(
                    image,
                    lang=self.limits.ocr_languages,
                    config="--psm 3",
                    output_type=pytesseract.Output.DICT,
                )
            except Exception as primary_exc:
                if self.limits.ocr_languages == "eng":
                    raise
                data = pytesseract.image_to_data(
                    image,
                    lang="eng",
                    config="--psm 3",
                    output_type=pytesseract.Output.DICT,
                )
                fallback_warning = (
                    "Configured OCR languages were unavailable; English fallback used "
                    f"after {type(primary_exc).__name__}"
                )
            else:
                fallback_warning = ""

            groups: dict[tuple[int, int], list[dict[str, Any]]] = {}
            texts = data.get("text", [])
            for index, raw_word in enumerate(texts):
                word = normalize_block_text(str(raw_word))
                if not word:
                    continue
                confidence = self._ocr_confidence(
                    data.get("conf", []),
                    index,
                )
                if confidence < 0:
                    continue
                key = (
                    self._int_at(data.get("block_num", []), index),
                    self._int_at(data.get("par_num", []), index),
                )
                groups.setdefault(key, []).append(
                    {
                        "text": word,
                        "confidence": confidence,
                        "left": self._int_at(data.get("left", []), index),
                        "top": self._int_at(data.get("top", []), index),
                        "width": self._int_at(data.get("width", []), index),
                        "height": self._int_at(data.get("height", []), index),
                        "line": self._int_at(data.get("line_num", []), index),
                    }
                )

            blocks: list[DocumentBlock] = []
            all_confidences: list[float] = []
            for words in groups.values():
                words.sort(key=lambda item: (item["line"], item["top"], item["left"]))
                text = normalize_block_text(" ".join(item["text"] for item in words))
                if not text:
                    continue
                values = [item["confidence"] for item in words]
                confidence = sum(values) / len(values) / 100.0
                all_confidences.extend(values)
                left = min(item["left"] for item in words)
                top = min(item["top"] for item in words)
                right = max(item["left"] + item["width"] for item in words)
                bottom = max(item["top"] + item["height"] for item in words)
                bounds = BoundingBox(
                    x0=left * page_width / max(1, image.width),
                    y0=top * page_height / max(1, image.height),
                    x1=right * page_width / max(1, image.width),
                    y1=bottom * page_height / max(1, image.height),
                )
                sequence = len(blocks)
                blocks.append(
                    DocumentBlock(
                        block_id=_block_id(
                            version_id,
                            page_number,
                            sequence,
                            text,
                        ),
                        page_number=page_number,
                        sequence=sequence,
                        kind=BlockKind.IMAGE_TEXT,
                        text=text,
                        confidence=max(0.0, min(1.0, confidence)),
                        bbox=bounds,
                        metadata={"extraction_method": "ocr"},
                    )
                )

            page_confidence = (
                sum(all_confidences) / len(all_confidences) / 100.0
                if all_confidences
                else 0.0
            )
            warnings = [fallback_warning] if fallback_warning else []
            if not blocks:
                warnings.append("OCR produced no usable text")
            elif page_confidence < 0.65:
                warnings.append(
                    f"OCR confidence {page_confidence:.2f} requires human review"
                )
            return OcrPageResult(
                blocks=blocks,
                confidence=max(0.0, min(1.0, page_confidence)),
                orientation_correction=orientation,
                deskew_angle=deskew,
                warnings=warnings,
            )
        except PdfExtractionError:
            raise
        except Exception as exc:
            return OcrPageResult(
                blocks=[],
                confidence=0.0,
                warnings=[f"OCR failed safely: {type(exc).__name__}"],
            )
        finally:
            if image is not None:
                image.close()

    def prepare_ocr_image(
        self,
        image: Any,
        pytesseract: Any,
    ) -> tuple[Any, int, float]:
        from PIL import ImageOps

        image = ImageOps.exif_transpose(image)
        orientation = 0
        try:
            osd = pytesseract.image_to_osd(image)
            match = re.search(r"Rotate:\s*(0|90|180|270)", osd)
            if match:
                orientation = int(match.group(1))
        except Exception:
            orientation = 0
        if orientation:
            image = image.rotate(-orientation, expand=True, fillcolor="white")

        deskew = self._estimate_skew(image)
        if deskew:
            image = image.rotate(
                deskew,
                expand=True,
                fillcolor="white",
            )
        if image.width * image.height > self.limits.max_page_pixels:
            raise PdfExtractionError(
                "OCR rotation expanded the page beyond the pixel limit",
                status=ParseStatus.LIMIT_EXCEEDED,
                error_code="pdf_rotated_pixel_limit",
            )
        return image, orientation, deskew

    @staticmethod
    def _estimate_skew(image: Any) -> float:
        from PIL import ImageOps

        sample = ImageOps.grayscale(image)
        sample.thumbnail((700, 900))
        sample = ImageOps.autocontrast(sample)
        if sample.width * sample.height == 0:
            return 0.0
        ink = sum(value < 190 for value in sample.tobytes())
        if ink < max(40, sample.width):
            return 0.0

        def projection_score(angle: float) -> float:
            rotated = sample.rotate(
                angle,
                expand=False,
                fillcolor=255,
            )
            data = rotated.tobytes()
            width = rotated.width
            rows = [
                sum(value < 190 for value in data[offset : offset + width])
                for offset in range(0, len(data), width)
            ]
            mean = sum(rows) / max(1, len(rows))
            return sum((value - mean) ** 2 for value in rows) / max(1, len(rows))

        baseline = projection_score(0.0)
        candidates = [
            (angle, projection_score(angle))
            for angle in (-4.0, -3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0)
        ]
        angle, score = max(candidates, key=lambda item: item[1])
        if abs(angle) < 0.75 or score <= baseline * 1.03:
            return 0.0
        return angle

    @staticmethod
    def _ocr_confidence(values: list[Any], index: int) -> float:
        try:
            return float(values[index])
        except (IndexError, TypeError, ValueError):
            return -1.0

    @staticmethod
    def _int_at(values: list[Any], index: int) -> int:
        try:
            return int(values[index])
        except (IndexError, TypeError, ValueError):
            return 0

    @staticmethod
    def _validate_blocks(
        blocks: list[DocumentBlock],
        page_number: int,
        version_id: str,
    ) -> None:
        seen: set[str] = set()
        for sequence, block in enumerate(blocks):
            block.text = normalize_block_text(block.text)
            if not block.text:
                raise ValueError("Normalized PDF block cannot be empty")
            block.page_number = page_number
            block.sequence = sequence
            block.block_id = _block_id(
                version_id,
                page_number,
                sequence,
                block.text,
            )
            if block.block_id in seen:
                raise ValueError("PDF block identifiers are not unique")
            seen.add(block.block_id)
            block.metadata["char_length"] = len(block.text)
            block.metadata["source_span_validated"] = True
