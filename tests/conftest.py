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
def _isolated_config_plane(tmp_path_factory, monkeypatch):
    """The product configuration plane (`config/`: prompt sets, LLM settings,
    role overrides, users, audit) is operator state. Point every test at a
    throwaway directory so a saved override on this machine can never change
    what the suite asserts, and no test can write into the real plane. Tests
    that want their own directory monkeypatch `S7_CONFIG_DIR` again, which
    simply wins."""
    monkeypatch.setenv("S7_CONFIG_DIR", str(tmp_path_factory.mktemp("config_plane")))


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
