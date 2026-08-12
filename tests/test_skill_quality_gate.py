import shutil
from pathlib import Path

from scripts import skill_gate

ROOT = Path(__file__).resolve().parents[1]
BUILTINS = ROOT / "src" / "ai_layer" / "builtin_skills"


def _catalog_copy(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(BUILTINS, root / "src" / "ai_layer" / "builtin_skills")
    return root


def test_bundled_skill_quality_floor_accepts_shipped_catalog() -> None:
    result = skill_gate.run_gate(ROOT)

    assert result["ok"] is True, result["errors"]
    assert result["skills"] == 43
    assert result["quality_floor"]["min_content_chars"] == 7000
    assert result["quality_floor"]["min_content_words"] == 850
    assert result["quality_floor"]["min_sections"] == 10


def test_bundled_skill_quality_floor_rejects_shallow_skill(tmp_path: Path) -> None:
    root = _catalog_copy(tmp_path)
    design = root / "src" / "ai_layer" / "builtin_skills" / "design.md"
    content = design.read_text(encoding="utf-8")
    design.write_text(content[:1200], encoding="utf-8")

    result = skill_gate.run_gate(root)

    assert result["ok"] is False
    assert any("design: bundled skill is too shallow" in error for error in result["errors"])
    assert any("design: bundled skill is too terse" in error for error in result["errors"])


def test_bundled_skill_quality_floor_rejects_near_duplicate_skill(tmp_path: Path) -> None:
    root = _catalog_copy(tmp_path)
    skills = root / "src" / "ai_layer" / "builtin_skills"
    svelte = (skills / "svelte.md").read_text(encoding="utf-8")
    copied = svelte.replace("slug: svelte", "slug: vue", 1)
    (skills / "vue.md").write_text(copied, encoding="utf-8")

    result = skill_gate.run_gate(root)

    assert result["ok"] is False
    assert any(
        "svelte/vue: bundled skill bodies are suspiciously similar" in error
        for error in result["errors"]
    )
