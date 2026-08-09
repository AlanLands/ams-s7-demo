"""Rule-based test skeletons: deterministic, one failing test per AC,
names shared with the simulated lane so evidence joins by name."""

from s7_delivery.factory import test_skeletons as ts

STORY = {
    "story_id": "US-1",
    "title": "Establish project with initial build pipeline",
    "acceptance_criteria": [
        {"ac_id": "US-1-AC1", "text": "Given the repository, when checked, then it should build"},
        {"ac_id": "US-1-AC2", "text": "Given a push to the main branch, when checked, then CI runs"},
    ],
}


def test_slug_name_matches_simulate_fallback():
    from s7_delivery.factory.simulate import _test_name
    text = "Given the repository, when checked, then it should build"
    assert ts.slug_test_name(text) == _test_name("US-9", "US-9-AC1", text, scripted=False)


def test_pytest_file_name():
    assert ts.pytest_file_name("US-1") == "test_us_1.py"


def test_render_pytest_one_failing_test_per_ac():
    files = ts.render_pytest(STORY)
    assert list(files) == ["test_us_1.py"]
    content = files["test_us_1.py"]
    assert content.count("def test_") == 2
    assert "US-1-AC1" in content and "US-1-AC2" in content
    assert content.count('pytest.fail("Not implemented:') == 2


def test_render_pytest_is_deterministic():
    assert ts.render_pytest(STORY) == ts.render_pytest(STORY)


def test_render_story_tests_manifest():
    files, manifest = ts.render_story_tests(STORY, "pytest")
    assert manifest["story_id"] == "US-1"
    assert manifest["stack"] == "pytest"
    assert manifest["runnable"] is True
    assert manifest["provenance"] == "rule_based"
    assert [t["ac_id"] for t in manifest["tests"]] == ["US-1-AC1", "US-1-AC2"]
    assert all(t["file"] == "test_us_1.py" for t in manifest["tests"])
    assert all(t["test_name"].startswith("test_") for t in manifest["tests"])
    assert set(files) == {"test_us_1.py"}


def test_unknown_stack_renders_reference_only():
    files, manifest = ts.render_story_tests(STORY, None)
    assert manifest["runnable"] is False
    assert manifest["stack"] == ""
    assert set(files) == {"test_us_1.py"}
