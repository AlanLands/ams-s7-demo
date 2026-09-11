---
id: scaffold-pytest-smoke-test
layer: template
title: New-application scaffold — Python build smoke test
stage: intake
summary: One passing test committed with the new-application Python scaffold, so the repository's first CI run is genuinely green and pytest writes a junit report. It proves the toolchain, nothing else — which is exactly what makes a later red run attributable to the published test skeletons rather than to a suite that never collected.
---
"""Committed by S7 when this repository was provisioned.

It asserts nothing about the application — its only job is to make the suite
produce a real junit report from the first commit, so that a later failing
run is attributable to the code under test and not to a suite that never
collected. Delete it once real tests exist.
"""


def test_toolchain_runs_tests():
    assert True, "the pytest toolchain collects and runs tests"
