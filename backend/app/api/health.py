from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "nyaysetu-backend",
        "version": "1.0.0",
    }
