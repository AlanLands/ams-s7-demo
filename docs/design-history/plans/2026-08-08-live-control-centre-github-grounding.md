# Live Control Centre with GitHub Repo Grounding — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Control Centre's upstream half genuinely live — connect GitHub repos, run real LLM intake analysis / clarification / planning grounded in their content, badged `live_ai` and validated before render.

**Architecture:** Approach A from the spec (`docs/superpowers/specs/2026-08-08-live-control-centre-github-grounding-design.md`): live functions live in a new `s7_delivery/factory/live_intake.py` beside the engine, produce the factory's existing Pydantic shapes, and the engine branches on `run.mode is DemoMode.LIVE` inside `intake_analyse` / `planning_generate`. Repo connect is a shallow clone into the run's artifact tree plus a stored context-pack artifact that becomes the `ref` prompt layer. Simulation mode is untouched.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, `common.llm.complete()` + `PromptLayers`, plain `subprocess` git, vanilla JS UI (no build step), pytest.

## Global Constraints

- **Hard rules 1–2:** all content synthetic MapleSure fiction; no client names anywhere (code, repos, commits, UI).
- **Hard rule 4:** no new dependencies, no CDN, no build step. Plain Python + subprocess git + the existing FastAPI/Pydantic stack.
- **No silent fallback:** a live-mode LLM failure is an error the UI shows (`LLMError` → HTTP 502); a live run never serves seeded content.
- **Provenance discipline:** live artifacts carry `Provenance.LIVE_AI` when `LLM_MODE` ∈ {live, record}, `Provenance.REPLAYED_AI` under replay. Activity events from live calls use `actor_type="live_ai"` (already counted as AI work by `_activity_summary`).
- **All tests offline:** no network, no API key. LLM calls are monkeypatched; git operations use local fixture repos.
- **Run the full suite (`pytest -q`) before every commit.** All existing tests must stay green.
- `CLAUDE.md` and `AGENTS.md` must be updated **in the same commit** when scope/rules/layout change (Task 9).

## File Structure

| File | Responsibility |
|---|---|
| `demo/create_target_repos.py` (create) | Generate the two synthetic MapleSure app trees under `target-apps/`; `--push` publishes them private via `gh` |
| `.gitignore` (modify) | Ignore `target-apps/` |
| `s7_delivery/factory/models.py` (modify) | Add `RepoRecord` |
| `s7_delivery/factory/repos.py` (create) | `clone_repo()` (shallow clone + metadata), `build_context_pack()` (architecture.md + tree + capped excerpts) |
| `s7_delivery/factory/live_intake.py` (create) | Live prompts + strict validators: `run_analysis()`, `run_clarification()`, `run_plan()` |
| `s7_delivery/factory/engine.py` (modify) | `intake_connect_repo()`, `intake_clarify()`, `intake_clarify_answer()`, live branches in `intake_analyse()` / `planning_generate()`, state exposure |
| `s7_delivery/factory/roles.py` (modify) | Permissions `connect_repository`, `ask_clarification` |
| `apps/control/server.py` (modify) | Allow `mode=live`, `LLMError` handler, three new routes |
| `apps/control/static/index.html` (modify) | `Live` option in the environment selector |
| `apps/control/static/app.js` (modify) | Connect-repository card, live clarification modal, live-aware hints |
| `tests/test_target_repos.py`, `tests/test_factory_repos.py`, `tests/test_live_intake.py`, `tests/test_factory_live_engine.py` (create) | Per-task tests, all offline |

---

### Task 1: Target repo generator

Two synthetic MapleSure application trees, generated to `target-apps/` (gitignored), pushed private with `gh` only when `--push` is passed. Generation is pure file-writing so it is fully testable offline.

**Files:**
- Create: `demo/create_target_repos.py`
- Modify: `.gitignore` (add `target-apps/`)
- Test: `tests/test_target_repos.py`

**Interfaces:**
- Produces: `PORTAL_FILES: dict[str, str]`, `API_FILES: dict[str, str]`, `write_repo(name: str, files: dict[str, str], root: Path) -> Path`. Task 2's tests reuse `write_repo` to build clone fixtures.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_target_repos.py
"""The target-repo generator: pure file generation, offline."""
from pathlib import Path

from demo.create_target_repos import API_FILES, PORTAL_FILES, write_repo


def test_write_repo_creates_tree(tmp_path: Path):
    root = write_repo("maplesure-sponsor-portal", PORTAL_FILES, tmp_path)
    assert root == tmp_path / "maplesure-sponsor-portal"
    assert (root / "architecture.md").is_file()
    assert (root / "app.py").is_file()


def test_both_repos_carry_architecture_md_with_scope_exclusions(tmp_path: Path):
    for name, files in (("maplesure-sponsor-portal", PORTAL_FILES),
                        ("maplesure-claims-api", API_FILES)):
        root = write_repo(name, files, tmp_path)
        text = (root / "architecture.md").read_text(encoding="utf-8")
        assert "MapleSure" in text
        # The design-review grounding pattern: what the app is NOT is explicit.
        assert "does not" in text.lower()


def test_portal_lacks_disability_submission(tmp_path: Path):
    """The epic's gap must exist: no disability claim feature in the portal."""
    root = write_repo("maplesure-sponsor-portal", PORTAL_FILES, tmp_path)
    source = "\n".join(
        p.read_text(encoding="utf-8") for p in root.rglob("*.py")
    )
    assert "disability" not in source.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_target_repos.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'demo.create_target_repos'`

- [ ] **Step 3: Write the generator**

`demo/` has no `__init__.py`; add one (empty) so the module imports in tests: `demo/__init__.py`.

```python
# demo/create_target_repos.py
"""Generate the two synthetic MapleSure target-application repos.

Usage:
    python -m demo.create_target_repos            # write trees to target-apps/
    python -m demo.create_target_repos --push     # also create private GitHub
                                                  # repos and push (needs gh auth)

All content is MapleSure fiction (hard rules 1-2). `target-apps/` is
gitignored: the generated repos are standalone, not part of this repo.
The portal deliberately lacks disability claim submission — that is the gap
EPIC-S7-001 fills, so the live analysis has something real to find.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

TARGET_ROOT = Path(__file__).resolve().parent.parent / "target-apps"

PORTAL_FILES: dict[str, str] = {
    "architecture.md": '''# MapleSure SponsorConnect Portal — architecture

The plan-sponsor web portal for MapleSure Insurance (fictional; all data
synthetic). Flask, server-rendered templates, no SPA framework.

## Components
- `app.py` — routes: dashboard, member directory, coverage summary.
- `portal/members.py` — member lookup against the claims API.
- `templates/` — Jinja pages; `static/portal.js` progressive enhancement.

## Data
The portal stores nothing. All member and plan data is read from the
maplesure-claims-api service (`CLAIMS_API_URL`, default
http://localhost:8600). Sessions are cookie-based, server-side.

## What this application does NOT do
- No claim submission of any kind — sponsors are directed to the paper/PDF
  process handled outside the portal.
- No document upload or storage.
- No claim status visibility.
- No direct database access; the claims API is the only backend.
''',
    "README.md": "# MapleSure SponsorConnect Portal\n\nSynthetic demo application. See architecture.md.\n",
    "app.py": '''"""SponsorConnect portal — plan sponsor web UI (synthetic demo app)."""
import os

from flask import Flask, render_template

from portal.members import member_summary, list_members

app = Flask(__name__)
CLAIMS_API_URL = os.environ.get("CLAIMS_API_URL", "http://localhost:8600")


@app.get("/")
def dashboard():
    return render_template("dashboard.html", members=list_members()[:5])


@app.get("/members")
def members():
    return render_template("members.html", members=list_members())


@app.get("/members/<member_id>")
def member(member_id: str):
    return render_template("member.html", member=member_summary(member_id))
''',
    "portal/__init__.py": "",
    "portal/members.py": '''"""Member lookup — reads the claims API; the portal holds no data."""
import os
import urllib.request
import json

API = os.environ.get("CLAIMS_API_URL", "http://localhost:8600")


def list_members() -> list[dict]:
    with urllib.request.urlopen(f"{API}/members") as resp:
        return json.load(resp)


def member_summary(member_id: str) -> dict:
    with urllib.request.urlopen(f"{API}/members/{member_id}") as resp:
        return json.load(resp)
''',
    "templates/base.html": "<!doctype html><html><head><title>SponsorConnect</title></head>\n<body>{% block body %}{% endblock %}</body></html>\n",
    "templates/dashboard.html": "{% extends 'base.html' %}{% block body %}<h1>Sponsor dashboard</h1>\n<p>{{ members|length }} recent members</p>{% endblock %}\n",
    "templates/members.html": "{% extends 'base.html' %}{% block body %}<h1>Member directory</h1>\n<ul>{% for m in members %}<li>{{ m.name }}</li>{% endfor %}</ul>{% endblock %}\n",
    "templates/member.html": "{% extends 'base.html' %}{% block body %}<h1>{{ member.name }}</h1>\n<p>Plan: {{ member.plan_id }}</p>{% endblock %}\n",
    "static/portal.js": "// Progressive enhancement only; the portal works without JS.\ndocument.querySelectorAll('[data-expand]').forEach((n) => {\n  n.addEventListener('click', () => n.classList.toggle('open'));\n});\n",
}

API_FILES: dict[str, str] = {
    "architecture.md": '''# MapleSure Claims API — architecture

The claims intake API for MapleSure Insurance (fictional; all data
synthetic). FastAPI over SQLite.

## Components
- `main.py` — app factory and routes: member lookup, plan lookup, claim list.
- `claims/models.py` — Pydantic models: Member, Plan, Claim.
- `claims/db.py` — SQLite persistence (`claims.db`), schema created on start.

## Data
SQLite, single file. Members belong to a sponsor organization; a sponsor may
only read members of their own plans. Claims are read-only rows loaded from
seed data — there is no claim creation endpoint.

## What this application does NOT do
- No claim submission or mutation endpoints — claims arrive by an offline
  batch load, not through this API.
- No document handling of any kind.
- No claim status workflow; a claim row has a static `state` string.
- No authentication of its own; it trusts the portal's session (demo scope).
''',
    "README.md": "# MapleSure Claims API\n\nSynthetic demo service. See architecture.md.\n",
    "main.py": '''"""MapleSure claims API — synthetic demo service."""
from fastapi import FastAPI, HTTPException

from claims.db import get_member, list_claims, list_members
from claims.models import Claim, Member

app = FastAPI(title="MapleSure Claims API")


@app.get("/members")
def members() -> list[Member]:
    return list_members()


@app.get("/members/{member_id}")
def member(member_id: str) -> Member:
    found = get_member(member_id)
    if found is None:
        raise HTTPException(status_code=404, detail="No such member")
    return found


@app.get("/members/{member_id}/claims")
def claims(member_id: str) -> list[Claim]:
    return list_claims(member_id)
''',
    "claims/__init__.py": "",
    "claims/models.py": '''from pydantic import BaseModel


class Member(BaseModel):
    member_id: str
    name: str
    plan_id: str
    sponsor_org: str


class Plan(BaseModel):
    plan_id: str
    name: str
    sponsor_org: str


class Claim(BaseModel):
    claim_id: str
    member_id: str
    kind: str
    state: str
''',
    "claims/db.py": '''"""SQLite layer. Schema created on import; seed rows are synthetic."""
import sqlite3
from pathlib import Path

from claims.models import Claim, Member

DB_PATH = Path(__file__).resolve().parent.parent / "claims.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS members (member_id TEXT PRIMARY KEY, "
        "name TEXT, plan_id TEXT, sponsor_org TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS claims (claim_id TEXT PRIMARY KEY, "
        "member_id TEXT, kind TEXT, state TEXT)"
    )
    return conn


def list_members() -> list[Member]:
    rows = _conn().execute("SELECT member_id, name, plan_id, sponsor_org FROM members")
    return [Member(member_id=r[0], name=r[1], plan_id=r[2], sponsor_org=r[3]) for r in rows]


def get_member(member_id: str) -> Member | None:
    row = _conn().execute(
        "SELECT member_id, name, plan_id, sponsor_org FROM members WHERE member_id=?",
        (member_id,),
    ).fetchone()
    if row is None:
        return None
    return Member(member_id=row[0], name=row[1], plan_id=row[2], sponsor_org=row[3])


def list_claims(member_id: str) -> list[Claim]:
    rows = _conn().execute(
        "SELECT claim_id, member_id, kind, state FROM claims WHERE member_id=?",
        (member_id,),
    )
    return [Claim(claim_id=r[0], member_id=r[1], kind=r[2], state=r[3]) for r in rows]
''',
}

REPOS = {
    "maplesure-sponsor-portal": PORTAL_FILES,
    "maplesure-claims-api": API_FILES,
}


def write_repo(name: str, files: dict[str, str], root: Path) -> Path:
    repo = root / name
    for rel, content in files.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return repo


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True)


def push_repo(repo: Path) -> None:
    """Create the private GitHub repo and push. Requires `gh auth login`."""
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "Initial synthetic MapleSure demo application")
    subprocess.run(
        ["gh", "repo", "create", repo.name, "--private",
         "--source", str(repo), "--push"],
        check=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--push", action="store_true",
                        help="create private GitHub repos and push")
    args = parser.parse_args(argv)
    for name, files in REPOS.items():
        repo = write_repo(name, files, TARGET_ROOT)
        print(f"wrote {repo}")
        if args.push:
            push_repo(repo)
            print(f"pushed {repo.name} (private)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Add to `.gitignore`:

```
target-apps/
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_target_repos.py -v`
Expected: 3 PASS

- [ ] **Step 5: Full suite, then commit**

```bash
pytest -q
git add demo/__init__.py demo/create_target_repos.py .gitignore tests/test_target_repos.py
git commit -m "feat: synthetic MapleSure target-repo generator"
```

- [ ] **Step 6: Actually create and push the repos (manual, once)**

Run: `python -m demo.create_target_repos --push`
Expected: both repos printed as pushed. Verify: `gh repo view maplesure-sponsor-portal --json visibility` shows `"PRIVATE"`.

---

### Task 2: `RepoRecord` + clone and context pack (`factory/repos.py`)

**Files:**
- Modify: `s7_delivery/factory/models.py` (add `RepoRecord` after `Requirement`, ~line 110)
- Create: `s7_delivery/factory/repos.py`
- Test: `tests/test_factory_repos.py`

**Interfaces:**
- Consumes: `write_repo`, `PORTAL_FILES` from `demo.create_target_repos` (fixture building).
- Produces:
  - `RepoRecord(BaseModel)`: `url: str`, `name: str`, `head_sha: str`, `default_branch: str`, `file_count: int`, `cloned_at: str` (defaults `now_iso()`), `provenance: Provenance = Provenance.HUMAN`
  - `clone_repo(url: str, dest_root: Path) -> RepoRecord` — raises `RepoConnectError` on failure
  - `build_context_pack(repo_dir: Path, name: str, cap_bytes: int = 15000) -> str`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_factory_repos.py
"""Clone + context pack. Offline: fixtures are local git repos."""
import subprocess
from pathlib import Path

import pytest

from demo.create_target_repos import PORTAL_FILES, write_repo
from s7_delivery.factory.repos import RepoConnectError, build_context_pack, clone_repo


def make_fixture_repo(tmp_path: Path) -> Path:
    repo = write_repo("maplesure-sponsor-portal", PORTAL_FILES, tmp_path / "src")
    env_id = ["-c", "user.email=demo@example.invalid", "-c", "user.name=demo"]
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), *env_id, "commit", "-qm", "init"], check=True)
    return repo


def test_clone_repo_records_metadata(tmp_path: Path):
    src = make_fixture_repo(tmp_path)
    rec = clone_repo(str(src), tmp_path / "dest")
    assert rec.name == "maplesure-sponsor-portal"
    assert len(rec.head_sha) == 40
    assert rec.file_count > 5
    assert (tmp_path / "dest" / rec.name / "architecture.md").is_file()


def test_clone_repo_bad_url_raises(tmp_path: Path):
    with pytest.raises(RepoConnectError):
        clone_repo(str(tmp_path / "no-such-repo"), tmp_path / "dest")


def test_context_pack_contains_architecture_tree_and_excerpts(tmp_path: Path):
    src = make_fixture_repo(tmp_path)
    rec = clone_repo(str(src), tmp_path / "dest")
    pack = build_context_pack(tmp_path / "dest" / rec.name, rec.name)
    assert "What this application does NOT do" in pack   # architecture.md verbatim
    assert "portal/members.py" in pack                    # file tree
    assert "def list_members" in pack                     # source excerpt


def test_context_pack_respects_cap(tmp_path: Path):
    src = make_fixture_repo(tmp_path)
    rec = clone_repo(str(src), tmp_path / "dest")
    pack = build_context_pack(tmp_path / "dest" / rec.name, rec.name, cap_bytes=2000)
    assert len(pack.encode("utf-8")) <= 4000  # cap governs excerpts; header+tree small
    assert "[truncated" in pack
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_factory_repos.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 's7_delivery.factory.repos'`

- [ ] **Step 3: Add `RepoRecord` to models and write `repos.py`**

In `s7_delivery/factory/models.py`, after the `Requirement` class:

```python
class RepoRecord(BaseModel):
    """A connected target repository — cloned at connect time, then local."""

    url: str
    name: str
    head_sha: str
    default_branch: str
    file_count: int
    cloned_at: str = Field(default_factory=now_iso)
    provenance: Provenance = Provenance.HUMAN
```

```python
# s7_delivery/factory/repos.py
"""Repo connect: shallow clone + context pack (spec §2).

The pack is extraction, not generation — architecture.md verbatim, a file
tree, and size-capped source excerpts. It becomes the `ref` layer of every
live prompt, so after connect no live call needs the network for repo
content (hard rule 5).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from s7_delivery.factory.models import RepoRecord

# Extensions worth excerpting, in priority order after architecture.md.
_SOURCE_EXTS = (".py", ".js", ".html", ".md", ".sql", ".toml", ".cfg")
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv"}


class RepoConnectError(Exception):
    """Clone failed: bad URL, no access, no network."""


def _git(cwd: Path | None, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *(["-C", str(cwd)] if cwd else []), *args],
            check=True, capture_output=True, text=True, timeout=120,
        )
    except subprocess.CalledProcessError as exc:
        raise RepoConnectError(exc.stderr.strip() or str(exc)) from exc
    except subprocess.TimeoutExpired as exc:
        raise RepoConnectError(f"git timed out: {args}") from exc
    return out.stdout.strip()


def _repo_files(repo_dir: Path) -> list[Path]:
    return sorted(
        p for p in repo_dir.rglob("*")
        if p.is_file() and not any(part in _SKIP_DIRS for part in p.parts)
    )


def clone_repo(url: str, dest_root: Path) -> RepoRecord:
    name = url.rstrip("/").removesuffix(".git").rsplit("/", 1)[-1]
    dest = dest_root / name
    if dest.exists():
        raise RepoConnectError(f"{name} is already connected")
    dest_root.mkdir(parents=True, exist_ok=True)
    _git(None, "clone", "--depth", "1", url, str(dest))
    return RepoRecord(
        url=url,
        name=name,
        head_sha=_git(dest, "rev-parse", "HEAD"),
        default_branch=_git(dest, "rev-parse", "--abbrev-ref", "HEAD"),
        file_count=len(_repo_files(dest)),
    )


def build_context_pack(repo_dir: Path, name: str, cap_bytes: int = 15000) -> str:
    """Architecture.md verbatim + file tree + capped source excerpts."""
    files = _repo_files(repo_dir)
    parts: list[str] = [f"# Repository: {name}\n"]

    arch = repo_dir / "architecture.md"
    if arch.is_file():
        parts.append("## architecture.md (verbatim)\n\n"
                     + arch.read_text(encoding="utf-8"))

    tree = "\n".join(str(p.relative_to(repo_dir)) for p in files)
    parts.append(f"## File tree ({len(files)} files)\n\n{tree}")

    budget = cap_bytes
    excerpts: list[str] = []
    candidates = [
        p for p in files
        if p.suffix in _SOURCE_EXTS and p.name != "architecture.md"
    ]
    for path in candidates:
        if budget <= 0:
            excerpts.append(f"### [truncated — excerpt budget of {cap_bytes} bytes reached]")
            break
        text = path.read_text(encoding="utf-8", errors="replace")
        take = text.encode("utf-8")[:budget].decode("utf-8", errors="ignore")
        note = "" if take == text else "\n[truncated]"
        excerpts.append(f"### {path.relative_to(repo_dir)}\n```\n{take}{note}\n```")
        budget -= len(take.encode("utf-8"))
    parts.append("## Source excerpts\n\n" + "\n\n".join(excerpts))
    return "\n\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_factory_repos.py -v`
Expected: 4 PASS. (Note: `git clone --depth 1` on a local path prints a harmless "--depth is ignored in local clones" warning — fine.)

- [ ] **Step 5: Full suite, then commit**

```bash
pytest -q
git add s7_delivery/factory/models.py s7_delivery/factory/repos.py tests/test_factory_repos.py
git commit -m "feat: repo connect — shallow clone and context pack"
```

---

### Task 3: Engine action `intake_connect_repo` + route + state

**Files:**
- Modify: `s7_delivery/factory/engine.py` (new method in the intake section, after `intake_upload_document`)
- Modify: `s7_delivery/factory/roles.py` (add permission)
- Modify: `apps/control/server.py` (new route)
- Test: `tests/test_factory_live_engine.py` (new file — this task's tests plus later live-engine tests)

**Interfaces:**
- Consumes: `clone_repo`, `build_context_pack`, `RepoConnectError` from Task 2.
- Produces: `Engine.intake_connect_repo(role: Role, url: str) -> None`; run state gains `intake["repos"]: list[dict]`; artifacts `intake/repos.json` and `intake/context/<name>.md`; permission name `connect_repository`; route `POST /api/runs/{run_id}/intake/connect-repo` body `{role, url}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_factory_live_engine.py
"""Live-mode engine behaviour. All offline; LLM and git are local/fake."""
import subprocess
from pathlib import Path

import pytest

from demo.create_target_repos import PORTAL_FILES, write_repo
from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, Role


def fixture_repo(tmp_path: Path, name: str = "maplesure-sponsor-portal") -> Path:
    repo = write_repo(name, PORTAL_FILES, tmp_path / "src")
    ident = ["-c", "user.email=demo@example.invalid", "-c", "user.name=demo"]
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), *ident, "commit", "-qm", "init"], check=True)
    return repo


def test_connect_repo_records_and_builds_pack(tmp_path: Path):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    src = fixture_repo(tmp_path)
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(src))
    state = eng.state()
    repos = state["intake"]["repos"]
    assert [r["name"] for r in repos] == ["maplesure-sponsor-portal"]
    assert repos[0]["provenance"] == "human"
    assert eng.store.exists("intake", "context", "maplesure-sponsor-portal.md")
    # Provenance ledger carries the connect event.
    assert any(r["artifact_type"] == "repository" for r in state["provenance_ledger"])


def test_connect_repo_bad_url_is_engine_error(tmp_path: Path):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="clone"):
        eng.intake_connect_repo(Role.DELIVERY_LEAD, str(tmp_path / "nope"))
    assert eng.state()["intake"]["repos"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_factory_live_engine.py -v`
Expected: FAIL with `AttributeError: 'Engine' object has no attribute 'intake_connect_repo'`

- [ ] **Step 3: Implement engine method, permission, route**

`s7_delivery/factory/roles.py` — in `PERMISSIONS` under `# intake`:

```python
    "connect_repository": {Role.PRODUCT_ANALYST, Role.DELIVERY_LEAD, Role.ENGINEERING_LEAD},
```

`s7_delivery/factory/engine.py` — after `intake_upload_document` (~line 430):

```python
    def intake_connect_repo(self, role: Role, url: str) -> None:
        """Connect a target repository: shallow clone under the run's own
        artifact tree, record metadata, store the context pack that grounds
        every live call (spec: live-control-centre §2)."""
        roles.require("connect_repository", role)
        from s7_delivery.factory.repos import RepoConnectError, build_context_pack, clone_repo

        try:
            rec = clone_repo(url, self.store.path("repos"))
        except RepoConnectError as exc:
            raise EngineError(f"Repository clone failed: {exc}") from exc

        repos = self.store.read_json_or([], "intake", "repos.json")
        repos.append(rec.model_dump(mode="json"))
        self.store.write_json(repos, "intake", "repos.json")

        pack = build_context_pack(self.store.path("repos", rec.name), rec.name)
        self.store.write_text(pack, "intake", "context", f"{rec.name}.md")

        self._record(
            artifact_id=f"REPO-{rec.name}", artifact_type="repository",
            payload=rec, author=role.value, stage=Stage.INTAKE,
            action="connect-repo", outcome="created",
        )
        self._activity(
            stage=Stage.INTAKE, actor=role.value, actor_type="human",
            workflow="connect-repository", artifact=rec.name,
            outcome="connected",
            details=f"{rec.url} @ {rec.head_sha[:10]}, {rec.file_count} files",
        )

    def _connected_repos(self) -> list[dict]:
        return self.store.read_json_or([], "intake", "repos.json")

    def _context_packs(self) -> dict[str, str]:
        return {
            r["name"]: self.store.path("intake", "context", f"{r['name']}.md")
            .read_text(encoding="utf-8")
            for r in self._connected_repos()
        }
```

In `Engine.state()`, extend the `"intake"` dict:

```python
            "intake": {
                "requirement": self.store.read_json_or(None, "intake", "requirement.json"),
                "analysis": self.store.read_json_or(None, "intake", "analysis.json"),
                "epic": self.store.read_json_or(None, "intake", "epic.json"),
                "repos": self.store.read_json_or([], "intake", "repos.json"),
                "clarifications": self.store.read_json_or(None, "intake", "clarifications.json"),
            },
```

(`clarifications` lands in Task 6; exposing the key now keeps the shape stable.)

`apps/control/server.py` — after the upload-document routes:

```python
class ConnectRepoBody(BaseModel):
    role: str
    url: str


@app.post("/api/runs/{run_id}/intake/connect-repo")
def post_intake_connect_repo(run_id: str, body: ConnectRepoBody) -> dict:
    eng = _engine(run_id)
    eng.intake_connect_repo(_role(body.role), body.url)
    return eng.state()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_factory_live_engine.py -v`
Expected: 2 PASS

- [ ] **Step 5: Full suite, then commit**

```bash
pytest -q
git add s7_delivery/factory/engine.py s7_delivery/factory/roles.py apps/control/server.py tests/test_factory_live_engine.py
git commit -m "feat: intake_connect_repo engine action, permission and route"
```

---

### Task 4: `live_intake.py` — live analysis call + validator

**Files:**
- Create: `s7_delivery/factory/live_intake.py`
- Test: `tests/test_live_intake.py`

**Interfaces:**
- Consumes: `complete`, `parse_json_response`, `LLMError` from `common.llm`; `PromptLayers` from `common.prompt`; `IntakeAnalysis`, `Provenance` from `factory.models`.
- Produces:
  - `provenance_now() -> Provenance` (LIVE_AI for live/record, REPLAYED_AI otherwise)
  - `run_analysis(requirement: dict, packs: dict[str, str], transcript: list[dict]) -> tuple[IntakeAnalysis, dict]` — the dict is the usage block (`input_tokens`/`output_tokens`, possibly None values)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_live_intake.py
"""Live prompt validators, exercised against canned model JSON. Offline."""
import json

import pytest

from common.llm import LLMError
from s7_delivery.factory import live_intake

REQUIREMENT = {
    "request_id": "REQ-2026-114",
    "title": "Online disability claim submission for plan sponsors",
    "description": "Sponsors need to submit disability claims online.",
}
PACKS = {
    "maplesure-sponsor-portal": "# Repository: maplesure-sponsor-portal\n...",
    "maplesure-claims-api": "# Repository: maplesure-claims-api\n...",
}

GOOD_ANALYSIS = {
    "problem_understood": True,
    "business_impact": "Sponsors abandon the paper process; intake rekeys forms.",
    "affected_applications": [
        "maplesure-sponsor-portal",
        "maplesure-claims-api",
        "Policy system of record (externally owned)",
    ],
    "stakeholders": ["Group Benefits Operations", "Plan sponsor administrators"],
    "dependencies": ["Claims API has no claim-creation endpoint today"],
    "risks": ["Portal has no upload capability at all"],
    "clarification_questions": ["Which attachments are mandatory at submission?"],
    "assumptions": ["Existing portal authentication applies unchanged"],
    "business_rules": [
        {"rule_id": "BR-01", "text": "A sponsor may only submit for members of their own plans."}
    ],
    "risk_register": [
        {"text": "Claims API is read-only today", "severity": "high"}
    ],
    "confidence": 82,
}


def fake_complete(response: dict):
    def _fake(prompt, *, json_mode=False, cache_key=None, usage_out=None, **kw):
        if usage_out is not None:
            usage_out.update({"input_tokens": 1200, "output_tokens": 400})
        return json.dumps(response)
    return _fake


def test_run_analysis_validates_and_badges(monkeypatch):
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_ANALYSIS))
    monkeypatch.setenv("LLM_MODE", "live")
    analysis, usage = live_intake.run_analysis(REQUIREMENT, PACKS, [])
    assert analysis.provenance.value == "live_ai"
    assert analysis.affected_applications[0] == "maplesure-sponsor-portal"
    assert usage["input_tokens"] == 1200


def test_run_analysis_replay_mode_badges_replayed(monkeypatch):
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_ANALYSIS))
    monkeypatch.setenv("LLM_MODE", "replay")
    analysis, _ = live_intake.run_analysis(REQUIREMENT, PACKS, [])
    assert analysis.provenance.value == "replayed_ai"


def test_run_analysis_rejects_unknown_application(monkeypatch):
    bad = dict(GOOD_ANALYSIS, affected_applications=["some-invented-repo"])
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="affected_applications"):
        live_intake.run_analysis(REQUIREMENT, PACKS, [])


def test_run_analysis_rejects_missing_rule_ids(monkeypatch):
    bad = dict(GOOD_ANALYSIS, business_rules=[{"text": "no id"}])
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="business_rules"):
        live_intake.run_analysis(REQUIREMENT, PACKS, [])


def test_run_analysis_requires_connected_repos():
    with pytest.raises(LLMError, match="[Cc]onnect"):
        live_intake.run_analysis(REQUIREMENT, {}, [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_live_intake.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 's7_delivery.factory.live_intake'`

- [ ] **Step 3: Write `live_intake.py` (analysis half)**

```python
# s7_delivery/factory/live_intake.py
"""Live LLM calls for the Control Centre's upstream half (spec §3-§6).

Every function here: builds a `PromptLayers` whose `ref` layer is the
connected repos' context packs, calls `common.llm.complete` in JSON mode,
and validates the response strictly into the factory's own Pydantic shapes.
Reject, don't repair: a malformed response raises `LLMError`, and the engine
surfaces it — a live run never silently serves seeded content.
"""
from __future__ import annotations

import hashlib
import json
import os

from common.llm import LLMError, complete, parse_json_response
from common.prompt import PromptLayers
from s7_delivery.factory.models import IntakeAnalysis, Provenance

MAX_CLARIFICATION_ROUNDS = 2

RULES = (
    "You are an AI delivery assistant for MapleSure Insurance, a fictional "
    "insurer in a tabletop exercise. All data is synthetic. Answer with "
    "structured JSON only, and never invent facts the input does not support."
)

ANALYSIS_ROLE = (
    "Your role is intake analysis: read a business change request against the "
    "connected application repositories and extract what a delivery lead "
    "needs — impact, affected applications, stakeholders, dependencies, "
    "risks, open questions, assumptions and business rules. Ground every "
    "claim in the requirement or the repository context; where the "
    "repositories show a capability is absent, say so as a dependency or "
    "risk, not a guess."
)


def provenance_now() -> Provenance:
    mode = os.environ.get("LLM_MODE", "replay").lower()
    return Provenance.LIVE_AI if mode in {"live", "record"} else Provenance.REPLAYED_AI


def _ref(requirement: dict, packs: dict[str, str]) -> str:
    packs_text = "\n\n---\n\n".join(packs[name] for name in sorted(packs))
    return (
        f"The connected application repositories:\n\n{packs_text}\n\n---\n\n"
        f"The change request, verbatim:\n\n{json.dumps(requirement, indent=2)}"
    )


def _transcript_text(transcript: list[dict]) -> str:
    if not transcript:
        return "(none yet)"
    return "\n".join(f"{t['role']}: {t['text']}" for t in transcript)


def _cache_digest(*parts: str) -> str:
    return hashlib.sha256("\x1e".join(parts).encode("utf-8")).hexdigest()[:16]


def _call(*, role: str, ref: str, task: str, beat: str, key_material: str) -> tuple[dict, dict]:
    usage: dict = {}
    response = complete(
        PromptLayers(rules=RULES, role=role, ref=ref, task=task),
        json_mode=True,
        cache_key=f"s7_factory_{beat}:{_cache_digest(key_material)}",
        usage_out=usage,
    )
    return parse_json_response(response), usage


_ANALYSIS_SHAPE = """{
  "problem_understood": true,
  "business_impact": "<one paragraph>",
  "affected_applications": ["<connected repository name, or an external system suffixed ' (externally owned)'>"],
  "stakeholders": ["<who>"],
  "dependencies": ["<what this depends on, grounded in the repositories>"],
  "risks": ["<risk>"],
  "clarification_questions": ["<open question for the SME>"],
  "assumptions": ["<assumption carried>"],
  "business_rules": [{"rule_id": "BR-<n>", "text": "<rule in the requirement's words>"}],
  "risk_register": [{"text": "<risk>", "severity": "high|medium|low"}],
  "confidence": <0-100 self-assessment>
}"""


def run_analysis(
    requirement: dict, packs: dict[str, str], transcript: list[dict]
) -> tuple[IntakeAnalysis, dict]:
    if not packs:
        raise LLMError(
            "Live analysis needs at least one connected repository — connect "
            "the target repos first (grounding is the point)."
        )
    task = f"""Clarification conversation so far:
{_transcript_text(transcript)}

Analyse the change request against the connected repositories. Return JSON
exactly matching:
{_ANALYSIS_SHAPE}"""
    data, usage = _call(
        role=ANALYSIS_ROLE,
        ref=_ref(requirement, packs),
        task=task,
        beat="analysis",
        # Pack content is in the key: a repo update honestly misses the cache.
        key_material=json.dumps(requirement, sort_keys=True)
        + "".join(packs[k] for k in sorted(packs))
        + json.dumps(transcript, sort_keys=True),
    )
    return _validate_analysis(data, set(packs)), usage


def _validate_analysis(data: dict, repo_names: set[str]) -> IntakeAnalysis:
    apps = data.get("affected_applications")
    if not isinstance(apps, list) or not apps:
        raise LLMError("analysis has no affected_applications")
    grounded = [a for a in apps if a in repo_names]
    if not grounded:
        raise LLMError(
            "affected_applications names no connected repository — "
            f"got {apps}, connected {sorted(repo_names)}"
        )
    for a in apps:
        if a not in repo_names and not a.endswith("(externally owned)"):
            raise LLMError(
                f"affected_applications entry {a!r} is neither a connected "
                "repository nor marked '(externally owned)'"
            )
    for rule in data.get("business_rules", []):
        if not (isinstance(rule, dict) and rule.get("rule_id") and rule.get("text")):
            raise LLMError(f"business_rules entry missing rule_id/text: {rule!r}")
    for row in data.get("risk_register", []):
        if not (isinstance(row, dict) and row.get("text")
                and row.get("severity") in {"high", "medium", "low"}):
            raise LLMError(f"risk_register entry malformed: {row!r}")
    _excluded = {"provenance", "generated_at"}  # ours to set, not the model's
    try:
        return IntakeAnalysis(
            **{k: v for k, v in data.items()
               if k in IntakeAnalysis.model_fields and k not in _excluded},
            provenance=provenance_now(),
        )
    except Exception as exc:  # pydantic ValidationError → one LLMError vocabulary
        raise LLMError(f"analysis failed validation: {exc}") from exc
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_live_intake.py -v`
Expected: 5 PASS

- [ ] **Step 5: Full suite, then commit**

```bash
pytest -q
git add s7_delivery/factory/live_intake.py tests/test_live_intake.py
git commit -m "feat: live intake analysis call with strict validation"
```

---

### Task 5: Engine live branch for `intake_analyse` + live run creation

**Files:**
- Modify: `s7_delivery/factory/engine.py` (`intake_analyse`)
- Modify: `apps/control/server.py` (remove the live-mode 400; add `LLMError` handler)
- Test: `tests/test_factory_live_engine.py` (extend)

**Interfaces:**
- Consumes: `live_intake.run_analysis` (Task 4), `_connected_repos`/`_context_packs` (Task 3).
- Produces: live `intake_analyse` writing `intake/analysis.json` with `provenance: "live_ai"`; `POST /api/runs {"mode": "live"}` succeeds; `LLMError` → HTTP 502.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_factory_live_engine.py`)

```python
from common.llm import LLMError
from s7_delivery.factory import live_intake
from s7_delivery.factory.models import IntakeAnalysis, Provenance


def _fake_analysis() -> IntakeAnalysis:
    return IntakeAnalysis(
        problem_understood=True,
        business_impact="impact",
        affected_applications=["maplesure-sponsor-portal"],
        stakeholders=["ops"], dependencies=["dep"], risks=["risk"],
        clarification_questions=["q1"], assumptions=["a1"],
        business_rules=[{"rule_id": "BR-01", "text": "rule"}],
        risk_register=[{"text": "r", "severity": "high"}],
        confidence=80, provenance=Provenance.LIVE_AI,
    )


def _live_engine_with_repo(tmp_path, monkeypatch):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    src = fixture_repo(tmp_path)
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(src))
    return eng


def test_live_analyse_calls_model_and_badges(tmp_path, monkeypatch):
    eng = _live_engine_with_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(
        live_intake, "run_analysis",
        lambda req, packs, transcript: (_fake_analysis(), {"input_tokens": 10, "output_tokens": 5}),
    )
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    analysis = eng.state()["intake"]["analysis"]
    assert analysis["provenance"] == "live_ai"
    events = eng.state()["activity"]
    assert any(e["actor_type"] == "live_ai" and e["workflow"] == "intake-analysis"
               for e in events)


def test_live_analyse_without_repos_is_an_error(tmp_path):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="[Cc]onnect"):
        eng.intake_analyse(Role.PRODUCT_ANALYST)
    assert eng.state()["intake"]["analysis"] is None


def test_live_analyse_llm_failure_leaves_state_unchanged(tmp_path, monkeypatch):
    eng = _live_engine_with_repo(tmp_path, monkeypatch)
    def boom(req, packs, transcript):
        raise LLMError("model returned garbage")
    monkeypatch.setattr(live_intake, "run_analysis", boom)
    with pytest.raises(LLMError):
        eng.intake_analyse(Role.PRODUCT_ANALYST)
    assert eng.state()["intake"]["analysis"] is None  # no silent fallback


def test_simulation_mode_never_touches_live(tmp_path, monkeypatch):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path / "runs")
    def forbidden(*a, **kw):
        raise AssertionError("live path called in simulation mode")
    monkeypatch.setattr(live_intake, "run_analysis", forbidden)
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    assert eng.state()["intake"]["analysis"]["provenance"] == "simulated"
```

And an API-level test appended to `tests/test_control_api.py` (follow that file's existing client fixture pattern):

```python
def test_create_live_run_allowed(client):
    resp = client.post("/api/runs", json={"mode": "live"})
    assert resp.status_code == 200
    assert resp.json()["run"]["mode"] == "live"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_factory_live_engine.py tests/test_control_api.py -v`
Expected: new tests FAIL (`intake_analyse` writes seeded analysis regardless of mode; live run creation returns 400).

- [ ] **Step 3: Implement**

`s7_delivery/factory/engine.py` — replace `intake_analyse` with:

```python
    def intake_analyse(self, role: Role) -> None:
        roles.require("run_intake_analysis", role)
        self._stage_in_progress(Stage.INTAKE)
        if self.run().mode is DemoMode.LIVE:
            self._intake_analyse_live()
            return
        analysis = seed.ANALYSIS.model_copy(update={"generated_at": now_iso()})
        self.store.write_json(analysis, "intake", "analysis.json")
        self._record(
            artifact_id="ANL-001", artifact_type="intake_analysis",
            payload=analysis, author="intake-analysis (simulated)",
            stage=Stage.INTAKE, action="analyse",
            outcome="created", inputs=[seed.REQUIREMENT.request_id],
        )
        self._activity(
            stage=Stage.INTAKE, actor="intake-analysis", actor_type="simulation",
            workflow="intake-analysis", artifact="ANL-001", duration_s=6.0,
            outcome="created", details="requirement analysed; open questions surfaced",
        )

    def _intake_analyse_live(self) -> None:
        """The live path: real model call over the connected repos' context.
        Raises (never falls back) on failure — CLAUDE.md § Staged output."""
        import time

        from s7_delivery.factory import live_intake

        packs = self._context_packs()
        if not packs:
            raise EngineError(
                "Live analysis needs a connected repository — use "
                "'Connect repository' first."
            )
        requirement = self.store.read_json("intake", "requirement.json")
        transcript = (self.store.read_json_or({}, "intake", "clarifications.json")
                      .get("transcript", []))
        t0 = time.monotonic()
        analysis, usage = live_intake.run_analysis(requirement, packs, transcript)
        self.store.write_json(analysis, "intake", "analysis.json")
        repo_ids = [f"REPO-{name}" for name in sorted(packs)]
        self._record(
            artifact_id="ANL-001", artifact_type="intake_analysis",
            payload=analysis, author="intake-analysis (live)",
            stage=Stage.INTAKE, action="analyse", outcome="created",
            inputs=[requirement["request_id"], *repo_ids],
        )
        self._activity(
            stage=Stage.INTAKE, actor="intake-analysis", actor_type="live_ai",
            workflow="intake-analysis", artifact="ANL-001",
            duration_s=round(time.monotonic() - t0, 2), outcome="created",
            details=f"in={usage.get('input_tokens')} out={usage.get('output_tokens')} tokens",
        )
```

`apps/control/server.py`:

1. Delete the `if mode is DemoMode.LIVE: raise HTTPException(...)` block in `post_runs`.
2. Add next to the other exception handlers:

```python
from common.llm import LLMError


@app.exception_handler(LLMError)
async def _llm_error(_req: Any, exc: LLMError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_factory_live_engine.py tests/test_control_api.py -v`
Expected: PASS

- [ ] **Step 5: Full suite, then commit**

```bash
pytest -q
git add s7_delivery/factory/engine.py apps/control/server.py tests/test_factory_live_engine.py tests/test_control_api.py
git commit -m "feat: live intake analysis in the engine; live runs creatable"
```

---

### Task 6: Live clarification loop

**Files:**
- Modify: `s7_delivery/factory/live_intake.py` (add `run_clarification`)
- Modify: `s7_delivery/factory/engine.py` (add `intake_clarify`, `intake_clarify_answer`)
- Modify: `s7_delivery/factory/roles.py` (add `ask_clarification`)
- Modify: `apps/control/server.py` (two routes)
- Test: `tests/test_live_intake.py`, `tests/test_factory_live_engine.py` (extend)

**Interfaces:**
- Produces:
  - `live_intake.run_clarification(requirement: dict, packs: dict[str, str], transcript: list[dict]) -> tuple[list[str], dict]` — 1–4 questions + usage; raises `LLMError` past the cap or on bad shape.
  - `Engine.intake_clarify(role)` — model asks; questions stored.
  - `Engine.intake_clarify_answer(role, answers: list[str])` — answers recorded into the transcript.
  - Artifact `intake/clarifications.json`: `{"transcript": [{"role": "assistant"|"user", "text": str}], "pending": [str], "rounds_used": int, "max_rounds": 2}`
  - Routes: `POST .../intake/clarify` `{role}`; `POST .../intake/clarify-answer` `{role, answers}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_live_intake.py`:

```python
GOOD_QUESTIONS = {"questions": [
    "Which attachments are mandatory at submission time?",
    "What are the authoritative claim status values?",
]}


def test_run_clarification_returns_questions(monkeypatch):
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_QUESTIONS))
    questions, usage = live_intake.run_clarification(REQUIREMENT, PACKS, [])
    assert len(questions) == 2
    assert usage["output_tokens"] == 400


def test_run_clarification_rejects_too_many(monkeypatch):
    monkeypatch.setattr(live_intake, "complete",
                        fake_complete({"questions": ["q"] * 6}))
    with pytest.raises(LLMError, match="1-4"):
        live_intake.run_clarification(REQUIREMENT, PACKS, [])


def test_run_clarification_enforces_round_cap(monkeypatch):
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_QUESTIONS))
    transcript = [
        {"role": "assistant", "text": "q1"}, {"role": "user", "text": "a1"},
        {"role": "assistant", "text": "q2"}, {"role": "user", "text": "a2"},
    ]
    with pytest.raises(LLMError, match="cap"):
        live_intake.run_clarification(REQUIREMENT, PACKS, transcript)
```

Append to `tests/test_factory_live_engine.py`:

```python
def test_clarify_roundtrip(tmp_path, monkeypatch):
    eng = _live_engine_with_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(
        live_intake, "run_clarification",
        lambda req, packs, transcript: (["Which attachments are mandatory?"], {}),
    )
    eng.intake_clarify(Role.PRODUCT_ANALYST)
    clar = eng.state()["intake"]["clarifications"]
    assert clar["pending"] == ["Which attachments are mandatory?"]
    assert clar["rounds_used"] == 1

    eng.intake_clarify_answer(Role.PRODUCT_ANALYST, ["Employer statement only."])
    clar = eng.state()["intake"]["clarifications"]
    assert clar["pending"] == []
    assert clar["transcript"][-1]["role"] == "user"
    assert "Employer statement" in clar["transcript"][-1]["text"]


def test_clarify_in_simulation_mode_is_an_error(tmp_path):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="live"):
        eng.intake_clarify(Role.PRODUCT_ANALYST)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_live_intake.py tests/test_factory_live_engine.py -v`
Expected: new tests FAIL (`run_clarification` / `intake_clarify` missing)

- [ ] **Step 3: Implement**

`live_intake.py` — append:

```python
CLARIFY_ROLE = (
    "Your role is a product analyst preparing a change request for delivery: "
    "ask only the clarifying questions whose answers would materially change "
    "the analysis or the plan. Most requests need one short round, not an "
    "interrogation."
)


def run_clarification(
    requirement: dict, packs: dict[str, str], transcript: list[dict]
) -> tuple[list[str], dict]:
    if not packs:
        raise LLMError("Live clarification needs a connected repository.")
    rounds_used = sum(1 for t in transcript if t["role"] == "assistant")
    if rounds_used >= MAX_CLARIFICATION_ROUNDS:
        raise LLMError(
            f"Clarification cap reached ({MAX_CLARIFICATION_ROUNDS} rounds) — "
            "answer what is open or run the analysis with assumptions."
        )
    task = f"""Clarification conversation so far:
{_transcript_text(transcript)}

Ask the 1 to 4 clarifying questions (one topic each) whose answers would most
change the delivery plan. Return JSON exactly matching:
{{"questions": ["<question>"]}}"""
    data, usage = _call(
        role=CLARIFY_ROLE,
        ref=_ref(requirement, packs),
        task=task,
        beat="clarify",
        key_material=json.dumps(requirement, sort_keys=True)
        + json.dumps(transcript, sort_keys=True),
    )
    questions = [str(q).strip() for q in data.get("questions", []) if str(q).strip()]
    if not 1 <= len(questions) <= 4:
        raise LLMError(f"expected 1-4 clarifying questions, got {len(questions)}")
    return questions, usage
```

`roles.py` — under `# intake`:

```python
    "ask_clarification": {Role.PRODUCT_ANALYST, Role.DELIVERY_LEAD},
```

`engine.py` — after `_intake_analyse_live`:

```python
    def _clarifications(self) -> dict:
        return self.store.read_json_or(
            {"transcript": [], "pending": [], "rounds_used": 0,
             "max_rounds": 2},
            "intake", "clarifications.json",
        )

    def intake_clarify(self, role: Role) -> None:
        """Live mode only: the model asks its clarifying questions."""
        roles.require("ask_clarification", role)
        if self.run().mode is not DemoMode.LIVE:
            raise EngineError("AI clarification runs in live mode only")
        import time

        from s7_delivery.factory import live_intake

        clar = self._clarifications()
        if clar["pending"]:
            raise EngineError("Answer the open questions before asking again")
        requirement = self.store.read_json("intake", "requirement.json")
        t0 = time.monotonic()
        questions, usage = live_intake.run_clarification(
            requirement, self._context_packs(), clar["transcript"]
        )
        clar["transcript"].append({"role": "assistant", "text": "\n".join(questions)})
        clar["pending"] = questions
        clar["rounds_used"] = sum(
            1 for t in clar["transcript"] if t["role"] == "assistant"
        )
        self.store.write_json(clar, "intake", "clarifications.json")
        self._activity(
            stage=Stage.INTAKE, actor="intake-analysis", actor_type="live_ai",
            workflow="clarification", duration_s=round(time.monotonic() - t0, 2),
            outcome="asked", details=f"{len(questions)} questions; "
            f"in={usage.get('input_tokens')} out={usage.get('output_tokens')} tokens",
        )

    def intake_clarify_answer(self, role: Role, answers: list[str]) -> None:
        roles.require("ask_clarification", role)
        clar = self._clarifications()
        if not clar["pending"]:
            raise EngineError("There are no open questions to answer")
        if len(answers) != len(clar["pending"]):
            raise EngineError(
                f"Expected {len(clar['pending'])} answers, got {len(answers)}"
            )
        joined = "\n".join(
            f"Q: {q}\nA: {a.strip() or '(no answer — make a stated assumption)'}"
            for q, a in zip(clar["pending"], answers, strict=True)
        )
        clar["transcript"].append({"role": "user", "text": joined})
        clar["pending"] = []
        self.store.write_json(clar, "intake", "clarifications.json")
        self._activity(
            stage=Stage.INTAKE, actor=role.value, actor_type="human",
            workflow="clarification", outcome="answered",
            details=f"{len(answers)} answers recorded",
        )
```

`server.py`:

```python
@app.post("/api/runs/{run_id}/intake/clarify")
def post_intake_clarify(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_clarify(_role(body.role))
    return eng.state()


class ClarifyAnswerBody(BaseModel):
    role: str
    answers: list[str]


@app.post("/api/runs/{run_id}/intake/clarify-answer")
def post_intake_clarify_answer(run_id: str, body: ClarifyAnswerBody) -> dict:
    eng = _engine(run_id)
    eng.intake_clarify_answer(_role(body.role), body.answers)
    return eng.state()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_live_intake.py tests/test_factory_live_engine.py -v`
Expected: PASS

- [ ] **Step 5: Full suite, then commit**

```bash
pytest -q
git add s7_delivery/factory/live_intake.py s7_delivery/factory/engine.py s7_delivery/factory/roles.py apps/control/server.py tests/test_live_intake.py tests/test_factory_live_engine.py
git commit -m "feat: live clarification loop, capped and transcripted"
```

---

### Task 7: Live planning

**Files:**
- Modify: `s7_delivery/factory/live_intake.py` (add `run_plan` + validator)
- Modify: `s7_delivery/factory/engine.py` (live branch in `planning_generate`)
- Test: `tests/test_live_intake.py`, `tests/test_factory_live_engine.py` (extend)

**Interfaces:**
- Consumes: `seed.TEAMS` (the fixed team roster), connected repo names, the stored analysis (business-rule ids are the coverage targets), the epic record, the clarification transcript.
- Produces: `live_intake.run_plan(epic: dict, analysis: dict, packs: dict[str, str], transcript: list[dict], teams: list[str]) -> tuple[list[Story], dict, dict, dict]` — stories, confidence dict, rationale dict, usage. Engine writes the same artifacts the simulated path writes (`stories.json`, `confidence.json`, `rationale.json`) so sign-off, `_seed_tasks` and every renderer work unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_live_intake.py`:

```python
GOOD_STORY = {
    "story_id": "US-001",
    "title": "Claim submission record",
    "purpose": "Persist the submission as a first-class record.",
    "accountable_team": "Data Team",
    "target_application": "maplesure-claims-api",
    "target_repository": "maplesure-claims-api",
    "target_component": "claims data model",
    "acceptance_criteria": [
        {"ac_id": "US-001-AC1", "text": "A submission persists across a dropped session."},
        {"ac_id": "US-001-AC2", "text": "Every submission carries an audit trail."},
    ],
    "dependencies": [],
    "impacts": ["claims/db.py schema"],
    "feature_flag": {"name": "sponsor_claim_submission"},
    "rollback_plan": {"method": "disable feature flag; additive schema"},
    "task_type": "feature",
    "estimate": 5,
    "sprint": 1,
    "traces_to": ["BR-01"],
}

GOOD_PLAN = {
    "stories": [GOOD_STORY],
    "confidence": 78,
    "rationale": "Data model first; the journey consumes it.",
}

EPIC = {"epic_id": "EPIC-S7-001", "title": "Online disability claim submission",
        "business_outcome": "Sponsors submit online."}
ANALYSIS = {"business_rules": [{"rule_id": "BR-01", "text": "Sponsor-scoped lookup only."}]}
TEAMS = ["Portal Team", "Services Team", "Data Team"]


def test_run_plan_validates_stories(monkeypatch):
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_PLAN))
    monkeypatch.setenv("LLM_MODE", "live")
    stories, confidence, rationale, usage = live_intake.run_plan(
        EPIC, ANALYSIS, PACKS, [], TEAMS
    )
    assert stories[0].story_id == "US-001"
    assert stories[0].provenance.value == "live_ai"
    assert confidence["value"] == 78
    assert "self-assessment" in confidence["basis"]


def test_run_plan_rejects_unknown_team(monkeypatch):
    bad = {**GOOD_PLAN, "stories": [dict(GOOD_STORY, accountable_team="Invented Team")]}
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="team"):
        live_intake.run_plan(EPIC, ANALYSIS, PACKS, [], TEAMS)


def test_run_plan_rejects_unconnected_repo(monkeypatch):
    bad = {**GOOD_PLAN, "stories": [dict(GOOD_STORY, target_repository="other-repo")]}
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="repository"):
        live_intake.run_plan(EPIC, ANALYSIS, PACKS, [], TEAMS)


def test_run_plan_rejects_unclaimed_business_rule(monkeypatch):
    bad = {**GOOD_PLAN, "stories": [dict(GOOD_STORY, traces_to=[])]}
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="BR-01"):
        live_intake.run_plan(EPIC, ANALYSIS, PACKS, [], TEAMS)


def test_run_plan_rejects_bad_estimate(monkeypatch):
    bad = {**GOOD_PLAN, "stories": [dict(GOOD_STORY, estimate=4)]}
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="estimate"):
        live_intake.run_plan(EPIC, ANALYSIS, PACKS, [], TEAMS)
```

Append to `tests/test_factory_live_engine.py`:

```python
from s7_delivery.factory.models import Story, AcceptanceCriterion, FeatureFlag, RollbackPlan


def _fake_story() -> Story:
    return Story(
        story_id="US-001", epic_id="EPIC-S7-001", title="t", purpose="p",
        accountable_team="Data Team", target_application="maplesure-claims-api",
        target_component="c", target_repository="maplesure-claims-api",
        acceptance_criteria=[AcceptanceCriterion(ac_id="US-001-AC1", text="x")],
        feature_flag=FeatureFlag(name="f"), rollback_plan=RollbackPlan(method="m"),
        estimate=5, sprint=1, traces_to=["BR-01"],
        provenance=Provenance.LIVE_AI,
    )


def test_live_planning_generate(tmp_path, monkeypatch):
    eng = _live_engine_with_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(
        live_intake, "run_analysis",
        lambda req, packs, transcript: (_fake_analysis(), {}),
    )
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    eng.intake_pass_gate(Role.DELIVERY_LEAD)

    monkeypatch.setattr(
        live_intake, "run_plan",
        lambda epic, analysis, packs, transcript, teams: (
            [_fake_story()],
            {"value": 78, "basis": "Planning model self-assessment (live).",
             "provenance": "live_ai"},
            {"text": "why", "provenance": "live_ai"},
            {},
        ),
    )
    eng.planning_generate(Role.DELIVERY_LEAD)
    state = eng.state()
    assert state["planning"]["stories"][0]["provenance"] == "live_ai"
    assert state["planning"]["confidence"]["value"] == 78
    # Sign-off and task seeding work on live stories unchanged.
    eng.planning_sign_off(Role.BUSINESS_OWNER, "Jordan Hale")
    state = eng.state()
    assert state["build"]["tasks"][0]["story_id"] == "US-001"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_live_intake.py tests/test_factory_live_engine.py -v`
Expected: new tests FAIL (`run_plan` missing; simulated planning path writes seeded stories)

- [ ] **Step 3: Implement**

`live_intake.py` — append:

```python
PLAN_ROLE = (
    "Your role is delivery planning: break the epic into small, independently "
    "deliverable user stories with owners, grounded in the connected "
    "repositories — a story lands in the repository whose code it changes. "
    "Where the repositories show a capability does not exist, the story that "
    "introduces it comes first in the dependency order."
)

_POINT_SCALE = (1, 2, 3, 5, 8, 13)

_PLAN_SHAPE = """{
  "stories": [
    {
      "story_id": "US-<n>, numbered from 1 in delivery order",
      "title": "<short imperative title>",
      "purpose": "<why this story exists, one or two sentences>",
      "accountable_team": "<one team from the roster>",
      "target_application": "<the connected repository this changes>",
      "target_repository": "<same connected repository name>",
      "target_component": "<the part of that repository this lands in>",
      "acceptance_criteria": [
        {"ac_id": "US-<n>-AC<m>", "text": "Given <context>, when <action>, then <observable result>"}
      ],
      "dependencies": ["<story ids this cannot start before>"],
      "impacts": ["<existing file or behaviour this touches>"],
      "feature_flag": {"name": "<flag to ship dark behind>"},
      "rollback_plan": {"method": "<one line: how this is backed out>"},
      "task_type": "feature | config | migration | integration | test",
      "estimate": <integer: 1/2/3/5/8/13>,
      "sprint": <1, 2 or 3>,
      "traces_to": ["<business rule ids from the analysis this story delivers>"]
    }
  ],
  "confidence": <0-100 self-assessment of the draft>,
  "rationale": "<one paragraph: the decomposition logic>"
}"""


def run_plan(
    epic: dict,
    analysis: dict,
    packs: dict[str, str],
    transcript: list[dict],
    teams: list[str],
) -> tuple[list, dict, dict, dict]:
    from s7_delivery.factory.models import Status, Story

    if not packs:
        raise LLMError("Live planning needs a connected repository.")
    rule_ids = [r["rule_id"] for r in analysis.get("business_rules", [])]
    roster = "\n".join(f"- {t}" for t in teams)
    task = f"""The approved epic:
{json.dumps(epic, indent=2)}

The intake analysis' business rules (every rule id must be claimed by at
least one story's "traces_to"):
{json.dumps(analysis.get("business_rules", []), indent=2)}

Clarification conversation so far:
{_transcript_text(transcript)}

The team roster. Assign each story's accountable_team from this list ONLY:
{roster}

Break the epic into 4 to 8 stories across sprints 1 to 3. Every story's
target_repository must be one of the connected repositories. Return JSON
exactly matching:
{_PLAN_SHAPE}"""
    data, usage = _call(
        role=PLAN_ROLE,
        ref=_ref(epic, packs),
        task=task,
        beat="plan",
        key_material=json.dumps(epic, sort_keys=True)
        + json.dumps(rule_ids)
        + json.dumps(transcript, sort_keys=True),
    )

    raw_stories = data.get("stories")
    if not isinstance(raw_stories, list) or not 1 <= len(raw_stories) <= 10:
        raise LLMError("plan must contain 1-10 stories")

    provenance = provenance_now()
    stories: list[Story] = []
    seen: set[str] = set()
    for raw in raw_stories:
        sid = str(raw.get("story_id", ""))
        if not sid or sid in seen:
            raise LLMError(f"missing or duplicate story_id {sid!r}")
        seen.add(sid)
        if raw.get("accountable_team") not in teams:
            raise LLMError(
                f"story {sid}: accountable_team {raw.get('accountable_team')!r} "
                "is not on the team roster"
            )
        if raw.get("target_repository") not in packs:
            raise LLMError(
                f"story {sid}: target_repository {raw.get('target_repository')!r} "
                "is not a connected repository"
            )
        if raw.get("estimate") not in _POINT_SCALE:
            raise LLMError(f"story {sid}: estimate must be one of {_POINT_SCALE}")
        if not raw.get("acceptance_criteria"):
            raise LLMError(f"story {sid}: no acceptance criteria")
        _excluded = {"provenance", "status", "version", "epic_id"}  # ours to set
        try:
            story = Story(
                **{k: v for k, v in raw.items()
                   if k in Story.model_fields and k not in _excluded},
                epic_id=str(epic.get("epic_id", "")),
                provenance=provenance,
            )
        except Exception as exc:
            raise LLMError(f"story {sid} failed validation: {exc}") from exc
        if story.sprint != 1:
            story = story.model_copy(update={"status": Status.PLANNED})
        stories.append(story)

    ids = {s.story_id for s in stories}
    for s in stories:
        dangling = [d for d in s.dependencies if d not in ids]
        if dangling:
            raise LLMError(f"story {s.story_id} depends on unknown stories {dangling}")

    claimed = {rid for s in stories for rid in s.traces_to}
    unclaimed = [rid for rid in rule_ids if rid not in claimed]
    if unclaimed:
        raise LLMError(f"business rules claimed by no story: {unclaimed}")

    confidence = {
        "value": data.get("confidence"),
        "basis": "Planning model self-assessment of the draft decomposition "
                 "(live) — not a measured outcome.",
        "provenance": provenance.value,
    }
    rationale = {
        "text": str(data.get("rationale", "")),
        "provenance": provenance.value,
    }
    return stories, confidence, rationale, usage
```

`engine.py` — in `planning_generate`, after `self._stage_in_progress(Stage.PLANNING)` insert:

```python
        if self.run().mode is DemoMode.LIVE:
            self._planning_generate_live()
            return
```

and add the method:

```python
    def _planning_generate_live(self) -> None:
        import time

        from s7_delivery.factory import live_intake

        packs = self._context_packs()
        epic = self.store.read_json_or(None, "intake", "epic.json")
        if epic is None:
            raise EngineError("Create the epic before generating the plan")
        analysis = self.store.read_json("intake", "analysis.json")
        transcript = self._clarifications()["transcript"]
        t0 = time.monotonic()
        stories, confidence, rationale, usage = live_intake.run_plan(
            epic, analysis, packs, transcript, seed.TEAMS
        )
        payloads = [s.model_dump(mode="json") for s in stories]
        self.store.write_json(payloads, "planning", "stories.json")
        self.store.write_json(confidence, "planning", "confidence.json")
        self.store.write_json(rationale, "planning", "rationale.json")
        for s in payloads:
            self._record(
                artifact_id=s["story_id"], artifact_type="story", payload=s,
                author="planning (live)", stage=Stage.PLANNING,
                action="decompose", outcome="created",
                inputs=[s["epic_id"], "ANL-001",
                        f"REPO-{s['target_repository']}"],
            )
        self._activity(
            stage=Stage.PLANNING, actor="planning", actor_type="live_ai",
            workflow="epic-decomposition",
            duration_s=round(time.monotonic() - t0, 2), outcome="created",
            details=f"{len(payloads)} stories; "
            f"in={usage.get('input_tokens')} out={usage.get('output_tokens')} tokens",
        )
```

(The live path writes no `design.json` — the simulated `DES-001` narrative belongs to the seeded scenario. `state()` already tolerates its absence via `read_json_or(None, ...)`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_live_intake.py tests/test_factory_live_engine.py -v`
Expected: PASS

- [ ] **Step 5: Full suite, then commit**

```bash
pytest -q
git add s7_delivery/factory/live_intake.py s7_delivery/factory/engine.py tests/test_live_intake.py tests/test_factory_live_engine.py
git commit -m "feat: live epic-to-stories planning, validated to the factory contract"
```

---

### Task 8: UI — live option, connect card, clarification modal

No JS test harness exists in this repo; this task is verified by driving the app (Step 4). Keep every change in the existing style: `el()` builders, `act()` for engine actions, `openModal()` for dialogs.

**Files:**
- Modify: `apps/control/static/index.html` (~line 33)
- Modify: `apps/control/static/app.js` (`renderIntake`, ~lines 440–517)

**Interfaces:**
- Consumes: `intake.repos`, `intake.clarifications`, `run.mode` from the state payload; routes from Tasks 3/6.

- [ ] **Step 1: Add the Live option**

`index.html`:

```html
      <select id="envSelect">
        <option value="simulation">Demo</option>
        <option value="replay">Replay</option>
        <option value="live">Live</option>
      </select>
```

- [ ] **Step 2: Connect-repository card in `renderIntake`**

In `apps/control/static/app.js`, inside `renderIntake` (before `const rail = ...`), add:

```js
    const isLive = state.data?.run?.mode === "live";
    const repos = state.data?.intake?.repos ?? [];

    const repoCard = isLive ? el("div", { class: "card" },
      el("div", { class: "section-title" }, el("h3", { text: "Connected Repositories" }),
        el("span", { class: "chip", text: `${repos.length} connected` })),
      el("ul", { class: "plain" }, repos.map((r) =>
        el("li", {},
          el("span", { class: "mono", text: r.name }),
          el("span", { class: "hint", text: ` @ ${r.head_sha.slice(0, 10)} · ${r.file_count} files` })))),
      (() => {
        const url = el("input", { type: "text", placeholder: "https://github.com/<owner>/<repo>" });
        const btn = el("button", {
          class: "outline", text: "Connect repository",
          onclick: () => { if (url.value.trim()) act("/intake/connect-repo", { url: url.value.trim() }, "Repository connected"); },
        });
        return el("div", { class: "row", style: "margin-top:10px; display:flex; gap:8px" }, url, btn);
      })(),
      repos.length === 0 ? el("p", { class: "hint", text: "Live analysis is grounded in the connected repos — connect them before analysing." }) : null) : null;
```

Note: `act()` merges the role automatically the way every other call site does; pass only `{ url }`. Render `repoCard` above `reqCard` in the returned layout:

```js
        repoCard ? el("div", { style: "margin-bottom:14px" }, repoCard) : null,
        reqCard,
```

- [ ] **Step 3: Live clarification button + modal**

Replace the permanently disabled button in the rail (`app.js` ~lines 490–493) with:

```js
        isLive
          ? el("button", {
              class: "outline block", style: "margin-top:10px", text: "Ask AI Clarification",
              onclick: () => act("/intake/clarify", {}, "Clarifying questions requested"),
            })
          : Object.assign(el("button", {
              class: "outline block", style: "margin-top:10px", text: "Ask AI Clarification",
              title: "Live clarification runs in live mode. In demo mode the analysis lists its open questions below — honestly disabled, not mocked.",
            }), { disabled: true }),
```

And after the `aiCard` block in the main column, render pending questions as an answer form:

```js
    const clar = state.data?.intake?.clarifications;
    const clarCard = clar?.pending?.length ? el("div", { class: "card" },
      el("div", { class: "section-title" }, el("h3", { text: "AI Clarification" }),
        el("span", { class: "chip", text: `round ${clar.rounds_used} of ${clar.max_rounds}` })),
      (() => {
        const inputs = clar.pending.map((q) =>
          ({ q, input: el("input", { type: "text", placeholder: "Answer (blank = stated assumption)" }) }));
        return el("div", {},
          ...inputs.map(({ q, input }) => el("div", { style: "margin-bottom:8px" },
            el("p", { text: q }), input)),
          el("button", {
            class: "primary sq", text: "Submit answers",
            onclick: () => act("/intake/clarify-answer",
              { answers: inputs.map(({ input }) => input.value) }, "Answers recorded"),
          }));
      })()) : null;
```

Insert `clarCard` between the analysis card and the rules card in the returned layout. Also update the analysis-regeneration hint: after answers are recorded, "⟳ Regenerate Analysis" reruns the analysis with the transcript — in live mode retitle its toast to "Live analysis regenerated".

- [ ] **Step 4: Verify by driving the app**

```bash
demo/run_control.sh &
```

Then in a browser (or via curl):
1. Switch Environment to **Live** → a new live run is created (no 400).
2. Intake shows the Connected Repositories card; connect `https://github.com/AlanLands/maplesure-sponsor-portal` and the claims API repo; both rows appear with SHAs.
3. "Ask AI Clarification" is enabled; clicking it (with `LLM_MODE=live` and a key in `.env`) shows questions; answering records them.
4. Run Intake Analysis → analysis renders with the `live_ai` provenance badge.
5. Switch back to a simulation run → button disabled with tooltip, no repos card.

- [ ] **Step 5: Commit**

```bash
git add apps/control/static/index.html apps/control/static/app.js
git commit -m "feat(ui): live mode — repo connect card and clarification chat"
```

---

### Task 9: Docs, rehearsal note, final sweep

**Files:**
- Modify: `CLAUDE.md` (§ Status table, § LLM access note), `AGENTS.md` (mirror), `README.md` (live-mode section), `docs/superpowers/specs/2026-08-08-live-control-centre-github-grounding-design.md` (status line)

- [ ] **Step 1: Update the docs**

- `CLAUDE.md` status table: change the "real AI output" not-built row to reflect that the Control Centre's intake analysis, clarification and planning run live in live mode, grounded in the two `maplesure-*` GitHub repos; simulation stays the demo default (hard rule 5).
- Add one paragraph under § Surfaces noting the live mode + repo grounding, and that `demo/create_target_repos.py --push` provisions the target repos.
- Mirror both edits in `AGENTS.md` **in the same commit**.
- `README.md`: a "Live mode" subsection — `.env` needs `LLM_PROVIDER`/key, `LLM_MODE=record` to rehearse, `replay` on demo day.
- Spec status line → `implemented`.

- [ ] **Step 2: Rehearsal check (manual, needs the API key — not CI)**

With `LLM_MODE=record`: create a live run, connect both repos, clarify → answer → analyse → epic → gate → plan → sign off. Then set `LLM_MODE=replay`, reset, repeat the same inputs: every beat must replay offline. This is the demo-day insurance; record the outcome in the commit message.

- [ ] **Step 3: Full suite + ruff, commit**

```bash
pytest -q && ruff check .
git add CLAUDE.md AGENTS.md README.md docs/superpowers/specs/2026-08-08-live-control-centre-github-grounding-design.md
git commit -m "docs: live control centre — status, surfaces, live-mode runbook"
```
