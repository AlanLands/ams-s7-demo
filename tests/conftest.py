"""Test-suite-wide setup."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add repo root to path so imports like `from demo import ...` work
repo_root = Path(__file__).parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))


@pytest.fixture(autouse=True)
def _isolated_known_repos_registry(tmp_path_factory, monkeypatch):
    """`Engine.intake_connect_repo` writes into the global known-repos
    registry (`artifacts/known_repos.json`) on every connect, unconditionally
    — that file is meant to survive run deletion, so it lives outside any
    run's own gitignored tree and is not gitignored itself. Point every test
    at a throwaway registry root so the suite never touches this repo's real
    `artifacts/known_repos.json`. Individual tests that care about the
    registry re-monkeypatch this to their own tmp_path, which simply wins."""
    from s7_delivery.factory import repos as repos_mod

    registry_root = tmp_path_factory.mktemp("known_repos_registry")
    monkeypatch.setattr(repos_mod, "_default_root", lambda: registry_root)
