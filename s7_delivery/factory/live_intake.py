"""Live LLM calls for the Control Centre's upstream half (spec §3-§6).

Every function here: builds a `PromptLayers` whose `ref` layer is the
connected repos' context packs, calls `common.llm.complete` in JSON mode,
and validates the response strictly into the factory's own Pydantic shapes.
Reject, don't repair: a malformed response raises `LLMError`, and the engine
surfaces it — a live run never silently serves seeded content.
"""
from __future__ import annotations

import hashlib
import json
import os

from common.llm import LLMError, complete, parse_json_response
from common.prompt import PromptLayers
from s7_delivery.factory.models import IntakeAnalysis, Provenance

MAX_CLARIFICATION_ROUNDS = 2

RULES = (
    "You are an AI delivery assistant for MapleSure Insurance, a fictional "
    "insurer in a tabletop exercise. All data is synthetic. Answer with "
    "structured JSON only, and never invent facts the input does not support."
)

ANALYSIS_ROLE = (
    "Your role is intake analysis: read a business change request against the "
    "connected application repositories and extract what a delivery lead "
    "needs — impact, affected applications, stakeholders, dependencies, "
    "risks, open questions, assumptions and business rules. Ground every "
    "claim in the requirement or the repository context; where the "
    "repositories show a capability is absent, say so as a dependency or "
    "risk, not a guess."
)

CLARIFY_ROLE = (
    "Your role is a product analyst preparing a change request for delivery: "
    "ask only the clarifying questions whose answers would materially change "
    "the analysis or the plan. Most requests need one short round, not an "
    "interrogation."
)


def provenance_now() -> Provenance:
    mode = os.environ.get("LLM_MODE", "replay").lower()
    return Provenance.LIVE_AI if mode in {"live", "record"} else Provenance.REPLAYED_AI


def _ref(requirement: dict, packs: dict[str, str]) -> str:
    packs_text = "\n\n---\n\n".join(packs[name] for name in sorted(packs))
    return (
        f"The connected application repositories:\n\n{packs_text}\n\n---\n\n"
        f"The change request, verbatim:\n\n{json.dumps(requirement, indent=2)}"
    )


def _transcript_text(transcript: list[dict]) -> str:
    if not transcript:
        return "(none yet)"
    return "\n".join(f"{t['role']}: {t['text']}" for t in transcript)


def _cache_digest(*parts: str) -> str:
    return hashlib.sha256("\x1e".join(parts).encode("utf-8")).hexdigest()[:16]


def _call(*, role: str, ref: str, task: str, beat: str, key_material: str) -> tuple[dict, dict]:
    usage: dict = {}
    response = complete(
        PromptLayers(rules=RULES, role=role, ref=ref, task=task),
        json_mode=True,
        cache_key=f"s7_factory_{beat}:{_cache_digest(key_material)}",
        usage_out=usage,
    )
    return parse_json_response(response), usage


_ANALYSIS_SHAPE = """{
  "problem_understood": true,
  "business_impact": "<one paragraph>",
  "affected_applications":
    ["<connected repository name, or an external system suffixed ' (externally owned)'>"],
  "stakeholders": ["<who>"],
  "dependencies": ["<what this depends on, grounded in the repositories>"],
  "risks": ["<risk>"],
  "clarification_questions": ["<open question for the SME>"],
  "assumptions": ["<assumption carried>"],
  "business_rules": [{"rule_id": "BR-<n>", "text": "<rule in the requirement's words>"}],
  "risk_register": [{"text": "<risk>", "severity": "high|medium|low"}],
  "confidence": <0-100 self-assessment>
}"""


def run_analysis(
    requirement: dict, packs: dict[str, str], transcript: list[dict]
) -> tuple[IntakeAnalysis, dict]:
    if not packs:
        raise LLMError(
            "Live analysis needs at least one connected repository — connect "
            "the target repos first (grounding is the point)."
        )
    task = f"""Clarification conversation so far:
{_transcript_text(transcript)}

Analyse the change request against the connected repositories. Return JSON
exactly matching:
{_ANALYSIS_SHAPE}"""
    data, usage = _call(
        role=ANALYSIS_ROLE,
        ref=_ref(requirement, packs),
        task=task,
        beat="analysis",
        # Pack content is in the key: a repo update honestly misses the cache.
        key_material=json.dumps(requirement, sort_keys=True)
        + "".join(packs[k] for k in sorted(packs))
        + json.dumps(transcript, sort_keys=True),
    )
    return _validate_analysis(data, set(packs)), usage


def _validate_analysis(data: dict, repo_names: set[str]) -> IntakeAnalysis:
    apps = data.get("affected_applications")
    if not isinstance(apps, list) or not apps:
        raise LLMError("analysis has no affected_applications")
    grounded = [a for a in apps if a in repo_names]
    if not grounded:
        raise LLMError(
            "affected_applications names no connected repository — "
            f"got {apps}, connected {sorted(repo_names)}"
        )
    for a in apps:
        if a not in repo_names and not a.endswith("(externally owned)"):
            raise LLMError(
                f"affected_applications entry {a!r} is neither a connected "
                "repository nor marked '(externally owned)'"
            )
    for rule in data.get("business_rules", []):
        if not (isinstance(rule, dict) and rule.get("rule_id") and rule.get("text")):
            raise LLMError(f"business_rules entry missing rule_id/text: {rule!r}")
    for row in data.get("risk_register", []):
        if not (isinstance(row, dict) and row.get("text")
                and row.get("severity") in {"high", "medium", "low"}):
            raise LLMError(f"risk_register entry malformed: {row!r}")
    _excluded = {"provenance", "generated_at"}  # ours to set, not the model's
    try:
        return IntakeAnalysis(
            **{k: v for k, v in data.items()
               if k in IntakeAnalysis.model_fields and k not in _excluded},
            provenance=provenance_now(),
        )
    except Exception as exc:  # pydantic ValidationError → one LLMError vocabulary
        raise LLMError(f"analysis failed validation: {exc}") from exc


ROUTE_ROLE = (
    "Your role is requirement routing: decide whether a business change "
    "request's capabilities plausibly land inside the connected application "
    "repositories, or whether it needs an application that does not exist "
    "yet. Ground the verdict in what the repositories' architecture.md files "
    "say they do and do not do."
)

_ROUTE_SHAPE = """{
  "verdict": "routable" | "new_application_needed",
  "reasoning": "<one paragraph>",
  "candidate_repos": ["<connected repository name, only if routable>"],
  "confidence": <0-100 self-assessment>
}"""


def route_requirement(
    requirement: dict, packs: dict[str, str]
) -> tuple["RoutingVerdict", dict]:
    from s7_delivery.factory.models import RoutingVerdict

    if not packs:
        # Deterministic: zero connected repos always means a new application
        # is needed. No model call — cheaper and more honest than asking a
        # model to notice an empty list. HUMAN provenance because this is
        # engine logic, not a model assertion (same use as RepoRecord's
        # "extraction, not generation").
        return RoutingVerdict(
            verdict="new_application_needed",
            reasoning="No repositories are connected yet.",
            candidate_repos=[],
            confidence=100,
            provenance=Provenance.HUMAN,
        ), {}
    task = f"""Decide whether this change request fits inside the connected
repositories, or needs an application that does not exist yet. Return JSON
exactly matching:
{_ROUTE_SHAPE}"""
    data, usage = _call(
        role=ROUTE_ROLE,
        ref=_ref(requirement, packs),
        task=task,
        beat="route",
        key_material=json.dumps(requirement, sort_keys=True)
        + "".join(packs[k] for k in sorted(packs)),
    )
    return _validate_route(data, set(packs)), usage


def _validate_route(data: dict, repo_names: set[str]) -> "RoutingVerdict":
    from s7_delivery.factory.models import RoutingVerdict

    verdict = data.get("verdict")
    if verdict not in {"routable", "new_application_needed"}:
        raise LLMError(
            f"route verdict must be 'routable' or 'new_application_needed', "
            f"got {verdict!r}"
        )
    reasoning = data.get("reasoning")
    if not isinstance(reasoning, str) or not reasoning.strip():
        raise LLMError("route reasoning must be a non-empty string")
    candidates = data.get("candidate_repos") or []
    if not isinstance(candidates, list):
        raise LLMError("candidate_repos must be a list")
    unknown = [c for c in candidates if c not in repo_names]
    if unknown:
        raise LLMError(f"candidate_repos names non-connected repositories: {unknown}")
    if verdict == "routable" and not candidates:
        raise LLMError("verdict is routable but candidate_repos is empty")
    return RoutingVerdict(
        verdict=verdict,
        reasoning=reasoning,
        candidate_repos=candidates,
        confidence=data.get("confidence"),
        provenance=provenance_now(),
    )


def run_clarification(
    requirement: dict, packs: dict[str, str], transcript: list[dict]
) -> tuple[list[str], dict]:
    if not packs:
        raise LLMError("Live clarification needs a connected repository.")
    rounds_used = sum(1 for t in transcript if t["role"] == "assistant")
    if rounds_used >= MAX_CLARIFICATION_ROUNDS:
        raise LLMError(
            f"Clarification cap reached ({MAX_CLARIFICATION_ROUNDS} rounds) — "
            "answer what is open or run the analysis with assumptions."
        )
    task = f"""Clarification conversation so far:
{_transcript_text(transcript)}

Ask the 1 to 4 clarifying questions (one topic each) whose answers would most
change the delivery plan. Return JSON exactly matching:
{{"questions": ["<question>"]}}"""
    data, usage = _call(
        role=CLARIFY_ROLE,
        ref=_ref(requirement, packs),
        task=task,
        beat="clarify",
        key_material=json.dumps(requirement, sort_keys=True)
        + json.dumps(transcript, sort_keys=True),
    )
    questions = [str(q).strip() for q in data.get("questions", []) if str(q).strip()]
    if not 1 <= len(questions) <= 4:
        raise LLMError(f"expected 1-4 clarifying questions, got {len(questions)}")
    return questions, usage


PLAN_ROLE = (
    "Your role is delivery planning: break the epic into small, independently "
    "deliverable user stories with owners, grounded in the connected "
    "repositories — a story lands in the repository whose code it changes. "
    "Where the repositories show a capability does not exist, the story that "
    "introduces it comes first in the dependency order."
)

_POINT_SCALE = (1, 2, 3, 5, 8, 13)

_PLAN_SHAPE = """{
  "stories": [
    {
      "story_id": "US-<n>, numbered from 1 in delivery order",
      "title": "<short imperative title>",
      "purpose": "<why this story exists, one or two sentences>",
      "accountable_team": "<one team from the roster>",
      "target_application": "<the connected repository this changes>",
      "target_repository": "<same connected repository name>",
      "target_component": "<the part of that repository this lands in>",
      "acceptance_criteria": [
        {"ac_id": "US-<n>-AC<m>",
         "text": "Given <context>, when <action>, then <observable result>"}
      ],
      "dependencies": ["<story ids this cannot start before>"],
      "impacts": ["<existing file or behaviour this touches>"],
      "feature_flag": {"name": "<flag to ship dark behind>"},
      "rollback_plan": {"method": "<one line: how this is backed out>"},
      "task_type": "feature | config | migration | integration | test",
      "estimate": <integer: 1/2/3/5/8/13>,
      "sprint": <1, 2 or 3>,
      "traces_to": ["<business rule ids from the analysis this story delivers>"]
    }
  ],
  "confidence": <0-100 self-assessment of the draft>,
  "rationale": "<one paragraph: the decomposition logic>"
}"""


def run_plan(
    epic: dict,
    analysis: dict,
    packs: dict[str, str],
    transcript: list[dict],
    teams: list[str],
) -> tuple[list, dict, dict, dict]:
    from s7_delivery.factory.models import Status, Story

    # Volatile timestamps must not enter prompt or key material, or the beat
    # can never replay across runs (each run stamps its own epic afresh).
    epic = {k: v for k, v in epic.items() if k not in {"created_at", "generated_at"}}

    if not packs:
        raise LLMError("Live planning needs a connected repository.")
    rule_ids = [r["rule_id"] for r in analysis.get("business_rules", [])]
    roster = "\n".join(f"- {t}" for t in teams)
    task = f"""The approved epic:
{json.dumps(epic, indent=2)}

The intake analysis' business rules (every rule id must be claimed by at
least one story's "traces_to"):
{json.dumps(analysis.get("business_rules", []), indent=2)}

Clarification conversation so far:
{_transcript_text(transcript)}

The team roster. Assign each story's accountable_team from this list ONLY:
{roster}

Break the epic into 4 to 8 stories across sprints 1 to 3. Every story needs
2 to 4 acceptance criteria, each independently testable. Every story's
target_repository must be one of the connected repositories. Return JSON
exactly matching:
{_PLAN_SHAPE}"""
    data, usage = _call(
        role=PLAN_ROLE,
        ref=_ref(epic, packs),
        task=task,
        beat="plan",
        key_material=json.dumps(epic, sort_keys=True)
        + json.dumps(rule_ids)
        + json.dumps(transcript, sort_keys=True),
    )

    raw_stories = data.get("stories")
    if not isinstance(raw_stories, list) or not 1 <= len(raw_stories) <= 10:
        raise LLMError("plan must contain 1-10 stories")

    provenance = provenance_now()
    stories: list[Story] = []
    seen: set[str] = set()
    for raw in raw_stories:
        sid = str(raw.get("story_id", ""))
        if not sid or sid in seen:
            raise LLMError(f"missing or duplicate story_id {sid!r}")
        seen.add(sid)
        if raw.get("accountable_team") not in teams:
            raise LLMError(
                f"story {sid}: accountable_team {raw.get('accountable_team')!r} "
                "is not on the team roster"
            )
        if raw.get("target_repository") not in packs:
            raise LLMError(
                f"story {sid}: target_repository {raw.get('target_repository')!r} "
                "is not a connected repository"
            )
        if raw.get("estimate") not in _POINT_SCALE:
            raise LLMError(f"story {sid}: estimate must be one of {_POINT_SCALE}")
        if len(raw.get("acceptance_criteria") or []) < 2:
            raise LLMError(
                f"story {sid}: needs at least 2 acceptance criteria"
            )
        _excluded = {"provenance", "status", "version", "epic_id"}  # ours to set
        try:
            story = Story(
                **{k: v for k, v in raw.items()
                   if k in Story.model_fields and k not in _excluded},
                epic_id=str(epic.get("epic_id", "")),
                provenance=provenance,
            )
        except Exception as exc:
            raise LLMError(f"story {sid} failed validation: {exc}") from exc
        if story.sprint != 1:
            story = story.model_copy(update={"status": Status.PLANNED})
        stories.append(story)

    ids = {s.story_id for s in stories}
    for s in stories:
        dangling = [d for d in s.dependencies if d not in ids]
        if dangling:
            raise LLMError(f"story {s.story_id} depends on unknown stories {dangling}")

    claimed = {rid for s in stories for rid in s.traces_to}
    unclaimed = [rid for rid in rule_ids if rid not in claimed]
    if unclaimed:
        raise LLMError(f"business rules claimed by no story: {unclaimed}")

    confidence = {
        "value": data.get("confidence"),
        "basis": "Planning model self-assessment of the draft decomposition "
                 "(live) — not a measured outcome.",
        "provenance": provenance.value,
    }
    rationale = {
        "text": str(data.get("rationale", "")),
        "provenance": provenance.value,
    }
    return stories, confidence, rationale, usage
