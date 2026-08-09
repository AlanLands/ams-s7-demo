# Build & Review — Customer Demonstration Script

The story in one breath: *S7 plans and prepares. AI generates governed
engineering context. Approved packs are published to Git. Human developers
work normally in their own workspaces. S7 collects evidence, an isolated
reviewer challenges the implementation, and only verified work proceeds to
Final Gating.*

Run in **simulation mode** (the default — hard rule 5). Every simulated
artifact is visibly badged `SIMULATED`; say so out loud once, early — the
badging *is* the governance story. Roles: switch via the header role picker
as each step names its actor.

1. **Gate 1 approved** (Business Owner, Planning → Plan Sign-off). Point at
   the checklist: epic, stories, ACs, teams, dependencies, estimates,
   sprints, risks, repository mapping, named approver — and note what is
   *not* on it: architecture. G1 authorises context generation; it never
   authorises AI to write production code.
2. **Architecture generated** (Engineering Lead, Build & Review →
   Architecture). Generate; walk the rendered architecture.md preview and
   the five-file pack. Versioned, canonical, referenced — never copied.
3. **Architecture accepted.** The service generated it; a *human* accepts
   it. No phase self-approves.
4. **Delivery packs generated** (Delivery Packs page). One pack per team;
   open one and show the layered contents — thin task packs whose
   context.json references plan v1 / architecture v1.
5. **Pack previewed** — AGENTS.md with its scope boundaries, out-of-scope
   list and completion conditions.
6. **Pack downloaded** — the portable ZIP. No state changed.
7. **Pack published to Git** ("Publish to Git", or "Publish All"). Show the
   publication record: repository, `s7/<run>-<team>` branch, commit,
   artifact count — and the SIMULATED badge; in live mode this is a real
   branch on the connected repo. Canonical artifacts remain in S7 for audit.
8. **Developer Workspace becomes Ready** (Developer Workspaces page). The
   page says it plainly: Human Controlled · AI Assisted. Assign a developer.
9. **Developer commit and PR appear.** Open the workspace drawer; use the
   clearly-labelled "Simulate developer activity" controls — start, red
   baseline, implementation evidence, verify. Commit, PR and CI populate.
10. **Build/Test evidence collected** (Build & Test Evidence page): the
    AC → test table, red-baseline-first.
11. **One AC fails.** US-003's equality boundary (`<` where the criterion
    says `≤`) — the scripted defect. The failure analysis card names the
    criterion, expected vs observed, and the likely component. No stack
    traces, no model internals — customer-safe.
12. **Independent Review blocks the story** (Independent Review page).
    REV-00N, one major gap. The reviewer is isolated: it cannot modify
    source and never approves its own output.
13. **Story returned to developer.** Task flips to Correction Requested in
    its workspace.
14. **Correction evidence arrives** — re-run the simulated activity; new
    commit, tests green.
15. **Re-review passes.** A *new* review version — the blocked REV is never
    mutated. Read the review history aloud: blocked, then passed.
16. **Build Summary shows the story ready for Final Gating.** The §21 handoff
    rule as named conditions — current context, passing tests, evidenced
    ACs, passing review, no open majors, PR+CI evidence. Conditions, not a
    score. Hand off to Final Gating.

Shortcut for rehearsal: `POST /api/demo/review-failure` stages steps 1–12 in
one call; `happy-path` stages the whole arc.

If asked "is this live?": simulation is the default and everything simulated
says so on its face. Live mode exists (connected repos, real branches, the
`S7_LIVE_STORY` lane) and is rehearsed separately; a beat that is adequate
five times in five beats one that is impressive four times in five.
