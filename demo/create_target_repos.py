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
- `app.py` — routes: dashboard (`/`), member directory (`/members`), member detail (`/members/<id>`).
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
- `main.py` — app factory and routes: member list (`/members`), member detail (`/members/{id}`), claims by member (`/members/{id}/claims`).
- `claims/models.py` — Pydantic models: Member, Claim.
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
