---
id: scaffold-pytest-config
layer: template
title: New-application scaffold — pyproject.toml (pytest config)
stage: intake
summary: Minimal pytest configuration committed with the new-application Python scaffold. It points pytest at tests/ and turns on the cobertura coverage report the S7 CI workflow already knows how to read, so coverage_pct stops being permanently unset. Deliberately not a packaging manifest — only the tool table.
---
# Created by S7 when this repository was provisioned. Test configuration
# only: this is not a packaging manifest, and a story that needs one adds
# its own tables here in a single, named commit.
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=. --cov-report=xml --cov-report=term-missing"
