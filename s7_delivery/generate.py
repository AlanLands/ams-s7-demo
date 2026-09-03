"""Real model-generated upstream artifacts — the same shapes `staged.py` fakes.

Selected by `S7_ARTIFACTS=ai` (see `pipeline.build_state`). Every call goes
through `common.llm.complete`, so `LLM_MODE=record` records against the live
provider and `LLM_MODE=replay` replays the committed recordings offline.

Provenance is `REPLAYED_AI` in replay mode and `LIVE_AI` otherwise — never
`STAGED`, because this module only returns output a model actually produced.
A failure here (replay miss, malformed JSON, invalid diagram) raises; the
caller falls back to `staged`, which keeps its badge. No third option.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime

from common.llm import complete
from s7_delivery.factory import layers
from s7_delivery.models import (
    AcceptanceCriterion,
    AssessedTask,
    Assessment,
    Coverage,
    DesignArtifact,
    Epic,
    Provenance,
    Stream,
    Task,
    UserStory,
)
from s7_delivery.product import llm_settings

# The Rules layer of the staged pipeline — a file, pinned by recordings,
# resolved at call time from the active prompt set like the task templates.
_RULES_ID = "staged-pipeline"
_STAGE = "staged-pipeline"

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def _system() -> str:
    return layers.rules(_RULES_ID)


def _provenance() -> Provenance:
    mode = os.environ.get("LLM_MODE", "replay").lower()
    return Provenance.REPLAYED_AI if mode == "replay" else Provenance.LIVE_AI


def parse_json_block(text: str):
    """Parse a JSON reply, tolerating a model that wrapped it in a fence."""
    text = text.strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    return json.loads(text)


# --- assessment ------------------------------------------------------------


def assessment(epic: Epic) -> Assessment:
    streams = ", ".join(s.value for s in Stream)
    prompt = layers.render_task(
        "staged-assessment-task", epic_body=epic.body, streams=streams
    )
    data = parse_json_block(
        complete(prompt, system=_system(), json_mode=True, cache_key="s7:assess",
                 **llm_settings.for_stage(_STAGE))
    )
    tasks = tuple(
        AssessedTask(
            id=str(t["id"]),
            summary=str(t["summary"]),
            stream=Stream(t["stream"]),
            coverage=Coverage(t["coverage"]),
            estimate_days=float(t["estimate_days"]),
            rationale=str(t.get("rationale", "")),
            depends_on=tuple(str(d) for d in t.get("depends_on", [])),
            blocked_by_external=bool(t.get("blocked_by_external", False)),
        )
        for t in data["tasks"]
    )
    return Assessment(
        epic_id=epic.id,
        tasks=tasks,
        integration_note=str(data.get("integration_note", "")),
        provenance=_provenance(),
        generated_at=datetime.now(UTC),
    )


# --- design ----------------------------------------------------------------


def design(epic: Epic, assessment: Assessment) -> tuple[DesignArtifact, ...]:
    task_lines = "\n".join(
        f"- {t.id} [{t.stream.value}/{t.coverage.value}] {t.summary}" for t in assessment.tasks
    )
    prompt = layers.render_task(
        "staged-design-task", epic_body=epic.body, task_lines=task_lines
    )
    data = parse_json_block(
        complete(prompt, system=_system(), json_mode=True, cache_key="s7:design",
                 **llm_settings.for_stage(_STAGE))
    )
    dfd = data["dfd"]
    er = data["er"]
    if not str(dfd["mermaid"]).lstrip().startswith("flowchart"):
        raise ValueError("DFD mermaid source does not start with 'flowchart'")
    if not str(er["mermaid"]).lstrip().startswith("erDiagram"):
        raise ValueError("ER mermaid source does not start with 'erDiagram'")
    prov = _provenance()
    return (
        DesignArtifact(
            id="DFD-1",
            kind="dfd",
            title=str(dfd["title"]),
            source=str(dfd["mermaid"]),
            notes=str(dfd.get("notes", "")),
            provenance=prov,
        ),
        DesignArtifact(
            id="ER-1",
            kind="er",
            title=str(er["title"]),
            source=str(er["mermaid"]),
            notes=str(er.get("notes", "")),
            provenance=prov,
        ),
    )


# --- stories ---------------------------------------------------------------


def stories(epic: Epic, assessment: Assessment) -> tuple[UserStory, ...]:
    streams = ", ".join(s.value for s in Stream)
    task_lines = "\n".join(
        f"- {t.id} [{t.stream.value}/{t.coverage.value}] {t.summary}" for t in assessment.tasks
    )
    prompt = layers.render_task(
        "staged-stories-task", epic_body=epic.body, task_lines=task_lines,
        streams=streams,
    )
    data = parse_json_block(
        complete(prompt, system=_system(), json_mode=True, cache_key="s7:stories",
                 **llm_settings.for_stage(_STAGE))
    )
    prov = _provenance()
    built: list[UserStory] = []
    for s in data["stories"]:
        story_id = str(s["id"])
        tasks = tuple(
            Task(
                id=str(t["id"]),
                story_id=story_id,
                summary=str(t["summary"]),
                stream=Stream(t["stream"]),
                coverage=Coverage(t["coverage"]),
                estimate_days=float(t["estimate_days"]),
                provenance=prov,
                satisfies=tuple(str(x) for x in t.get("satisfies", [])),
                depends_on=tuple(str(x) for x in t.get("depends_on", [])),
                owning_team=t.get("owning_team"),
            )
            for t in s.get("tasks", [])
        )
        built.append(
            UserStory(
                id=story_id,
                title=str(s["title"]),
                narrative=str(s["narrative"]),
                acceptance=tuple(
                    AcceptanceCriterion(id=str(a["id"]), text=str(a["text"]))
                    for a in s.get("acceptance", [])
                ),
                streams=tuple(Stream(x) for x in s.get("streams", [])),
                estimate_points=int(s.get("estimate_points", 0)),
                provenance=prov,
                epic_id=epic.id,
                assumptions=tuple(str(x) for x in s.get("assumptions", [])),
                tasks=tasks,
            )
        )
    return tuple(built)
