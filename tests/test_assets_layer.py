"""The Assets layer — project artifacts a delivery carries into the repo.

The eighth delivery-profile layer (2026-09-11). Unlike Standards and
Templates, an asset's body is the artifact itself and is published byte for
byte, so the tests here are mostly about two things: that nothing is
rendered on the way through, and that an operator-supplied path can never
escape `.s7/assets/`.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from s7_delivery.factory import delivery_packs as dp
from s7_delivery.factory import layers, publication

SQL_BODY = """-- baseline schema
CREATE TABLE sponsor (
    sponsor_id   BIGINT PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL
);
"""

# Deliberately full of another engine's templating syntax: an asset must
# survive it untouched (see `layers.ASSET_LAYERS`).
HANDLEBARS_BODY = """<h1>{{organisation}}</h1>
<p>Claim {{claim.id}} for {{member_name}}.</p>
{{#each documents}}<li>{{this.name}}</li>{{/each}}
"""


@pytest.fixture()
def profile(tmp_path: Path) -> Path:
    """A delivery profile overlay with an empty Assets layer."""
    root = tmp_path / "profile"
    (root / "assets").mkdir(parents=True)
    (root / "profile.json").write_text(
        json.dumps({"name": "test-profile", "description": "fixture"}),
        encoding="utf-8",
    )
    return root


def _add(root: Path, file_id: str, dest: str, body: str, **kw) -> dict:
    return layers.create_file(
        "asset", file_id,
        title=kw.pop("title", file_id.replace("-", " ").title()),
        stage=kw.pop("stage", "build_review"),
        summary=kw.pop("summary", "a project artifact"),
        body=body, dest=dest, note="test", root=root, **kw
    )


# --- registration ---------------------------------------------------------

def test_assets_is_the_eighth_layer_group():
    ids = [gid for gid, _, _ in layers.LAYER_GROUPS]
    assert ids[-1] == "assets"
    assert "asset" in layers._SUBDIR
    assert layers._SUBDIR["asset"] == "assets"


def test_the_default_set_ships_no_assets():
    """Hard rule 5 and the publication contract both depend on this: a fresh
    clone must publish exactly what it published before the layer existed."""
    assert layers.assets(layers.LAYERS_ROOT) == []
    assert dp.render_asset_files([]) == {}


def test_an_asset_never_enters_a_model_call():
    assert "asset" not in layers.PROMPT_LAYERS


# --- the verbatim contract ------------------------------------------------

def test_an_asset_is_not_a_variable_layer(profile: Path):
    """The point of the layer: `{{...}}` is the content's own syntax."""
    assert "asset" not in layers.VARIABLE_LAYERS
    _add(profile, "claim-letter", "templates/claim-letter.hbs", HANDLEBARS_BODY)
    lf = layers.asset("claim-letter", profile)
    assert lf.body == HANDLEBARS_BODY.rstrip("\n")
    assert "{{organisation}}" in lf.body
    assert "{{#each documents}}" in lf.body


def test_rendering_an_asset_is_refused(profile: Path):
    _add(profile, "baseline", "db/baseline.sql", SQL_BODY)
    with pytest.raises(layers.LayerError, match="not a renderable layer"):
        layers.render("baseline", profile, organisation="x")


def test_asset_accessor_refuses_a_non_asset():
    with pytest.raises(layers.LayerError, match="not an asset"):
        layers.asset("git-workflow")


# --- the path guard -------------------------------------------------------

@pytest.mark.parametrize("dest", [
    "db/baseline.sql", "openapi.yaml", "a/b/c/d/e.json",
    "doc_template-v2.html", "X1.sql",
])
def test_accepted_destinations(dest):
    assert layers.check_asset_dest(dest) == dest


@pytest.mark.parametrize("dest,why", [
    ("/etc/passwd", "leading slash"),
    ("../../escape.sql", "parent traversal"),
    ("db/../../out.sql", "traversal mid-path"),
    ("db//x.sql", "empty segment"),
    ("no-extension", "no extension"),
    ("db\\win.sql", "backslash"),
    ("a/b/c/d/e/f.txt", "too deep"),
    ("", "empty"),
    ("  ", "blank"),
    (".hidden", "no stem"),
])
def test_refused_destinations(dest, why):
    with pytest.raises(layers.LayerError):
        layers.check_asset_dest(dest)


def test_a_bad_dest_is_refused_at_creation(profile: Path):
    with pytest.raises(layers.LayerError):
        _add(profile, "escapee", "../../../evil.sql", SQL_BODY)


def test_a_bad_dest_is_refused_at_load(profile: Path):
    """Hand-editing the file past the create-time check must still fail."""
    _add(profile, "baseline", "db/baseline.sql", SQL_BODY)
    path = profile / "assets" / "baseline.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "dest: db/baseline.sql", "dest: ../../../evil.sql"
        ),
        encoding="utf-8",
    )
    with pytest.raises(layers.LayerError, match="relative path"):
        layers.load_all(profile)


def test_a_non_asset_may_not_declare_a_dest(profile: Path):
    with pytest.raises(layers.LayerError, match="only an asset publishes"):
        layers.create_file(
            "standard", "some-standard", title="t", stage="s", summary="s",
            body="text", dest="x/y.md", note="n", root=profile,
        )


def test_an_asset_needs_a_dest(profile: Path):
    with pytest.raises(layers.LayerError, match="needs a `dest:`"):
        layers.create_file(
            "asset", "no-dest", title="t", stage="s", summary="s",
            body=SQL_BODY, note="n", root=profile,
        )


def test_two_assets_may_not_claim_one_destination(profile: Path):
    _add(profile, "schema-a", "db/baseline.sql", SQL_BODY)
    _add(profile, "schema-b", "db/baseline.sql", SQL_BODY)
    with pytest.raises(layers.LayerError, match="both publish to"):
        layers.assets(profile)


# --- ordering and versioning ---------------------------------------------

def test_assets_are_ordered_by_destination(profile: Path):
    _add(profile, "zeta", "z/last.sql", SQL_BODY)
    _add(profile, "alpha", "a/first.sql", SQL_BODY)
    assert [a.dest for a in layers.assets(profile)] == ["a/first.sql", "z/last.sql"]


def test_an_asset_is_versioned_like_any_layer_file(profile: Path):
    rec = _add(profile, "baseline", "db/baseline.sql", SQL_BODY)
    assert rec["version"] == 1
    layers.write_body(
        "baseline", SQL_BODY + "\nALTER TABLE sponsor ADD COLUMN status VARCHAR(20);",
        note="add status", root=profile,
    )
    assert layers.version_of("baseline", profile)["version"] == 2
    # the dest survives the edit — write_body preserves frontmatter verbatim
    assert layers.asset("baseline", profile).dest == "db/baseline.sql"


def test_an_asset_edit_does_not_disturb_the_default_set(profile: Path):
    _add(profile, "baseline", "db/baseline.sql", SQL_BODY)
    assert layers.assets(layers.LAYERS_ROOT) == []
    assert "baseline" not in layers.load_all(layers.LAYERS_ROOT)


# --- pack rendering -------------------------------------------------------

def test_assets_render_into_the_pack_verbatim(profile: Path):
    _add(profile, "baseline", "db/baseline.sql", SQL_BODY,
         summary="Flyway baseline schema")
    _add(profile, "claim-letter", "templates/claim-letter.hbs", HANDLEBARS_BODY,
         summary="Claim acknowledgement letter")
    with layers.use(profile):
        files = dp.render_asset_files()

    assert files["assets/db/baseline.sql"] == SQL_BODY.rstrip("\n") + "\n"
    assert files["assets/templates/claim-letter.hbs"] == HANDLEBARS_BODY.rstrip("\n") + "\n"

    manifest = files["assets-manifest.json"]
    assert manifest["count"] == 2
    assert manifest["provenance"] == "rule_based"
    assert [a["published_to"] for a in manifest["assets"]] == [
        ".s7/assets/db/baseline.sql",
        ".s7/assets/templates/claim-letter.hbs",
    ]


def test_agents_md_lists_the_assets_and_states_precedence(profile: Path):
    _add(profile, "baseline", "db/baseline.sql", SQL_BODY,
         summary="Flyway baseline schema")
    story = {"story_id": "US-001", "title": "t", "acceptance_criteria": [],
             "target_component": "submission data model"}
    with layers.use(profile):
        md = dp.render_team_agents_md(
            "data-team", [story], [], architecture_version=1,
        )
    assert "## Project Assets" in md
    assert "`.s7/assets/db/baseline.sql` — Flyway baseline schema" in md
    assert "**the repository wins**" in md
    assert "Never edit a file under `.s7/assets/`" in md
    assert "reference material, not source" in md


def test_agents_md_is_unchanged_when_there_are_no_assets():
    """The whole layer is inert for a profile that supplies none — this is
    what keeps every pack generated before it byte-identical."""
    story = {"story_id": "US-001", "title": "t", "acceptance_criteria": [],
             "target_component": "submission data model"}
    md = dp.render_team_agents_md(
        "data-team", [story], [], architecture_version=1, assets=[],
    )
    assert "## Project Assets" not in md


# --- publication ----------------------------------------------------------

class _Store:
    def __init__(self, base: Path):
        self.base = base

    def path(self, *segments: str) -> Path:
        return self.base.joinpath(*segments)


def test_published_assets_land_under_the_managed_root(tmp_path: Path, profile: Path):
    _add(profile, "baseline", "db/baseline.sql", SQL_BODY)
    with layers.use(profile):
        files = dp.render_asset_files()

    slug = "data-team"
    packs = tmp_path / "build" / "packs" / slug
    (packs / "assets" / "db").mkdir(parents=True)
    (packs / "assets" / "db" / "baseline.sql").write_text(
        files["assets/db/baseline.sql"], encoding="utf-8"
    )
    (packs / "assets-manifest.json").write_text(
        json.dumps(files["assets-manifest.json"]), encoding="utf-8"
    )
    for name in ("AGENTS.md", "workspace-manifest.json", "assigned-stories.json",
                 "git-workflow.md"):
        (packs / name).write_text("x", encoding="utf-8")
    arch = tmp_path / "architecture" / "v1"
    arch.mkdir(parents=True)
    for name in ("architecture.md", "engineering-rules.md", "repository-map.json"):
        (arch / name).write_text("x", encoding="utf-8")

    pack = {"team_slug": slug, "architecture_version": 1,
            "story_ids": [], "task_ids": []}
    plan = publication.file_plan(_Store(tmp_path), pack)

    assert plan[".s7/assets/db/baseline.sql"] == SQL_BODY.rstrip("\n") + "\n"
    assert ".s7/shared/assets-manifest.json" in plan
    # every destination stays inside an already-managed root
    for dest in plan:
        assert dest == "AGENTS.md" or dest.startswith(
            (".s7/", publication.PYTEST_ROOT + "/", publication.JUNIT_ROOT + "/")
        ), dest
    assert publication.ASSETS_ROOT.startswith(".s7/")


def test_a_pack_without_assets_publishes_none(tmp_path: Path):
    slug = "data-team"
    packs = tmp_path / "build" / "packs" / slug
    packs.mkdir(parents=True)
    for name in ("AGENTS.md", "workspace-manifest.json", "assigned-stories.json",
                 "git-workflow.md"):
        (packs / name).write_text("x", encoding="utf-8")
    arch = tmp_path / "architecture" / "v1"
    arch.mkdir(parents=True)
    for name in ("architecture.md", "engineering-rules.md", "repository-map.json"):
        (arch / name).write_text("x", encoding="utf-8")

    pack = {"team_slug": slug, "architecture_version": 1,
            "story_ids": [], "task_ids": []}
    plan = publication.file_plan(_Store(tmp_path), pack)
    assert not [d for d in plan if d.startswith(".s7/assets/")]
    assert ".s7/shared/assets-manifest.json" not in plan
