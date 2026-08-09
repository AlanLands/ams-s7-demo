"""Deterministic architecture validations and the derived landscape.

The checks are honest rule-based computations over the rendered pack and the
plan — the same discipline as extraction.py. A mandatory failure blocks
acceptance (enforced in the engine, tested in test_factory_architecture.py).
"""

from s7_delivery.factory import architecture as arch
from s7_delivery.factory.architecture_checks import mandatory_failures, run_checks


def story(sid, team="Portal Team", repo="sponsorconnect-portal",
          app="SponsorConnect portal", deps=None):
    return {
        "story_id": sid,
        "accountable_team": team,
        "target_repository": repo,
        "target_application": app,
        "target_component": "web",
        "dependencies": deps or [],
    }


REPOS = [{"name": "sponsorconnect-portal", "default_branch": "main"}]


def render(stories, repos=REPOS):
    return arch.render_pack(
        epic={"title": "T"}, requirement=None, stories=stories,
        analysis=None, repos=repos, version=1,
    )


def by_id(checks):
    return {c["check_id"]: c for c in checks}


def test_all_pass_on_well_formed_plan():
    stories = [story("US-001"), story("US-002", deps=["US-001"])]
    checks = by_id(run_checks(stories, REPOS, render(stories)))
    assert len(checks) == 9
    assert all(c["result"] == "passed" for c in checks.values())
    assert mandatory_failures(list(checks.values())) == []


def test_missing_repository_fails_repo_mapping():
    stories = [story("US-001", repo="")]
    checks = by_id(run_checks(stories, REPOS, render(stories)))
    assert checks["repo_mapping"]["result"] == "failed"
    assert "repo_mapping" in mandatory_failures(list(checks.values()))


def test_unknown_dependency_fails_validity():
    stories = [story("US-001", deps=["US-999"])]
    checks = by_id(run_checks(stories, REPOS, render(stories)))
    assert checks["dependency_validity"]["result"] == "failed"
    assert "US-999" in checks["dependency_validity"]["detail"]


def test_cycle_fails_circular_dependencies():
    stories = [story("US-001", deps=["US-002"]), story("US-002", deps=["US-001"])]
    checks = by_id(run_checks(stories, REPOS, render(stories)))
    assert checks["circular_dependencies"]["result"] == "failed"


def test_missing_data_flow_section_is_warning_not_failure():
    stories = [story("US-001")]
    files = render(stories)
    files["architecture.md"] = files["architecture.md"].replace("## Data Flow", "## Flows")
    checks = by_id(run_checks(stories, REPOS, files))
    assert checks["data_flow"]["result"] == "warning"
    assert mandatory_failures(list(checks.values())) == []


def test_unconnected_repo_is_team_ownership_warning():
    stories = [story("US-001", repo="not-connected-repo")]
    checks = by_id(run_checks(stories, REPOS, render(stories)))
    assert checks["team_ownership"]["result"] == "warning"
    assert mandatory_failures(list(checks.values())) == []


def test_missing_team_fails_team_ownership():
    stories = [story("US-001", team="")]
    checks = by_id(run_checks(stories, REPOS, render(stories)))
    assert checks["team_ownership"]["result"] == "failed"


# --- landscape ---------------------------------------------------------------


def test_landscape_classifies_layers_and_edges():
    stories = [
        story("US-001", team="Portal Team", repo="sponsorconnect-portal",
              app="SponsorConnect portal"),
        story("US-002", team="Services Team", repo="sponsorconnect-api",
              app="SponsorConnect API services", deps=["US-001"]),
        story("US-003", team="Data Team", repo="sponsorconnect-db",
              app="Submission data store"),
    ]
    repos = REPOS + [
        {"name": "sponsorconnect-api", "default_branch": "main"},
        {"name": "sponsorconnect-db", "default_branch": "main"},
    ]
    analysis = {"affected_applications": ["Policy/member system of record (externally owned)"]}
    land = arch.landscape(stories, analysis, repos)
    layers = {n["application"]: n["layer"] for n in land["nodes"]}
    assert layers["SponsorConnect portal"] == "client"
    assert layers["SponsorConnect API services"] == "core"
    assert layers["Submission data store"] == "data"
    assert layers["Policy/member system of record (externally owned)"] == "external"
    kinds = {(e["from_app"], e["to_app"]): e["kind"] for e in land["edges"]}
    # cross-team story dependency US-001 (portal) -> US-002 (api) = sync edge
    assert kinds[("SponsorConnect portal", "SponsorConnect API services")] == "sync"
    # core services persist to the delivery's data stores
    assert kinds[("SponsorConnect API services", "Submission data store")] == "data"


def test_landscape_nodes_carry_repository_and_teams():
    stories = [story("US-001")]
    land = arch.landscape(stories, None, REPOS)
    node = land["nodes"][0]
    assert node["repository"] == "sponsorconnect-portal"
    assert node["teams"] == ["Portal Team"]
