from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes import generation, seams

import json

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        json.loads(settings.CORS_ORIGINS)
        if isinstance(settings.CORS_ORIGINS, str) and settings.CORS_ORIGINS.strip().startswith("[")
        else [
            o.strip()
            for o in (settings.CORS_ORIGINS or "").split(",")
            if o.strip()
        ]
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generation.router)
app.include_router(seams.router)


@app.get("/")
async def root():
    return {
        "message": "Welcome to Atticus API",
        "version": settings.APP_VERSION,
        "status": "running"
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": settings.APP_NAME
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
