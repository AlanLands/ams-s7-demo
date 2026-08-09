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


def test_junit_class_name():
    assert ts.junit_class_name("US-1") == "US1AcceptanceTest"


def test_render_junit_one_failing_test_per_ac():
    files = ts.render_junit(STORY)
    assert list(files) == ["US1AcceptanceTest.java"]
    content = files["US1AcceptanceTest.java"]
    assert "package s7;" in content
    assert content.count("@Test") == 2
    assert content.count('fail("Not implemented:') == 2
    # method names identical to the pytest names — the join key
    assert ts.slug_test_name(STORY["acceptance_criteria"][0]["text"]) in content


def test_render_story_tests_maven_is_runnable_junit():
    files, manifest = ts.render_story_tests(STORY, "maven")
    assert set(files) == {"US1AcceptanceTest.java"}
    assert manifest["runnable"] is True and manifest["stack"] == "maven"


def test_runnable_root():
    assert ts.runnable_root("pytest") == "tests/s7"
    assert ts.runnable_root("maven") == "src/test/java/s7"


def test_manifest_is_byte_identical_for_identical_input():
    """M1: no generated_at — identical inputs, identical bytes."""
    import json
    _, first = ts.render_story_tests(STORY, "pytest")
    _, second = ts.render_story_tests(STORY, "pytest")
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert "generated_at" not in first


def test_scripted_names_come_from_this_module():
    """I3: test_skeletons is the single naming authority — the manifest names
    for the seeded US-003 story equal the simulated records' names."""
    from s7_delivery.factory import seed, simulate

    story = next(
        s.model_dump(mode="json") for s in seed.build_stories() if s.story_id == "US-003"
    )
    _, manifest = ts.render_story_tests(story, "pytest")
    assert [t["test_name"] for t in manifest["tests"]] == [
        t.name for t in simulate.tests_for(story)
    ]
    assert "test_rejects_first_day_absent_before_last_day_worked" in [
        t["test_name"] for t in manifest["tests"]
    ]


def test_scripted_names_do_not_apply_to_human_stories():
    story = {
        "story_id": "US-003", "title": "Hand-written", "provenance": "human",
        "acceptance_criteria": [
            {"ac_id": "US-003-AC3", "text": "Given equality, when checked, then rejected"},
        ],
    }
    _, manifest = ts.render_story_tests(story, "pytest")
    assert manifest["tests"][0]["test_name"] == ts.slug_test_name(
        story["acceptance_criteria"][0]["text"]
    )


def test_ac_text_cannot_break_out_of_a_docstring_or_comment():
    """M5: author-supplied AC text is rendered inert in both stacks."""
    story = {
        "story_id": "US-9", "title": 'Bad */ title """here',
        "acceptance_criteria": [
            {"ac_id": "US-9-AC1",
             "text": 'Given """ and */ and\na newline, when checked, then safe'},
        ],
    }
    py = ts.render_pytest(story)["test_us_9.py"]
    assert '"""US-9-AC1:' in py
    body = py.split('"""US-9-AC1:', 1)[1].split('"""', 1)[0]
    assert '"""' not in body and "\n" not in body
    compile(py, "test_us_9.py", "exec")  # it is real, importable Python
    java = ts.render_junit(story)["US9AcceptanceTest.java"]
    comment = [ln for ln in java.splitlines() if ln.strip().startswith("// US-9-AC1")][0]
    assert "*/" not in comment
    # the javadoc header closes exactly once, at its own terminator
    assert java.count("*/") == 1 and "Bad * / title" in java


def test_duplicate_generated_names_are_disambiguated():
    """M6: two criteria whose slugs collide still yield unique names, in the
    manifest and in both rendered stacks."""
    text = "Given the sponsor portal submission journey is open and ready" \
           " for the member"
    story = {
        "story_id": "US-8", "title": "Collide",
        "acceptance_criteria": [
            {"ac_id": "US-8-AC1", "text": text + ", when A, then A"},
            {"ac_id": "US-8-AC2", "text": text + ", when B, then B"},
        ],
    }
    files, manifest = ts.render_story_tests(story, "pytest")
    names = [t["test_name"] for t in manifest["tests"]]
    assert len(set(names)) == 2 and names[1].endswith("_2")
    py = files["test_us_8.py"]
    for n in names:
        assert f"def {n}():" in py
    java = ts.render_junit(story)["US8AcceptanceTest.java"]
    for n in names:
        assert f"void {n}()" in java


def test_resolve_stack_prefers_bootstrap_record(tmp_path):
    assert ts.resolve_stack({"ci_bootstrap_status": "bootstrapped:maven"}, tmp_path) == "maven"
    assert ts.resolve_stack({"ci_bootstrap_status": "unsupported_stack"}, tmp_path) is None
    (tmp_path / "requirements.txt").write_text("pytest\n")
    assert ts.resolve_stack({}, tmp_path) == "pytest"
    assert ts.resolve_stack(None, tmp_path / "missing") is None
