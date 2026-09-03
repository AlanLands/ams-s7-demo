"""Replay-recording inventory and the ephemeral cache — read the deliverable,
clear only the throwaway."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from s7_delivery.factory import layers
from s7_delivery.product import config, recordings


@pytest.fixture(autouse=True)
def _cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("S7_CONFIG_DIR", str(tmp_path / "config"))


def _write(base: Path, name: str, *, system: str, prompt: str,
           provider: str = "anthropic", model: str = "test-model") -> None:
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{name}.json").write_text(json.dumps({
        "prompt": prompt, "system": system, "provider": provider, "model": model,
        "response": "ok", "usage": {},
    }), encoding="utf-8")


@pytest.fixture()
def replay(tmp_path, monkeypatch) -> Path:
    base = tmp_path / "replay"
    rules = layers.rules("delivery-assistant")
    skill = layers.skill("intake-analysis")
    _write(base, "aaa-upstream", system=rules + "\n\n" + skill,
           prompt="Analyse the requirement " + "x" * 300)
    _write(base, "bbb-downstream", system=layers.rules("downstream-lane"),
           prompt=layers.skill("developer") + "\n\nTask body", provider="openai")
    _write(base, "ccc-retired", system="Some retired wording", prompt="old prompt")
    (base / "not-a-recording.txt").write_text("ignored", encoding="utf-8")
    monkeypatch.setenv("LLM_REPLAY_DIR", str(base))
    return base


def test_inventory_attributes_lane_and_skill_by_the_guard_rule(replay):
    inv = recordings.inventory()
    assert inv["replay_dir"] == str(replay)
    assert inv["count"] == 3
    assert inv["total_bytes"] == sum(p.stat().st_size for p in replay.glob("*.json"))
    by_name = {i["name"]: i for i in inv["items"]}
    up = by_name["aaa-upstream.json"]
    assert (up["lane"], up["skill"]) == ("delivery-assistant", "intake-analysis")
    assert up["provider"] == "anthropic" and up["model"] == "test-model"
    assert up["prompt_head"] == ("Analyse the requirement " + "x" * 300)[:160]
    assert len(up["prompt_head"]) == 160
    assert up["size"] > 0 and up["modified_at"].endswith("+00:00")
    down = by_name["bbb-downstream.json"]
    assert (down["lane"], down["skill"]) == ("downstream-lane", "developer")
    assert down["provider"] == "openai"
    retired = by_name["ccc-retired.json"]
    assert (retired["lane"], retired["skill"]) == (None, None)
    assert set(up) == {"name", "provider", "model", "lane", "skill", "prompt_head",
                       "size", "modified_at"}


def test_pinned_count_finds_a_body_in_system_or_prompt(replay):
    assert recordings.pinned_count(layers.rules("delivery-assistant")) == 1
    assert recordings.pinned_count(layers.skill("intake-analysis")) == 1
    assert recordings.pinned_count(layers.skill("developer")) == 1  # rides in the prompt
    assert recordings.pinned_count(layers.rules("downstream-lane")) == 1
    assert recordings.pinned_count(layers.skill("reviewer")) == 0
    assert recordings.pinned_count("") == 0
    # CRLF-normalised: an editor's copy of the body still matches.
    assert recordings.pinned_count(layers.skill("intake-analysis").replace("\n", "\r\n")) == 1


def test_inventory_of_a_missing_replay_dir_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_REPLAY_DIR", str(tmp_path / "nope"))
    inv = recordings.inventory()
    assert inv["count"] == 0 and inv["items"] == [] and inv["total_bytes"] == 0


def test_the_committed_recordings_all_attribute_to_a_current_lane(monkeypatch):
    """The inventory over the real replay dir agrees with the recordings
    guard: every recording that starts with a current rules body carries a
    skill this repo holds (or none for the skill-less staged lane)."""
    monkeypatch.delenv("LLM_REPLAY_DIR", raising=False)
    inv = recordings.inventory(Path("s7_delivery/cache/llm"))
    assert inv["count"] > 0
    lanes = {i["lane"] for i in inv["items"]} - {None}
    assert lanes == {"delivery-assistant", "downstream-lane", "staged-pipeline"}
    for item in inv["items"]:
        if item["lane"] == "downstream-lane":
            assert item["skill"] in {"developer", "tester", "reviewer"}, item["name"]
        if item["lane"] == "staged-pipeline":
            assert item["skill"] is None


def test_cache_stats_and_clear_touch_only_the_cache_dir(tmp_path, monkeypatch, replay):
    cache = tmp_path / "cache"
    (cache / "sub").mkdir(parents=True)
    (cache / "a.json").write_text("{}", encoding="utf-8")
    (cache / "sub" / "b.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("LLM_CACHE_DIR", str(cache))
    stats = recordings.cache_stats()
    assert stats == {"cache_dir": str(cache), "count": 2, "total_bytes": 4}
    assert recordings.clear_cache(actor="ops") == {"removed": 2}
    assert recordings.cache_stats()["count"] == 0
    # The replay dir is untouched.
    assert recordings.inventory()["count"] == 3
    rec = config.audit_log(action="cache.clear")[0]
    assert rec["actor"] == "ops" and rec["detail"] == "removed 2 file(s)"
    assert recordings.clear_cache() == {"removed": 0}


def test_clear_refuses_when_cache_dir_is_the_replay_dir(monkeypatch, replay):
    monkeypatch.setenv("LLM_CACHE_DIR", str(replay))
    with pytest.raises(config.ConfigError, match="committed replay directory"):
        recordings.clear_cache()
    assert recordings.inventory()["count"] == 3


def test_missing_cache_dir_is_empty_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "nope"))
    assert recordings.cache_stats()["count"] == 0
    assert recordings.clear_cache() == {"removed": 0}
