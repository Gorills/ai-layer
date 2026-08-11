from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEEL = ROOT / "dist/local_ai_development_layer-0.12.2-py3-none-any.whl"

if not WHEEL.is_file():
    raise SystemExit(f"release wheel missing: {WHEEL}")

wheel_digest = hashlib.sha256(WHEEL.read_bytes()).hexdigest()
manifest_path = ROOT / "release/release-manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["version"] = "0.12.2"
manifest["application_wheel"] = "dist/local_ai_development_layer-0.12.2-py3-none-any.whl"
manifest["application_wheel_sha256"] = wheel_digest
manifest["notes"] = (
    "0.12.2 fixes Dashboard background load: passive read-side refreshes no longer invoke "
    "authoritative task_next repository guards, duplicate Task reads are removed, the Epic list "
    "uses a lightweight summary query, native catalog counts are cached, and browser polling is "
    "adaptive and paused for hidden tabs. No schema or Task/Epic transition semantics changed."
)
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

policy_path = ROOT / "release/governance-policy.json"
policy = json.loads(policy_path.read_text(encoding="utf-8"))
protected: dict[str, str] = {}
for raw in policy["protected_paths"]:
    path = ROOT / raw
    if not path.is_file():
        raise SystemExit(f"protected governance path missing: {raw}")
    protected[raw] = hashlib.sha256(path.read_bytes()).hexdigest()

baseline = {
    "schema": 1,
    "policy_sha256": hashlib.sha256(policy_path.read_bytes()).hexdigest(),
    "protected": protected,
    "note": "Local tamper-evident baseline; production trust is external protected CI/release signing.",
}
(ROOT / "release/governance-baseline.json").write_text(
    json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
print(wheel_digest)
