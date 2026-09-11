---
id: scaffold-pytest-requirements
layer: template
title: New-application scaffold — Python requirements.txt
stage: intake
summary: The pinned test dependencies S7 commits alongside the CI workflow when it creates a brand-new Python repository, so `pytest` runs and reports coverage from the first commit. Pinned per hard rule 4; application dependencies are added by the stories that need them.
---
# Created by S7 when this repository was provisioned, so that `pytest` runs
# from the first commit and CI evidence means something. Test tooling only:
# a story that needs an application dependency adds it here in its own
# single, named commit (see .s7/shared/git-workflow.md).
pytest==8.2.2
pytest-cov==5.0.0
