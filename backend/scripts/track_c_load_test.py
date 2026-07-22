"""Repeatable mixed-format load probe for the Track C ingestion boundary.

Run from backend:
    python scripts/track_c_load_test.py --documents 80 --concurrency 8

This is intentionally infrastructure-free. It benchmarks parsing, immutable local
storage, and output consistency. Production acceptance should run a separate HTTP
soak against PostgreSQL, the worker, and object storage.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import mimetypes
import statistics
import sys
import tempfile
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.document_intelligence.ingestion import DocumentIngestionService
from app.document_intelligence.models import DocumentIR
from app.document_intelligence.storage import LocalDocumentStore


DEFAULT_CORPUS = BACKEND_ROOT / "tests" / "golden_corpus" / "generated"


@dataclass(frozen=True)
class Sample:
    source: str
    case_id: str
    duration_ms: float
    status: str
    parser: str
    pages: int
    fingerprint: str
    error: str | None = None


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * fraction)))
    return ordered[index]


def semantic_fingerprint(document: DocumentIR) -> str:
    payload = {
        "format": document.document_format.value,
        "status": document.status.value,
        "parser": document.parser_name,
        "warnings": sorted(document.warnings),
        "pages": [
            {
                "number": page.page_number,
                "blocks": [
                    {
                        "kind": block.kind.value,
                        "text": block.text,
                        "confidence": round(block.confidence, 4),
                    }
                    for block in page.blocks
                ],
            }
            for page in document.pages
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ingest_one(
    store: LocalDocumentStore,
    path: Path,
    index: int,
    source_count: int,
) -> Sample:
    started = time.perf_counter()
    case_id = f"load-case-{index // source_count:04d}-{index % source_count:04d}"
    try:
        result = DocumentIngestionService(store).ingest(
            tenant_id="load-test",
            case_id=case_id,
            filename=path.name,
            media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            stream=io.BytesIO(path.read_bytes()),
        )
        document = result.document
        return Sample(
            source=path.name,
            case_id=case_id,
            duration_ms=(time.perf_counter() - started) * 1000,
            status=document.status.value,
            parser=document.parser_name,
            pages=len(document.pages),
            fingerprint=semantic_fingerprint(document),
        )
    except Exception as exc:
        return Sample(
            source=path.name,
            case_id=case_id,
            duration_ms=(time.perf_counter() - started) * 1000,
            status="exception",
            parser="",
            pages=0,
            fingerprint="",
            error=f"{type(exc).__name__}: {exc}",
        )


def run(corpus: Path, document_count: int, concurrency: int) -> dict[str, Any]:
    sources = sorted(
        path
        for path in corpus.iterdir()
        if path.is_file() and path.suffix.casefold() in {
            ".pdf", ".docx", ".xlsx", ".csv", ".txt", ".eml",
            ".png", ".jpg", ".jpeg", ".tif", ".tiff",
        }
    )
    if not sources:
        raise SystemExit(f"No supported corpus files found in {corpus}")
    selected = [sources[index % len(sources)] for index in range(document_count)]

    wall_started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="nyaysetu-track-c-load-") as directory:
        store = LocalDocumentStore(Path(directory), max_upload_bytes=32 * 1024 * 1024)
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [
                executor.submit(ingest_one, store, path, index, len(sources))
                for index, path in enumerate(selected)
            ]
            samples = [future.result() for future in as_completed(futures)]
    wall_seconds = time.perf_counter() - wall_started

    fingerprints: dict[str, set[str]] = defaultdict(set)
    for sample in samples:
        if sample.fingerprint:
            fingerprints[sample.source].add(sample.fingerprint)
    inconsistent = sorted(
        source for source, values in fingerprints.items() if len(values) > 1
    )
    durations = [sample.duration_ms for sample in samples]
    failures = [asdict(sample) for sample in samples if sample.error]
    statuses: dict[str, int] = defaultdict(int)
    parsers: dict[str, int] = defaultdict(int)
    for sample in samples:
        statuses[sample.status] += 1
        parsers[sample.parser or "none"] += 1

    return {
        "documents": len(samples),
        "corpus_files": len(sources),
        "concurrency": concurrency,
        "wall_seconds": round(wall_seconds, 3),
        "documents_per_second": round(len(samples) / max(wall_seconds, 0.001), 3),
        "latency_ms": {
            "min": round(min(durations), 2),
            "mean": round(statistics.fmean(durations), 2),
            "p50": round(percentile(durations, 0.50), 2),
            "p95": round(percentile(durations, 0.95), 2),
            "max": round(max(durations), 2),
        },
        "statuses": dict(sorted(statuses.items())),
        "parsers": dict(sorted(parsers.items())),
        "exceptions": failures,
        "inconsistent_sources": inconsistent,
        "consistent": not failures and not inconsistent,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--documents", type=int, default=80)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.documents < 1 or args.concurrency < 1:
        parser.error("--documents and --concurrency must be positive")

    result = run(args.corpus.resolve(), args.documents, args.concurrency)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if result["consistent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
