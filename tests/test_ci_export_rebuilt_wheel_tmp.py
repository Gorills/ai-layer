from __future__ import annotations

import base64
import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _builder():
    path = ROOT / "scripts" / "build_release_wheel.py"
    spec = importlib.util.spec_from_file_location("build_release_wheel_tmp", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_export_rebuilt_wheel_for_ci_fix(tmp_path: Path) -> None:
    rebuilt = _builder().build(tmp_path)
    data = rebuilt.read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    print("WHEEL_SHA256=" + hashlib.sha256(data).hexdigest())
    print("WHEEL_B64_BEGIN")
    for offset in range(0, len(encoded), 120):
        print(encoded[offset : offset + 120])
    print("WHEEL_B64_END")
    pytest.fail("temporary CI wheel export; remove before final diff")
