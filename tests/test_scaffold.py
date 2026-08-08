"""Scaffold generation — canned model JSON, offline."""
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
