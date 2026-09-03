"""Prompt sets: named, complete copies of the layer files under the product
configuration directory, each with its own version ledger.

What matters: a set is a *copy* (one tree a person can read top to bottom),
`default` is the committed tree and is never writable through this API,
`use()` switches every layer accessor to the set for the block only, and a
set a run still names cannot be deleted from under it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from s7_delivery.factory import layers
from s7_delivery.product import config, prompt_sets


@pytest.fixture(autouse=True)
def cfg(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("S7_CONFIG_DIR", str(tmp_path))
    return tmp_path


def test_default_set_is_the_committed_layers_tree() -> None:
    assert prompt_sets.root_of("default") == layers.LAYERS_ROOT
    assert prompt_sets.exists("default")
    only = prompt_sets.list_sets()
    assert [s["name"] for s in only] == ["default"]
    assert only[0]["is_default"] and only[0]["counts"]["task"] >= 18


def test_create_clones_every_file_and_starts_its_own_ledger(cfg: Path) -> None:
    desc = prompt_sets.create_set("tighter", description="stricter wording", author="qa")
    root = prompt_sets.root_of("tighter")
    assert root == cfg / "prompt-sets" / "tighter"
    assert desc["cloned_from"] == "default" and desc["description"] == "stricter wording"
    # Same ids, same bytes, v1 in the new set's own ledger.
    src, dst = layers.load_all(), layers.load_all(root)
    assert set(src) == set(dst)
    assert all(src[i].sha256 == dst[i].sha256 for i in src)
    assert layers.unrecorded(root) == []
    assert all(rec["version"] == 1 for rec in layers.history(root))
    assert layers.skill_ref("developer", root) == "developer@v1"
    # The source's ledger was not copied, but the clone names the versions.
    meta = json.loads((root / prompt_sets.META_FILE).read_text(encoding="utf-8"))
    assert meta["source_versions"]["developer"] == layers.version_of("developer")["version"]
    assert [a["action"] for a in config.audit_log()] == ["prompt_set.create"]


def test_clone_from_a_custom_set_and_list(cfg: Path) -> None:
    prompt_sets.create_set("base", author="qa")
    layers.write_body("developer", "You are a stricter Developer agent.",
                      note="tighten", root=prompt_sets.root_of("base"))
    prompt_sets.create_set("derived", cloned_from="base", author="qa")
    assert layers.skill("developer", prompt_sets.root_of("derived")) == (
        "You are a stricter Developer agent."
    )
    assert [s["name"] for s in prompt_sets.list_sets()] == ["default", "base", "derived"]
    assert prompt_sets.describe("derived")["cloned_from"] == "base"


def test_names_are_validated_and_duplicates_refused() -> None:
    for bad in ("Default", "with space", "a", "-lead", "x" * 41):
        with pytest.raises(prompt_sets.PromptSetError, match="kebab-case"):
            prompt_sets.create_set(bad)
    prompt_sets.create_set("twice")
    with pytest.raises(prompt_sets.PromptSetError, match="already exists"):
        prompt_sets.create_set("twice")
    with pytest.raises(prompt_sets.PromptSetError, match="cannot be re-created"):
        prompt_sets.create_set("default")
    with pytest.raises(prompt_sets.PromptSetError, match="unknown prompt set"):
        prompt_sets.root_of("never-made")
    assert not prompt_sets.exists("never-made")


def test_default_cannot_be_deleted_or_described_away() -> None:
    with pytest.raises(prompt_sets.PromptSetError, match="cannot be deleted"):
        prompt_sets.delete_set("default")
    with pytest.raises(prompt_sets.PromptSetError, match="fixed"):
        prompt_sets.update_description("default", "nope")


def test_delete_refuses_a_set_in_use_then_removes_it(cfg: Path) -> None:
    prompt_sets.create_set("in-use", author="qa")
    with pytest.raises(prompt_sets.PromptSetError, match="S7-00001"):
        prompt_sets.delete_set("in-use", in_use_by=["S7-00001"])
    assert prompt_sets.exists("in-use")
    prompt_sets.delete_set("in-use", author="qa")
    assert not prompt_sets.exists("in-use")
    assert not (cfg / "prompt-sets" / "in-use").exists()
    assert [a["action"] for a in config.audit_log()][0] == "prompt_set.delete"


def test_update_description_is_audited() -> None:
    prompt_sets.create_set("named", author="qa")
    out = prompt_sets.update_description("named", "  now described  ", author="qa")
    assert out["description"] == "now described"
    assert prompt_sets.describe("named")["description"] == "now described"
    assert config.audit_log()[0]["action"] == "prompt_set.describe"


def test_use_switches_the_active_root_for_the_block_only() -> None:
    prompt_sets.create_set("scoped", author="qa")
    root = prompt_sets.root_of("scoped")
    layers.write_body("delivery-assistant", "SCOPED RULES", note="edit", root=root)
    before = layers.rules("delivery-assistant")
    with prompt_sets.use("scoped") as active:
        assert active == root
        assert layers.active_root() == root
        assert layers.rules("delivery-assistant") == "SCOPED RULES"
        assert layers.skill_ref("delivery-assistant") == "delivery-assistant@v2"
        assert layers.describe()["default_set"] is False
    assert layers.rules("delivery-assistant") == before
    assert layers.active_root() == layers.LAYERS_ROOT
    with prompt_sets.use("default"):
        assert layers.active_root() == layers.LAYERS_ROOT


def test_editing_a_set_never_touches_the_default_tree() -> None:
    prompt_sets.create_set("edited", author="qa")
    root = prompt_sets.root_of("edited")
    original = layers.get("reviewer-task")
    layers.write_body("reviewer-task", "Review {{task_id}} strictly.\n{{acceptance_criteria}}",
                      note="shorter", root=root)
    assert layers.get("reviewer-task").sha256 == original.sha256
    assert layers.unrecorded() == []
    assert layers.version_of("reviewer-task", root)["version"] == 2
    with pytest.raises(layers.LayerError, match="not declared"):
        layers.write_body("reviewer-task", "{{not_a_variable}}", note="bad", root=root)
