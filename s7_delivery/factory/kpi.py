"""Delivery KPI scorecard — evidence or absence, never invention.

S7 is measured on delivery KPIs (§ Metrics): velocity, cycle time,
estimation accuracy, defect leakage, first-time-right, on-time/on-budget,
cost per release. This module computes each one **from the run's own
records where the run can evidence it**, and reports `value: None` with
the reason where it cannot — the same discipline as `common/telemetry.py`
(log what is real, leave unset what is not). Everything here is
deterministic derivation, provenance `rule_based`.

The consolidated view maps the client's four outcome dimensions; the
support-scope half of each dimension is explicitly labelled as provided
by S1–S6 — another team's scope, never presented as this repo's evidence.
"""

from __future__ import annotations

from datetime import datetime

_DONE = {"passed", "completed"}


def _kpi(value, unit: str, basis: str, note: str = "") -> dict:
    return {
        "value": value,
        "unit": unit,
        "basis": basis,
        "note": note,
        "evidenced": value is not None,
    }


def _parse(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def scorecard(
    *,
    stories: list[dict],
    tasks: list[dict],
    reviews: list[dict],
    provenance: list[dict],
    release: dict | None,
    run_mode: str,
) -> dict:
    story_of = {t.get("task_id"): t.get("story_id") for t in tasks}
    completed_sids = {
        t.get("story_id") for t in tasks
        if str(t.get("status", "")).lower() in _DONE
    }
    by_sid = {s.get("story_id"): s for s in stories}

    # Velocity — completed story points per sprint spanned by completed work.
    done_stories = [by_sid[sid] for sid in completed_sids if sid in by_sid]
    points = sum(int(s.get("estimate") or 0) for s in done_stories)
    sprints = {int(s.get("sprint") or 1) for s in done_stories}
    velocity = _kpi(
        round(points / len(sprints), 1) if done_stories else None,
        "points per sprint",
        "completed story points over the sprints they span, from the plan "
        "and task records",
        "" if done_stories else "no completed stories yet",
    )

    # Cycle time — story record created → its review passed, from ledger
    # timestamps. Real clocks; in simulation the clock is honest but the
    # pacing is a demo's, and the note says so.
    created: dict[str, datetime] = {}
    for rec in provenance:
        if rec.get("artifact_type") == "story":
            ts = _parse(rec.get("timestamp", ""))
            sid = rec.get("artifact_id")
            if ts and sid and sid not in created:
                created[sid] = ts
    cycles: list[float] = []
    for r in reviews:
        if r.get("result") != "passed":
            continue
        sid = story_of.get(r.get("task_id"))
        end = _parse(r.get("created_at", ""))
        if sid in created and end:
            cycles.append((end - created[sid]).total_seconds())
    sim_note = (
        "ledger timestamps are real, but simulation compresses time — this "
        "reflects demo pacing, not delivery pacing"
        if run_mode != "live" else ""
    )
    cycle_time = _kpi(
        round(sum(cycles) / len(cycles)) if cycles else None,
        "seconds, story defined → independently verified",
        "provenance and review ledger timestamps",
        sim_note if cycles else "no story has completed review yet",
    )

    # First-time-right — stories whose review passed on the first attempt.
    attempts: dict[str, list[str]] = {}
    for r in reviews:
        sid = story_of.get(r.get("task_id"))
        if sid:
            attempts.setdefault(sid, []).append(str(r.get("result")))
    reviewed = {sid for sid, rs in attempts.items() if "passed" in rs}
    right_first = {
        sid for sid in reviewed
        if attempts[sid][0] == "passed" and len(attempts[sid]) == 1
    }
    first_time_right = _kpi(
        round(100 * len(right_first) / len(reviewed)) if reviewed else None,
        "%",
        "review ledger: stories verified without a returned attempt",
        "" if reviewed else "no reviewed stories yet",
    )

    # Defect leakage — needs a post-release observation window a demo run
    # does not have. The review-caught count is reported as context.
    findings = sum(len(r.get("findings", []) or []) for r in reviews)
    defect_leakage = _kpi(
        None,
        "defects reaching production",
        "requires a post-release observation window",
        f"not evidenced by a demo run; independent review caught "
        f"{findings} finding(s) before release",
    )

    estimation_accuracy = _kpi(
        None,
        "estimate vs actual",
        "requires historical delivery actuals",
        "not evidenced: estimates are placeholders today; historical "
        "delivery data is the named grounding source (§ Design review 3)",
    )
    on_time_on_budget = _kpi(
        None,
        "schedule / budget variance",
        "requires a baseline schedule and budget",
        "not evidenced: a demo run records neither",
    )
    cost_per_release = _kpi(
        None,
        "cost per release",
        "requires provider token pricing over measured usage",
        "not evidenced: telemetry logs what providers report and the "
        "pricing table is deliberately empty — costs are never invented",
    )

    support_note = (
        "provided by the support scope (S1–S6), built elsewhere by the "
        "team — not this repo's evidence"
    )
    consolidated = [
        {"dimension": "efficiency",
         "delivery": ["velocity", "cycle_time"], "support": support_note},
        {"dimension": "service_quality",
         "delivery": ["first_time_right", "defect_leakage"],
         "support": support_note},
        {"dimension": "issue_resolution",
         "delivery": ["defect_leakage"], "support": support_note},
        {"dimension": "delivery_productivity",
         "delivery": ["velocity", "cost_per_release"], "support": support_note},
    ]

    return {
        "kpis": {
            "velocity": velocity,
            "cycle_time": cycle_time,
            "first_time_right": first_time_right,
            "defect_leakage": defect_leakage,
            "estimation_accuracy": estimation_accuracy,
            "on_time_on_budget": on_time_on_budget,
            "cost_per_release": cost_per_release,
        },
        "consolidated": consolidated,
        "provenance": "rule_based",
    }
