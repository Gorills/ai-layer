from pathlib import Path

from ai_layer.memory.scanner import (
    build_file_state,
    extract_imports,
    infer_purpose,
    iter_files,
    language_for,
    parse_dependencies,
    prepare_index_text,
    read_stable_text,
    redact_secrets,
)


def test_scanner_helpers(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\nversion="0.1"\ndependencies=["fastapi>=1"]\n')
    assert language_for(Path("main.py")) == "python"
    assert "entry point" in infer_purpose("main.py", "", "python").lower()
    imports = extract_imports("import os\nfrom pathlib import Path\nroute='/health'\n")
    assert "os" in imports and "pathlib" in imports
    assert "/health" not in imports
    assert parse_dependencies(tmp_path)["python"] == ["fastapi>=1"]


def test_secret_redaction():
    text = (
        "API_KEY=abc123\n"
        "password: hunter2\n"
        "AWS_SECRET_ACCESS_KEY=aws-secret\n"
        "SERVICE_TOKEN=service-secret\n"
        "export PRIVATE_KEY=private-secret\n"
        "\"SERVICE_TOKEN\": \"json-secret\",\n"
        "const API_KEY = js-secret;\n"
        "DATABASE_URL=postgres://user:db-secret@localhost/db\n"
        "registry=https://user:url-secret@example.invalid/simple?token=query-secret\n"
        "Authorization: Bearer abcdefghijklmnop\n"
        "normal=value\n"
    )
    redacted = redact_secrets(text)
    for secret in (
        "abc123", "hunter2", "aws-secret", "service-secret", "private-secret", "json-secret",
        "js-secret", "db-secret", "url-secret", "query-secret", "abcdefghijklmnop",
    ):
        assert secret not in redacted
    assert "normal=value" in redacted


def test_secret_redaction_covers_minified_json_object_pairs():
    marker = "AI_LAYER_JSON_SECRET_PROBE_MINIFIED"
    text = '{"SERVICE_TOKEN":"' + marker + '","normal":"keep"}'
    redacted = redact_secrets(text)
    assert marker not in redacted
    assert '"SERVICE_TOKEN":<redacted>' in redacted
    assert '"normal":"keep"' in redacted


def test_scanner_excludes_environment_secret_variants_but_keeps_templates(tmp_path: Path):
    for name in (
        ".env", ".env.local", ".env.staging", ".env.production", ".envrc",
        ".git-credentials", "credentials.json", "secrets.yaml", "terraform.tfstate", "prod.tfvars",
    ):
        (tmp_path / name).write_text("SERVICE_TOKEN=secret\n", encoding="utf-8")
    for name in (".env.example", ".env.sample", ".env.template"):
        (tmp_path / name).write_text("SERVICE_TOKEN=placeholder\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")

    names = {path.name for path in iter_files(tmp_path)}
    assert {".env.example", ".env.sample", ".env.template", "app.py"} <= names
    assert not ({
        ".env", ".env.local", ".env.staging", ".env.production", ".envrc",
        ".git-credentials", "credentials.json", "secrets.yaml", "terraform.tfstate", "prod.tfvars",
    } & names)


def test_ai_layer_bootstrap_is_not_indexed(tmp_path: Path):
    managed = "<!-- BEGIN AI-LAYER MANAGED -->\nmandatory memory_context\n<!-- END AI-LAYER MANAGED -->"
    assert prepare_index_text(".cursor/rules/ai-layer.mdc", managed) is None
    assert prepare_index_text("AGENTS.md", managed) is None
    mixed = "# User rules\nKeep domain services pure.\n\n" + managed
    assert prepare_index_text("AGENTS.md", mixed) == "# User rules\nKeep domain services pure."

    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    control = tmp_path / ".cursor" / "rules" / "ai-layer.mdc"
    control.parent.mkdir(parents=True)
    control.write_text(managed, encoding="utf-8")
    shared = tmp_path / "AGENTS.md"
    shared.write_text(managed, encoding="utf-8")
    state = build_file_state(tmp_path)
    assert "app.py" in state
    assert "AGENTS.md" in state  # metadata-only tracking; managed content is still not indexed
    assert ".cursor/rules/ai-layer.mdc" not in state


def test_dependency_metadata_redacts_embedded_credentials(tmp_path: Path):
    marker = "ultra-secret-marker"
    (tmp_path / "requirements.txt").write_text(
        f"private-lib @ https://build:{marker}@packages.example.invalid/private-lib.whl\n"
        "public-lib==1.2.3\n",
        encoding="utf-8",
    )
    deps = parse_dependencies(tmp_path)["python"]
    rendered = "\n".join(deps)
    assert marker not in rendered
    assert "<redacted>@packages.example.invalid" in rendered
    assert "public-lib==1.2.3" in rendered


def test_project_file_upsert_is_idempotent():
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from ai_layer.db.base import Base
    from ai_layer.db.models import Project, ProjectFile
    from ai_layer.memory.scanner import _upsert_project_file

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        project = Project(name="demo", root_path="/demo", languages={}, dependencies={}, architecture_summary="")
        db.add(project)
        db.flush()
        base = {
            "project_id": project.id,
            "path": ".gitignore",
            "language": None,
            "purpose": "Project file",
            "imports": [],
            "risk_flags": [],
            "sha256": "a" * 64,
            "size_bytes": 10,
        }
        _upsert_project_file(db, base)
        db.flush()
        _upsert_project_file(db, {**base, "sha256": "b" * 64, "size_bytes": 20})
        db.flush()

        rows = db.scalars(select(ProjectFile).where(ProjectFile.project_id == project.id)).all()
        assert len(rows) == 1
        assert rows[0].sha256 == "b" * 64
        assert rows[0].size_bytes == 20


def test_stable_read_rejects_file_changed_during_read(monkeypatch):
    import stat

    from ai_layer.memory import source

    class Stat:
        st_dev = 1
        st_ino = 1
        st_mode = stat.S_IFREG | 0o644

        def __init__(self, size, mtime):
            self.st_size = size
            self.st_mtime_ns = mtime

    class MovingPath:
        def __init__(self):
            self.calls = 0

        def lstat(self):
            self.calls += 1
            return Stat(10, 100) if self.calls == 1 else Stat(11, 200)

    monkeypatch.setattr(source, "read_text", lambda path: "old-content")
    assert read_stable_text(MovingPath()) is None


def test_scan_reembeds_existing_decisions_when_vector_space_changes(tmp_path: Path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from ai_layer.db.base import Base
    from ai_layer.db.models import Decision, Project
    from ai_layer.memory import indexer, scanner

    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")

    class Embedder:
        def embed(self, texts):
            vectors = []
            for text in texts:
                marker = 0.75 if text == "Use PostgreSQL" else 0.25
                vectors.append([marker] + [0.0] * 383)
            return vectors

    monkeypatch.setattr(indexer, "get_embedder", lambda: Embedder())

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        project = Project(name="demo", root_path=str(tmp_path), languages={}, dependencies={}, architecture_summary="")
        db.add(project)
        db.flush()
        decision = Decision(
            project_id=project.id,
            title="DB",
            context="architecture",
            decision="Use PostgreSQL",
            rationale="durability",
            embedding=[0.0] * 384,
        )
        db.add(decision)
        db.flush()

        scanner.scan_project(db, project, tmp_path, reembed_decisions=True)
        db.flush()

        assert decision.embedding[0] == 0.75
        assert len(decision.embedding) == 384


def test_scanner_never_follows_project_symlinks_outside_root(tmp_path: Path):
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("SERVICE_TOKEN=outside-secret-marker\n", encoding="utf-8")
    (tmp_path / "linked.txt").symlink_to(outside)

    outside_requirements = tmp_path.parent / "outside-requirements.txt"
    outside_requirements.write_text(
        "private @ https://user:outside-requirements-marker@example.invalid/pkg.whl\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").symlink_to(outside_requirements)
    (tmp_path / "app.py").write_text("print('safe')\n", encoding="utf-8")

    indexed = {path.name for path in iter_files(tmp_path)}
    assert "app.py" in indexed
    assert "linked.txt" not in indexed
    assert "requirements.txt" not in indexed
    assert parse_dependencies(tmp_path) == {}


def test_scan_never_persists_minified_json_source_content_as_knowledge(tmp_path: Path, monkeypatch):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from ai_layer.db.base import Base
    from ai_layer.db.models import Knowledge, Project, ProjectFile
    from ai_layer.memory import indexer, scanner

    marker = "AI_LAYER_JSON_SECRET_PROBE_PERSISTED"
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.json").write_text(
        '{"SERVICE_TOKEN":"' + marker + '","normal":"keep"}',
        encoding="utf-8",
    )

    class Embedder:
        def embed(self, texts):
            return [[0.0] * 384 for _ in texts]

    monkeypatch.setattr(indexer, "get_embedder", lambda: Embedder())

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        project = Project(name="demo", root_path=str(tmp_path), languages={}, dependencies={}, architecture_summary="")
        db.add(project)
        db.flush()
        scanner.scan_project(db, project, tmp_path)
        db.flush()

        assert db.scalar(select(Knowledge).where(Knowledge.project_id == project.id)) is None
        evidence = db.scalar(
            select(ProjectFile).where(
                ProjectFile.project_id == project.id,
                ProjectFile.path == "config/settings.json",
            )
        )
        assert evidence is not None
        persisted = repr({
            "purpose": evidence.purpose,
            "imports": evidence.imports,
            "risk_flags": evidence.risk_flags,
            "sha256": evidence.sha256,
        })
        assert marker not in persisted
        assert '"normal":"keep"' not in persisted


def test_git_scanner_respects_standard_ignore_rules(tmp_path: Path):
    import subprocess

    subprocess.run(["git", "-C", str(tmp_path), "init"], check=True, capture_output=True)
    (tmp_path / ".gitignore").write_text("private-note.txt\n.cache-custom/\n", encoding="utf-8")
    (tmp_path / "private-note.txt").write_text("private\n", encoding="utf-8")
    cache = tmp_path / ".cache-custom"
    cache.mkdir()
    (cache / "blob.txt").write_text("private cache\n", encoding="utf-8")
    (tmp_path / "visible.py").write_text("print('visible')\n", encoding="utf-8")

    paths = {path.relative_to(tmp_path).as_posix() for path in iter_files(tmp_path)}

    assert "visible.py" in paths
    assert ".gitignore" in paths
    assert "private-note.txt" not in paths
    assert ".cache-custom/blob.txt" not in paths
