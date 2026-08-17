"""Bridge from the Control Centre's factory dicts to the real, LLM-backed
build/test/review lane in `s7_delivery.downstream`.

This is the seam between two engines that were built separately: the factory
(`engine.py` + `simulate.py`) drives the Control Centre's demo with fixed,
repeatable evidence; `downstream.py` is the genuine Developer/Tester/Reviewer
lane the old console used, real model calls over `common.llm`. This module
adapts one story/task at a time from the factory's dict shape into the
`s7_delivery.models` contract `downstream.run_lane` expects, so a single
story can opt into real evidence (`Provenance.LIVE_AI`) without touching the
default simulated path for everything else.

Routing: live/replay runs send every agentic story here (see
`engine.task_develop`); `S7_LIVE_STORY` remains a per-story opt-in for
simulation runs. Stream and coverage are derived from the plan via
`factory.coverage`, never hard-coded.
"""

from __future__ import annotations

from pathlib import Path

from s7_delivery import downstream
from s7_delivery.factory import coverage as coverage_mod
from s7_delivery.models import AcceptanceCriterion, Coverage, Provenance, Stream, Task, UserStory


def _stream_of(story: dict) -> Stream:
    value = coverage_mod.classify(story)["stream"]
    try:
        return Stream(value)
    except ValueError:
        # platform/unrouted have no Stream member; the lane only runs for
        # agentic stories, so this is a defensive fallback, not a claim.
        return Stream.FRONTEND


def _story_obj(story: dict) -> UserStory:
    return UserStory(
        id=story["story_id"],
        title=story["title"],
        narrative=story.get("purpose", story["title"]),
        acceptance=tuple(
            AcceptanceCriterion(id=ac["ac_id"], text=ac["text"])
            for ac in story["acceptance_criteria"]
        ),
        streams=(_stream_of(story),),
        estimate_points=story.get("estimate", 0),
        provenance=Provenance.LIVE_AI,
        epic_id=story.get("epic_id"),
    )


def _task_obj(task: dict, story: dict) -> Task:
    lane = coverage_mod.classify(story)["coverage"]
    try:
        cov = Coverage(lane)
    except ValueError:
        cov = Coverage.AGENTIC  # the lane only runs for agentic stories
    return Task(
        id=task["task_id"],
        story_id=task["story_id"],
        summary=task["summary"],
        stream=_stream_of(story),
        coverage=cov,
        estimate_days=1.0,
        provenance=Provenance.LIVE_AI,
        satisfies=tuple(ac["ac_id"] for ac in story["acceptance_criteria"]),
    )


def run(task: dict, story: dict, root: Path) -> downstream.LaneResult:
    """Run the real Developer/Tester/Reviewer lane for one factory task.

    `root` is a directory under the run's own artifact tree (see
    `RunStore.path`); `downstream.run_lane` writes the generated app,
    `events.jsonl` and `review.json` under it exactly as it does for the
    console's downstream lane.
    """
    return downstream.run_lane(_story_obj(story), _task_obj(task, story), root)
