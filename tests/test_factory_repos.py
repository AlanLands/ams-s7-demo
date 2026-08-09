"""Clone + context pack. Offline: fixtures are local git repos."""
import subprocess
from pathlib import Path

import pytest

from demo.create_target_repos import PORTAL_FILES, write_repo
from s7_delivery.factory.repos import (
    RepoConnectError,
    build_context_pack,
    clone_repo,
    forget_repo,
    known_repos,
    remember_repo,
)


def make_fixture_repo(tmp_path: Path) -> Path:
    repo = write_repo("maplesure-sponsor-portal", PORTAL_FILES, tmp_path / "src")
    env_id = ["-c", "user.email=demo@example.invalid", "-c", "user.name=demo"]
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), *env_id, "commit", "-qm", "init"], check=True)
    return repo


def test_clone_repo_records_metadata(tmp_path: Path):
    src = make_fixture_repo(tmp_path)
    rec = clone_repo(str(src), tmp_path / "dest")
    assert rec.name == "maplesure-sponsor-portal"
    assert len(rec.head_sha) == 40
    assert rec.file_count > 5
    assert (tmp_path / "dest" / rec.name / "architecture.md").is_file()


def test_clone_repo_bad_url_raises(tmp_path: Path):
    with pytest.raises(RepoConnectError):
        clone_repo(str(tmp_path / "no-such-repo"), tmp_path / "dest")


def test_context_pack_contains_architecture_tree_and_excerpts(tmp_path: Path):
    src = make_fixture_repo(tmp_path)
    rec = clone_repo(str(src), tmp_path / "dest")
    pack = build_context_pack(tmp_path / "dest" / rec.name, rec.name)
    assert "What this application does NOT do" in pack   # architecture.md verbatim
    assert "portal/members.py" in pack                    # file tree
    assert "def list_members" in pack                     # source excerpt


def test_context_pack_respects_cap(tmp_path: Path):
    src = make_fixture_repo(tmp_path)
    rec = clone_repo(str(src), tmp_path / "dest")
    pack = build_context_pack(tmp_path / "dest" / rec.name, rec.name, cap_bytes=2000)
    assert len(pack.encode("utf-8")) <= 4000  # cap governs excerpts; header+tree small
    assert "[truncated" in pack


def test_clone_repo_rejects_ext_transport(tmp_path: Path):
    with pytest.raises(RepoConnectError, match="Unsupported repository URL"):
        clone_repo("ext::sh -c 'touch /tmp/pwned'", tmp_path / "dest")


def test_clone_repo_rejects_option_injection(tmp_path: Path):
    with pytest.raises(RepoConnectError, match="Unsupported repository URL"):
        clone_repo("--upload-pack=touch /tmp/pwned", tmp_path / "dest")


def test_failed_clone_leaves_no_stale_dir_and_retry_works(tmp_path: Path):
    src = make_fixture_repo(tmp_path)
    bad = tmp_path / "src" / "maplesure-sponsor-portal-missing"
    with pytest.raises(RepoConnectError):
        clone_repo(str(bad), tmp_path / "dest")
    assert not (tmp_path / "dest" / "maplesure-sponsor-portal-missing").exists()
    rec = clone_repo(str(src), tmp_path / "dest")
    assert rec.name == "maplesure-sponsor-portal"


# --- known-repos registry (survives run deletion) ---------------------------


def test_known_repos_on_missing_file_is_empty(tmp_path: Path):
    assert known_repos(tmp_path) == []


def test_remember_repo_upserts_by_url_newest_first(tmp_path: Path):
    remember_repo(
        {"url": "https://x/a", "name": "a", "default_branch": "main",
         "last_connected_at": "t1"},
        tmp_path,
    )
    remember_repo(
        {"url": "https://x/b", "name": "b", "default_branch": "main",
         "last_connected_at": "t2"},
        tmp_path,
    )
    items = known_repos(tmp_path)
    assert [i["url"] for i in items] == ["https://x/b", "https://x/a"]

    # Re-connecting "a" moves it to front and updates its fields — no duplicate.
    remember_repo(
        {"url": "https://x/a", "name": "a", "default_branch": "develop",
         "last_connected_at": "t3"},
        tmp_path,
    )
    items = known_repos(tmp_path)
    assert [i["url"] for i in items] == ["https://x/a", "https://x/b"]
    assert len(items) == 2
    assert items[0]["default_branch"] == "develop"
    assert items[0]["last_connected_at"] == "t3"


def test_forget_repo_removes_and_reports_whether_it_existed(tmp_path: Path):
    remember_repo(
        {"url": "https://x/a", "name": "a", "default_branch": "main",
         "last_connected_at": "t1"},
        tmp_path,
    )
    assert forget_repo("https://x/a", tmp_path) is True
    assert known_repos(tmp_path) == []
    assert forget_repo("https://x/a", tmp_path) is False


def test_forget_repo_on_missing_file_returns_false(tmp_path: Path):
    assert forget_repo("https://x/never-connected", tmp_path) is False


# --- credentials never reach disk (I6) ---------------------------------------


def test_normalize_repo_url_strips_userinfo():
    from s7_delivery.factory.repos import normalize_repo_url

    assert normalize_repo_url(
        "https://alan:ghp_secret@github.com/AlanLands/app.git"
    ) == "https://github.com/AlanLands/app.git"
    assert normalize_repo_url(
        "https://github.com/AlanLands/app"
    ) == "https://github.com/AlanLands/app"
    assert normalize_repo_url("") == ""


def test_clone_record_strips_credentials_but_git_still_gets_them(tmp_path, monkeypatch):
    from s7_delivery.factory import repos as repos_mod

    calls: list[tuple] = []

    def fake_git(cwd, *args):
        calls.append(args)
        if "clone" in args:
            Path(args[-1]).mkdir(parents=True)
            return ""
        return "main" if "--abbrev-ref" in args else "a" * 40

    monkeypatch.setattr(repos_mod, "_git", fake_git)
    rec = clone_repo(
        "https://alan:ghp_secret@github.com/AlanLands/app.git", tmp_path / "dest"
    )
    assert rec.url == "https://github.com/AlanLands/app.git"
    assert "ghp_secret" not in rec.model_dump_json()
    # the credential still did its one job: authenticating the clone
    assert any("ghp_secret" in " ".join(a) for a in calls)


def test_clone_failure_message_is_redacted(tmp_path, monkeypatch):
    import subprocess as sp

    from s7_delivery.factory import repos as repos_mod

    def boom(*args, **kwargs):
        raise sp.CalledProcessError(
            128, "git",
            stderr="fatal: could not read from"
                   " https://alan:ghp_secret@github.com/AlanLands/app.git",
        )

    monkeypatch.setattr(repos_mod.subprocess, "run", boom)
    with pytest.raises(RepoConnectError) as exc:
        clone_repo("https://alan:ghp_secret@github.com/AlanLands/app.git",
                   tmp_path / "dest")
    assert "ghp_secret" not in str(exc.value)


def test_registry_never_stores_credentials(tmp_path: Path):
    remember_repo(
        {"url": "https://alan:ghp_secret@github.com/AlanLands/app.git",
         "name": "app", "default_branch": "main", "last_connected_at": "t"},
        tmp_path,
    )
    items = known_repos(tmp_path)
    assert items[0]["url"] == "https://github.com/AlanLands/app.git"
    assert "ghp_secret" not in (tmp_path / "known_repos.json").read_text()
    # forgetting works from either form
    assert forget_repo(
        "https://alan:ghp_secret@github.com/AlanLands/app.git", tmp_path
    ) is True
