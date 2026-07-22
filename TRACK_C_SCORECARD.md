# Track C Backend Quality Scorecard

Research snapshot: 17 July 2026. The comparison is based on source code and tests,
not only README claims, at these revisions:

- NyaySetu: local revision `96fa1ba` plus the Track C implementation in this worktree.
- PlantBrain: Hugging Face Space revision `eb116c5`.
- LabCard AI: Hugging Face Space revision `0aaa5bc`.

Sources: [LabCard AI backend](https://huggingface.co/spaces/ayush712145/labcardai-backend),
[PlantBrain backend](https://huggingface.co/spaces/ayush712145/plantbrain_backend), and
the NyaySetu backend in this repository.

## Executive result

**NyaySetu is the best overall Track C backend (92/100).** It is the only one of
the three that combines immutable source versions, exact page/block/character
evidence spans, deterministic integrity checks, separate legal research,
multi-agent synthesis, durable PostgreSQL jobs with SSE, case ownership, report
history, and a judge-facing review/export workflow.

**PlantBrain is second (75/100)** and is the strongest donor for broad industrial
multi-format and multimodal extraction. It has a capable PDF/OCR pipeline,
DOCX/spreadsheet/image support, Graph-RAG, Neo4j, Chroma, review queues, and an
optional Celery/Redis worker path. Its evidence contract is less exact than
NyaySetu's legal provenance model and its SQL, graph, vector, and filesystem
writes do not form one atomic transaction.

**LabCard AI is third for Track C (57/100)** but is the best focused lab-report
analyser. Its dual pdfplumber/PyMuPDF extraction and deterministic biomarker,
unit, range, and scoring logic are appropriate for born-digital lab PDFs. It is
not a general document-synthesis backend: scanned PDFs are detected but OCR is
explicitly unsupported, input is PDF/text only, jobs are process-local, and the
reported facts do not resolve to exact source spans.

## Weighted score

| Category | Weight | NyaySetu | PlantBrain | LabCard AI |
|---|---:|---:|---:|---:|
| Multi-format and PDF extraction | 20 | 19 | 18 | 11 |
| Integrity, provenance, and review | 20 | 20 | 13 | 11 |
| Extraction and synthesis agents | 15 | 14 | 11 | 8 |
| Durable scale and consistency | 15 | 13 | 11 | 6 |
| Security and tenant/case isolation | 10 | 10 | 6 | 6 |
| Operational APIs and judge workflow | 10 | 9 | 8 | 7 |
| Tests and maintainability | 10 | 7 | 8 | 8 |
| **Total** | **100** | **92** | **75** | **57** |

Scores measure fitness for the stated Track C challenge, not the quality of each
product in its own domain. A narrow lab analyser is intentionally penalized for
not being a multi-agent legal/technical document platform.

## PDF extraction capability

| Capability | NyaySetu | PlantBrain | LabCard AI |
|---|---|---|---|
| Born-digital PDFs | PyMuPDF page/block extraction | PyMuPDF with page boundaries | pdfplumber first, PyMuPDF fallback |
| Scanned PDFs | Per-page OCR fallback with confidence and review state | Tesseract/OpenCV OCR and multimodal extraction | Detects likely scans; no OCR |
| Mixed text/image pages | Page-level fallback | Supported through parser/OCR paths | No |
| Rotation/degradation | Rotation/deskew-aware OCR tests | Image preprocessing and degraded-image tests | No OCR path |
| Tables | Structured PDF table fixtures and cells | Text/page extraction plus multimodal schema extraction | Strong pdfplumber table handling for lab layouts |
| Failure handling | Corrupt, encrypted, unsupported and limit paths | Corrupt/encrypted clean failure shape | Extraction warnings; thin scanned-PDF path |
| Legal provenance | Document version, page, block and exact character span | Filename/page/section citations | Page number is mostly diagnostic; no exact span chain |
| Benchmark coverage | Checked-in SHA-256 golden corpus across formats | Parser unit and Neo4j integration tests | Three focused parser/scoring/noise test files |

**PDF winner: NyaySetu.** PlantBrain is close on extraction breadth, while
LabCard can outperform both for clean tabular Indian lab reports because its
normalization is domain-specific. NyaySetu wins the legal use case because
extraction quality is coupled to immutable provenance, confidence gates, review,
and integrity verification.

## Backend-by-backend assessment

### NyaySetu

Strengths:

- Content-addressed immutable uploads and versions in local or S3-compatible storage.
- PDF, DOCX, text, CSV/XLSX, email, and image routing with normalized Document IR.
- Evidence atoms carry source quotes and exact document-version/page/block/character spans.
- Extractor, legal-research, synthesis, adversarial critic, mediator/verifier, and cited chat workflow.
- PostgreSQL jobs use idempotency keys, leases, `FOR UPDATE SKIP LOCKED`, retries, cancellation, persisted events, and SSE replay.
- Tenant/case ownership, JWT validation, MIME sniffing, quotas, rate limits, audit events, and RLS schema.
- Judge workflow covers upload, parser state, evidence, research, relationships, chronology, integrity, review decisions, report versions, retry, and PDF/JSON export.

Disadvantages and residual risk:

- Production operation needs PostgreSQL, a worker process, OCR dependencies, and object storage; the local fallback is not a scale target.
- The test suite validates queue algorithms and repository contracts without a sustained distributed PostgreSQL/S3 soak test.
- Embedding infrastructure is represented in the schema, but retrieval quality still needs a legal-domain benchmark and production embedding/reranker evaluation.
- PDF export depends on WeasyPrint and should be smoke-tested in the final deployment image.
- The local 80-document load run left 20 scan-heavy inputs as `ocr_required` and 12 as `partial`; production OCR language packs and worker sizing are deployment gates.
- Observability is event/audit based; production metrics, traces, alert thresholds, backup/restore, and disaster-recovery drills remain deployment work.

### PlantBrain

Strengths:

- Broad PDF, DOCX, TXT, XLSX and image/TIFF parsing, magic-byte PDF detection, OCR confidence, and page-aware chunks.
- Gemini multimodal structured extraction is well matched to P&IDs, logs, manuals, and equipment relationships.
- Graph-RAG combines Neo4j relationships, Chroma retrieval, citations, compliance data, and low-confidence review queues.
- Optional Celery/Redis dispatch provides a real durable worker path; local async fallback keeps demos simple.
- Good parser tests cover multi-page PDFs/TIFFs, spreadsheets, corrupt/password-protected files, confidence, and degraded images.

Disadvantages:

- Source traceability generally stops at filename/page/section; it does not cryptographically bind each claim to an immutable exact source span.
- Upload bytes are stored under mutable worker-local paths without the same content-addressed object/version contract.
- SQL status, filesystem files, Neo4j merges, and Chroma writes can partially succeed across independent stores.
- The local `asyncio.create_task` fallback is not durable, and the Celery task does not declare explicit retry/backoff/dead-letter policy in the task definition.
- Ingestion/list APIs are not visibly tenant/case scoped; an admin key protects selected operations but is not equivalent to per-case ownership.
- It synthesizes Graph-RAG answers and compliance views, but does not implement the full Extractor-to-Synthesis-to-Critic legal report contract.

### LabCard AI

Strengths:

- Simple, readable pipeline with pdfplumber/PyMuPDF fallback running off the event loop.
- Excellent domain-specific normalization for noisy biomarker names, units, reference ranges, and lab table layouts.
- Deterministic range/scoring logic reduces dependence on LLM output; provider fallback is isolated in the explanation layer.
- Focused tests cover parser behavior, scoring, and noisy unit text.

Disadvantages:

- PDF/text only; no DOCX, spreadsheet, email, image, or general multi-format Document IR.
- Scanned PDFs are flagged with the explicit message that OCR is not supported.
- No immutable object/version ledger, byte hash contract, exact source spans, relationship/chronology model, or integrity engine.
- `asyncio.create_task` report persistence is process-local and can be lost on restart.
- It is a staged analyser, not a collaborative Extractor/Synthesis multi-agent system.
- Supabase persistence and user-tier logic are useful product features, but do not establish case-scoped legal authorization or RLS evidence isolation in the reviewed code.

## Recommendation

Use **NyaySetu as the Track C submission and runtime**. Keep PlantBrain as the
reference for future multimodal diagram/OCR and graph ingestion improvements,
and LabCard as the reference for deterministic domain validators and confidence
gates. Do not combine the three backends at runtime: that would add consistency
and security failure modes. Port only proven parser or validation patterns into
NyaySetu's immutable Document IR and integrity boundary.

## Verification completed

- NyaySetu backend: **144 tests passed**, including golden corpus, PDF failure
  paths, job retry/lease behavior, tenant isolation, S3/local immutability,
  workspace API contracts, exports, and a 24-file concurrent-ingestion check.
- NyaySetu frontend: production `next build` passed.
- Repeatable mixed-format load probe: 80 documents from 40 corpus sources at
  concurrency 8, zero exceptions, zero inconsistent outputs, 1.908 documents/s,
  2.31 s p50 and 9.73 s p95 on the local audit machine. Statuses were 48 ready,
  12 partial, and 20 OCR-required.
- Judge workspace: desktop and 390 px mobile browser checks passed with no
  document-level horizontal overflow or console errors; tab overflow is
  intentionally scrollable.

This scorecard does not claim a production load ceiling. The final confidence
step is a deployment-environment soak test against real PostgreSQL, object
storage, OCR binaries, and representative confidential case files.
