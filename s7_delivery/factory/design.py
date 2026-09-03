"""Design diagrams — the client-named step between epic and stories.

Two sources, both honest and neither an AI call:

- `curated_diagrams()` — the MapleSure disability-submission DFD and entity
  relationships, scripted content for simulation/demo runs (SIMULATED, the
  same discipline as every other seeded artifact). Ported from the original
  staged pipeline (`s7_delivery/staged.py`, retired 2026-09-03) so the
  Control Centre finally shows the design phase the brief names.
- `derived_diagrams(stories, repos)` — a deterministic derivation from the
  run's own plan for live/replay runs (RULE_BASED): the data-flow diagram
  routes actors through each accountable team into the connected
  repositories, and the relationship diagram traces epic → story → team →
  repository. A real rendering of real records, never presented as a model's
  design.
"""

from __future__ import annotations

_CURATED_DFD = """flowchart LR
  sponsor([Plan sponsor\\nbenefits administrator])

  subgraph portal[MapleSure SponsorConnect]
    ui[Submission journey UI]
    api[Submission API]
    store[(Submission &\\ndocument store)]
  end

  subgraph external[Outside the delivery team]
    sor[(Policy / member\\nsystem of record)]
    intake[Intake & indexing]
  end

  sponsor -->|policy no. + member id| ui
  ui -->|lookup| api
  api -->|read member + plan| sor
  sor -.->|pre-populated details| api
  api -.->|details for confirmation| ui
  sponsor -->|claim details + attestation| ui
  sponsor -->|supporting documents| ui
  ui -->|submit| api
  api -->|persist submission + docs| store
  api -->|associated packet| intake
  intake -.->|status updates| api
  api -.->|reference + status| ui
  ui -.->|confirmation of receipt| sponsor
"""

_CURATED_DFD_NOTES = (
    "The trust boundary sits at the portal edge: a sponsor may only ever "
    "retrieve or submit for a member their own organization sponsors, so "
    "the sponsor-scoping check belongs on the API, not the UI. Dashed "
    "edges are responses. The system of record is read-only to this "
    "project except for the one field addition."
)

_CURATED_ER = """erDiagram
  PLAN_SPONSOR ||--o{ MEMBER : sponsors
  PLAN_SPONSOR ||--o{ SUBMISSION : submits
  MEMBER ||--o{ SUBMISSION : "is subject of"
  SUBMISSION ||--o{ DOCUMENT : includes
  SUBMISSION ||--|| STATUS : has
  POLICY ||--o{ MEMBER : covers
  PLAN_SPONSOR ||--o{ POLICY : holds
"""

_CURATED_ER_NOTES = (
    "A submission belongs to exactly one member and one sponsor, which is "
    "what makes the scoping rule enforceable. Status values are deliberately "
    "not enumerated here — the epic lists them as unvalidated."
)


def curated_diagrams() -> dict:
    return {
        "dfd": {
            "title": "Disability claim submission — data flow",
            "mermaid": _CURATED_DFD,
            "notes": _CURATED_DFD_NOTES,
        },
        "relationship": {
            "title": "Core entities and their relationships",
            "mermaid": _CURATED_ER,
            "notes": _CURATED_ER_NOTES,
        },
    }


def _node_id(prefix: str, name: str) -> str:
    return prefix + "".join(c if c.isalnum() else "_" for c in name)


def derived_diagrams(stories: list[dict], repos: list[dict]) -> dict:
    """Deterministic diagrams from the run's own plan and repositories."""
    teams = sorted({str(s.get("accountable_team") or "Unassigned") for s in stories})
    repo_names = sorted({str(r.get("name")) for r in repos if r.get("name")})
    story_repos = {
        str(s.get("target_repository") or "") for s in stories
    } - {""}
    stores = sorted(set(repo_names) | story_repos)

    lines = ["flowchart LR", "  requester([Business requester])"]
    lines.append("  subgraph delivery[Delivery teams]")
    for team in teams:
        lines.append(f"    {_node_id('t_', team)}[{team}]")
    lines.append("  end")
    for name in stores:
        lines.append(f"  {_node_id('r_', name)}[({name})]")
    for s in stories:
        team = str(s.get("accountable_team") or "Unassigned")
        sid = str(s.get("story_id", "?"))
        lines.append(f"  requester -->|{sid}| {_node_id('t_', team)}")
        target = str(s.get("target_repository") or "")
        if target:
            lines.append(
                f"  {_node_id('t_', team)} -->|changes| {_node_id('r_', target)}"
            )
    dfd = "\n".join(lines) + "\n"

    relationship = "\n".join([
        "erDiagram",
        "  EPIC ||--o{ STORY : decomposes_into",
        "  TEAM ||--o{ STORY : delivers",
        "  STORY }o--|| REPOSITORY : lands_in",
    ]) + "\n"

    return {
        "dfd": {
            "title": "Delivery data flow — derived from the plan",
            "mermaid": dfd,
            "notes": (
                f"Derived from {len(stories)} stories across {len(teams)} "
                f"teams and {len(stores)} target repositories — a rendering "
                "of the plan's own records, not a model's design."
            ),
        },
        "relationship": {
            "title": "Delivery relationships — epic, stories, teams, repositories",
            "mermaid": relationship,
            "notes": (
                "Structural relationships traced from the run's records. "
                "Domain entity modelling stays a human design activity in "
                "the target repository's architecture.md."
            ),
        },
    }
