#!/usr/bin/env python3
"""Build the AI Layer pure-Python wheel deterministically using only the stdlib.

The release archive ships this prebuilt wheel, so end-user installation does not
need a floating build backend. This builder is intentionally small and auditable.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import os
import re
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
SRC = ROOT / "src" / "ai_layer"
DIST = ROOT / "dist"
FIXED_TIMESTAMP = (2026, 8, 10, 0, 0, 0)


def digest(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def wheel_name(version: str) -> str:
    normalized = re.sub(r"[-]+", "_", version)
    return f"local_ai_development_layer-{normalized}-py3-none-any.whl"


def build(output_dir: Path = DIST) -> Path:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    version = project["version"]
    filename = wheel_name(version)
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / filename
    dist_info = f"local_ai_development_layer-{version}.dist-info"

    files: dict[str, bytes] = {}
    for path in sorted(SRC.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        arc = Path("ai_layer") / path.relative_to(SRC)
        files[arc.as_posix()] = path.read_bytes()

    metadata = [
        "Metadata-Version: 2.3",
        "Name: local-ai-development-layer",
        f"Version: {version}",
        f"Summary: {project['description']}",
        f"Requires-Python: {project['requires-python']}",
    ]
    metadata.extend(f"Requires-Dist: {dep}" for dep in project.get("dependencies", []))
    metadata.append("")
    files[f"{dist_info}/METADATA"] = "\n".join(metadata).encode()
    files[f"{dist_info}/WHEEL"] = (
        b"Wheel-Version: 1.0\nGenerator: ai-layer-stdlib-release-builder\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    )
    scripts = project.get("scripts", {})
    entry_points = ["[console_scripts]"]
    entry_points.extend(f"{name} = {target}" for name, target in sorted(scripts.items()))
    entry_points.append("")
    files[f"{dist_info}/entry_points.txt"] = "\n".join(entry_points).encode()
    files[f"{dist_info}/top_level.txt"] = b"ai_layer\n"

    record_rows: list[list[str]] = []
    for name in sorted(files):
        data = files[name]
        record_rows.append([name, digest(data), str(len(data))])
    record_path = f"{dist_info}/RECORD"
    record_rows.append([record_path, "", ""])
    buf = io.StringIO(newline="")
    csv.writer(buf, lineterminator="\n").writerows(record_rows)
    files[record_path] = buf.getvalue().encode()

    tmp = out.with_suffix(out.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, FIXED_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 3
            zf.writestr(info, files[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    os.replace(tmp, out)
    return out


if __name__ == "__main__":
    print(build())
