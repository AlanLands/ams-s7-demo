"""Build → test → review for one AGENTIC task. Happy path, hard-capped.

Three role-labelled model calls — Developer, Tester, Reviewer — over plain
orchestration. This is deliberately *not* an agent framework (the 2026-08-04
review rejected going agentic on this timeline); the roles are visible names
for sequential stages, which is all the demo claims they are.

Every artifact lands under the given root:

    root/app/           the generated application + its generated tests
    root/events.jsonl   one JSON line per agent action — the console's feed
    root/review.json    the Reviewer's verdict against the acceptance criteria

The pytest run over the generated files is real: red tests flip the result to
not-ok and are reported, never hidden (§ Determinism — "None is an admission",
applied to a whole lane).

Events line schema (the contract the console animates):
    {"ts": float, "agent": "developer"|"tester"|"reviewer"|"system",
     "action": str, "artifact": str|null, "status": "start"|"done"|"fail"}
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from common.llm import complete
from s7_delivery.factory import layers
from s7_delivery.generate import parse_json_block
from s7_delivery.models import Task, UserStory
from s7_delivery.product import llm_settings

# The Rules layer of the lane (`factory/layers.py`): one system prompt shared
# by all three agents. The Skills layer is the opening sentence of each
# agent's task prompt — this lane pre-dates the PromptLayers convention and
# its prompt bytes are pinned by committed recordings, so the skill rides in
# the prompt exactly where it always was (the `{{skill}}` placeholder of each
# task template). Every file is resolved at call time from the active prompt
# set — nothing is pinned at import.
_RULES_ID = "downstream-lane"


def _system() -> str:
    return layers.rules(_RULES_ID)


# pytest timing varies run to run; anything embedded in a prompt must be
# deterministic or the prompt hash changes and replay misses the recording.
_TIMING = re.compile(r"\d+\.\d+s")

MAX_REVISION_ROUNDS = 2
"""Hard cap on review→fix rounds. At the cap, remaining failures are
reported in the events and the result — never presented as success."""


def _sanitize(test_output: str) -> str:
    return _TIMING.sub("N.NNs", test_output)


@dataclass
class LaneResult:
    ok: bool
    app_dir: Path
    events_path: Path
    test_output: str
    review: dict
    revised: bool = False
    """True when the reviewer rejected the first build and the Developer's
    bounded revision pass produced the final artifact."""


class _Events:
    def __init__(self, path: Path):
        self.path = path
        path.write_text("")

    def emit(
        self, agent: str, action: str, artifact: str | None = None, status: str = "done"
    ) -> None:
        line = {"ts": time.time(), "agent": agent, "action": action,
                "artifact": artifact, "status": status}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")


def _write_files(data: dict, dest: Path) -> list[str]:
    """Write the files an agent returned. Paths are flattened to basenames:
    the generated app is deliberately flat, and a model reply must not be able
    to write outside its directory."""
    names: list[str] = []
    for f in data["files"]:
        rel = Path(str(f["path"])).name
        (dest / rel).write_text(str(f["content"]), encoding="utf-8")
        names.append(rel)
    return names


def _criteria_block(story: UserStory, task: Task) -> str:
    wanted = set(task.satisfies) or {a.id for a in story.acceptance}
    return "\n".join(f"- {a.id}: {a.text}" for a in story.acceptance if a.id in wanted)


def _read_if_exists(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _findings_block(review: dict) -> str:
    return "\n".join(
        f"- {c.get('id')}: {'met' if c.get('met') else 'NOT MET'} — {c.get('note', '')}"
        for c in review.get("criteria", [])
    )


def _developer_prompt(story: UserStory, task: Task) -> str:
    return layers.render_task(
        "developer-task",
        skill=layers.skill("developer"),
        task_id=task.id, stream=task.stream.value, task_summary=task.summary,
        story_id=story.id, story_title=story.title, narrative=story.narrative,
        acceptance_criteria=_criteria_block(story, task),
    )


def _tester_prompt(story: UserStory, task: Task, files: list[str], app_dir: Path) -> str:
    generated = "\n\n".join(
        f"--- {name} ---\n{(app_dir / name).read_text(encoding='utf-8')}" for name in files
    )
    return layers.render_task(
        "tester-task",
        skill=layers.skill("tester"),
        task_id=task.id, task_summary=task.summary, generated_files=generated,
        acceptance_criteria=_criteria_block(story, task),
    )


def _reviewer_prompt(story: UserStory, task: Task, app_dir: Path, test_output: str) -> str:
    listing = "\n".join(sorted(p.name for p in app_dir.iterdir()))
    html = _read_if_exists(app_dir / "index.html")
    return layers.render_task(
        "reviewer-task",
        skill=layers.skill("reviewer"),
        task_id=task.id, acceptance_criteria=_criteria_block(story, task),
        file_listing=listing, html=html, test_output=test_output,
    )


def _revision_prompt(
    story: UserStory, task: Task, app_dir: Path, review: dict, test_output: str
) -> str:
    html = (app_dir / "index.html").read_text(encoding="utf-8")
    tests = _read_if_exists(app_dir / "test_app.py")
    return layers.render_task(
        "developer-revision-task",
        skill=layers.skill("developer"),
        task_id=task.id, findings=_findings_block(review),
        reviewer_notes=review.get("notes"),
        acceptance_criteria=_criteria_block(story, task),
        html=html, tests=tests, test_output=test_output,
    )


def _test_revision_prompt(
    story: UserStory, task: Task, app_dir: Path, review: dict, test_output: str
) -> str:
    html = (app_dir / "index.html").read_text(encoding="utf-8")
    tests = (app_dir / "test_app.py").read_text(encoding="utf-8")
    return layers.render_task(
        "tester-revision-task",
        skill=layers.skill("tester"),
        findings=_findings_block(review), html=html, tests=tests,
        test_output=test_output,
    )


def _run_pytest(app_dir: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", str(app_dir)],
        capture_output=True, text=True, timeout=120,
    )
    return proc.returncode == 0, proc.stdout


def run_lane(story: UserStory, task: Task, root: Path) -> LaneResult:
    app_dir = root / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    ev = _Events(root / "events.jsonl")
    # Provider/model per lane role from the per-stage settings; unset falls
    # through to the environment. The reviewer key also honours REVIEW_LLM_*
    # so an independent *different* model can review when configured — the
    # events say which.
    developer_kwargs = llm_settings.for_stage("development-lane.developer")
    tester_kwargs = llm_settings.for_stage("development-lane.tester")
    reviewer_kwargs = llm_settings.for_stage("development-lane.reviewer")

    ev.emit("developer", f"picked up {task.id}: {task.summary}", status="start")
    dev = parse_json_block(
        complete(_developer_prompt(story, task), system=_system(), json_mode=True,
                 cache_key="s7:downstream:developer", **developer_kwargs)
    )
    files = _write_files(dev, app_dir)
    ev.emit("developer", "wrote application code", artifact=", ".join(files))

    ev.emit("tester", "writing tests against acceptance criteria", status="start")
    tst = parse_json_block(
        complete(_tester_prompt(story, task, files, app_dir), system=_system(), json_mode=True,
                 cache_key="s7:downstream:tester", **tester_kwargs)
    )
    test_files = _write_files(tst, app_dir)
    ev.emit("tester", "wrote tests", artifact=", ".join(test_files))

    ev.emit("tester", "running pytest", status="start")
    green, test_out = _run_pytest(app_dir)
    ev.emit(
        "tester",
        "tests green" if green else "tests FAILED",
        artifact=test_files[0] if test_files else None,
        status="done" if green else "fail",
    )

    ev.emit(
        "reviewer",
        "independent review against acceptance criteria"
        + (f" (second model: {reviewer_kwargs['model']})"
           if "model" in reviewer_kwargs
           else " (same model, isolated reviewer prompt)"),
        status="start",
    )
    review = parse_json_block(
        complete(_reviewer_prompt(story, task, app_dir, _sanitize(test_out)), system=_system(),
                 json_mode=True, cache_key="s7:downstream:reviewer", **reviewer_kwargs)
    )
    verdict_ok = review.get("verdict") == "pass"
    ev.emit(
        "reviewer",
        f"verdict: {review.get('verdict')}",
        artifact="review.json",
        status="done" if verdict_ok else "fail",
    )

    # Bounded revision loop, per the reference architecture's hard-capped TDD
    # loop: the reviewer's findings triage back to the role that must fix
    # them, at most MAX_REVISION_ROUNDS times. If the result still fails at
    # the cap, that is reported, not hidden.
    revised = False
    rounds = 0
    while not (green and verdict_ok) and rounds < MAX_REVISION_ROUNDS:
        rounds += 1
        revised = True
        if rounds == 1:
            (root / "review_first.json").write_text(json.dumps(review, indent=2), encoding="utf-8")
        ev.emit("developer", f"revision {rounds}: addressing reviewer findings", status="start")
        fix = parse_json_block(
            complete(_revision_prompt(story, task, app_dir, review, _sanitize(test_out)),
                     system=_system(), json_mode=True,
                     cache_key=f"s7:downstream:developer:fix{rounds}", **developer_kwargs)
        )
        files = _write_files(fix, app_dir)
        ev.emit("developer", "applied fixes from review", artifact=", ".join(files))

        ev.emit("tester", "re-running pytest against revised build", status="start")
        green, test_out = _run_pytest(app_dir)
        ev.emit("tester", "tests green" if green else "tests FAILED",
                status="done" if green else "fail")

        # Triage to the role that must fix it: if the tests are still red
        # after the Developer's pass, the defect may be in the tests — the
        # Tester gets one bounded fix of its own, then evidence decides.
        if not green:
            ev.emit("tester", "revision: fixing defective test per review diagnosis",
                    status="start")
            fixt = parse_json_block(
                complete(_test_revision_prompt(story, task, app_dir, review, _sanitize(test_out)),
                         system=_system(), json_mode=True,
                         cache_key=f"s7:downstream:tester:fix{rounds}", **tester_kwargs)
            )
            _write_files(fixt, app_dir)
            green, test_out = _run_pytest(app_dir)
            ev.emit("tester", "tests green" if green else "tests still FAILED",
                    status="done" if green else "fail")

        ev.emit("reviewer", "re-review of revised build", status="start")
        review = parse_json_block(
            complete(_reviewer_prompt(story, task, app_dir, _sanitize(test_out)),
                     system=_system(), json_mode=True,
                     cache_key=f"s7:downstream:reviewer:recheck{rounds}", **reviewer_kwargs)
        )
        verdict_ok = review.get("verdict") == "pass"
        ev.emit("reviewer", f"verdict: {review.get('verdict')}", artifact="review.json",
                status="done" if verdict_ok else "fail")

    (root / "review.json").write_text(json.dumps(review, indent=2), encoding="utf-8")
    ok = green and verdict_ok
    ev.emit(
        "system",
        "lane complete — ready for release gate" if ok else "lane finished with failures",
        status="done" if ok else "fail",
    )
    return LaneResult(
        ok=ok,
        app_dir=app_dir,
        events_path=ev.path,
        test_output=test_out[-2000:],
        review=review,
        revised=revised,
    )
