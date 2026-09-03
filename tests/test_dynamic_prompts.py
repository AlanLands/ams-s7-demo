"""Every prompt is dynamic per API call.

A run names its prompt set; every model call of that run resolves rules,
skill and task text against that set *at call time*; provider and model come
from the per-stage settings; and the activity ledger names the version that
actually ran. All offline — `common.llm.complete` is captured at the module
seam, never called.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from s7_delivery.factory import layers, live_intake
from s7_delivery.factory import scaffold as scaffold_mod
from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, Role
from s7_delivery.product import llm_settings, prompt_sets
from tests.test_factory_live_engine import _fake_analysis, fixture_repo


@pytest.fixture(autouse=True)
def cfg(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("S7_CONFIG_DIR", str(tmp_path / "config"))
    return tmp_path / "config"


def _capture(monkeypatch, module, response: dict) -> list[dict]:
    calls: list[dict] = []

    def fake(prompt, **kw):
        system, body = prompt.assemble()
        calls.append({"system": system, "prompt": body, "cache_key": kw.get("cache_key"),
                      "overrides": {k: kw[k] for k in ("provider", "model") if k in kw},
                      "llm_mode": os.environ.get("LLM_MODE")})
        if kw.get("usage_out") is not None:
            kw["usage_out"].update({"input_tokens": 3, "output_tokens": 2})
        return json.dumps(response)

    monkeypatch.setattr(module, "complete", fake)
    return calls


ANALYSIS = _fake_analysis().model_dump(mode="json")
ANALYSIS.pop("provenance")
ANALYSIS.pop("generated_at")


def _custom_set(name: str = "tighter") -> Path:
    prompt_sets.create_set(name, author="qa")
    root = prompt_sets.root_of(name)
    layers.write_body("delivery-assistant", "CUSTOM RULES: answer tersely.",
                      note="tighten", root=root)
    layers.write_body("intake-analysis", "You are the custom intake analyst.",
                      note="tighten", root=root)
    layers.write_body("intake-analysis-task",
                      "Transcript:\n{{transcript}}\nCUSTOM TASK — return the analysis JSON.",
                      note="tighten", root=root)
    return root


# --- the run's prompt set reaches the model call --------------------------------


def test_live_run_on_a_custom_set_sends_the_custom_prompt(tmp_path, monkeypatch):
    _custom_set()
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs", prompt_set="tighter")
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(fixture_repo(tmp_path)))
    calls = _capture(monkeypatch, live_intake, ANALYSIS)
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    assert len(calls) == 1
    assert calls[0]["system"] == (
        "CUSTOM RULES: answer tersely.\n\nYou are the custom intake analyst."
    )
    assert calls[0]["prompt"].endswith(
        "Transcript:\n(none yet)\nCUSTOM TASK — return the analysis JSON."
    )
    # The ledger names the version from the set that ran — v2 in "tighter",
    # while the default set's intake-analysis skill is still its own v1.
    ev = [e for e in eng.state()["activity"] if e["workflow"] == "intake-analysis"][-1]
    assert ev["skill"] == "intake-analysis@v2"
    assert layers.skill_ref("intake-analysis") == "intake-analysis@v1"
    # And the default set itself never moved.
    assert layers.unrecorded() == []


def test_default_run_sends_the_committed_prompt_even_with_custom_sets_around(
    tmp_path, monkeypatch,
):
    _custom_set()
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(fixture_repo(tmp_path)))
    calls = _capture(monkeypatch, live_intake, ANALYSIS)
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    assert calls[0]["system"] == (
        layers.rules("delivery-assistant") + "\n\n" + layers.skill("intake-analysis")
    )
    assert '"business_rules"' in calls[0]["prompt"]


def test_two_runs_on_different_sets_do_not_leak_into_each_other(tmp_path, monkeypatch):
    _custom_set()
    a = Engine.create(DemoMode.LIVE, root=tmp_path / "runs", prompt_set="tighter")
    b = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    src = fixture_repo(tmp_path)
    a.intake_connect_repo(Role.DELIVERY_LEAD, str(src))
    b.intake_connect_repo(Role.DELIVERY_LEAD, str(src))
    calls = _capture(monkeypatch, live_intake, ANALYSIS)
    a.intake_analyse(Role.PRODUCT_ANALYST)
    b.intake_analyse(Role.PRODUCT_ANALYST)
    a.intake_analyse(Role.PRODUCT_ANALYST)
    assert [c["system"].startswith("CUSTOM RULES") for c in calls] == [True, False, True]
    assert layers.active_root() == layers.LAYERS_ROOT  # nothing left behind


def test_scaffold_call_resolves_the_run_set_too(tmp_path, monkeypatch):
    root = _custom_set()
    layers.write_body("new-application-scaffold-task",
                      "Scaffold {{name}} ({{stack}}): {{description}}", note="t", root=root)
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs", prompt_set="tighter")
    setup = {"name": "maplesure-x", "description": "d", "stack": "Flask",
             "transcript": [], "pending": [], "rounds_used": 0}
    eng.store.write_json(setup, "intake", "new_app.json")
    calls = _capture(monkeypatch, scaffold_mod,
                     {"architecture_md": "# a", "readme_md": "# r"})
    eng.intake_generate_scaffold(Role.DELIVERY_LEAD)
    assert calls[0]["prompt"] == "Scaffold maplesure-x (Flask): d"
    assert calls[0]["system"].startswith("CUSTOM RULES")


# --- per-stage provider/model settings reach `complete` --------------------------


def test_per_stage_settings_reach_complete_kwargs(monkeypatch):
    llm_settings.save({
        "default": {"provider": "openai", "model": "house-model"},
        "stages": {"intake-analysis": {"model": "analysis-model"}},
    })
    calls = _capture(monkeypatch, live_intake, ANALYSIS)
    live_intake.run_analysis({"request_id": "R"}, {"maplesure-sponsor-portal": "pack"}, [])
    assert calls[0]["overrides"] == {"provider": "openai", "model": "analysis-model"}
    # A stage with nothing configured takes the default entry.
    calls = _capture(monkeypatch, live_intake, {"questions": ["Which plans?"]})
    live_intake.run_clarification({"request_id": "R"}, {"maplesure-sponsor-portal": "pack"}, [])
    assert calls[-1]["overrides"] == {"provider": "openai", "model": "house-model"}


def test_no_settings_means_no_overrides(monkeypatch):
    calls = _capture(monkeypatch, live_intake, ANALYSIS)
    live_intake.run_analysis({"request_id": "R"}, {"maplesure-sponsor-portal": "pack"}, [])
    assert calls[0]["overrides"] == {}


# --- the single LLM environment wrapper ----------------------------------------


def test_live_run_honours_the_configured_mode_override(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODE", "live")
    llm_settings.save({"llm_mode": "replay"})
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(fixture_repo(tmp_path)))
    calls = _capture(monkeypatch, live_intake, ANALYSIS)
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    assert calls[0]["llm_mode"] == "replay"
    assert os.environ["LLM_MODE"] == "live"  # scoped to the call, not global


def test_replay_run_pins_replay_whatever_the_settings_say(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODE", "live")
    llm_settings.save({"llm_mode": "live"})
    eng = Engine.create(DemoMode.REPLAY, root=tmp_path / "runs")
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(fixture_repo(tmp_path)))
    calls = _capture(monkeypatch, live_intake, ANALYSIS)
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    assert calls[0]["llm_mode"] == "replay"
    assert os.environ["LLM_MODE"] == "live"


# --- task templates ------------------------------------------------------------


def test_render_task_refuses_unsupplied_and_undeclared_variables(tmp_path):
    with pytest.raises(layers.LayerError, match=r"no value supplied for \['transcript'\]"):
        layers.render_task("intake-analysis-task")
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "t.md").write_text(
        "---\nid: t\nlayer: task\ntitle: T\nstage: s\nsummary: x\nvariables: a\n---\n"
        "{{a}} and {{b}}\n", encoding="utf-8",
    )
    with pytest.raises(layers.LayerError, match=r"\['b'\] are not declared"):
        layers.get("t", tmp_path)


def test_render_task_substitutes_values_verbatim_in_one_pass(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "t.md").write_text(
        "---\nid: t\nlayer: task\ntitle: T\nstage: s\nsummary: x\nvariables: a, b\n---\n"
        "A={{a}} B={{b}} {braces} {{a}}\n", encoding="utf-8",
    )
    out = layers.render_task("t", tmp_path, a="{{b}}", b=["x", 1])
    assert out == "A={{b}} B=['x', 1] {braces} {{b}}"


# --- the run carries its prompt set ----------------------------------------------


def test_run_state_carries_prompt_set_and_reset_preserves_it(tmp_path):
    prompt_sets.create_set("kept", author="qa")
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path / "runs", prompt_set="kept")
    state = eng.state()
    assert state["prompt_set"] == "kept" and state["run"]["prompt_set"] == "kept"
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.reset(Role.DELIVERY_LEAD)
    state = eng.state()
    assert state["prompt_set"] == "kept" and state["intake"]["analysis"] is None
    assert "prompt_set=kept" in state["activity"][-1]["details"]
    # The default is the default, and a run.json from before the field
    # existed reads as the default set.
    assert Engine.create(DemoMode.SIMULATION, root=tmp_path / "runs").run().prompt_set == "default"


def test_unknown_prompt_set_is_refused_at_create_and_at_the_api(tmp_path, monkeypatch):
    with pytest.raises(EngineError, match="Unknown prompt set 'nope'"):
        Engine.create(DemoMode.SIMULATION, root=tmp_path / "runs", prompt_set="nope")
    assert list((tmp_path / "runs").glob("*")) == [] if (tmp_path / "runs").exists() else True

    from apps.control.server import app
    from s7_delivery.factory import store as store_module

    monkeypatch.setattr(store_module, "RUNS_ROOT", tmp_path / "api-runs")
    client = TestClient(app)
    res = client.post("/api/runs", json={"mode": "simulation", "prompt_set": "nope"})
    assert res.status_code == 400 and "Unknown prompt set 'nope'" in res.json()["detail"]
    prompt_sets.create_set("real", author="qa")
    res = client.post("/api/runs", json={"mode": "simulation", "prompt_set": "real"})
    assert res.status_code == 200 and res.json()["prompt_set"] == "real"
    res = client.post("/api/runs", json={"mode": "simulation"})
    assert res.status_code == 200 and res.json()["prompt_set"] == "default"


def test_named_user_is_recorded_as_the_human_actor(tmp_path):
    """With a request-scoped user set, human actions record the person on
    activity and on the gate; without one the role label stands as before."""
    from s7_delivery.product import users

    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path / "runs")
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    with users.acting_as({"id": "u-1", "name": "Ana Lee", "role": "business_owner"}):
        eng.intake_pass_gate(Role.BUSINESS_OWNER)
    state = eng.state()
    gate_event = next(e for e in state["activity"] if e["workflow"] == "intake-gate")
    assert gate_event["actor"] == "Ana Lee" and gate_event["actor_type"] == "human"
    g0 = next(g for g in state["gates"] if g["gate_id"] == "G0")
    assert g0["decided_by"] == "Ana Lee"
    # Without a user, the role label stands exactly as before users existed.
    eng.planning_generate(Role.DELIVERY_LEAD)
    eng.planning_sign_off(Role.BUSINESS_OWNER, "Jordan Hale")
    human = [e for e in eng.state()["activity"]
             if e["actor_type"] == "human" and e["workflow"] != "intake-gate"]
    assert human and all(e["actor"] in {r.value for r in Role} | {"Jordan Hale"}
                         for e in human)


def test_deleted_set_fails_the_run_loudly_not_silently(tmp_path, monkeypatch):
    prompt_sets.create_set("gone", author="qa")
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs", prompt_set="gone")
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(fixture_repo(tmp_path)))
    prompt_sets.delete_set("gone")
    _capture(monkeypatch, live_intake, ANALYSIS)
    with pytest.raises(EngineError, match="'gone' no longer exists"):
        eng.intake_analyse(Role.PRODUCT_ANALYST)
