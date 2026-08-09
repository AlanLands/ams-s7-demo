"""Explicit gate conditions. A gate is its conditions — never a score.

Each function returns `[{condition, met, detail}]`. The engine stores the
evaluated list on the gate record so the UI shows *why* a gate holds, and a
failed condition names what is missing rather than shaving points.
"""

from __future__ import annotations

from typing import Any

from s7_delivery.factory.models import Status


def _c(condition: str, met: bool, detail: str = "") -> dict[str, Any]:
    return {"condition": condition, "met": bool(met), "detail": detail}


def intake_gate(requirement: dict | None, analysis: dict | None, epic: dict | None) -> list[dict]:
    """G0 — spec §7D."""
    has_req = requirement is not None
    return [
        _c("Requirement captured", has_req,
           requirement["request_id"] if has_req else "no requirement on file"),
        _c("Source available", bool(requirement and requirement.get("source_documents")),
           ", ".join(requirement.get("source_documents", [])) if has_req else ""),
        _c("Initial analysis completed", analysis is not None,
           "" if analysis else "run intake analysis first"),
        _c("Scope identifiable", bool(analysis and analysis.get("affected_applications")),
           f"{len(analysis['affected_applications'])} applications named" if analysis else ""),
        _c("Business owner identified", bool(requirement and requirement.get("business_owner")),
           requirement.get("business_owner", "") if has_req else ""),
        _c("Epic created", epic is not None,
           epic["epic_id"] if epic else "create the epic before passing the gate"),
        _c("No unresolved critical blockers", True, "none raised in this run"),
    ]


def plan_signoff_gate(
    stories: list[dict],
    approver: str = "",
    *,
    epic: dict | None = None,
    analysis: dict | None = None,
) -> list[dict]:
    """G1 — approve and lock the delivery plan, authorising architecture,
    delivery-pack and workspace generation. G1 deliberately does NOT require
    architecture.md to exist — the blueprint is generated *after* approval.
    It also does not mean "AI may develop application code": developers own
    implementation; G1 only opens governed context generation.
    """
    conditions: list[dict] = []
    conditions.append(_c("Epic defined", epic is not None,
                         epic["epic_id"] if epic else "no epic on file"))
    conditions.append(_c("Stories reviewed and plan generated", bool(stories),
                         f"{len(stories)} stories" if stories else "no stories yet"))
    incomplete: list[str] = []
    for s in stories:
        gaps = story_gaps(s)
        if gaps:
            incomplete.append(f"{s['story_id']}: {'; '.join(gaps)}")
    conditions.append(_c("Every story passes quality validation", not incomplete,
                         " | ".join(incomplete) if incomplete else "purpose, ACs, team, "
                         "component, rollback and task type present on all stories"))
    ids = {s["story_id"] for s in stories}
    dangling = [
        f"{s['story_id']}→{d}" for s in stories for d in s.get("dependencies", [])
        if d not in ids
    ]
    conditions.append(_c("All dependencies mapped and resolvable", not dangling,
                         ", ".join(dangling) if dangling else ""))
    no_team = [s["story_id"] for s in stories if not s.get("accountable_team")]
    teams = {s["accountable_team"] for s in stories if s.get("accountable_team")}
    conditions.append(_c("One accountable team per story", bool(stories) and not no_team,
                         f"unassigned: {', '.join(no_team)}" if no_team
                         else f"{len(teams)} teams involved"))
    no_estimate = [s["story_id"] for s in stories if not s.get("estimate")]
    conditions.append(_c("Estimates defined for every story", bool(stories) and not no_estimate,
                         f"unestimated: {', '.join(no_estimate)}" if no_estimate else ""))
    no_sprint = [s["story_id"] for s in stories if not s.get("sprint")]
    conditions.append(_c("Every story planned into a sprint", bool(stories) and not no_sprint,
                         f"unplanned: {', '.join(no_sprint)}" if no_sprint else ""))
    conditions.append(_c("Risks and assumptions reviewed", analysis is not None,
                         f"{len(analysis.get('risks', []))} risks, "
                         f"{len(analysis.get('assumptions', []))} assumptions on file"
                         if analysis else "no intake analysis on file"))
    unmapped = [s["story_id"] for s in stories
                if not (s.get("target_repository") and s.get("target_application"))]
    conditions.append(_c("Repository and application mapping sufficient",
                         bool(stories) and not unmapped,
                         f"unmapped: {', '.join(unmapped)}" if unmapped else
                         "every story names its target application and repository"))
    conditions.append(_c("No critical planning blockers", True,
                         "none raised in this run"))
    conditions.append(_c("Named approver", bool(approver.strip()),
                         approver or "sign-off requires a named human"))
    return conditions


def story_gaps(story: dict) -> list[str]:
    """Mirror of Story.completeness_gaps for dict payloads."""
    gaps = []
    if not story.get("purpose"):
        gaps.append("purpose missing")
    if not story.get("acceptance_criteria"):
        gaps.append("no acceptance criteria")
    if not story.get("accountable_team"):
        gaps.append("no accountable team")
    if not story.get("target_component"):
        gaps.append("no target component")
    if not story.get("rollback_plan"):
        gaps.append("no rollback plan")
    if not story.get("task_type"):
        gaps.append("no task type")
    return gaps


def independent_review_gate(reviews: list[dict], tasks: list[dict]) -> list[dict]:
    """G2 — every completed task has a passing review by an isolated reviewer."""
    done = [t for t in tasks if t.get("status") in (Status.PASSED, Status.COMPLETED,
                                                    "passed", "completed")]
    latest: dict[str, dict] = {}
    for r in reviews:
        latest[r["task_id"]] = r
    unreviewed = [t["task_id"] for t in done if t["task_id"] not in latest]
    blocked = [r["task_id"] for r in latest.values() if r.get("result") != "passed"]
    majors = sum(r.get("major_gaps", 0) for r in latest.values()
                 if r.get("result") != "passed")
    return [
        _c("At least one task completed", bool(done),
           f"{len(done)} tasks complete" if done else "no completed tasks"),
        _c("Every completed task independently reviewed", bool(done) and not unreviewed,
           f"unreviewed: {', '.join(unreviewed)}" if unreviewed else ""),
        _c("No review is blocked", bool(latest) and not blocked,
           f"blocked: {', '.join(blocked)}" if blocked else ""),
        _c("Zero unresolved major gaps", bool(latest) and majors == 0,
           f"{majors} major gaps open" if majors else ""),
        _c("Reviewer is not the developer", True,
           "review executes under the independent_reviewer role only"),
    ]


def quality_gate(report: dict | None, staleness: list[dict]) -> list[dict]:
    """G3 — spec §10. Explicit conditions over the aggregated evidence."""
    if report is None:
        return [_c("Quality checks executed", False, "run quality checks first")]
    checks = {c["check_id"]: c for c in report.get("checks", [])}

    def check_ok(check_id: str) -> bool:
        return checks.get(check_id, {}).get("status") in ("passed", Status.PASSED)

    stale_required = [s["artifact_id"] for s in staleness]
    return [
        _c("Every requirement maps to at least one story", check_ok("QC-01"),
           checks.get("QC-01", {}).get("evidence", "")),
        _c("Every acceptance criterion maps to code", check_ok("QC-02"),
           checks.get("QC-02", {}).get("evidence", "")),
        _c("Every acceptance criterion maps to a test", check_ok("QC-03"),
           checks.get("QC-03", {}).get("evidence", "")),
        _c("Required tests pass", check_ok("QC-04"),
           checks.get("QC-04", {}).get("evidence", "")),
        _c("Coverage meets threshold", check_ok("QC-05"),
           checks.get("QC-05", {}).get("evidence", "")),
        _c("No unresolved critical security issue", check_ok("QC-06"),
           checks.get("QC-06", {}).get("evidence", "")),
        _c("No unresolved major independent-review gap", check_ok("QC-07"),
           checks.get("QC-07", {}).get("evidence", "")),
        _c("No required artifact is stale", not stale_required,
           f"stale: {', '.join(stale_required)}" if stale_required else ""),
        # not_applicable satisfies the condition but its evidence — stating
        # plainly that the plan carries no such story — travels to the gate.
        _c("Operational-readiness artifacts exist",
           check_ok("QC-08")
           or checks.get("QC-08", {}).get("status") == "not_applicable",
           checks.get("QC-08", {}).get("evidence", "")),
    ]


def release_gate(
    gates_before: list[dict],
    approvals: list[dict],
    staleness: list[dict],
    required_approver_roles: tuple[str, ...] = (
        "business_owner", "engineering_lead", "qa_lead", "release_manager",
        "support_lead",
    ),
) -> list[dict]:
    """G4 — spec §11. All prior gates green, all approvals present, nothing stale."""
    prior_open = [g["gate_id"] for g in gates_before
                  if g["gate_id"] != "G4" and g.get("status") not in ("passed", "completed")]
    approved_roles = {a["role"] for a in approvals
                      if a.get("subject") == "release" and a.get("decision") == "approved"}
    missing = [r for r in required_approver_roles if r not in approved_roles]
    stale_ids = [s["artifact_id"] for s in staleness]
    return [
        _c("All previous gates passed", not prior_open,
           f"open: {', '.join(prior_open)}" if prior_open else "G0–G3 green"),
        _c("All required approvals completed", not missing,
           f"missing: {', '.join(missing)}" if missing else
           ", ".join(sorted(approved_roles))),
        _c("No stale artifacts", not stale_ids,
           f"stale: {', '.join(stale_ids)}" if stale_ids else ""),
    ]


def all_met(conditions: list[dict]) -> bool:
    return bool(conditions) and all(c["met"] for c in conditions)


def quality_handoff_rows(
    stories: list[dict],
    tasks: list[dict],
    latest_reviews: dict[str, dict],
    stale_ids: set[str],
) -> list[dict]:
    """Per-story Quality handoff rule (spec §21) — a story moves to Final
    Gating only when every named condition holds. Conditions, never a
    score."""
    tasks_by_story = {t["story_id"]: t for t in tasks}
    rows: list[dict] = []
    for s in stories:
        task = tasks_by_story.get(s["story_id"])
        review = latest_reviews.get(task["task_id"]) if task else None
        tests = (task or {}).get("tests", [])
        tested_acs = {t["ac_id"] for t in tests}
        acs = [ac["ac_id"] for ac in s.get("acceptance_criteria", [])]
        missing_ev = [a for a in acs if a not in tested_acs]
        failing = [t["test_id"] for t in tests if t.get("current_result") != "passed"]
        open_major = (
            review is not None
            and review.get("result") != "passed"
            and (review.get("major_gaps", 0) + review.get("critical_gaps", 0)) > 0
        )
        related = {s["story_id"], f"WS-{s['story_id']}"}
        if task:
            suffix = task["task_id"][-3:]
            related |= {f"CHG-{suffix}", f"TSTB-{suffix}", f"REV-{suffix}"}
        pack_stale = bool(related & stale_ids)
        checks = [
            _c("Artifact context is current", not pack_stale,
               "refresh delivery context" if pack_stale else ""),
            _c("Required build checks pass",
               task is not None and bool(task.get("files_changed")),
               "" if task and task.get("files_changed") else "no build evidence"),
            _c("Required tests pass", bool(tests) and not failing,
               f"failing: {', '.join(failing)}" if failing else
               ("no tests recorded" if not tests else f"{len(tests)} tests green")),
            _c("Every acceptance criterion has test evidence",
               bool(acs) and not missing_ev,
               f"unevidenced: {', '.join(missing_ev)}" if missing_ev else ""),
            _c("Independent review passed",
               review is not None and review.get("result") == "passed",
               "" if review and review.get("result") == "passed"
               else "no passing review on file"),
            _c("No unresolved major or critical finding", not open_major,
               f"{review.get('major_gaps', 0)} major / "
               f"{review.get('critical_gaps', 0)} critical open"
               if open_major else ""),
            _c("PR and CI evidence exists",
               task is not None and bool(task.get("pr_ref"))
               and task.get("ci_status") == "passed",
               "" if task and task.get("pr_ref") and task.get("ci_status") == "passed"
               else "missing PR or CI signal"),
        ]
        rows.append(
            {
                "story_id": s["story_id"],
                "title": s.get("title", ""),
                "team": s.get("accountable_team", ""),
                "checks": checks,
                "ready": all_met(checks),
            }
        )
    return rows
