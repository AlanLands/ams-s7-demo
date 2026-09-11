"""The Templates layer of a delivery profile (plan 2026-09-07-delivery-profiles,
phase 2): the CI bootstrap workflows and the release-document theme are
profile-editable layer files under `s7_delivery/layers/templates/`.

Two disciplines under test. The default profile renders *byte for byte* what
the code rendered before the templates were files — the goldens under
`tests/golden/templates/` were captured from the pre-extraction constants.
The two CI goldens were regenerated on 2026-09-10, when the workflows
started reporting whether the build itself succeeded; from that date they
pin the current default bytes rather than the pre-extraction ones, and a
change to either template is a deliberate regeneration, never a surprise.
And a profile override can restyle a template but never drop a token the
Control Centre depends on (`locked:`), because evidence sync joins on them.

Offline throughout: no model call, no network; git runs against a local bare
remote exactly as the CI bootstrap tests do.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from s7_delivery.factory import ci_bootstrap, ci_sync, layers, release_doc
from s7_delivery.product import profiles

GOLDEN = Path(__file__).parent / "golden" / "templates"
TEMPLATE_IDS = ("ci-maven", "ci-pytest", "release-doc-theme")


def _golden(name: str) -> str:
    # Goldens live outside `s7_delivery/layers/`, so a Windows checkout with
    # autocrlf may hand them back CRLF; the renderers always produce LF.
    return (GOLDEN / name).read_bytes().decode("utf-8").replace("\r\n", "\n")


def _data() -> dict:
    return json.loads(_golden("release-document-data.json"))


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("S7_CONFIG_DIR", str(tmp_path / "config"))
    return tmp_path / "config"


def _git(cwd, *args):
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
        env={"GIT_AUTHOR_NAME": "Dev", "GIT_AUTHOR_EMAIL": "dev@test",
             "GIT_COMMITTER_NAME": "Dev", "GIT_COMMITTER_EMAIL": "dev@test",
             "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(cwd)},
    )


@pytest.fixture
def clone(tmp_path):
    """A clone of a local bare remote, so `bootstrap` can commit and push
    for real without a network."""
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "--initial-branch=main")
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "--initial-branch=main")
    (seed / "README.md").write_text("seed\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "initial scaffold")
    _git(seed, "remote", "add", "origin", str(remote))
    _git(seed, "push", "-q", "origin", "main")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(remote), str(clone)],
                   check=True, capture_output=True)
    return clone


# --- the default profile is byte-identical to the pre-template code -----------


def test_template_files_are_templates_and_recorded():
    for file_id in TEMPLATE_IDS:
        lf = layers.get(file_id)
        assert lf.layer == "template" and lf.source == "default"
        assert layers.version_of(file_id)["recorded"], f"{file_id} has no ledger line"
    # the consumers name the files they read, so a run can pin the versions
    assert ci_bootstrap.PINNED_LAYER_FILES == (
        "ci-maven", "ci-pytest",
        "scaffold-maven-pom", "scaffold-maven-smoke-test",
        "scaffold-pytest-requirements", "scaffold-pytest-config",
        "scaffold-pytest-smoke-test",
    )
    assert release_doc.PINNED_LAYER_FILES == ("release-doc-theme", "identity")


def test_ci_templates_equal_the_golden_yaml_byte_for_byte():
    assert ci_bootstrap.workflow_for("maven") == _golden("ci-maven.yml")
    assert ci_bootstrap.workflow_for("pytest") == _golden("ci-pytest.yml")
    assert layers.template("ci-maven") + "\n" == _golden("ci-maven.yml")
    assert layers.template("ci-pytest") + "\n" == _golden("ci-pytest.yml")
    assert ci_bootstrap.workflow_for(None) is None
    assert ci_bootstrap.workflow_for("gradle") is None


def test_ci_templates_lock_what_ci_sync_depends_on():
    """The locked tokens are the join keys: the workflow name `latest_run`
    filters by, the artifact and file `download_summary` fetches, and the
    summary keys the engine reads into evidence."""
    for file_id in ("ci-maven", "ci-pytest"):
        locked = layers.get(file_id).locked
        assert f"name: {ci_sync.S7_WORKFLOW_NAME}" in locked
        assert "name: ci-summary" in locked and "ci-summary.json" in locked
        for key in ("tests_total", "tests_passed", "tests_failed", "coverage_pct",
                    "outcome", "build", "exit_code", "build_error"):
            assert f'"{key}"' in locked, (file_id, key)
        # the exit code is what separates "the build failed" from "the tests
        # failed": a profile may restyle the workflow but not stop recording it
        assert "test-exit-code" in locked
    assert "target/site/jacoco/jacoco.xml" in layers.get("ci-maven").locked
    assert "--junitxml=junit.xml" in layers.get("ci-pytest").locked


def test_bootstrap_writes_exactly_the_default_template(clone):
    assert ci_bootstrap.bootstrap(clone, "main", "maven") == "bootstrapped:maven"
    workflow = clone / ".github" / "workflows" / "s7-ci.yml"
    # read_text normalises the CRLF a Windows text-mode write produces
    assert workflow.read_text(encoding="utf-8") == _golden("ci-maven.yml")
    # and stays idempotent against the same template
    assert ci_bootstrap.bootstrap(clone, "main", "maven") == "bootstrapped:maven"


def test_release_document_default_is_byte_identical():
    data = _data()
    assert release_doc.render_html(data) == _golden("release-document.html")
    assert release_doc.render_markdown(data) == _golden("release-document.md")
    # branding still comes from the identity file, not a literal in code
    identity = layers.structured("identity")
    html = release_doc.render_html(data)
    assert identity["organisation"] in html
    assert f'<span class="mark">{identity["short_mark"]}</span>' in html


# --- a profile restyles without breaking the contract --------------------------


def test_profile_identity_restyles_the_release_document(cfg):
    profiles.create("tenant-t", author="op")
    root = profiles.root_of("tenant-t")
    identity = layers.structured("identity")
    identity["organisation"] = "Northwind"
    identity["short_mark"] = "NW"
    identity["palette"]["primary"] = "#0055aa"
    profiles.write("tenant-t", "identity", json.dumps(identity, indent=2),
                   note="tenant", author="op")
    data = _data()
    with layers.use(root):
        html = release_doc.render_html(data)
    assert "#0055aa" in html and "Northwind" in html
    assert '<span class="mark">NW</span>' in html
    assert "#a20a29" not in html and "MapleSure" not in html
    # the default profile is untouched
    assert release_doc.render_html(data) == _golden("release-document.html")


def test_profile_theme_override_is_rendered_and_default_stays(cfg):
    profiles.create("tenant-t", author="op")
    root = profiles.root_of("tenant-t")
    body = layers.get("release-doc-theme").body
    assert "font-size:26px" in body
    profiles.write("tenant-t", "release-doc-theme",
                   body.replace("font-size:26px", "font-size:32px"),
                   note="bigger title", author="op")
    # an override may use any identity token the frontmatter declares …
    profiles.write("tenant-t", "release-doc-theme",
                   layers.get("release-doc-theme", root).body.replace(
                       "--surface:#fff;", "--surface:{{surface}};"),
                   note="surface from identity", author="op")
    with layers.use(root):
        html = release_doc.render_html(_data())
    assert "font-size:32px" in html and "--surface:#ffffff;" in html
    assert "font-size:32px" not in release_doc.render_html(_data())
    # … but never data the workflow does not pass
    with pytest.raises(layers.LayerError, match="not declared"):
        profiles.write("tenant-t", "release-doc-theme",
                       body.replace("#fff", "{{logo_url}}"), note="x")


def test_profile_override_dropping_a_locked_token_is_refused(cfg):
    profiles.create("tenant-t", author="op")
    root = profiles.root_of("tenant-t")
    body = layers.get("ci-maven").body
    with pytest.raises(layers.LayerError, match="locked tokens"):
        profiles.write("tenant-t", "ci-maven", body.replace("name: ci-summary", "name: summary"),
                       note="rename artifact", author="op")
    with pytest.raises(layers.LayerError, match="locked tokens"):
        profiles.write("tenant-t", "ci-pytest",
                       layers.get("ci-pytest").body.replace("name: S7 CI", "name: CI"),
                       note="rename workflow", author="op")
    # nothing was written: the default still shows through
    assert layers.overridden(root) == []
    with layers.use(root):
        assert ci_bootstrap.workflow_for("maven") == _golden("ci-maven.yml")


def test_profile_override_of_an_unlocked_line_is_what_bootstrap_writes(cfg, clone):
    profiles.create("tenant-t", author="op")
    root = profiles.root_of("tenant-t")
    body = layers.get("ci-maven").body
    assert "java-version: '21'" in body
    rec = profiles.write("tenant-t", "ci-maven",
                         body.replace("java-version: '21'", "java-version: '17'"),
                         note="tenant runs Java 17", author="op")
    assert rec["version"] == 1 and rec["overrides"].startswith("default@v")
    with layers.use(root):
        assert ci_bootstrap.bootstrap(clone, "main", "maven") == "bootstrapped:maven"
        expected = layers.template("ci-maven") + "\n"
    written = (clone / ".github" / "workflows" / "s7-ci.yml").read_text(encoding="utf-8")
    assert written == expected
    assert "java-version: '17'" in written and "name: S7 CI" in written
    # outside the profile the default template is unchanged
    assert ci_bootstrap.workflow_for("maven") == _golden("ci-maven.yml")
