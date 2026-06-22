# NyaySetu

NyaySetu is India's Adversarial Agentic Justice Navigator. It is a full-stack application featuring a Next.js frontend with Google OAuth, Neon PostgreSQL via Drizzle ORM, Supabase private storage, and an SSE Agent Arena proxying a Python FastAPI + LangGraph backend.

## Architecture Stack

- **Frontend**: Next.js App Router, TypeScript, TailwindCSS, NextAuth v5
- **Backend**: Python 3.11+, FastAPI, LangGraph, asyncpg, WeasyPrint
- **Database**: Neon PostgreSQL (Drizzle ORM for frontend, asyncpg raw SQL for backend)
- **Storage**: Supabase Storage (private buckets for documents, petitions, voice)
- **AI/APIs**: Anthropic (Claude 3.5 Sonnet for agents), Sarvam AI (voice/translation), IndianKanoon (legal research), Twilio (SMS notifications)

## Running Locally

The easiest way to run both services together for local testing or demoing is via Docker Compose.

```bash
# Start both frontend and backend
docker-compose up --build
```
- Frontend will be available at `http://localhost:3000`
- Backend API will be available at `http://localhost:8000`

### Seed Data
To populate the database with realistic multilingual demo cases and mid-debate states:
```bash
# Make sure your backend environment variables are set, then run:
python backend/app/data/seed.py
```

## Environment Variables

Both the frontend and backend require environment files to function. 
Copy `.env.example` to `.env.local` (for frontend) and `.env` (for backend) respectively.

### Frontend (`frontend/.env.local`)
```ini
# NextAuth requires a 32-byte base64 string
# Generate via: openssl rand -base64 32
NEXTAUTH_SECRET=your_generated_secret_here
NEXTAUTH_URL=http://localhost:3000

# Get these from Google Cloud Console -> APIs & Services -> Credentials
GOOGLE_CLIENT_ID=your_google_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_google_client_secret

# Get from Neon.tech Dashboard
DATABASE_URL=postgresql://user:password@ep-host.neon.tech/nyaysetu?sslmode=require

# Get from Supabase Project settings
NEXT_PUBLIC_SUPABASE_URL=https://your-project-id.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key

NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
PYTHON_BACKEND_URL=http://localhost:8000
```

### Backend (`backend/.env`)
```ini
# Same Neon DB string as frontend
DATABASE_URL=postgresql://user:password@ep-host.neon.tech/nyaysetu?sslmode=require

# API Keys for Core Services
ANTHROPIC_API_KEY=sk-ant-your_anthropic_api_key
SARVAM_API_KEY=your_sarvam_api_key
INDIANKANOON_API_KEY=your_indian_kanoon_token

# Twilio SMS Alerts
TWILIO_ACCOUNT_SID=AC_your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_FROM_NUMBER=+1234567890
```

## API Routes & Endpoints

### Frontend Proxy Routes
These Next.js route handlers securely proxy requests to the Python backend or Supabase:
- `GET /api/agent-stream/[caseId]`: Streams SSE from the LangGraph backend.
- `GET /api/petition/[caseId]/pdf`: Proxies the generated PDF document.
- `POST /api/upload`: Uploads to Supabase and returns signed URLs.
- `GET/POST /api/cases`: Interacts directly with Drizzle ORM and triggers the backend agent chain.

### Python Backend Contract
- `POST /run-agents`: Initiates the background LangGraph orchestrator.
- `GET /stream/{caseId}`: Yields SSE events from the active debate.
- `GET /petition/{caseId}/pdf`: Renders the petition HTML template to PDF via WeasyPrint.
- `POST /voice/transcribe`: Proxies raw audio to Sarvam AI.

## Known Limitations

While NyaySetu is built to be a robust production-grade prototype, the following limitations exist in the current implementation:

1. **Voice Streaming Architecture**: The `/new-case` voice recorder currently relies on the browser's `MediaRecorder` API to capture the full audio blob, which is then sent to the backend as a single `POST` request. True real-time bidirectional audio streaming (e.g., using WebSockets or WebRTC) was not fully implemented.
2. **Twilio Sandboxing**: SMS notifications are fully wired up in the integration client, but using a trial/sandbox Twilio account requires the destination phone numbers to be manually pre-verified in the Twilio console. Unverified numbers will silently fail to receive status alerts during live demos.
3. **IndianKanoon Rate Limits**: The free tier of the IndianKanoon API is highly restrictive. A simple in-memory backoff and rate-limiter was added to the client, but sustained concurrent agent debates will quickly exhaust the quota, triggering the gracefully degraded fallback logic.
4. **Auth Callbacks**: `next-auth` currently redirects perfectly after login, but session invalidation edge-cases (like cookie expiration during an active Agent Arena stream) have not been rigorously handled with interceptors.
