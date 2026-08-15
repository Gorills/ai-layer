from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ai_layer.cli.doctor import DoctorDependencies, doctor_report
from ai_layer.observability.render import render_monitor

ROOT = Path(__file__).resolve().parents[1]
MISSING_BLACK_BOX = "docs/BLACK-BOX_PROJECT_INTELLIGENCE_v0.7.0_RU.md"
FORBIDDEN_AGENT_LABELS = (
    "подключённые агенты",
    "подключенные агенты",
    "подключённых агентов",
    "подключенных агентов",
    "connected agents",
    "connected agent",
    "agents / mcp",
)


def test_missing_black_box_doc_is_absent() -> None:
    assert not (ROOT / MISSING_BLACK_BOX).is_file()


def test_doctor_does_not_point_at_missing_black_box_doc(tmp_path: Path) -> None:
    doctor_src = (ROOT / "src/ai_layer/cli/doctor.py").read_text(encoding="utf-8")
    assert MISSING_BLACK_BOX not in doctor_src
    assert "BLACK-BOX_PROJECT_INTELLIGENCE" not in doctor_src

    stable_bin = tmp_path / "current" / "bin"
    stable_bin.mkdir(parents=True)
    (stable_bin / "ai-layer").write_text("", encoding="utf-8")
    (stable_bin / "ai-layer-mcp").write_text("", encoding="utf-8")
    machine_runtime = tmp_path / "machine-runtime"
    (machine_runtime / "alembic").mkdir(parents=True)
    (machine_runtime / "docker-compose.yml").write_text("", encoding="utf-8")
    settings = SimpleNamespace(
        stable_bin_dir=stable_bin,
        stable_mcp_executable=stable_bin / "ai-layer-mcp",
        config_file=tmp_path / "config.yaml",
        machine_runtime_dir=machine_runtime,
        projects_registry_file=tmp_path / "projects.json",
    )
    settings.config_file.write_text("version: test\n", encoding="utf-8")

    deps = DoctorDependencies(
        version="0.14.0",
        integration_template_version=1,
        get_settings=lambda: settings,
        docker_compose_available=lambda: (True, "/usr/bin/docker"),
        database_status=lambda: {"connected": True, "pgvector": True},
        global_integration_status=lambda: {
            "cursor": {"ready": True},
            "antigravity": {"ready": True},
            "codex": {"ready": True},
        },
        global_bootstrap_status=lambda: {
            "cursor": {"ready": True, "runtime_acceptance_required": True}
        },
        list_registered_projects=lambda: [],
        list_mcp_processes=lambda: [],
        read_install_state=lambda: {"version": "0.14.0"},
        service_status=lambda: {},
        get_registered_project=lambda _root: None,
        normalize_root=lambda path: Path(path).resolve(),
        project_config_path=lambda root: root / ".ai-layer" / "project.yaml",
        project_mode=lambda _root: "standard",
        project_provenance=lambda _root: "allow",
        project_meta_dir=lambda root: root / ".ai-layer",
        integration_status=lambda _root: {"ready": True},
        repository_footprint=lambda _root: {},
        privacy_check=lambda _root: {"ok": True},
        git_privacy_guard_status=lambda _root: {"ready": True},
        overlapping_registered_projects=lambda _root: [],
    )

    payload = doctor_report(deps, machine_only=True)
    serialized = str(payload)
    assert MISSING_BLACK_BOX not in serialized
    acceptance = [
        issue for issue in payload["issues"] if "black-box acceptance" in issue["problem"]
    ]
    assert len(acceptance) == 1
    action = acceptance[0]["action"]
    assert "release/release-manifest.json" in action
    assert (ROOT / "release" / "release-manifest.json").is_file()
    assert MISSING_BLACK_BOX not in action
    assert payload["ok"] is True


def test_named_architecture_reports_are_marked_superseded() -> None:
    native = (ROOT / "docs/NATIVE_SKILL_ARCHITECTURE_REPORT.md").read_text(encoding="utf-8")
    epics = (ROOT / "docs/EPICS_V1_SUPPORTED_HOST_ACCEPTANCE.md").read_text(encoding="utf-8")
    for text in (native, epics):
        banner = "\n".join(text.splitlines()[:8])
        assert "**Superseded.**" in banner
        assert "not current" in banner.casefold()


def test_operator_facing_copy_labels_mcp_bridges_not_connected_agents() -> None:
    surfaces = [
        ROOT / "src/ai_layer/dashboard/static/js/views/project.js",
        ROOT / "src/ai_layer/dashboard/static/js/components/common.js",
        ROOT / "src/ai_layer/observability/render.py",
    ]
    for path in surfaces:
        text = path.read_text(encoding="utf-8")
        folded = text.casefold()
        for phrase in FORBIDDEN_AGENT_LABELS:
            assert phrase not in folded, f"{path} still labels MCP bridges as {phrase!r}"
        assert "mcp bridge" in folded

    rendered = render_monitor(
        {"version": "0.14.0", "database": {}, "projects": [], "mcp_processes": []}
    )
    assert "MCP bridges" in rendered
    assert "AGENTS / MCP" not in rendered
    assert "connected agent" not in rendered.casefold()
