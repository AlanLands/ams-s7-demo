"""The Standards layer of delivery profiles: what developers are told.

The git workflow, engineering rules, UI guidelines, DB conventions and the
starter UI files are files under `s7_delivery/layers/standards/`, rendered
per run through the profile overlay. Two disciplines are checked here:

- **The default profile renders the bytes the code rendered before the
  extraction.** `tests/fixtures/standards/` holds the outputs captured from
  the seeded simulation run before any renderer read a file; the same run
  must reproduce them byte for byte (CRLF-normalised — the working copy is
  checked out with `core.autocrlf=true`).
- **A profile can restyle a standard but cannot break the convention the
  Control Centre reads by.** Overrides show up in the pack and in its pins;
  locked tokens survive every edit; identity changes flow into the UI files.

Everything here is offline: simulation runs make no model call.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from s7_delivery.factory import delivery_packs as dp
from s7_delivery.factory import layers
from s7_delivery.factory import publication as pub
from s7_delivery.factory.engine import Engine
from s7_delivery.factory.models import DemoMode, Role
from s7_delivery.product import profiles

FIXTURES = Path(__file__).parent / "fixtures" / "standards"
TEAMS = (
    "data-team", "services-team", "portal-team", "intake-integration-team",
    "qa-automation", "platform-team",
)
STANDARD_IDS = (
    "git-workflow", "code-conventions", "engineering-rules", "ui-guidelines",
    "db-conventions",
    "ui-starter-css", "ui-layout-thymeleaf", "ui-layout-jinja",
)
# The variables each renderer supplies — the contract an edit may use.
ENGINE_VARIABLES = {
    "git-workflow": {
        "team", "repository", "context_branch", "default_branch", "branch_rows",
        "note_rows", "phrase_start", "phrase_plan", "phrase_build",
        "phrase_commit", "phrase_push",
    },
    "code-conventions": {"team", "stack_line", "scope_line"},
    "engineering-rules": set(),
    "ui-guidelines": {
        "team", "scope_line", "css_block", "token_rows", "organisation",
        "short_mark", "product_line", "synthetic_domain",
    },
    "db-conventions": {"default_branch", "note_rows"},
    "ui-starter-css": {"css_tokens"},
    "ui-layout-thymeleaf": {"organisation", "short_mark", "product_line"},
    "ui-layout-jinja": {"organisation", "short_mark", "product_line"},
}


def fixture(*parts: str) -> str:
    return (FIXTURES.joinpath(*parts)).read_bytes().decode("utf-8").replace("\r\n", "\n")


def stored(eng: Engine, *segments: str) -> str:
    return eng.store.path(*segments).read_bytes().decode("utf-8").replace("\r\n", "\n")


def run_to_packs(root: Path, prompt_set: str = "default") -> Engine:
    e = Engine.create(DemoMode.SIMULATION, root=root, prompt_set=prompt_set)
    e.intake_analyse(Role.PRODUCT_ANALYST)
    e.intake_create_epic(Role.PRODUCT_ANALYST)
    e.intake_pass_gate(Role.BUSINESS_OWNER)
    e.planning_generate(Role.PRODUCT_ANALYST)
    e.planning_sign_off(Role.BUSINESS_OWNER, "Jordan Blake", "approved")
    e.architecture_generate(Role.ENGINEERING_LEAD)
    e.architecture_accept(Role.ENGINEERING_LEAD, "Sam Whitfield")
    e.delivery_packs_generate(Role.ENGINEERING_LEAD)
    return e


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("S7_CONFIG_DIR", str(tmp_path / "config"))
    return tmp_path / "config"


@pytest.fixture(scope="module")
def eng(tmp_path_factory):
    return run_to_packs(tmp_path_factory.mktemp("runs"))


# --- (a) the default profile renders the pre-extraction bytes -----------------


def test_seeded_run_renders_the_captured_standards_byte_for_byte(eng):
    packs = {p["team_slug"]: p for p in eng.state()["build"]["delivery_packs"]}
    assert set(packs) == set(TEAMS)
    for slug in TEAMS:
        for name in ("git-workflow.md", "ui-guidelines.md"):
            assert stored(eng, "build", "packs", slug, name) == fixture(slug, name), (slug, name)
    assert stored(eng, "architecture", "v1", "engineering-rules.md") == fixture(
        "architecture", "engineering-rules.md"
    )


def test_agents_md_matches_the_captured_file(eng):
    """AGENTS.md is rendered from a hard-coded list in `render_team_agents_md`,
    not from the Standards layer, so nothing versions it — the fixture is its
    only guard. Editing that renderer means re-capturing here deliberately.

    Until the build discipline landed (2026-09-10) this test carried a
    documented old/new replacement pair proving the Standards-layer extraction
    changed AGENTS.md in exactly two ways. That proof is spent now the file is
    edited on purpose; git history keeps it, and a third replacement pair would
    only restate the renderer."""
    for slug in TEAMS:
        assert stored(eng, "build", "packs", slug, "AGENTS.md") == fixture(slug, "AGENTS.md"), slug


def test_new_standards_land_in_every_pack_with_the_marker(eng):
    for slug in TEAMS:
        db = stored(eng, "build", "packs", slug, "db-conventions.md")
        assert db.startswith(dp.S7_MARKER + "\n# Database conventions")
        assert "V<next>__<story-id-lowercase>_<short-desc>.sql" in db
        assert "spring.config.import: optional:classpath:config/" in db
        css = stored(eng, "build", "packs", slug, "ui", "app.css")
        assert css.startswith(dp.S7_MARKER_CSS + "\n")
        assert ":root {\n  --ms-ink: #36362f;" in css and "@media (max-width: 600px)" in css
        layout = stored(eng, "build", "packs", slug, "ui", "layout.html")
        assert layout.startswith(dp.S7_MARKER + "\n<!DOCTYPE html>")
        # the seeded repos have no clone, so the stack is unknown → Thymeleaf
        assert 'xmlns:th="http://www.thymeleaf.org"' in layout
        assert "/css/app.css" in layout and "Synthetic data only" in layout


def test_packs_and_architecture_pin_the_standards(eng):
    state = eng.state()
    pack = state["build"]["delivery_packs"][0]
    assert set(pack["pins"]) == set(dp.PINNED_LAYER_FILES) == {*STANDARD_IDS, "identity"} - {
        "engineering-rules"
    }
    assert pack["stale_pins"] == []
    assert set(state["build"]["architecture"]["pins"]) == {"engineering-rules"}


# --- (b) a profile override shows in the pack and in its pins ------------------


def test_profile_override_of_ui_guidelines_changes_the_pack_and_its_pin(cfg, tmp_path):
    profiles.create("tenant-a", author="op")
    body = layers.get("ui-guidelines").body.replace(
        "A page that passes its tests but looks like a framework default is not done.",
        "Tenant A rule: a page that passes its tests but looks like a framework"
        " default is not done, and the design lead signs every screenshot.",
    )
    assert body != layers.get("ui-guidelines").body
    profiles.write("tenant-a", "ui-guidelines", body, note="tenant wording", author="op")
    e = run_to_packs(tmp_path / "runs", prompt_set="tenant-a")
    pack = e.state()["build"]["delivery_packs"][0]
    text = stored(e, "build", "packs", pack["team_slug"], "ui-guidelines.md")
    assert "Tenant A rule:" in text
    assert pack["pins"]["ui-guidelines"] != layers.pin_ref("ui-guidelines")
    assert pack["pins"]["ui-guidelines"].startswith("ui-guidelines@v1+")
    # the untouched standards still pin the default versions
    assert pack["pins"]["git-workflow"] == layers.pin_ref("git-workflow")
    assert pack["stale_pins"] == []


# --- (c) identity flows into the UI standards ---------------------------------


def test_identity_override_restyles_ui_guidelines_and_starter_css(cfg, tmp_path):
    profiles.create("northwind", author="op")
    identity = layers.get("identity").body
    body = (
        identity.replace("MapleSure Insurance", "Northwind Assurance")
        .replace('"short_mark": "MS"', '"short_mark": "NW"')
        .replace('"primary": "#a20a29"', '"primary": "#004b8d"')
    )
    assert body != identity
    profiles.write("northwind", "identity", body, note="tenant identity", author="op")
    e = run_to_packs(tmp_path / "runs", prompt_set="northwind")
    slug = e.state()["build"]["delivery_packs"][0]["team_slug"]
    ui = stored(e, "build", "packs", slug, "ui-guidelines.md")
    assert "the `NW` mark" in ui and "| `--ms-red` | `#004b8d` |" in ui
    assert "  --ms-red: #004b8d;" in ui and "#a20a29" not in ui
    css = stored(e, "build", "packs", slug, "ui", "app.css")
    assert "  --ms-red: #004b8d;" in css and "#a20a29" not in css
    layout = stored(e, "build", "packs", slug, "ui", "layout.html")
    assert "Northwind Assurance" in layout and ">NW<" in layout
    assert "MapleSure" not in layout
    # the default profile is untouched
    assert "#a20a29" in dp.css_tokens() and "#004b8d" not in dp.css_tokens()


def test_ui_tokens_keep_their_names_and_take_values_from_identity():
    rows = dp.ui_tokens()
    assert [n for n, _, _ in rows] == [
        "--ms-ink", "--ms-muted", "--ms-bg", "--ms-surface", "--ms-surface-2",
        "--ms-border", "--ms-border-strong", "--ms-red", "--ms-red-dark",
        "--ms-red-pale", "--ms-green", "--ms-green-pale", "--ms-amber-text",
        "--ms-amber-pale", "--ms-radius-sm", "--ms-radius-md", "--ms-space", "--ms-font",
    ]
    identity = layers.structured("identity")
    assert dict((n, v) for n, v, _ in rows)["--ms-red"] == identity["palette"]["primary"]
    with pytest.raises(layers.LayerError, match="missing"):
        dp.ui_tokens({"palette": {}, "radius": {}, "space": "8px", "font": "x"})


# --- (d) locked tokens --------------------------------------------------------


def test_git_workflow_edit_that_drops_the_push_phrase_is_refused(cfg):
    profiles.create("tenant-a", author="op")
    body = layers.get("git-workflow").body.replace("{{phrase_push}}", "push it")
    assert "{{phrase_push}}" not in body
    with pytest.raises(layers.LayerError, match="locked tokens"):
        profiles.write("tenant-a", "git-workflow", body, note="drop the phrase", author="op")
    assert layers.overridden(profiles.root_of("tenant-a")) == []
    # the starter stylesheet is locked the same way: the :root block must stay
    css = layers.get("ui-starter-css").body.replace("{{css_tokens}}", "  --ms-ink: #000;")
    with pytest.raises(layers.LayerError, match="locked tokens"):
        profiles.write("tenant-a", "ui-starter-css", css, note="inline", author="op")


# --- (e) publication ships them under .s7/shared/ ------------------------------


def test_file_plan_ships_db_conventions_and_starter_ui_files(eng):
    pack = eng.state()["build"]["delivery_packs"][0]
    plan = pub.file_plan(eng.store, pack)
    for dest in (
        ".s7/shared/git-workflow.md", ".s7/shared/ui-guidelines.md",
        ".s7/shared/db-conventions.md", ".s7/shared/ui/app.css", ".s7/shared/ui/layout.html",
    ):
        assert dest in plan, dest
    assert plan[".s7/shared/db-conventions.md"].startswith(dp.S7_MARKER)
    assert plan[".s7/shared/ui/app.css"].startswith(dp.S7_MARKER_CSS)


def test_file_plan_tolerates_packs_generated_before_the_standards(eng):
    pack = eng.state()["build"]["delivery_packs"][0]
    slug = pack["team_slug"]
    removed = {}
    for name in ("db-conventions.md", "ui/app.css", "ui/layout.html"):
        path = eng.store.path("build", "packs", slug, name)
        removed[name] = path.read_bytes()
        path.unlink()
    try:
        plan = pub.file_plan(eng.store, pack)
        assert ".s7/shared/db-conventions.md" not in plan
        assert not any(k.startswith(".s7/shared/ui/") for k in plan)
    finally:
        for name, blob in removed.items():
            eng.store.path("build", "packs", slug, name).write_bytes(blob)


# --- (f) the layout follows the repository's stack -----------------------------


def test_layout_follows_the_stack(eng):
    stories = eng.state()["planning"]["stories"]
    team = stories[0]["accountable_team"]
    t_stories = [s for s in stories if s["accountable_team"] == team]
    tasks = [t for t in eng.state()["build"]["tasks"]
             if t["story_id"] in {s["story_id"] for s in t_stories}]

    def pack(stack):
        return dp.render_team_pack(
            run_id=eng.run_id, team=team, stories=t_stories, tasks=tasks,
            all_stories=stories, pack_version=1, plan_version=1,
            architecture_version=1, stack=stack,
        )

    jinja = pack("pytest")["ui/layout.html"]
    assert "{% block content %}{% endblock %}" in jinja and "th:" not in jinja
    assert "{{ url_for('static', filename='css/app.css') }}" in jinja
    assert "MapleSure Insurance" in jinja  # identity substituted, Jinja left alone
    maven = pack("maven")["ui/layout.html"]
    assert 'th:fragment="page(title, content)"' in maven and "{% block" not in maven
    assert pack(None)["ui/layout.html"] == maven
    assert dp.layout_file_for("pytest") == "ui-layout-jinja"
    assert dp.layout_file_for("unknown") == "ui-layout-thymeleaf"
    assert set(pack("pytest")) == set(dp.TEAM_FILES)


# --- (g) every standard declares what the engine supplies ----------------------


def test_every_standard_declares_its_variables_within_the_engine_contract():
    files = layers.load_all()
    standards = {fid for fid, lf in files.items() if lf.layer == "standard"}
    assert standards == set(STANDARD_IDS)
    for fid in STANDARD_IDS:
        lf = files[fid]
        used = set(layers.placeholders_of(lf.body))
        assert used <= set(lf.variables), (fid, used - set(lf.variables))
        extra = set(lf.variables) - ENGINE_VARIABLES[fid]
        assert not extra, (fid, extra)
        # renders with exactly the engine's variables — no LayerError
        text = layers.standard(fid, **{v: f"<{v}>" for v in ENGINE_VARIABLES[fid]})
        assert "{{" not in text.replace("{{ ", "")  # Jinja's spaced form is not a placeholder
        assert layers.version_of(fid)["recorded"], f"{fid} is unrecorded"
