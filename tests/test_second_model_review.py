"""Second-model independent review: generate with one model, review with a
different one (Design review item 4 — structural, not decorative).

Three guarantees: complete() honours per-call provider/model overrides (and
the override enters the cache key, so recordings can never cross models);
the downstream reviewer reads its model from REVIEW_LLM_* env; and the G2
gate's reviewer-independence condition is a data check, not a literal True.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import common.llm as llm
from s7_delivery import downstream
from s7_delivery.factory import gates

_ENV_KEYS = (
    "LLM_MODE", "LLM_PROVIDER", "LLM_CACHE_DIR", "LLM_REPLAY_DIR",
    "LLM_NO_CACHE", "LLM_TELEMETRY_PATH", "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL", "OPENAI_API_KEY", "OPENAI_MODEL",
    "REVIEW_LLM_PROVIDER", "REVIEW_LLM_MODEL",
)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_MODEL", "gen-model")
    monkeypatch.setenv("LLM_REPLAY_DIR", str(tmp_path / "replay"))
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("LLM_TELEMETRY_PATH", str(tmp_path / "telemetry.jsonl"))


def _write_recording(prompt: str, response: str, *, model: str) -> Path:
    path = llm._path_for_mode(
        mode="replay", provider="anthropic", model=model,
        system=None, prompt=prompt, cache_key=None,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "prompt": prompt, "system": None, "provider": "anthropic",
        "model": model, "response": response,
    }))
    return path


def test_model_override_selects_its_own_recording():
    """The override enters the cache key: the same prompt replayed under
    two models resolves to two distinct recordings."""
    _write_recording("p", "from gen model", model="gen-model")
    _write_recording("p", "from review model", model="review-model")
    assert llm.complete("p") == "from gen model"
    assert llm.complete("p", model="review-model") == "from review model"


def test_model_override_missing_recording_fails_loudly():
    _write_recording("p", "from gen model", model="gen-model")
    with pytest.raises(llm.LLMError, match="recording"):
        llm.complete("p", model="never-recorded")


def test_provider_override_is_validated():
    with pytest.raises(llm.LLMError, match="provider"):
        llm.complete("p", provider="not-a-provider")


def test_reviewer_kwargs_come_from_review_env(monkeypatch):
    monkeypatch.setenv("REVIEW_LLM_PROVIDER", "openai")
    monkeypatch.setenv("REVIEW_LLM_MODEL", "review-model")
    assert downstream._reviewer_llm_kwargs() == {
        "provider": "openai", "model": "review-model",
    }


def test_reviewer_kwargs_default_to_same_model():
    """No REVIEW_* config → same model reviews, and the caller can say so."""
    assert downstream._reviewer_llm_kwargs() == {}


def test_review_gate_checks_reviewer_is_not_the_developer():
    tasks = [{"task_id": "T-1", "story_id": "US-001", "status": "completed"}]
    reviews = [{"task_id": "T-1", "result": "passed", "major_gaps": 0,
                "reviewer": "j.doe"}]
    conditions = gates.independent_review_gate(
        reviews, tasks, developers={"US-001": "j.doe"})
    row = next(c for c in conditions if "not the developer" in c["condition"])
    assert row["met"] is False

    conditions = gates.independent_review_gate(
        reviews, tasks, developers={"US-001": "someone.else"})
    row = next(c for c in conditions if "not the developer" in c["condition"])
    assert row["met"] is True


def test_stream_complete_still_resolves_from_env(monkeypatch):
    """Regression: stream_complete has no override params and must resolve
    provider/model from env without NameError (a scripted edit once broke
    this)."""
    path = llm._path_for_mode(
        mode="replay", provider="anthropic", model="gen-model",
        system=None, prompt="sp", cache_key=None,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "prompt": "sp", "system": None, "provider": "anthropic",
        "model": "gen-model", "response": "streamed",
    }))
    assert "".join(llm.stream_complete("sp")) == "streamed"
