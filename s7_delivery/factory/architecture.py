"""Architecture pack rendering — the engineering blueprint generated from the
approved plan, AFTER Gate 1 (spec §5). Pure functions: plan data in, file
payloads out; the engine owns storage, versioning, provenance and phases.

Honesty: this renderer is deterministic — a structured projection of the
signed plan, the intake analysis and the connected repositories. In
simulation mode it is badged SIMULATED like all simulated evidence; in live
mode it is badged RULE_BASED (a real, deterministic, non-AI derivation of
real inputs — presenting it as AI output would be the mislabelling CLAUDE.md
§ Staged output forbids). A live-LLM architecture author can slot in behind
the same engine method later without changing this contract.
"""

from __future__ import annotations

FILES = (
    "architecture.md",
    "repository-map.json",
    "dependency-map.json",
    "integration-guidelines.md",
    "engineering-rules.md",
)


def team_slug(team: str) -> str:
    return "-".join(team.lower().split())


def _apps(stories: list[dict], analysis: dict | None) -> list[str]:
    ordered: list[str] = []
    for s in stories:
        app = s.get("target_application", "")
        if app and app not in ordered:
            ordered.append(app)
    for app in (analysis or {}).get("affected_applications", []):
        if app not in ordered:
            ordered.append(app)
    return ordered


def repository_map(stories: list[dict], repos: list[dict]) -> dict:
    """Team → repository → stories. The workspace name is where the team's
    delivery pack will land once published."""
    connected = {r["name"]: r for r in repos}
    rows: list[dict] = []
    for s in stories:
        team = s.get("accountable_team", "")
        repo = s.get("target_repository", "")
        row = next((r for r in rows if r["team"] == team and r["repository"] == repo), None)
        if row is None:
            row = {
                "team": team,
                "team_slug": team_slug(team),
                "repository": repo,
                "application": s.get("target_application", ""),
                "repository_connected": repo in connected,
                "default_branch": connected.get(repo, {}).get("default_branch", ""),
                "workspace": f"{team_slug(team)}-workspace",
                "stories": [],
            }
            rows.append(row)
        row["stories"].append(s["story_id"])
    return {"teams": rows}


def dependency_map(stories: list[dict]) -> dict:
    edges = [
        {"from": dep, "to": s["story_id"]}
        for s in stories
        for dep in s.get("dependencies", [])
    ]
    cross_team = []
    by_id = {s["story_id"]: s for s in stories}
    for e in edges:
        a, b = by_id.get(e["from"]), by_id.get(e["to"])
        if a and b and a.get("accountable_team") != b.get("accountable_team"):
            cross_team.append(
                {
                    "from_story": e["from"],
                    "from_team": a.get("accountable_team", ""),
                    "to_story": e["to"],
                    "to_team": b.get("accountable_team", ""),
                }
            )
    return {
        "nodes": [s["story_id"] for s in stories],
        "edges": edges,
        "integration_points": cross_team,
    }


def landscape(stories: list[dict], analysis: dict | None, repos: list[dict]) -> dict:
    """Customer-safe diagram data, derived by a stated classification rule —
    application names only, no invented middleware, nothing the run's own
    plan does not name.

    Node rule: one node per repository the plan maps (a repository is the
    delivery's own service unit; connected or not — connectivity is the
    team_ownership check's concern), plus one external node per
    analysis-named application no story maps a repository to. Layer rule:
    portal/web/mobile in the label ⇒ client; store/db/data ⇒ data; mapped
    repository otherwise ⇒ core; no repository ⇒ external. Edges: one sync
    edge per cross-team story dependency (between the two labels), plus a
    data edge from each core node to each data node in the delivery."""
    by_id = {s["story_id"]: s for s in stories}

    nodes: list[dict] = []

    def node_for(label: str, application: str, repository: str) -> dict:
        existing = next((n for n in nodes if n["label"] == label), None)
        if existing:
            return existing
        n = {
            "label": label,
            "application": application,
            "layer": "external",
            "repository": repository,
            "teams": [],
        }
        nodes.append(n)
        return n

    def label_of(s: dict) -> str:
        return s.get("target_repository") or s.get("target_application", "")

    for s in stories:
        label = label_of(s)
        if not label:
            continue
        n = node_for(label, s.get("target_application", ""), s.get("target_repository", ""))
        team = s.get("accountable_team", "")
        if team and team not in n["teams"]:
            n["teams"].append(team)
    mapped_apps = {s.get("target_application", "") for s in stories}
    for app in (analysis or {}).get("affected_applications", []):
        if app not in mapped_apps:
            node_for(app, app, "")

    for n in nodes:
        name = f"{n['label']} {n['application']}".lower()
        if not n["repository"]:
            n["layer"] = "external"
        elif any(w in name for w in ("portal", "web", "mobile")):
            n["layer"] = "client"
        elif any(w in name for w in ("store", "db", "data")):
            n["layer"] = "data"
        else:
            n["layer"] = "core"

    edges: list[dict] = []

    def add_edge(a: str, b: str, kind: str) -> None:
        if not a or not b or a == b:
            return
        if not any(e["from_app"] == a and e["to_app"] == b for e in edges):
            edges.append({"from_app": a, "to_app": b, "kind": kind})

    for s in stories:
        for dep in s.get("dependencies", []):
            other = by_id.get(dep)
            if not other:
                continue
            if other.get("accountable_team") != s.get("accountable_team"):
                add_edge(label_of(other), label_of(s), "sync")
    data_labels = [n["label"] for n in nodes if n["layer"] == "data"]
    for n in nodes:
        if n["layer"] == "core":
            for d in data_labels:
                add_edge(n["label"], d, "data")

    return {"nodes": nodes, "edges": edges}


def architecture_md(
    *,
    epic: dict | None,
    requirement: dict | None,
    stories: list[dict],
    analysis: dict | None,
    repos: list[dict],
    version: int,
    revision_note: str = "",
) -> str:
    apps = _apps(stories, analysis)
    repo_rows = repository_map(stories, repos)["teams"]
    deps = dependency_map(stories)
    title = (epic or {}).get("title", "Delivery blueprint")
    req_id = (requirement or {}).get("request_id", "")
    lines: list[str] = [
        f"# Architecture — {title}",
        "",
        f"Version {version}. Generated from the approved plan"
        + (f" for {req_id}" if req_id else "")
        + ". Canonical: teams and task packs reference this file by version;"
        " they do not copy it.",
        "",
        "## Application Landscape",
        "",
        "MapleSure group-benefits estate. The applications below participate in"
        " this delivery; everything else is out of scope for this epic.",
        "",
        "## Affected Applications",
        "",
    ]
    lines += [f"- **{a}**" for a in apps] or ["- (none named)"]
    lines += [
        "",
        "## Repository Mapping",
        "",
        "| Team | Repository | Application | Stories |",
        "|---|---|---|---|",
    ]
    for r in repo_rows:
        lines.append(
            f"| {r['team']} | `{r['repository']}` | {r['application']} | "
            f"{', '.join(r['stories'])} |"
        )
    lines += [
        "",
        "## Component Ownership",
        "",
    ]
    for s in stories:
        lines.append(
            f"- `{s.get('target_component', '?')}` ({s.get('target_application', '?')})"
            f" — owned by {s.get('accountable_team', '?')} ({s['story_id']})"
        )
    lines += [
        "",
        "## Integration Boundaries",
        "",
        "Applications communicate through their published service interfaces"
        " only. Cross-team dependencies below are the integration points this"
        " delivery must coordinate:",
        "",
    ]
    if deps["integration_points"]:
        lines += [
            f"- {p['from_story']} ({p['from_team']}) → {p['to_story']} ({p['to_team']})"
            for p in deps["integration_points"]
        ]
    else:
        lines.append("- No cross-team story dependencies in this plan.")
    lines += [
        "",
        "## API Dependencies",
        "",
        "Story-level dependency graph (see `dependency-map.json` for the"
        " machine-readable form):",
        "",
    ]
    lines += [f"- {e['from']} → {e['to']}" for e in deps["edges"]] or ["- none"]
    lines += [
        "",
        "## Data Flow",
        "",
        "Submission data enters through the sponsor portal, is validated by the"
        " claims services, persisted to the claims data store, and surfaced to"
        " intake operations. Documents follow the same path with virus scanning"
        " before persistence.",
        "",
        "## Security Constraints",
        "",
        "- No PII in logs, exports or test fixtures — synthetic data only.",
        "- All uploads are scanned and size-capped before persistence.",
        "- Access follows the role model; no shared credentials.",
        "",
        "## Deployment Constraints",
        "",
        "- Deployments run through the standard CI/CD pipeline with"
        " policy-enforced controls; no direct-to-production changes.",
        "- Feature flags gate every user-visible change (see each story's"
        " rollback plan).",
        "",
        "## Technology Standards",
        "",
        "- Follow each repository's existing stack and conventions — the"
        " repository's own `architecture.md` is authoritative for local detail.",
        "- Tests accompany every change; acceptance criteria map to executable"
        " evidence.",
        "",
        "## Legacy Constraints",
        "",
        "- The fragmented paper/PDF intake process remains live until cutover;"
        " nothing in this delivery may break the existing intake path.",
        "",
        "## Operational Considerations",
        "",
        "- Support handover, runbook and monitoring updates are release-gate"
        " conditions, not afterthoughts.",
    ]
    if revision_note:
        lines += ["", "## Revision Notes", "", f"- v{version}: {revision_note}"]
    return "\n".join(lines) + "\n"


def integration_guidelines_md(stories: list[dict]) -> str:
    deps = dependency_map(stories)
    lines = [
        "# Integration Guidelines",
        "",
        "How teams coordinate where stories touch more than one component.",
        "",
        "1. **Contract first.** Where a story depends on another team's story,"
        " agree the interface before implementation starts on either side.",
        "2. **No reaching around boundaries.** Consume other applications"
        " through their published interfaces; never read another system's"
        " data store directly.",
        "3. **Cross-team dependencies in this plan:**",
        "",
    ]
    if deps["integration_points"]:
        lines += [
            f"   - {p['from_story']} ({p['from_team']}) must land before"
            f" {p['to_story']} ({p['to_team']}) integrates against it."
            for p in deps["integration_points"]
        ]
    else:
        lines.append("   - None — every dependency is within a single team.")
    lines += [
        "",
        "4. **Integration evidence.** A dependency is only 'done' when the"
        " consuming story's tests exercise the integrated path.",
    ]
    return "\n".join(lines) + "\n"


def engineering_rules_md() -> str:
    return "\n".join(
        [
            "# Engineering Rules",
            "",
            "Non-negotiable rules for every workspace in this delivery.",
            "",
            "- **Scope**: change only components your story names. Touching an"
            " out-of-scope component requires a new ticket, not a bigger diff.",
            "- **Test-first**: every acceptance criterion has a linked,"
            " executable test; the red baseline is recorded before"
            " implementation.",
            "- **Traceability**: commits and pull requests reference their"
            " story and task ids.",
            "- **No self-approval**: the implementer never approves their own"
            " review; independent review precedes quality handoff.",
            "- **Rollback ready**: the story's feature flag and rollback plan"
            " are wired before release, not after.",
            "- **Data**: synthetic data only; no client-identifiable"
            " information anywhere in code, tests or fixtures.",
        ]
    ) + "\n"


def render_pack(
    *,
    epic: dict | None,
    requirement: dict | None,
    stories: list[dict],
    analysis: dict | None,
    repos: list[dict],
    version: int,
    revision_note: str = "",
) -> dict[str, object]:
    """All five canonical files, keyed by filename (spec §5)."""
    return {
        "architecture.md": architecture_md(
            epic=epic, requirement=requirement, stories=stories,
            analysis=analysis, repos=repos, version=version,
            revision_note=revision_note,
        ),
        "repository-map.json": repository_map(stories, repos),
        "dependency-map.json": dependency_map(stories),
        "integration-guidelines.md": integration_guidelines_md(stories),
        "engineering-rules.md": engineering_rules_md(),
    }
