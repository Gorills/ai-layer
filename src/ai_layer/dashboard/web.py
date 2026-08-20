from __future__ import annotations

import hashlib
import ipaddress
from importlib.resources import files
from pathlib import Path
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from ai_layer.application import work as work_uc
from ai_layer.core.request_context import operation_context
from ai_layer.domain.errors import ErrorCategory, ErrorCode, StructuredError, normalize_error
from ai_layer.domain.security import LOCAL_TRUSTED_ACTOR
from ai_layer.projections.dashboard_common import entry_for_key

router = APIRouter()
_STATIC_ROOT = Path(str(files("ai_layer.dashboard").joinpath("static")))


def _loopback_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _effective_port(scheme: str, port: int | None) -> int | None:
    if port is not None:
        return port
    if scheme == "http":
        return 80
    if scheme == "https":
        return 443
    return None


def _same_local_origin(request: Request) -> bool:
    source = request.headers.get("origin") or request.headers.get("referer")
    if not source:
        return False
    candidate = urlsplit(source)
    base = urlsplit(str(request.base_url))
    if candidate.scheme != base.scheme:
        return False
    candidate_hostname = candidate.hostname
    base_hostname = base.hostname
    if candidate_hostname is None or base_hostname is None:
        return False
    if not _loopback_host(candidate_hostname) or not _loopback_host(base_hostname):
        return False
    return candidate_hostname.casefold() == base_hostname.casefold() and _effective_port(
        candidate.scheme, candidate.port
    ) == _effective_port(base.scheme, base.port)


def _dashboard_action_forbidden() -> HTTPException:
    return HTTPException(
        status_code=403,
        detail=StructuredError(
            code=ErrorCode.REQUEST_UNAUTHORIZED,
            category=ErrorCategory.TRANSPORT,
            message="Dashboard mutations require a same-origin loopback browser request.",
            retryable=False,
            required_action="Open the local AI Layer Dashboard and use the Work action there.",
        ).to_dict(),
    )


def _work_complete_command_id(project_root: str, work_key: str) -> str:
    material = f"{project_root}\0{str(work_key).strip().upper()}".encode()
    return "dashboard-work-complete:" + hashlib.sha256(material).hexdigest()[:32]


def _dashboard_action_failure(exc: BaseException, *, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail=normalize_error(exc).to_dict())


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


@router.post("/dashboard/actions/work/complete", include_in_schema=False)
def dashboard_complete_work(request: Request, project_key: str, work_key: str):
    if not _same_local_origin(request):
        raise _dashboard_action_forbidden()
    entry = entry_for_key(project_key)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=StructuredError(
                code=ErrorCode.VALIDATION_FAILED,
                category=ErrorCategory.VALIDATION,
                message="Registered project not found.",
                retryable=True,
                required_action="Use a project key returned by the Dashboard.",
                ids={"project_key": project_key},
            ).to_dict(),
        )

    project_root = str(Path(str(entry["root"])).expanduser().resolve())
    command_id = _work_complete_command_id(project_root, work_key)
    try:
        with operation_context(
            actor=LOCAL_TRUSTED_ACTOR,
            interface="dashboard",
            command_id=command_id,
        ):
            work_uc.complete(
                project_root,
                work_key=work_key,
                summary="",
                idempotency_key=command_id,
            )
    except ValueError as exc:
        raise _dashboard_action_failure(exc, status_code=422) from exc
    except RuntimeError as exc:
        raise _dashboard_action_failure(exc, status_code=409) from exc

    project_part = quote(project_key, safe="")
    work_part = quote(str(work_key).strip().upper(), safe="")
    return RedirectResponse(url=f"/dashboard#/work/{project_part}/{work_part}", status_code=303)


def static_files() -> StaticFiles:
    return StaticFiles(directory=str(_STATIC_ROOT), html=False)
