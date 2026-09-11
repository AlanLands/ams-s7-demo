"""Repositories as the operator sees them: the cross-run known-repositories
registry (`artifacts/known_repos.json`, written by every successful connect
in `factory/repos.py`) joined with the runs that currently use each one,
plus forget. Read from files, derived on read, `RULE_BASED`.

Connecting a repository stays a per-run action in the Control Centre; this
module never clones, never pushes and never touches a run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from s7_delivery.factory import repos as repos_module
from s7_delivery.factory import store as store_module
from s7_delivery.product import integrations
from s7_delivery.product.config import audit, audit_log


class RepositoryNotFound(LookupError):
    pass


def _runs_root(root: Path | None) -> Path:
    return root or store_module.RUNS_ROOT


def _runs_by_url(runs_root: Path | None) -> dict[str, list[dict[str, Any]]]:
    """url → runs that name it in `intake/repos.json`, from the run files."""
    base = _runs_root(runs_root)
    out: dict[str, list[dict[str, Any]]] = {}
    if not base.is_dir():
        return out
    for run_dir in sorted(base.iterdir()):
        repos_path = run_dir / "intake" / "repos.json"
        run_path = run_dir / "run.json"
        if not repos_path.is_file():
            continue
        try:
            rows = json.loads(repos_path.read_text(encoding="utf-8"))
            run = json.loads(run_path.read_text(encoding="utf-8")) if run_path.is_file() else {}
        except json.JSONDecodeError:
            continue
        for rec in rows if isinstance(rows, list) else []:
            url = repos_module.normalize_repo_url(rec.get("url", ""))
            if not url:
                continue
            out.setdefault(url, []).append({
                "run_id": run.get("run_id", run_dir.name),
                "mode": run.get("mode", ""),
                "status": run.get("status", ""),
                "profile": run.get("prompt_set", "default"),
                "ci_bootstrap_status": rec.get("ci_bootstrap_status", ""),
                "default_branch": rec.get("default_branch", ""),
            })
    return out


def list_repositories(
    *, registry_root: Path | None = None, runs_root: Path | None = None,
) -> dict[str, Any]:
    """Every known repository with its runs, newest-first as the registry
    keeps them, plus repositories a run names that the registry forgot."""
    by_url = _runs_by_url(runs_root)
    checks = _last_checks()
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rec in repos_module.known_repos(registry_root):
        url = repos_module.normalize_repo_url(rec.get("url", ""))
        seen.add(url)
        parts = integrations.parse_repo_url(url)
        runs = by_url.get(url, [])
        rows.append({
            **rec, "url": url,
            "kind": parts["kind"], "host": parts["host"], "owner": parts["owner"],
            "in_registry": True,
            "runs": runs,
            "run_count": len(runs),
            "last_check": checks.get(url),
            "stack": (rec.get("ci_bootstrap_status") or "").split(":", 1)[1]
            if ":" in (rec.get("ci_bootstrap_status") or "") else "",
        })
    for url, runs in by_url.items():
        if url in seen:
            continue
        parts = integrations.parse_repo_url(url)
        rows.append({
            "url": url, "name": parts["repo"], "kind": parts["kind"],
            "host": parts["host"], "owner": parts["owner"],
            "default_branch": runs[0].get("default_branch", ""),
            "ci_bootstrap_status": runs[0].get("ci_bootstrap_status", ""),
            "in_registry": False, "runs": runs, "run_count": len(runs), "stack": "",
            "last_check": checks.get(url),
        })
    return {
        "provenance": "rule_based",
        "registry_path": str(repos_module._registry_path(registry_root)),
        "repositories": rows,
    }


def _last_checks() -> dict[str, dict[str, Any]]:
    """The newest `repository.test` audit line per URL — so a repository an
    operator probed and found gone (deleted on the host, made private) stays
    visibly gone on the next read instead of only in the probe's own popup.
    Derived from the ledger, never stored twice."""
    latest: dict[str, dict[str, Any]] = {}
    for rec in audit_log(limit=100_000, action="repository.test"):  # newest first
        url = rec.get("target", "")
        if url and url not in latest:
            detail = rec.get("detail") or ""
            latest[url] = {
                "at": rec.get("at", ""),
                "reachable": detail == "reachable",
                "detail": detail,
            }
    return latest


def forget(url: str, *, actor: str = "", registry_root: Path | None = None) -> None:
    """Drop a registry entry. Runs that connected it keep their own record;
    the registry only decides what the reconnect chips offer."""
    if not repos_module.forget_repo(url, registry_root):
        raise RepositoryNotFound(f"{url!r} is not in the known-repositories registry")
    audit(actor, "repository.forget", repos_module.normalize_repo_url(url))


def test_connection(url: str, *, actor: str = "") -> dict[str, Any]:
    """An explicit operator probe (`git ls-remote`), audited as one."""
    result = integrations.test_connection(url)
    audit(actor, "repository.test", repos_module.normalize_repo_url(url),
          detail="reachable" if result["reachable"] else result["error"])
    return result
