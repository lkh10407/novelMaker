"""FastAPI application entry point."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is on the path so novel_maker can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import projects, characters, settings, outline, generate, export, collab, media

app = FastAPI(
    title="NovelMaker API",
    description="멀티 에이전트 소설 자동 집필 시스템 API",
    version="0.1.0",
)

# CORS for Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(projects.router, prefix="/api/projects", tags=["Projects"])
app.include_router(characters.router, prefix="/api/projects", tags=["Characters"])
app.include_router(settings.router, prefix="/api/projects", tags=["Settings"])
app.include_router(outline.router, prefix="/api/projects", tags=["Outline"])
app.include_router(generate.router, prefix="/api/projects", tags=["Generate"])
app.include_router(export.router, prefix="/api/projects", tags=["Export"])
app.include_router(media.router, prefix="/api/projects", tags=["Media"])
app.include_router(collab.router, tags=["Collaboration"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# Serve built frontend (production) — MUST be last (catch-all)
_web_dist = Path(__file__).resolve().parent.parent / "web" / "dist"
if _web_dist.exists():
    app.mount("/", StaticFiles(directory=str(_web_dist), html=True), name="frontend")
