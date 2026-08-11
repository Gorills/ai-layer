from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

router = APIRouter()
_STATIC_ROOT = Path(str(files("ai_layer.dashboard").joinpath("static")))


@router.get("/", include_in_schema=False)
def dashboard_root_redirect():
    return RedirectResponse(url="/dashboard", status_code=307)


@router.get("/dashboard", include_in_schema=False)
def dashboard_index():
    return FileResponse(
        _STATIC_ROOT / "index.html",
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )


def static_files() -> StaticFiles:
    return StaticFiles(directory=str(_STATIC_ROOT), html=False)
