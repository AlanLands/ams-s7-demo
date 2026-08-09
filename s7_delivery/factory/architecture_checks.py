"""Deterministic architecture validations (spec 2026-08-09).

Honest rule-based checks over the plan and the rendered pack — the same
discipline as extraction.py. These are automated checks, never presented as
AI judgment. A mandatory failure blocks `architecture_accept` in the engine.
"""

from __future__ import annotations


def _check(check_id: str, label: str, result: str, detail: str, mandatory: bool) -> dict:
    return {
        "check_id": check_id,
        "label": label,
        "result": result,
        "detail": detail,
        "mandatory": mandatory,
    }


def _section_check(check_id: str, label: str, md: str, heading: str, mandatory: bool) -> dict:
    present = f"## {heading}" in md
    if present:
        return _check(check_id, label, "passed", f"{heading} section present", mandatory)
    result = "failed" if mandatory else "warning"
    return _check(check_id, label, result, f"architecture.md has no {heading} section", mandatory)


def _has_cycle(stories: list[dict]) -> list[str]:
    """Return the ids on a dependency cycle, empty when acyclic (iterative DFS)."""
    graph = {s["story_id"]: list(s.get("dependencies", [])) for s in stories}
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {n: WHITE for n in graph}
    for root in graph:
        if colour[root] != WHITE:
            continue
        stack: list[tuple[str, int]] = [(root, 0)]
        path: list[str] = []
        colour[root] = GREY
        path.append(root)
        while stack:
            node, idx = stack[-1]
            deps = [d for d in graph.get(node, []) if d in graph]
            if idx < len(deps):
                stack[-1] = (node, idx + 1)
                nxt = deps[idx]
                if colour[nxt] == GREY:
                    return path[path.index(nxt):] + [nxt]
                if colour[nxt] == WHITE:
                    colour[nxt] = GREY
                    path.append(nxt)
                    stack.append((nxt, 0))
            else:
                colour[node] = BLACK
                path.pop()
                stack.pop()
    return []


def run_checks(stories: list[dict], repos: list[dict], files: dict[str, object]) -> list[dict]:
    """Nine named checks; each row is passed | warning | failed with a detail."""
    md = str(files.get("architecture.md", ""))
    ids = {s["story_id"] for s in stories}
    connected = {r["name"] for r in repos}

    checks: list[dict] = []

    missing_app = [s["story_id"] for s in stories if not s.get("target_application")]
    checks.append(
        _check(
            "app_ownership", "Application ownership defined",
            "failed" if missing_app else "passed",
            f"stories without an application: {', '.join(missing_app)}"
            if missing_app else f"{len(stories)} stories name their application",
            True,
        )
    )

    missing_repo = [s["story_id"] for s in stories if not s.get("target_repository")]
    checks.append(
        _check(
            "repo_mapping", "Repository mapping complete",
            "failed" if missing_repo or not stories else "passed",
            f"stories without a repository: {', '.join(missing_repo)}"
            if missing_repo else f"{len(stories)} stories map to a repository",
            True,
        )
    )

    unknown = [
        f"{s['story_id']}→{d}"
        for s in stories
        for d in s.get("dependencies", [])
        if d not in ids
    ]
    checks.append(
        _check(
            "dependency_validity", "Dependency structure valid",
            "failed" if unknown else "passed",
            f"dependencies on unknown stories: {', '.join(unknown)}"
            if unknown else "every dependency names a story in this plan",
            True,
        )
    )

    cycle = _has_cycle(stories)
    checks.append(
        _check(
            "circular_dependencies", "No circular dependencies",
            "failed" if cycle else "passed",
            f"cycle: {' → '.join(cycle)}" if cycle else "dependency graph is acyclic",
            True,
        )
    )

    checks.append(
        _section_check(
            "integration_boundaries", "Integration boundaries defined",
            md, "Integration Boundaries", True,
        )
    )
    checks.append(
        _section_check(
            "security_constraints", "Security constraints defined",
            md, "Security Constraints", True,
        )
    )
    checks.append(
        _section_check(
            "deployment_constraints", "Deployment constraints defined",
            md, "Deployment Constraints", True,
        )
    )
    checks.append(
        _section_check("data_flow", "Data flow identified", md, "Data Flow", False)
    )

    missing_team = [s["story_id"] for s in stories if not s.get("accountable_team")]
    unconnected = sorted(
        {
            s["target_repository"]
            for s in stories
            if s.get("target_repository") and s["target_repository"] not in connected
        }
    )
    if missing_team:
        team_row = _check(
            "team_ownership", "Team ownership complete", "failed",
            f"stories without an accountable team: {', '.join(missing_team)}", True,
        )
    elif unconnected:
        team_row = _check(
            "team_ownership", "Team ownership complete", "warning",
            f"mapped repositories not connected: {', '.join(unconnected)}", True,
        )
    else:
        team_row = _check(
            "team_ownership", "Team ownership complete", "passed",
            "every story has an accountable team with a connected repository", True,
        )
    checks.append(team_row)

    return checks


def mandatory_failures(checks: list[dict]) -> list[str]:
    """check_ids that must block acceptance: mandatory AND failed (warnings pass)."""
    return [c["check_id"] for c in checks if c["mandatory"] and c["result"] == "failed"]
