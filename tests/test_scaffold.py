"""Scaffold generation — canned model JSON, offline."""
import subprocess

import pytest

from common.llm import LLMError
from s7_delivery.factory import scaffold


def fake_complete(response: dict):
    import json

    def _fake(prompt, *, json_mode=False, cache_key=None, usage_out=None, **kw):
        if usage_out is not None:
            usage_out.update({"input_tokens": 400, "output_tokens": 300})
        return json.dumps(response)
    return _fake


GOOD_SCAFFOLD = {
    "architecture_md": (
        "# MapleSure Eligibility Check — architecture\n\n"
        "New application. No components exist yet.\n\n"
        "## What this application does NOT do\n- Nothing is built yet.\n"
    ),
    "readme_md": "# MapleSure Eligibility Check\n\nNew synthetic demo application.\n",
}


def test_generate_scaffold_returns_two_files(monkeypatch):
    monkeypatch.setattr(scaffold, "complete", fake_complete(GOOD_SCAFFOLD))
    files, usage = scaffold.generate_scaffold(
        "maplesure-eligibility-check", "Retirement eligibility check.", "FastAPI"
    )
    assert set(files) == {"architecture.md", "README.md"}
    assert "does NOT do" in files["architecture.md"]
    assert usage["input_tokens"] == 400


def test_generate_scaffold_rejects_empty_architecture(monkeypatch):
    bad = dict(GOOD_SCAFFOLD, architecture_md="")
    monkeypatch.setattr(scaffold, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="empty"):
        scaffold.generate_scaffold("name", "desc", "stack")


def test_write_scaffold_locally_cleans_up_on_git_failure_and_allows_retry(tmp_path, monkeypatch):
    from s7_delivery.factory.repos import RepoConnectError

    dest_root = tmp_path / "dest"
    dest_root.mkdir()
    name = "maplesure-eligibility-check"
    files = {"architecture.md": "# arch\n", "README.md": "# readme\n"}

    def fail_git_init(cmd, *args, **kwargs):
        if "init" in cmd:
            raise subprocess.CalledProcessError(1, cmd, stderr="git init failed")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(scaffold.subprocess, "run", fail_git_init)
    with pytest.raises(RepoConnectError, match="git init failed"):
        scaffold.write_scaffold_locally(name, files, dest_root)

    # Cleanup happened: retry with the same name and dest_root must not
    # hit the "already exists locally" guard.
    assert not (dest_root / name).exists()

    monkeypatch.undo()
    repo = scaffold.write_scaffold_locally(name, files, dest_root)
    assert repo == dest_root / name
    assert (repo / "architecture.md").read_text(encoding="utf-8") == "# arch\n"
