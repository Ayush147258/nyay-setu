---
title: NyaySetu Backend
emoji: "⚖️"
colorFrom: indigo
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
---

# NyaySetu Backend

This Hugging Face Space runs the NyaySetu FastAPI backend. It provides the agent orchestration API, document intelligence pipeline, role-aware chat, and source-grounded legal-document analysis used by the NyaySetu frontend.

This is the backend API only. The Next.js frontend is deployed separately and calls this Space over HTTPS.

## Core Pipeline

```mermaid
flowchart LR
  A[Upload Document] --> B[Immutable Document Store]
  B --> C[Extractor Agent]
  C --> D[Synthesis Agent]
  D --> E[Reviewer Agent]
  E --> F[Role Final Agent]
  F --> G[Lawyer / Judge / Citizen Answer]
```

## Capabilities

- Multi-format ingestion: PDF, DOCX, TXT, CSV, XLSX, images, emails, and scans.
- PDF text extraction with OCR fallback.
- Versioned document storage with SHA-256 hashes.
- Evidence extraction with source spans, pages, blocks, and quotes.
- Structured report synthesis with claims, timelines, caveats, and review items.
- Integrity verification so generated claims remain tied to uploaded source spans.
- Role-aware chat for lawyer, judge, and citizen panels.
- Provider router for Gemini, Groq, and Anthropic with safe fallback diagnostics.

## Runtime

| Component | Technology |
| --- | --- |
| API | FastAPI |
| Server | Uvicorn |
| Validation | Pydantic v2 |
| Database | Neon PostgreSQL via asyncpg |
| Document parsing | pypdf, PyMuPDF, python-docx, openpyxl, pytesseract |
| AI | Gemini, Groq, Anthropic |
| Container | Docker Space |

## Important Routes

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/` | Root service status |
| `GET` | `/api/health` | Health check |
| `POST` | `/api/run-agents` | Starts the legacy agent debate workflow |
| `GET` | `/api/stream/{case_id}` | Streams legacy agent events |
| `POST` | `/api/documents/upload` | Uploads and parses a case document |
| `GET` | `/api/case-files/{case_id}/workspace` | Returns stored docs, jobs, reports, evidence, and integrity state |
| `POST` | `/api/case-files/{case_id}/analysis-jobs` | Starts the live document-analysis pipeline |
| `GET` | `/api/analysis-jobs/{job_id}/events` | Streams pipeline events over SSE |
| `POST` | `/api/case-files/{case_id}/chat` | Answers questions over uploaded records |

Interactive OpenAPI docs are available at `/docs`.

## Required Space Secrets

Set these in Hugging Face Space Settings -> Repository secrets. Do not commit a `.env` file.

```env
DATABASE_URL=postgresql://user:password@ep-xxx.neon.tech/nyaysetu?sslmode=require

JWT_SECRET=your_32_char_secret_here
JWT_ALGORITHM=HS256
JWT_ISSUER=nyaysetu-frontend
JWT_AUDIENCE=nyaysetu-backend

GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key
ANTHROPIC_API_KEY=your_claude_key
SARVAM_API_KEY=your_sarvam_key
INDIANKANOON_API_KEY=your_indiankanoon_key

TWILIO_ACCOUNT_SID=AC_your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=+1234567890

ALLOWED_ORIGINS=https://your-frontend.vercel.app,http://localhost:3005
ENVIRONMENT=production
LOG_LEVEL=info
```

At least one AI provider key is required for live model synthesis. If a provider is out of quota, the backend returns source-card fallback with a visible reason.

## Document Storage

Default local storage path:

```env
DOCUMENT_STORAGE_BACKEND=local
DOCUMENT_STORAGE_ROOT=data/document-intelligence
```

For production durability, configure S3-compatible storage with:

```env
DOCUMENT_STORAGE_BACKEND=s3
S3_DOCUMENT_BUCKET=your-bucket
S3_REGION=ap-south-1
S3_ACCESS_KEY_ID=your-access-key
S3_SECRET_ACCESS_KEY=your-secret-key
```

## Local Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Docker Run

```bash
docker build -t nyaysetu-backend .
docker run -p 7860:7860 --env-file .env nyaysetu-backend
```

## Data Integrity

The backend keeps data integrity through versioned source documents, citation-bearing evidence atoms, provenance-aware claims, integrity checks, and role-specific final agents. Generated answers are constrained to retrieved source cards and must cite valid source spans.