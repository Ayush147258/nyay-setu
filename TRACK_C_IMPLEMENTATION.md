# NyaySetu Track C Implementation Ledger

This ledger converts the source audit of NyaySetu, PlantBrain, LabCard AI,
PDF RAG, and Deep Agent into implementation work. NyaySetu is the product;
the other repositories are pattern donors, not runtime dependencies.

## Product boundary

NyaySetu accepts court, government, and supporting legal documents, preserves
their provenance, extracts facts and relationships, builds a cited legal
analysis, and answers role-aware questions for judges, authorities, lawyers,
and case analysts. It must never represent an unsupported claim as a sourced
fact or silently hide low-confidence extraction.

## Non-negotiable integrity rules

- Preserve every original upload and its SHA-256 digest.
- Version documents; never replace a source file or parsed representation.
- Attach every evidence atom to an exact document version, page, block, and
  character span.
- Label generated statements as fact, law, inference, or recommendation.
- Require factual report claims and factual chat answers to cite verified
  evidence atoms.
- Surface contradictions, unsupported claims, low-confidence OCR, parser
  warnings, and missing documents as review items or caveats.
- Record parser, extractor, prompt, model, and workflow versions.
- Make ingestion and analysis idempotent and resumable.
- Keep role presentation separate from authorization.

## Architecture checklist

- [x] Canonical Document IR and Evidence Atom contracts
- [x] Integrity result and review-item contracts
- [x] Immutable object storage with local and S3-compatible adapters
- [x] PDF, DOCX, text, spreadsheet, email, and image parser routing
- [x] OCR fallback with confidence and manual-review state
- [x] Case-scoped evidence, relationship, and chronology artifacts
- [x] Case-isolated BM25 retrieval plus pgvector-ready production schema
- [x] Extractor Agent with deterministic validators
- [x] Research Agent with separated legal-source results
- [x] Synthesis Agent producing a structured, cited legal report
- [x] Adversarial Critic and mechanical Verifier/Mediator
- [x] Maximum two revision rounds with exposed caveats
- [x] Role-aware, citation-bearing case chat
- [x] Versioned JSON and PDF report delivery
- [x] Durable PostgreSQL jobs, persisted events, leases, retries, and terminal failures
- [x] Postgres schema and row-level case isolation
- [x] Upload, live-run, evidence-review, relationship, report, and chat UI
- [x] Security, concurrency, regression, and mixed-format E2E tests

## Source audit coverage

| Donor | Pattern retained | Weakness not carried forward |
|---|---|---|
| PlantBrain | parser routing, OCR review, multimodal Document IR | non-atomic multi-store writes and worker-local paths |
| LabCard AI | deterministic validation and confidence gates | PDF-only, no OCR, no provenance, client-selected premium trust |
| PDF RAG | page/chunk citations and retrieval threshold | global state, duplicate indexing, local-only Chroma |
| Deep Agent | controlled research tools and provider fallback | demo-only orchestration, no tool loop, no user isolation |
| NyaySetu | adversarial legal agents, mediator, SSE trace | text-only intake, unverifiable citations, process-local jobs/events |

## Delivery verification

- Backend suite: 144 tests passed on 17 July 2026.
- Frontend: production Next.js build passed.
- Mixed-format load probe: 80 documents at concurrency 8, zero exceptions and
  zero divergent semantic outputs; 1.908 documents/s and 9.73 s p95 locally.
- Browser audit: desktop and 390 px mobile workspace layouts passed with no
  console errors or document-level horizontal overflow.
- Comparative research and residual risks are recorded in
  `TRACK_C_SCORECARD.md`.

Production soak/load testing, telemetry alerting, and disaster-recovery drills
remain deployment acceptance work because they require live PostgreSQL, object
storage, OCR binaries, and production-sized confidential inputs.

## Final audit definition of done

Before declaring a production deployment accepted, re-read this ledger and verify:

1. Every supported format has a successful and failure-path fixture.
2. Re-uploading identical bytes is idempotent; a changed file creates a new
   immutable version.
3. Every factual output resolves to the stored original through a valid span.
4. OCR and extraction below threshold enter the review queue.
5. Contradictory evidence remains visible through report and chat.
6. A failed worker resumes without duplicating evidence or report versions.
7. Concurrent cases cannot retrieve or display one another's content.
8. The five-agent legacy petition demo still passes its compatibility tests.
9. The frontend has useful empty, loading, partial, failed, and retry states.
10. Security, accessibility, mixed-language, load, and legal-safety checks pass.
