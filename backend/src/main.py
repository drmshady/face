"""FastAPI application entry point per T010."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.src.api.middleware import RateLimitMiddleware, SessionCookieMiddleware
from backend.src.api.routes import router
from backend.src.config import CORS_ORIGINS

app = FastAPI(title="FaceAnalyzer API", version="0.1.0")

# Middleware (order matters: outermost first)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SessionCookieMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
