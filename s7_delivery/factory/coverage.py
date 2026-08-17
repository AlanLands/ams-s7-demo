"""Stream routing and AI-coverage classification for a plan's stories.

The client-facing answer to "what does the AI cover, and what does it not"
(CLAUDE.md § The coverage model). Everything here is deterministic
derivation from the plan's own fields — provenance `rule_based`, never
presented as an AI result, and deliberately conservative: work that cannot
be routed to a known automated lane is classified manual rather than
quietly counted as coverage. Effort-weighting uses story estimates so one
heavy manual stream cannot hide behind a story count.

This module must not change any live-plan prompt: classification runs on
the stored plan after generation, so committed recordings stay valid.
"""

from __future__ import annotations

# Team → delivery stream. Teams outside this map are real work the demo
# does not operate — routed to the catch-all stream, classified manual.
TEAM_STREAMS: dict[str, str] = {
    "Portal Team": "frontend",
    "Services Team": "api",
    "Data Team": "database",
    "Intake Integration Team": "document_intake",
    "QA Automation": "test",
    "Platform Team": "platform",
    "Support Team": "platform",
}

# Stream → coverage class, with the reason a client would be given.
# agentic: the downstream lane executes it under governance.
# ai_assisted_external: AI prepares the package; an externally owned
#   system/team completes it (a ticket against another team — Design
#   review item 6).
# manual: human operational work; AI assists documentation only.
_STREAM_COVERAGE: dict[str, tuple[str, str]] = {
    "frontend": ("agentic", "portal code and tests run in the governed lane"),
    "api": ("agentic", "service code and tests run in the governed lane"),
    "database": ("agentic", "schema and data-access changes run in the governed lane"),
    "test": ("agentic", "regression suites are generated and executed in the lane"),
    "document_intake": (
        "ai_assisted_external",
        "AI prepares the handoff packet; the intake/indexing system is "
        "operated by another team — delivered as a ticket against them",
    ),
    "platform": (
        "manual",
        "deployment, monitoring and handover are human operational work; "
        "AI assists the runbook, not the change",
    ),
}

_UNROUTED = (
    "manual",
    "no automated lane is proven for this team — counted as manual rather "
    "than claimed as coverage",
)


def classify(story: dict) -> dict:
    """{stream, coverage, reason} for one story — pure derivation."""
    team = str(story.get("accountable_team", "") or "")
    stream = TEAM_STREAMS.get(team)
    if stream is None:
        cov, reason = _UNROUTED
        return {"stream": "unrouted", "coverage": cov, "reason": reason}
    cov, reason = _STREAM_COVERAGE[stream]
    return {"stream": stream, "coverage": cov, "reason": reason}


def breakdown(stories: list[dict]) -> dict:
    """Effort-weighted coverage rollup plus per-story routing rows."""
    rows = []
    effort: dict[str, int] = {"agentic": 0, "ai_assisted_external": 0, "manual": 0}
    count: dict[str, int] = {"agentic": 0, "ai_assisted_external": 0, "manual": 0}
    convergence: list[str] = []
    for s in stories:
        c = classify(s)
        est = int(s.get("estimate") or 0)
        effort[c["coverage"]] += est
        count[c["coverage"]] += 1
        if c["coverage"] == "ai_assisted_external":
            convergence.append(str(s.get("story_id", "?")))
        rows.append({
            "story_id": s.get("story_id"),
            "title": s.get("title"),
            "team": s.get("accountable_team"),
            "estimate": est,
            **c,
        })
    total = sum(effort.values())
    by_coverage = {
        k: {
            "stories": count[k],
            "effort_points": effort[k],
            "effort_pct": round(100 * effort[k] / total) if total else 0,
        }
        for k in effort
    }
    note = ""
    if convergence:
        ids = ", ".join(convergence)
        note = (
            f"Convergence point: {ids} — the externally owned handoff every "
            "parallel stream merges into; end-to-end verification waits on it."
        )
    return {
        "by_coverage": by_coverage,
        "stories": rows,
        "integration_note": note,
        "provenance": "rule_based",
    }
