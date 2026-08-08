"""The target-repo generator: pure file generation, offline."""
from pathlib import Path

from demo.create_target_repos import API_FILES, PORTAL_FILES, write_repo


def test_write_repo_creates_tree(tmp_path: Path):
    root = write_repo("maplesure-sponsor-portal", PORTAL_FILES, tmp_path)
    assert root == tmp_path / "maplesure-sponsor-portal"
    assert (root / "architecture.md").is_file()
    assert (root / "app.py").is_file()


def test_both_repos_carry_architecture_md_with_scope_exclusions(tmp_path: Path):
    for name, files in (("maplesure-sponsor-portal", PORTAL_FILES),
                        ("maplesure-claims-api", API_FILES)):
        root = write_repo(name, files, tmp_path)
        text = (root / "architecture.md").read_text(encoding="utf-8")
        assert "MapleSure" in text
        # The design-review grounding pattern: what the app is NOT is explicit.
        assert "does not" in text.lower()


def test_portal_lacks_disability_submission(tmp_path: Path):
    """The epic's gap must exist: no disability claim feature in the portal."""
    root = write_repo("maplesure-sponsor-portal", PORTAL_FILES, tmp_path)
    source = "\n".join(
        p.read_text(encoding="utf-8") for p in root.rglob("*.py")
    )
    assert "disability" not in source.lower()
