"""Release/design document — a deterministic rendering of run state
(spec 2026-08-10-demo-mode-and-release-document §4).

One `document_data` assembly feeds both renderers, so the markdown in the
artifact tree and the themed HTML page can never disagree. The document is
never AI output: it is badged rule_based in every mode, and the HTML is
fully self-contained (inline CSS, no external requests — hard rule 4),
branded MapleSure only (hard rule 2).
"""

from __future__ import annotations

import html as html_mod
from typing import Any

SECTIONS = [
    "Overview",
    "Plan Approval",
    "Architecture",
    "Development",
    "Testing & Quality",
    "Acceptance Criteria",
    "Release Approvals",
    "Deployment & Handover",
]


def _latest_review_by_story(state: dict) -> dict[str, dict]:
    """Last review per story, joined through the story's task."""
    build = state.get("build") or {}
    task_story = {t["task_id"]: t["story_id"] for t in build.get("tasks", [])}
    out: dict[str, dict] = {}
    for r in build.get("reviews", []):
        sid = task_story.get(r.get("task_id", ""))
        if sid:
            out[sid] = r  # ledger order — later entries win
    return out


def document_data(state: dict) -> dict[str, Any]:
    intake = state.get("intake") or {}
    build = state.get("build") or {}
    epic = intake.get("epic") or {}
    stories = (state.get("planning") or {}).get("stories", [])
    tasks = {t["story_id"]: t for t in build.get("tasks", [])}
    workspaces = {w["story_id"]: w for w in build.get("workspaces", [])}
    reviews = _latest_review_by_story(state)
    approvals = state.get("approvals") or []
    arch = build.get("architecture") or {}
    release = state.get("release") or {}
    quality = state.get("quality") or {}

    tester_by_story: dict[str, str] = {}
    for pack in build.get("delivery_packs", []):
        for sid in pack.get("story_ids", []):
            if pack.get("test_plan_approved_by"):
                tester_by_story[sid] = pack["test_plan_approved_by"]

    story_rows = []
    for s in stories:
        sid = s["story_id"]
        task = tasks.get(sid, {})
        results = {t["ac_id"]: t.get("current_result", "")
                   for t in task.get("tests", [])}
        review = reviews.get(sid, {})
        story_rows.append({
            "story_id": sid,
            "title": s.get("title", ""),
            "team": s.get("accountable_team", ""),
            "developer": workspaces.get(sid, {}).get("developer", "") or "—",
            "tester": tester_by_story.get(sid, "") or "—",
            "review_result": review.get("result", "pending"),
            "reviewer": review.get("reviewer", ""),
            "changes": task.get("change_summary", ""),
            "acceptance_criteria": [
                {
                    "ac_id": ac["ac_id"],
                    "text": ac.get("text", ""),
                    "result": results.get(ac["ac_id"], "not run"),
                }
                for ac in s.get("acceptance_criteria", [])
            ],
        })

    return {
        "toc": list(SECTIONS),
        "run_id": (state.get("run") or {}).get("run_id", ""),
        "epic": {
            "epic_id": epic.get("epic_id", ""),
            "title": epic.get("title", ""),
            "business_outcome": epic.get("business_outcome", ""),
        },
        "plan_approvals": [a for a in approvals if a.get("subject") == "plan"],
        "test_plan_approvals": [
            a for a in approvals
            if str(a.get("subject", "")).startswith("test-plan:")
        ],
        "architecture": {
            "version": arch.get("version"),
            "accepted_by": arch.get("accepted_by", ""),
            "accepted_at": arch.get("accepted_at", ""),
        },
        "stories": story_rows,
        "quality_checks": quality.get("checks", []),
        "release_approvals": [
            a for a in approvals if a.get("subject") == "release"
        ],
        "release": {
            "release_id": release.get("release_id", ""),
            "version": release.get("version", ""),
            "environment": release.get("environment", ""),
            "release_window": release.get("release_window", ""),
            "feature_flag": release.get("feature_flag", ""),
            "rollback_plan": release.get("rollback_plan", ""),
            "deployment": release.get("deployment"),
            "handover": release.get("handover"),
        },
    }


# --- markdown ---------------------------------------------------------------

def render_markdown(data: dict) -> str:
    lines: list[str] = []
    epic = data["epic"]
    lines += [
        f"# Release & Design Document — {epic['title']}",
        "",
        f"Epic {epic['epic_id']} · Release {data['release']['release_id']} "
        f"v{data['release']['version']} · Run {data['run_id']}",
        "",
        "## Table of Contents",
        "",
    ]
    lines += [f"{i}. {s}" for i, s in enumerate(data["toc"], start=1)]

    lines += ["", "## Overview", "", epic["business_outcome"] or "—", ""]

    lines += ["## Plan Approval", ""]
    for a in data["plan_approvals"]:
        lines.append(
            f"- **{a['approver']}** ({str(a['role']).replace('_', ' ')}) — "
            f"{a['decision']}, {a['decided_at']}"
            + (f" — {a['note']}" if a.get("note") else "")
        )
    if not data["plan_approvals"]:
        lines.append("- No plan approvals recorded")
    lines.append("")

    arch = data["architecture"]
    lines += ["## Architecture", ""]
    if arch["accepted_by"]:
        lines.append(
            f"Blueprint v{arch['version']} accepted by **{arch['accepted_by']}** "
            f"at {arch['accepted_at']}."
        )
    else:
        lines.append("Architecture not yet accepted.")
    lines.append("")

    lines += ["## Development", ""]
    lines.append("| Story | Title | Team | Developer | Independent Review |")
    lines.append("|---|---|---|---|---|")
    for s in data["stories"]:
        lines.append(
            f"| {s['story_id']} | {s['title']} | {s['team']} "
            f"| {s['developer']} | {s['review_result']} |"
        )
    lines.append("")
    for s in data["stories"]:
        if s["changes"]:
            lines += [f"**{s['story_id']} — changes:** {s['changes']}", ""]

    lines += ["## Testing & Quality", ""]
    lines.append("| Story | Tested By (QA sign-off) |")
    lines.append("|---|---|")
    for s in data["stories"]:
        lines.append(f"| {s['story_id']} | {s['tester']} |")
    lines.append("")
    for c in data["quality_checks"]:
        lines.append(f"- {c.get('check_id', '')} {c.get('name', '')}: "
                     f"**{c.get('status', '')}**")
    lines.append("")

    lines += ["## Acceptance Criteria", ""]
    for s in data["stories"]:
        lines += [f"### {s['story_id']} — {s['title']}", ""]
        lines.append("| Criterion | Description | Result |")
        lines.append("|---|---|---|")
        for ac in s["acceptance_criteria"]:
            lines.append(f"| {ac['ac_id']} | {ac['text']} | {ac['result']} |")
        lines.append("")

    lines += ["## Release Approvals", ""]
    for a in data["release_approvals"]:
        lines.append(
            f"- **{a['approver']}** ({str(a['role']).replace('_', ' ')}) — "
            f"{a['decision']}, {a['decided_at']}"
        )
    if not data["release_approvals"]:
        lines.append("- No release approvals recorded")
    lines.append("")

    rel = data["release"]
    lines += ["## Deployment & Handover", ""]
    lines.append(f"- Environment: {rel['environment']}")
    lines.append(f"- Window: {rel['release_window']}")
    lines.append(f"- Feature flag: {rel['feature_flag']}")
    lines.append(f"- Rollback: {rel['rollback_plan']}")
    dep = rel.get("deployment")
    if dep:
        lines.append(
            f"- Deployed: {dep.get('deployed_at', '')} "
            f"({dep.get('strategy', '')}, smoke tests "
            f"{dep.get('smoke_test_status', '')})"
        )
    h = rel.get("handover")
    if h:
        lines.append(
            f"- Handover accepted by {h.get('accepted_by', '')} "
            f"at {h.get('accepted_at', '')}"
        )
    lines.append("")
    return "\n".join(lines)


# --- themed HTML ------------------------------------------------------------

_CSS = """
:root{--red:#a20a29;--red2:#850822;--ink:#292923;--text:#36362f;
--muted:#66655b;--bg:#f2f2ef;--surface:#fff;--border:#d8d8d3;
--greenp:#dff0e8;--green:#125c43;--redp:#f8e9ed;}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);
font-family:"Segoe UI",Inter,Arial,sans-serif;line-height:1.55}
.brandline{height:4px;background:var(--red)}
header{background:var(--surface);border-bottom:1px solid var(--border);
padding:18px 34px;display:flex;align-items:center;gap:12px}
.mark{width:38px;height:38px;border-radius:8px;background:var(--red);
color:#fff;display:grid;place-items:center;font-weight:800;
font-family:Georgia,serif}
header small{display:block;color:var(--red);font-size:10px;
text-transform:uppercase;letter-spacing:.13em;font-weight:800}
header b{font-size:16px;color:var(--ink)}
main{max-width:900px;margin:0 auto;padding:30px 24px 60px}
h1{color:var(--ink);font-size:26px;margin:14px 0 4px}
.meta{color:var(--muted);font-size:13px;margin-bottom:22px}
h2{color:var(--red2);font-size:19px;margin:30px 0 10px;
border-bottom:2px solid var(--red);padding-bottom:5px}
h3{color:var(--ink);font-size:15px;margin:16px 0 6px}
ul,ol{margin:8px 0 8px 24px}
table{width:100%;border-collapse:collapse;background:var(--surface);
font-size:13.5px;margin:10px 0}
th{background:var(--red);color:#fff;text-align:left;padding:8px 10px}
td{border:1px solid var(--border);padding:7px 10px;vertical-align:top}
.pass{color:var(--green);background:var(--greenp);border-radius:99px;
padding:1px 9px;font-weight:700;font-size:12px}
.fail{color:var(--red2);background:var(--redp);border-radius:99px;
padding:1px 9px;font-weight:700;font-size:12px}
.toc{background:var(--surface);border:1px solid var(--border);
border-radius:10px;padding:16px 20px}
.changes{color:var(--muted);font-size:13px;margin:6px 0}
footer{color:var(--muted);font-size:12px;text-align:center;
padding:20px 0;border-top:1px solid var(--border)}
"""


def _e(text: Any) -> str:
    return html_mod.escape(str(text))


def _result_chip(result: str) -> str:
    cls = "pass" if result == "passed" else "fail"
    return f'<span class="{cls}">{_e(result)}</span>'


def _approval_list(rows: list[dict]) -> str:
    if not rows:
        return "<ul><li>No approvals recorded</li></ul>"
    items = "".join(
        f"<li><b>{_e(a['approver'])}</b> "
        f"({_e(str(a['role']).replace('_', ' '))}) — {_e(a['decision'])}, "
        f"{_e(a['decided_at'])}"
        + (f" — {_e(a['note'])}" if a.get("note") else "")
        + "</li>"
        for a in rows
    )
    return f"<ul>{items}</ul>"


def render_html(data: dict) -> str:
    epic = data["epic"]
    rel = data["release"]
    arch = data["architecture"]

    def sec_id(name: str) -> str:
        return name.lower().replace(" & ", "-").replace(" ", "-")

    toc = "".join(
        f'<li><a href="#{sec_id(s)}">{_e(s)}</a></li>' for s in data["toc"]
    )

    dev_rows = "".join(
        f"<tr><td>{_e(s['story_id'])}</td><td>{_e(s['title'])}</td>"
        f"<td>{_e(s['team'])}</td><td>{_e(s['developer'])}</td>"
        f"<td>{_result_chip(s['review_result'])}</td></tr>"
        for s in data["stories"]
    )
    changes = "".join(
        f"<p class=\"changes\"><b>{_e(s['story_id'])}</b> — {_e(s['changes'])}</p>"
        for s in data["stories"] if s["changes"]
    )
    test_rows = "".join(
        f"<tr><td>{_e(s['story_id'])}</td><td>{_e(s['tester'])}</td></tr>"
        for s in data["stories"]
    )
    quality = "".join(
        f"<li>{_e(c.get('check_id', ''))} {_e(c.get('name', ''))}: "
        f"{_result_chip(c.get('status', ''))}</li>"
        for c in data["quality_checks"]
    )
    ac_sections = "".join(
        f"<h3>{_e(s['story_id'])} — {_e(s['title'])}</h3>"
        "<table><tr><th>Criterion</th><th>Description</th><th>Result</th></tr>"
        + "".join(
            f"<tr><td>{_e(ac['ac_id'])}</td><td>{_e(ac['text'])}</td>"
            f"<td>{_result_chip(ac['result'])}</td></tr>"
            for ac in s["acceptance_criteria"]
        )
        + "</table>"
        for s in data["stories"]
    )

    dep = rel.get("deployment") or {}
    h = rel.get("handover") or {}
    deploy_bits = (
        f"<li>Environment: {_e(rel['environment'])}</li>"
        f"<li>Window: {_e(rel['release_window'])}</li>"
        f"<li>Feature flag: {_e(rel['feature_flag'])}</li>"
        f"<li>Rollback: {_e(rel['rollback_plan'])}</li>"
    )
    if dep:
        deploy_bits += (
            f"<li>Deployed: {_e(dep.get('deployed_at', ''))} "
            f"({_e(dep.get('strategy', ''))}, smoke tests "
            f"{_e(dep.get('smoke_test_status', ''))})</li>"
        )
    if h:
        deploy_bits += (
            f"<li>Handover accepted by {_e(h.get('accepted_by', ''))} "
            f"at {_e(h.get('accepted_at', ''))}</li>"
        )

    arch_line = (
        f"Blueprint v{_e(arch['version'])} accepted by "
        f"<b>{_e(arch['accepted_by'])}</b> at {_e(arch['accepted_at'])}."
        if arch["accepted_by"] else "Architecture not yet accepted."
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Release &amp; Design Document — {_e(epic['title'])}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="brandline"></div>
<header>
  <span class="mark">MS</span>
  <span><small>MapleSure Insurance</small><b>S7 Delivery — Release &amp; Design Document</b></span>
</header>
<main>
  <h1>{_e(epic['title'])}</h1>
  <p class="meta">Epic {_e(epic['epic_id'])} · Release {_e(rel['release_id'])}
  v{_e(rel['version'])} · Run {_e(data['run_id'])}</p>

  <h2 id="table-of-contents">Table of Contents</h2>
  <div class="toc"><ol>{toc}</ol></div>

  <h2 id="{sec_id('Overview')}">Overview</h2>
  <p>{_e(epic['business_outcome'])}</p>

  <h2 id="{sec_id('Plan Approval')}">Plan Approval</h2>
  {_approval_list(data['plan_approvals'])}

  <h2 id="{sec_id('Architecture')}">Architecture</h2>
  <p>{arch_line}</p>

  <h2 id="{sec_id('Development')}">Development</h2>
  <table><tr><th>Story</th><th>Title</th><th>Team</th><th>Developer</th>
  <th>Independent Review</th></tr>{dev_rows}</table>
  {changes}

  <h2 id="{sec_id('Testing & Quality')}">Testing &amp; Quality</h2>
  <table><tr><th>Story</th><th>Tested By (QA sign-off)</th></tr>{test_rows}</table>
  <ul>{quality}</ul>

  <h2 id="{sec_id('Acceptance Criteria')}">Acceptance Criteria</h2>
  {ac_sections}

  <h2 id="{sec_id('Release Approvals')}">Release Approvals</h2>
  {_approval_list(data['release_approvals'])}

  <h2 id="{sec_id('Deployment & Handover')}">Deployment &amp; Handover</h2>
  <ul>{deploy_bits}</ul>
</main>
<footer>MapleSure Insurance — generated by the S7 Delivery Control Centre from the run's own records</footer>
</body>
</html>
"""
