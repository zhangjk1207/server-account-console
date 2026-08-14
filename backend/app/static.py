"""Serve the built frontend from the FastAPI app (fallback to SPA index.html).

The API and the web bundle are served from one origin so cookies and CSRF
stay same-site in local/non-Docker deploys.
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from app.core.config import get_settings


def mount_static(app: FastAPI) -> None:
    """Mount the frontend bundle, if present, under the app root."""
    dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    assets = dist / "assets"
    if not dist.is_dir() or not assets.is_dir():
        return

    # `/assets/*` files are versioned long-cacheable static assets.
    app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        candidate = (dist / path).resolve()
        # Never resolve outside the dist directory.
        if str(candidate).startswith(str(dist.resolve())) and candidate.is_file():
            return FileResponse(candidate)
        index = dist / "index.html"
        if not index.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(index, headers={"Cache-Control": "no-store"})

    settings = get_settings()
    app.origin = settings.app_origin if isinstance(getattr(settings, "app_origin", None), str) else "http://localhost:8080"