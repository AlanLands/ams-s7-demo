"""Leads propose, the system refines — the step behind editable
architecture and test plans.

A lead's proposal is always recorded verbatim as HUMAN input. What folds it
into the artifact depends on the run mode:

- LIVE runs call the model for real through the same `live_intake._call`
  path as every other live beat (LIVE_AI, or REPLAYED_AI when served from a
  committed recording).
- SIMULATION runs never fake it: a deterministic normalizer structures the
  proposal, badged RULE_BASED and labelled as rules — presenting a heuristic
  as AI output is exactly what CLAUDE.md § Staged output forbids.

Either way the refined output is a *transformation of the proposal*, and the
artifact it lands in still needs its human checkpoint again (architecture
acceptance, QA test-plan approval) — editing never skips a gate.
"""

from __future__ import annotations

import re

from common.llm import LLMError
from s7_delivery.factory import layers
from s7_delivery.factory.models import DemoMode, Provenance

# Skill ids; the text is resolved at call time from the active prompt set.
_ARCH_SKILL = "architecture-refine"
_QA_SKILL = "test-plan-refine"


def _sentences(text: str) -> list[str]:
    """Split a proposal into normalized sentence/line items, rule-based."""
    parts: list[str] = []
    for line in text.splitlines():
        line = line.strip().lstrip("-*•").strip()
        if not line:
            continue
        for piece in re.split(r"(?<=[.!?])\s+", line):
            piece = piece.strip().rstrip(".")
            if piece:
                parts.append(piece)
    return parts


def refine_architecture_proposal(
    proposal: str, architecture_md: str, mode: DemoMode
) -> tuple[str, Provenance]:
    """(refined markdown section, provenance of the refinement)."""
    if mode in (DemoMode.LIVE, DemoMode.REPLAY):
        from s7_delivery.factory import live_intake

        task = layers.render_task(
            "architecture-refine-task",
            architecture_md=architecture_md, proposal=proposal,
        )
        data, _usage = live_intake._call(
            role=_ARCH_SKILL, stage="architecture-refine",
            ref="", task=task, beat="arch_refine",
            key_material=proposal + architecture_md[:2000],
        )
        refined = str(data.get("refined_markdown", "")).strip()
        if not refined:
            raise LLMError("architecture refinement returned no refined_markdown")
        return refined, live_intake.provenance_now()

    quoted = proposal.strip().replace("\n", "\n> ")
    lines = [
        "### Proposed change (human, verbatim)",
        "",
        f"> {quoted}",
        "",
        "### Normalized change list (rule-based)",
        "",
        *[f"- {s}" for s in _sentences(proposal)],
        "",
        "_Structured by deterministic rules — simulation mode runs no AI"
        " call._",
    ]
    return "\n".join(lines), Provenance.RULE_BASED


def refine_test_amendment(
    proposal: str, story: dict, mode: DemoMode
) -> tuple[list[dict], Provenance]:
    """(cases, provenance). Each case: {"case_id", "description"} — the
    governed test *names* are derived downstream by test_skeletons, so the
    refinement can never move a name CI evidence joins on."""
    if mode in (DemoMode.LIVE, DemoMode.REPLAY):
        from s7_delivery.factory import live_intake

        acs = "\n".join(
            f"- {ac['ac_id']}: {ac['text']}"
            for ac in story.get("acceptance_criteria", [])
        )
        task = layers.render_task(
            "test-plan-refine-task",
            story_id=story["story_id"], title=story.get("title", ""),
            acceptance_criteria=acs, proposal=proposal,
        )
        data, _usage = live_intake._call(
            role=_QA_SKILL, stage="test-plan-refine",
            ref="", task=task, beat="testplan_refine",
            key_material=story["story_id"] + proposal,
        )
        raw = data.get("cases")
        if not isinstance(raw, list) or not raw:
            raise LLMError("test-plan refinement returned no cases")
        cases = []
        for i, c in enumerate(raw):
            desc = str(c.get("description", "")).strip() if isinstance(c, dict) else ""
            if not desc:
                raise LLMError(f"test-plan refinement case {i + 1} has no description")
            cases.append({"case_id": f"QA-{i + 1}", "description": desc})
        return cases, live_intake.provenance_now()

    cases = [
        {"case_id": f"QA-{i + 1}", "description": s}
        for i, s in enumerate(_sentences(proposal))
    ]
    if not cases:
        raise LLMError("The amendment text contains no test cases")
    return cases, Provenance.RULE_BASED
