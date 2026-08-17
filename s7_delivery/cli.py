"""The CLI surface — where an agent executes (CLAUDE.md § Surfaces).

Thin text views and drivers over the same `factory.Engine` the Control
Centre uses: nothing is printed here that the run's own ledgers do not
hold, which is what makes the ledger assertable in pytest. Simulation and
demo runs may be driven end to end (scripted approvals are printed with
their named actors, exactly as the demo scenarios play them); live runs
are refused for approval-bearing steps — approvals are human actions and
belong on the app surface.

Usage:
    python -m s7_delivery runs [--root DIR]
    python -m s7_delivery state RUN_ID [--root DIR]
    python -m s7_delivery ledger RUN_ID [--root DIR]
    python -m s7_delivery downstream RUN_ID [--story ID] [--root DIR]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, Role
from s7_delivery.factory.store import list_runs


def _engine(run_id: str, root: str | None) -> Engine:
    root_path = Path(root) if root else None
    if run_id not in list_runs(root_path):
        raise SystemExit(f"Unknown run {run_id!r}; `python -m s7_delivery runs` lists them")
    return Engine(run_id, root=root_path)


def _cmd_runs(args: argparse.Namespace) -> int:
    root_path = Path(args.root) if args.root else None
    for run_id in list_runs(root_path):
        run = Engine(run_id, root=root_path).run()
        print(f"{run_id}  mode={run.mode.value}  entry={run.entry_mode}  "
              f"status={run.status.value}")
    return 0


def _cmd_state(args: argparse.Namespace) -> int:
    state = _engine(args.run_id, args.root).state()
    run = state["run"]
    print(f"run {run['run_id']}  mode={run['mode']}  entry={run['entry_mode']}"
          f"  status={run['status']}")
    print("stages:")
    for s in run["stages"]:
        print(f"  {s['stage']:<14} {s['status']}")
    print("gates:")
    for g in state["gates"]:
        decided = f"  by {g['decided_by']}" if g.get("decided_by") else ""
        print(f"  {g['gate_id']}  {g['label']:<38} {g['status']}{decided}")
    planning = state.get("planning") or {}
    stories = planning.get("stories") or []
    tasks = (state.get("build") or {}).get("tasks") or []
    print(f"stories: {len(stories)}   tasks: {len(tasks)}")
    return 0


def _cmd_ledger(args: argparse.Namespace) -> int:
    state = _engine(args.run_id, args.root).state()
    summary = state.get("activity_summary") or {}
    print("counters:")
    for key, value in (summary.get("counters") or {}).items():
        print(f"  {key:<22} {value}")
    basis = summary.get("stage_time_basis") or {}
    print(f"stage time: measured={basis.get('measured_s', 0)}s "
          f"scripted={basis.get('scripted_s', 0)}s")
    for stage, secs in (summary.get("stage_time_s") or {}).items():
        print(f"  {stage:<14} {round(secs, 1)}s")
    print(f"provenance records: {len(state.get('provenance_ledger') or [])}")
    card = state.get("kpi")
    if card:
        print("kpis (rule_based):")
        for name, k in card["kpis"].items():
            if k["evidenced"]:
                print(f"  {name:<20} {k['value']} {k['unit']}")
            else:
                print(f"  {name:<20} not evidenced — {k['note']}")
    return 0


def _prepare_context(eng: Engine, out=print) -> None:
    """G1-authorised context generation, as the demo scenarios script it —
    each approval printed with its named actor, never silent."""
    from s7_delivery.factory.demo import _DEVELOPERS

    build = eng.state()["build"]
    if not build.get("workspaces"):
        out("preparing governed context (scripted approvals, named):")
        if not build.get("architecture"):
            eng.architecture_generate(Role.ENGINEERING_LEAD)
            out("  architecture generated (engineering lead)")
        eng.architecture_accept(Role.ENGINEERING_LEAD, "A. Osei")
        out("  architecture accepted by A. Osei")
        eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
        for pack in eng.state()["build"]["delivery_packs"]:
            eng.test_plan_approve(Role.QA_LEAD, pack["delivery_pack_id"], "R. Osei")
        out("  delivery packs generated; test plans QA-approved by R. Osei")
        eng.delivery_packs_publish_all(Role.DELIVERY_LEAD)
        out("  packs published (pseudo-commit — no git in simulation)")
        for ws in eng.state()["build"]["workspaces"]:
            developer = _DEVELOPERS.get(ws["team"])
            if developer:
                eng.workspace_assign_developer(
                    Role.DELIVERY_LEAD, ws["workspace_id"], developer
                )
        out("  workspaces provisioned and developers assigned")


def _cmd_downstream(args: argparse.Namespace) -> int:
    eng = _engine(args.run_id, args.root)
    if eng.run().mode is DemoMode.LIVE:
        print("live runs carry human approvals — drive them from the app; "
              "the CLI scripts approvals only in simulation/demo")
        return 2
    try:
        _prepare_context(eng)
    except EngineError as exc:
        print(f"cannot prepare downstream context: {exc}")
        return 2

    tasks = sorted(
        eng.state()["build"]["tasks"], key=lambda t: t["story_id"]
    )
    if args.story:
        tasks = [t for t in tasks if t["story_id"] == args.story]
        if not tasks:
            print(f"no task for story {args.story}")
            return 2
    for task in tasks:
        if task["status"] in ("completed", "passed"):
            print(f"{task['story_id']}  already complete — skipped")
            continue
        tid = task["task_id"]
        try:
            eng.task_run_to_review(Role.ENGINEERING_LEAD, tid)
        except EngineError as exc:
            print(f"{task['story_id']}  cannot start: {exc}")
            return 2
        report = eng.review_execute(Role.INDEPENDENT_REVIEWER, tid)
        print(f"{task['story_id']}  develop → test → submit → review: "
              f"{report['result']}")
        if report["result"] != "passed":
            # The bounded-loop discipline: report the remaining failures,
            # never present partial output as success.
            for finding in report.get("findings", []):
                print(f"  {finding.get('finding_id', '?')}  "
                      f"{finding.get('severity', '')}: "
                      f"{finding.get('summary', finding.get('text', ''))}")
            print(f"{task['story_id']}  review blocked — fix and re-run, or "
                  "drive the corrective cycle from the app")
            return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m s7_delivery",
        description="S7 delivery CLI — text views and drivers over the run engine",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_runs = sub.add_parser("runs", help="list runs")
    p_runs.set_defaults(func=_cmd_runs)

    p_state = sub.add_parser("state", help="stages, gates and counts for a run")
    p_state.add_argument("run_id")
    p_state.set_defaults(func=_cmd_state)

    p_ledger = sub.add_parser("ledger", help="the run ledger as assertable text")
    p_ledger.add_argument("run_id")
    p_ledger.set_defaults(func=_cmd_ledger)

    p_down = sub.add_parser(
        "downstream",
        help="drive ready tasks through develop → test → review (sim/demo)",
    )
    p_down.add_argument("run_id")
    p_down.add_argument("--story", help="drive one story only")
    p_down.set_defaults(func=_cmd_downstream)

    for p in (p_runs, p_state, p_ledger, p_down):
        p.add_argument("--root", help="artifacts root (default artifacts/runs)")

    args = parser.parse_args(argv)
    return args.func(args)
