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
import re

from common.llm import LLMError, complete, parse_json_response
from common.prompt import PromptLayers
from s7_delivery.factory import layers
from s7_delivery.factory.models import IntakeAnalysis, Provenance, RoutingVerdict
from s7_delivery.product import llm_settings

MAX_CLARIFICATION_ROUNDS = 2

# Rules, role and task text are the Rules, Skills and Tasks layers of the
# delivery system (`factory/layers.py`): files, versioned, loaded verbatim
# — and resolved *at call time* against the active prompt set
# (`layers.use()` / the run's `prompt_set`), never pinned at import. The
# default set's bytes are pinned by committed recordings — edit the files,
# then re-record.
RULES_ID = "delivery-assistant"

_REPO_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{2,38}$")


def _rules() -> str:
    return layers.rules(RULES_ID)


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


def _call(
    *, role: str, ref: str, task: str, beat: str, key_material: str, stage: str,
) -> tuple[dict, dict]:
    """One JSON-mode model call. `role` is a skill *id*, resolved here so
    the text comes from whichever prompt set is active for this call;
    `stage` is the per-stage LLM-settings key whose provider/model (if
    configured) override the environment."""
    usage: dict = {}
    response = complete(
        PromptLayers(rules=_rules(), role=layers.skill(role), ref=ref, task=task),
        json_mode=True,
        cache_key=f"s7_factory_{beat}:{_cache_digest(key_material)}",
        usage_out=usage,
        **llm_settings.for_stage(stage),
    )
    return parse_json_response(response), usage


def run_analysis(
    requirement: dict, packs: dict[str, str], transcript: list[dict]
) -> tuple[IntakeAnalysis, dict]:
    if not packs:
        raise LLMError(
            "Live analysis needs at least one connected repository — connect "
            "the target repos first (grounding is the point)."
        )
    task = layers.render_task(
        "intake-analysis-task", transcript=_transcript_text(transcript)
    )
    data, usage = _call(
        role="intake-analysis",
        stage="intake-analysis",
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


def route_requirement(
    requirement: dict, packs: dict[str, str]
) -> tuple[RoutingVerdict, dict]:
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
    task = layers.render_task("requirement-routing-task")
    data, usage = _call(
        role="requirement-routing",
        stage="requirement-routing",
        ref=_ref(requirement, packs),
        task=task,
        beat="route",
        key_material=json.dumps(requirement, sort_keys=True)
        + "".join(packs[k] for k in sorted(packs)),
    )
    return _validate_route(data, set(packs)), usage


def _validate_route(data: dict, repo_names: set[str]) -> RoutingVerdict:
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
    task = layers.render_task(
        "clarification-task", transcript=_transcript_text(transcript)
    )
    data, usage = _call(
        role="clarification",
        stage="clarification",
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


def run_extraction(text: str) -> tuple[dict, dict]:
    if not text or not text.strip():
        raise LLMError("Live extraction needs non-empty source text.")
    task = layers.render_task("requirement-extraction-task", text=text)
    data, usage = _call(
        role="requirement-extraction",
        stage="requirement-extraction",
        ref="",
        task=task,
        beat="extract",
        key_material=text,
    )
    return _validate_extraction(data), usage


def _validate_extraction(data: dict) -> dict:
    title = str(data.get("epic_title", "")).strip()
    if not title:
        raise LLMError("extraction has no epic_title")
    objective = str(data.get("business_objective", "")).strip()
    if not objective:
        raise LLMError("extraction has no business_objective")
    summary = str(data.get("requirement_summary", "")).strip()
    if not summary:
        raise LLMError("extraction has no requirement_summary")
    reqs = data.get("extracted_requirements")
    if not isinstance(reqs, list) or not reqs:
        raise LLMError("extraction has no extracted_requirements")
    cleaned = []
    for r in reqs:
        if not (isinstance(r, dict) and r.get("rule_id") and r.get("text")):
            raise LLMError(f"extracted_requirements entry missing rule_id/text: {r!r}")
        cleaned.append({"rule_id": str(r["rule_id"]), "text": str(r["text"])})
    return {
        "epic_title": title,
        "business_objective": objective,
        "requirement_summary": summary,
        "extracted_requirements": cleaned,
    }


def run_new_app_setup(
    requirement: dict, transcript: list[dict]
) -> tuple[dict, dict]:
    rounds_used = sum(1 for t in transcript if t["role"] == "assistant")
    if rounds_used >= MAX_CLARIFICATION_ROUNDS:
        raise LLMError(
            f"New-application setup cap reached ({MAX_CLARIFICATION_ROUNDS} "
            "rounds) — name, description and stack must be settled by now."
        )
    force = rounds_used == MAX_CLARIFICATION_ROUNDS - 1
    force_note = (
        "\nThis is the final round — you may NOT ask further questions. "
        "Report name, description and stack now, making a reasonable "
        "assumption for anything still unclear.\n"
        if force else ""
    )
    task = layers.render_task(
        "new-application-setup-task",
        transcript=_transcript_text(transcript),
        force_note=force_note,
        requirement=json.dumps(requirement, indent=2),
    )
    data, usage = _call(
        role="new-application-setup",
        stage="new-application-setup",
        ref=json.dumps(requirement, indent=2),
        task=task,
        beat="new-app-setup",
        key_material=json.dumps(requirement, sort_keys=True)
        + json.dumps(transcript, sort_keys=True),
    )
    if data.get("needs_more_info"):
        if force:
            raise LLMError(
                "The model asked past the new-app setup cap — a prompt bug, "
                "not a valid response."
            )
        questions = [str(q).strip() for q in data.get("questions", []) if str(q).strip()]
        if not 1 <= len(questions) <= 3:
            raise LLMError(f"expected 1-3 setup questions, got {len(questions)}")
        return {"done": False, "questions": questions}, usage
    name = str(data.get("name", "")).strip()
    if not _REPO_NAME_RE.match(name):
        raise LLMError(f"new application name {name!r} is not a valid repository name")
    description = str(data.get("description", "")).strip()
    stack = str(data.get("stack", "")).strip()
    if not description or not stack:
        raise LLMError("new application setup is missing description or stack")
    return {"done": True, "name": name, "description": description, "stack": stack}, usage


_POINT_SCALE = (1, 2, 3, 5, 8, 13)


def _collect_plan_defects(
    data: dict, *, epic: dict, packs: dict, teams: list[str], rule_ids: list[str]
) -> tuple[list, list[str]]:
    """Validate the model's plan and return (stories, defects).

    Every defect the model can see and repair — wrong team, missing
    acceptance criteria, bad estimate, dangling dependency, unclaimed
    business rule — is collected as a string rather than raised, so the
    caller can run one bounded corrective pass naming all of them at once.
    Only an unrecoverable shape (no usable story list) raises directly:
    there is no draft to hand back for correction.

    The stories list is only trustworthy when defects is empty; a story
    with a named defect may still appear in it (or be absent, if it failed
    model validation), and the caller must discard the batch either way.
    """
    from s7_delivery.factory.models import Status, Story

    raw_stories = data.get("stories")
    if not isinstance(raw_stories, list) or not 1 <= len(raw_stories) <= 10:
        raise LLMError("plan must contain 1-10 stories")

    provenance = provenance_now()
    defects: list[str] = []
    stories: list[Story] = []
    seen: set[str] = set()
    for raw in raw_stories:
        sid = str(raw.get("story_id", ""))
        if not sid or sid in seen:
            defects.append(f"missing or duplicate story_id {sid!r}")
            continue
        seen.add(sid)
        if raw.get("accountable_team") not in teams:
            defects.append(
                f"story {sid}: accountable_team {raw.get('accountable_team')!r} "
                "is not on the team roster"
            )
        if raw.get("target_repository") not in packs:
            defects.append(
                f"story {sid}: target_repository {raw.get('target_repository')!r} "
                "is not a connected repository"
            )
        if raw.get("estimate") not in _POINT_SCALE:
            defects.append(f"story {sid}: estimate must be one of {_POINT_SCALE}")
        if len(raw.get("acceptance_criteria") or []) < 2:
            defects.append(f"story {sid}: needs at least 2 acceptance criteria")
        _excluded = {"provenance", "status", "version", "epic_id"}  # ours to set
        try:
            story = Story(
                **{k: v for k, v in raw.items()
                   if k in Story.model_fields and k not in _excluded},
                epic_id=str(epic.get("epic_id", "")),
                provenance=provenance,
            )
        except Exception as exc:
            defects.append(f"story {sid} failed validation: {exc}")
            continue
        if story.sprint != 1:
            story = story.model_copy(update={"status": Status.PLANNED})
        stories.append(story)

    ids = {s.story_id for s in stories}
    for s in stories:
        dangling = [d for d in s.dependencies if d not in ids]
        if dangling:
            defects.append(
                f"story {s.story_id} depends on unknown stories {dangling}"
            )

    claimed = {rid for s in stories for rid in s.traces_to}
    unclaimed = [rid for rid in rule_ids if rid not in claimed]
    if unclaimed:
        defects.append(f"business rules claimed by no story: {unclaimed}")
    return stories, defects


def run_plan(
    epic: dict,
    analysis: dict,
    packs: dict[str, str],
    transcript: list[dict],
    teams: list[str],
) -> tuple[list, dict, dict, dict]:
    # Volatile timestamps must not enter prompt or key material, or the beat
    # can never replay across runs (each run stamps its own epic afresh).
    epic = {k: v for k, v in epic.items() if k not in {"created_at", "generated_at"}}

    if not packs:
        raise LLMError("Live planning needs a connected repository.")
    rule_ids = [r["rule_id"] for r in analysis.get("business_rules", [])]
    roster = "\n".join(f"- {t}" for t in teams)
    task = layers.render_task(
        "epic-decomposition-task",
        epic=json.dumps(epic, indent=2),
        business_rules=json.dumps(analysis.get("business_rules", []), indent=2),
        transcript=_transcript_text(transcript),
        roster=roster,
    )
    base_key = (
        json.dumps(epic, sort_keys=True)
        + json.dumps(rule_ids)
        + json.dumps(transcript, sort_keys=True)
    )
    data, usage = _call(
        role="epic-decomposition",
        stage="epic-decomposition",
        ref=_ref(epic, packs),
        task=task,
        beat="plan",
        key_material=base_key,
    )

    stories, defects = _collect_plan_defects(
        data, epic=epic, packs=packs, teams=teams, rule_ids=rule_ids
    )
    if defects:
        # One bounded corrective pass: name every defect, hand back the
        # draft, demand a full correction. Repairing its own draft is the
        # model's job — the human gate judges the plan's content, not its
        # formatting. Distinct key material so the recorded first response
        # can never be replayed as the answer to this correction.
        defect_list = "\n".join(f"- {d}" for d in defects)
        retry_task = layers.render_task(
            "epic-decomposition-correction-task",
            task=task,
            defects=defect_list,
            draft_stories=json.dumps(data.get("stories", []), indent=2),
            point_scale=_POINT_SCALE,
        )
        data, retry_usage = _call(
            role="epic-decomposition",
            stage="epic-decomposition",
            ref=_ref(epic, packs),
            task=retry_task,
            beat="plan",
            key_material=base_key + f"correction:{json.dumps(defects)}",
        )
        for k, v in retry_usage.items():
            usage[k] = usage.get(k, 0) + v if isinstance(v, (int, float)) else v
        stories, defects = _collect_plan_defects(
            data, epic=epic, packs=packs, teams=teams, rule_ids=rule_ids
        )
        if defects:
            raise LLMError("; ".join(defects))

    provenance = provenance_now()
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
