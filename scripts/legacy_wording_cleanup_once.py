from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count < 1:
        raise RuntimeError(f"{path}: expected text not found: {old!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


replace(
    "src/ai_layer/core/runtime.py",
    "Unversioned Task Layer schema is partially migrated; manual recovery is required.",
    "Unversioned managed Task schema is partially migrated; manual recovery is required.",
)
replace(
    "src/ai_layer/core/runtime.py",
    "Unversioned Task Layer schema is inconsistent with its prerequisite revisions.",
    "Unversioned managed Task schema is inconsistent with its prerequisite revisions.",
)
replace(
    "src/ai_layer/projections/dashboard.py",
    "def _latest_memory_context_skill_state(events: list[dict]) -> dict:",
    "def _latest_legacy_memory_context_skill_state(events: list[dict]) -> dict:",
)
replace(
    "src/ai_layer/projections/dashboard.py",
    "last_context = _latest_memory_context_skill_state(events)",
    "last_context = _latest_legacy_memory_context_skill_state(events)",
)
replace(
    "src/ai_layer/integrations/config_files.py",
    "def _legacy_owned_file(path: Path, content: str) -> bool:\n",
    "def _legacy_owned_file(path: Path, content: str) -> bool:\n    # Historical markers are intentionally preserved only for safe ownership detection/removal.\n    # They are not current agent instructions or current workflow semantics.\n",
)
print("legacy wording cleanup applied")
