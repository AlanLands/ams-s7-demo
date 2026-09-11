---
id: ci-pytest
layer: template
title: CI bootstrap — pytest (GitHub Actions)
stage: intake
summary: The GitHub Actions workflow S7 commits once to a connected Python repository as .github/workflows/s7-ci.yml, so a real developer push produces a real run that ci_sync reads back. Reports whether the build itself succeeded, so a run that never collected a test cannot be read as a run that found no failures. Locked tokens are what ci_sync and the engine join on — the workflow name, the artifact name, the summary file and its keys, and the junit/cobertura report paths.
locked: name: S7 CI, name: ci-summary, ci-summary.json, --junitxml=junit.xml, coverage.xml, test-exit-code, "build", "exit_code", "build_error", "tests_total", "tests_passed", "tests_failed", "coverage_pct", "tests": tests, "outcome"
---
name: S7 CI
on:
  push:
    branches: ['**']
  pull_request:
jobs:
  build-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
          pip install pytest
      - name: Run tests
        shell: bash
        run: |
          set +e
          pytest --junitxml=junit.xml | tee test-output.log
          code=${PIPESTATUS[0]}
          set -e
          echo "$code" > test-exit-code
          exit "$code"
      - name: Summarize results
        if: always()
        run: |
          python3 - <<'PY'
          import json, os, xml.etree.ElementTree as ET
          tests = []
          reports = os.path.exists("junit.xml")
          if reports:
              for case in ET.parse("junit.xml").getroot().iter("testcase"):
                  outcome = "passed"
                  if case.find("failure") is not None or case.find("error") is not None:
                      outcome = "failed"
                  elif case.find("skipped") is not None:
                      outcome = "skipped"
                  tests.append({"name": case.get("name", ""), "outcome": outcome})
          counted = [t for t in tests if t["outcome"] != "skipped"]
          failed = sum(1 for t in counted if t["outcome"] == "failed")
          # Did the run get far enough to collect any test at all? No report
          # plus a non-zero exit is a build failure — an import error, a
          # missing dependency, an unusable interpreter — not a run that
          # found zero failures. The counts are null in that case, never
          # zero: "0 failing tests" for a suite that never ran is a false
          # green, and this file is the evidence the red baseline is read
          # from. pytest's exit 5 is "nothing collected", not a failure.
          exit_code = None
          if os.path.exists("test-exit-code"):
              exit_code = int(open("test-exit-code").read().strip() or "0")
          if reports:
              build = "succeeded"
          elif exit_code in (None, 0, 5):
              build = "no_tests"
          else:
              build = "failed"
          ran = build != "failed"
          # coverage.xml (cobertura format): line-rate is a 0..1 fraction on
          # the report root. Absent file/attribute means unset, never a guess.
          coverage_pct = None
          if os.path.exists("coverage.xml"):
              cov_root = ET.parse("coverage.xml").getroot()
              line_rate = cov_root.get("line-rate")
              if line_rate is not None:
                  coverage_pct = round(float(line_rate) * 100, 1)
          summary = {"build": build, "exit_code": exit_code,
                     "tests_total": len(counted) if ran else None,
                     "tests_passed": (len(counted) - failed) if ran else None,
                     "tests_failed": failed if ran else None,
                     "coverage_pct": coverage_pct, "tests": tests}
          if not ran:
              lines = []
              if os.path.exists("test-output.log"):
                  raw = open("test-output.log", errors="replace").read()
                  lines = [ln for ln in raw.splitlines() if ln.strip()]
              summary["build_error"] = "\n".join(lines[-20:])[-2000:]
          json.dump(summary, open("ci-summary.json", "w"))
          PY
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: ci-summary
          path: ci-summary.json
