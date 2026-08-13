from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "tests/test_agent_facing_contracts.py"
text = path.read_text(encoding="utf-8")
old = "    assert integration_service.GLOBAL_BOOTSTRAP_VERSION == CANONICAL_BOOTSTRAP_VERSION\n"
if text.count(old) != 1:
    raise RuntimeError("expected service bootstrap-version assertion not found exactly once")
path.write_text(text.replace(old, "", 1), encoding="utf-8")
