"""Portable, per-story artifact export (spec: requirement-routing-and-
delivery-handoff-design.md §C).

One folder per story, in this repo's own AGENTS.md convention: AGENTS.md
(context), acceptance-criteria.md (checklist), context.md (the target
repo's architecture.md). Vendor-neutral markdown — no `.claude/`-specific
tooling (hard rule 4).
"""
from __future__ import annotations

import re


def _slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "story"


def story_folder_name(story: dict) -> str:
    return f"{story['story_id']}-{_slug(story['title'])}"


def render_agents_md(story: dict) -> str:
    flag = story.get("feature_flag")
    flag_line = flag["name"] if isinstance(flag, dict) and flag.get("name") else "none"
    rollback = story.get("rollback_plan")
    rollback_line = (
        rollback["method"] if isinstance(rollback, dict) and rollback.get("method")
        else "none recorded"
    )
    deps = ", ".join(story.get("dependencies") or []) or "none"
    lines = [
        f"# {story['story_id']} — {story['title']}",
        "",
        "## Purpose",
        story.get("purpose", ""),
        "",
        "## Target",
        f"- Application: {story.get('target_application', '')}",
        f"- Repository: {story.get('target_repository', '')}",
        f"- Component: {story.get('target_component', '')}",
        "",
        "## Delivery details",
        f"- Accountable team: {story.get('accountable_team', '')}",
        f"- Task type: {story.get('task_type', '')}",
        f"- Estimate: {story.get('estimate', 0)} points",
        f"- Dependencies: {deps}",
        f"- Feature flag: {flag_line}",
        f"- Rollback plan: {rollback_line}",
    ]
    return "\n".join(lines) + "\n"


def render_acceptance_criteria_md(story: dict) -> str:
    lines = [f"# Acceptance criteria — {story['story_id']}", ""]
    for ac in story.get("acceptance_criteria", []):
        lines.append(f"- [ ] {ac['ac_id']}: {ac['text']}")
    return "\n".join(lines) + "\n"


def render_story_package(story: dict, repo_architecture_md: str) -> dict[str, str]:
    return {
        "AGENTS.md": render_agents_md(story),
        "acceptance-criteria.md": render_acceptance_criteria_md(story),
        "context.md": repo_architecture_md,
    }
