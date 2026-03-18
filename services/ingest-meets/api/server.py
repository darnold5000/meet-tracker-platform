"""
FastAPI public API server for USAG Meet Score Tracker.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("USAG Meet Tracker API starting up")
    yield
    logger.info("USAG Meet Tracker API shutting down")


app = FastAPI(
    title="USAG Meet Score Tracker API",
    description="Unified gymnastics meet results — scores, athletes, gyms, and meet history.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register route modules
from api.routes import meets, athletes, scores, gyms  # noqa: E402
app.include_router(meets.router, prefix="/meets", tags=["meets"])
app.include_router(athletes.router, prefix="/athletes", tags=["athletes"])
app.include_router(scores.router, prefix="/scores", tags=["scores"])
app.include_router(gyms.router, prefix="/gyms", tags=["gyms"])


@app.get("/", tags=["health"])
def health():
    return {"status": "ok", "service": "USAG Meet Score Tracker API", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
