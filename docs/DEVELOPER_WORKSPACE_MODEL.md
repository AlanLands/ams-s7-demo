# Developer Workspace Model

**The dashboard is the governed control plane. The developer's own
environment is the engineering execution plane.** S7 never imitates an IDE.

## What a workspace is

One `DeveloperWorkspace` record per story, provisioned when the story's team
delivery pack is published (`Engine._provision_workspaces`). It names the
team, story, repository, context branch, assigned developer, pack version and
base commit. Stored in `build/workspaces.json`; recorded as `WS-<story>` in
provenance with the pack as input, so staleness reaches it.

## Ownership — who does what

| Owner | Owns |
|---|---|
| **Developer (human)** | implementation, commits, PRs, their IDE/CLI/Git, any coding assistant they choose |
| **S7** | governed context, traceability, evidence collection, artifact freshness, review orchestration |

Every execution surface shows **Human Controlled · AI Assisted**. S7 never
claims AI autonomously implemented production code.

## State

Static provisioning fields live on the record. Execution state is **derived
at read time** from the story's task (`Engine._workspaces_view`) so there is
one source of truth: current commit, PR, CI signal, and
`development_status` ∈ provisioned / ready / in_development / in_review /
correction_requested / complete. `artifact_status` flips to `stale` when the
workspace's pack appears in `staleness.json`.

## Developer assignment

`PATCH /api/runs/{id}/workspaces/{ws}/developer` — a human action
(delivery/engineering lead), recorded in the activity log. Assignment
survives republication: a new pack version re-provisions the workspace but
never unassigns the developer.

## Evidence, honestly

In production, commits/PRs/CI arrive from the developer's real Git and CI.
In this demo the deterministic simulation engine produces that evidence, and
every such record is badged `SIMULATED` — the workspace page labels its
controls "Simulate developer activity" rather than pretending a person typed.
The one live escape hatch (`S7_LIVE_STORY`) runs a real model lane and is
badged `LIVE_AI`. Nothing simulated ever presents as live (CLAUDE.md
§ Staged output).
