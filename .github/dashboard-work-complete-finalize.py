from __future__ import annotations

from pathlib import Path

WEB_CONTENT = '''from __future__ import annotations

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
    if not _loopback_host(candidate.hostname) or not _loopback_host(base.hostname):
        return False
    return (
        candidate.hostname.casefold() == base.hostname.casefold()
        and _effective_port(candidate.scheme, candidate.port)
        == _effective_port(base.scheme, base.port)
    )


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
    material = f"{project_root}\\0{str(work_key).strip().upper()}".encode()
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
'''

TEST_CONTENT = '''from __future__ import annotations

import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from ai_layer.application import work as work_uc
from ai_layer.dashboard import web as dashboard_web
from ai_layer.db.base import Base
from ai_layer.db.models import CommandReceipt, Project, RuntimeEvent
from ai_layer.db.work_models import AgentRun, WorkItem
from ai_layer.domain.security import LOCAL_TRUSTED_ACTOR

ROOT = Path(__file__).resolve().parents[1]
WORK_JS = ROOT / "src/ai_layer/dashboard/static/js/views/work.js"


@contextmanager
def _bound_work_db(tmp_path: Path):
    import ai_layer.db.session as db_session

    engine = create_engine(f"sqlite:///{tmp_path / 'dashboard-work.db'}")
    root = (tmp_path / "project").resolve()
    root.mkdir()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(
            Project(
                name="Dashboard Work",
                root_path=str(root),
                languages={},
                dependencies={},
                architecture_summary="",
            )
        )
        db.commit()

    previous_engine = db_session._engine
    previous_session = db_session._SessionLocal
    db_session._engine = engine
    db_session._SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield engine, root
    finally:
        db_session._engine = previous_engine
        db_session._SessionLocal = previous_session
        engine.dispose()


def _dashboard_app() -> FastAPI:
    app = FastAPI()
    app.include_router(dashboard_web.router)
    return app


def test_dashboard_complete_work_is_same_origin_idempotent_and_attributed(
    monkeypatch, tmp_path: Path
) -> None:
    with _bound_work_db(tmp_path) as (engine, root):
        started = work_uc.begin(
            root,
            goal="Work was already finished in the host",
            kind="change",
            idempotency_key="dashboard-action-begin",
        )
        assert started["work"]["key"] == "W-0001"

        entry = {"root": str(root), "project_id": "alpha/beta", "name": "Dashboard Work"}
        monkeypatch.setattr(
            dashboard_web,
            "entry_for_key",
            lambda key: entry if key == "alpha/beta" else None,
        )
        client = TestClient(_dashboard_app(), base_url="http://127.0.0.1:8765")
        action = "/dashboard/actions/work/complete?project_key=alpha%2Fbeta&work_key=W-0001"

        rejected = client.post(
            action,
            headers={"Origin": "https://example.com"},
            follow_redirects=False,
        )
        assert rejected.status_code == 403
        with Session(engine) as db:
            work = db.scalar(select(WorkItem))
            assert work is not None
            assert work.status == "active"

        for _ in range(2):
            response = client.post(
                action,
                headers={"Origin": "http://127.0.0.1:8765"},
                follow_redirects=False,
            )
            assert response.status_code == 303
            assert response.headers["location"] == "/dashboard#/work/alpha%2Fbeta/W-0001"

        with Session(engine) as db:
            work = db.scalar(select(WorkItem))
            assert work is not None
            assert work.status == "completed"
            assert work.completed_at is not None

            runs = list(db.scalars(select(AgentRun).where(AgentRun.work_id == work.id)).all())
            assert len(runs) == 1
            assert runs[0].status == "completed"
            assert runs[0].ended_at is not None

            events = list(
                db.scalars(
                    select(RuntimeEvent).where(RuntimeEvent.event_type == "WorkCompleted")
                ).all()
            )
            assert len(events) == 1
            event = events[0]
            assert event.actor_id == LOCAL_TRUSTED_ACTOR.actor_id
            assert event.actor_kind == LOCAL_TRUSTED_ACTOR.kind
            assert event.interface == "dashboard"
            assert event.command_id is not None
            assert event.command_id.startswith("dashboard-work-complete:")

            receipts = list(
                db.scalars(
                    select(CommandReceipt).where(CommandReceipt.command_name == "work_complete")
                ).all()
            )
            assert len(receipts) == 1
            assert receipts[0].actor_id == LOCAL_TRUSTED_ACTOR.actor_id
            assert receipts[0].command_id == event.command_id


def test_work_detail_completion_action_is_plain_post_non_live_only(tmp_path: Path) -> None:
    if shutil.which("node") is None:
        raise AssertionError("node is required to execute Dashboard Work action helpers")
    source = WORK_JS.read_text(encoding="utf-8")
    assert "${workCompletionAction(project, work)}" in source

    script = tmp_path / "work_action_check.mjs"
    work_url = WORK_JS.resolve().as_uri()
    script.write_text(
        "\\n".join(
            [
                f"import {{ workCompletionAction }} from '{work_url}';",
                "const project = { key: 'alpha/beta' };",
                "const waiting = { key: 'W-0001', status: 'awaiting_feedback', live: false };",
                "const stale = { key: 'W-0002', status: 'active', live: false };",
                "const live = { key: 'W-0003', status: 'active', live: true };",
                "const completed = { key: 'W-0004', status: 'completed', live: false };",
                "const waitingHtml = workCompletionAction(project, waiting);",
                "if (!waitingHtml.includes('method=\\\"post\\\"')) throw new Error('missing post form');",
                "if (!waitingHtml.includes('project_key=alpha%2Fbeta&work_key=W-0001')) throw new Error('query action');",
                "if (!waitingHtml.includes('Завершить Work')) throw new Error('label');",
                "if (!workCompletionAction(project, stale)) throw new Error('stale action missing');",
                "if (workCompletionAction(project, live) !== '') throw new Error('live action leaked');",
                "if (workCompletionAction(project, completed) !== '') throw new Error('terminal action leaked');",
                "if (waitingHtml.includes('target=')) throw new Error('mutation must stay same-origin');",
            ]
        ) + "\\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        ["node", script],
        check=False,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
'''


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}, expected 1")
    return source.replace(old, new, 1)


def main() -> None:
    Path("src/ai_layer/dashboard/web.py").write_text(WEB_CONTENT, encoding="utf-8")

    work_js = Path("src/ai_layer/dashboard/static/js/views/work.js")
    source = work_js.read_text(encoding="utf-8")
    statuses = '''const WORK_STATUSES = [
  { label: "Все", value: "" },
  { label: "Активные", value: "active" },
  { label: "Blocked", value: "blocked" },
  { label: "Завершённые", value: "completed" },
  { label: "Failed", value: "failed" },
  { label: "Interrupted", value: "interrupted" },
  { label: "Abandoned", value: "abandoned" },
];
'''
    actions = statuses + '''
const COMPLETABLE_WORK_STATUSES = new Set(["active", "awaiting_feedback", "blocked"]);

export function workCompletionAction(project, work) {
  if (
    !project?.key ||
    !work?.key ||
    work.live ||
    !COMPLETABLE_WORK_STATUSES.has(work.status)
  ) return "";
  const action = `/dashboard/actions/work/complete?project_key=${encodeURIComponent(project.key)}&work_key=${encodeURIComponent(work.key)}`;
  return `<form method="post" action="${escapeHtml(action)}">
    <button class="button" type="submit" title="Закрыть Work как completed без запуска агента.">Завершить Work</button>
  </form>`;
}
'''
    source = replace_once(source, statuses, actions, "WORK_STATUSES")

    old_hero = '''      ${stateBadge(workDisplayState(work))}
    </div>
'''
    new_hero = '''      <div class="toolbar-controls">
        ${stateBadge(workDisplayState(work))}
        ${workCompletionAction(project, work)}
      </div>
    </div>
'''
    source = replace_once(source, old_hero, new_hero, "Work detail hero")
    work_js.write_text(source, encoding="utf-8")

    Path("tests/test_dashboard_work_actions.py").write_text(TEST_CONTENT, encoding="utf-8")


if __name__ == "__main__":
    main()
