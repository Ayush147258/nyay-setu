"""Evaluate the golden corpus and emit measurable extraction metrics."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT.parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.document_intelligence.models import ParseStatus
from app.document_intelligence.parsers import ParserRouter


MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    "xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ),
    "image": "image/png",
}


def ocr_environment() -> dict:
    executable = shutil.which("tesseract")
    languages: list[str] = []
    if executable:
        try:
            output = subprocess.run(
                [executable, "--list-langs"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.splitlines()
            languages = [
                line.strip()
                for line in output
                if line.strip() and not line.startswith("List of")
            ]
        except (OSError, subprocess.SubprocessError):
            languages = []
    return {
        "tesseract_available": executable is not None,
        "tesseract_path": executable,
        "languages": languages,
        "required_languages": ["eng", "hin"],
    }


def evaluate() -> dict:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    checksums = json.loads((ROOT / "checksums.json").read_text(encoding="utf-8"))
    parser = ParserRouter()
    results = []
    status_counts: Counter[str] = Counter()
    total_fragments = 0
    matched_fragments = 0
    structured_tables_expected = 0
    structured_tables_found = 0
    diagnostic_pages = 0
    total_pages = 0

    for item in manifest["documents"]:
        path = ROOT / "generated" / item["filename"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        checksum_valid = digest == checksums[item["filename"]]
        parsed = parser.parse(
            path,
            path.name,
            MEDIA_TYPES[item["format"]],
            f"golden-{item['id']}",
        )
        status_counts[parsed.status.value] += 1
        text = "\n".join(
            block.text
            for page in parsed.pages
            for block in page.blocks
        ).casefold()
        fragments = item["expected_fragments"]
        hits = [
            fragment
            for fragment in fragments
            if fragment.casefold() in text
        ]
        total_fragments += len(fragments)
        matched_fragments += len(hits)

        expected_table = item["expects_structured_table"]
        found_table = any(
            block.table is not None
            for page in parsed.pages
            for block in page.blocks
        )
        if expected_table:
            structured_tables_expected += 1
            structured_tables_found += int(found_table)

        total_pages += len(parsed.pages)
        diagnostic_pages += sum(
            page.extraction_method != "none"
            and 0.0 <= page.confidence <= 1.0
            for page in parsed.pages
        )
        results.append(
            {
                "id": item["id"],
                "status": parsed.status.value,
                "checksum_valid": checksum_valid,
                "pages": len(parsed.pages),
                "methods": [
                    page.extraction_method for page in parsed.pages
                ],
                "confidence": [
                    round(page.confidence, 4) for page in parsed.pages
                ],
                "fragment_hits": hits,
                "fragment_total": len(fragments),
                "structured_table": found_table,
                "warnings": parsed.warnings,
            }
        )

    accepted = {
        ParseStatus.READY.value,
        ParseStatus.PARTIAL.value,
    }
    successful = sum(
        count for status, count in status_counts.items() if status in accepted
    )
    return {
        "corpus_version": manifest["version"],
        "ocr_environment": ocr_environment(),
        "documents": len(results),
        "successful_documents": successful,
        "parse_success_rate": round(successful / max(1, len(results)), 4),
        "expected_fragment_recall": round(
            matched_fragments / max(1, total_fragments),
            4,
        ),
        "structured_table_recall": round(
            structured_tables_found / max(1, structured_tables_expected),
            4,
        ),
        "page_diagnostic_coverage": round(
            diagnostic_pages / max(1, total_pages),
            4,
        ),
        "status_counts": dict(status_counts),
        "results": results,
    }


def main() -> None:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("--output", type=Path)
    argument_parser.add_argument("--strict", action="store_true")
    args = argument_parser.parse_args()

    metrics = evaluate()
    encoded = json.dumps(metrics, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded)

    if args.strict:
        failures = []
        ocr = metrics["ocr_environment"]
        missing_languages = sorted(
            set(ocr["required_languages"]) - set(ocr["languages"])
        )
        if not ocr["tesseract_available"]:
            failures.append("tesseract_unavailable")
        elif missing_languages:
            failures.append(
                "missing_ocr_languages:" + ",".join(missing_languages)
            )
        if metrics["parse_success_rate"] < 0.90:
            failures.append("parse_success_rate")
        if metrics["expected_fragment_recall"] < 0.80:
            failures.append("expected_fragment_recall")
        if metrics["structured_table_recall"] < 0.90:
            failures.append("structured_table_recall")
        if metrics["page_diagnostic_coverage"] < 0.95:
            failures.append("page_diagnostic_coverage")
        if failures:
            raise SystemExit(
                "Golden corpus thresholds failed: " + ", ".join(failures)
            )


if __name__ == "__main__":
    main()
