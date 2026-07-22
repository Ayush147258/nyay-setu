from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.db.neon_client import close_pool
from app.api import agents, chat, document_intelligence, voice, health
from app.document_intelligence.security import configure_secure_logging


configure_secure_logging()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await close_pool()


app = FastAPI(
    title="NyaySetu Backend",
    description="Adversarial multi-agent legal rights navigator for India",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(agents.router, prefix="/api", tags=["agents"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(voice.router, prefix="/api/voice", tags=["voice"])
app.include_router(document_intelligence.router, prefix="/api", tags=["document-intelligence"])


@app.get("/")
async def root():
    return {"service": "NyaySetu Backend", "status": "running", "version": "1.0.0"}
