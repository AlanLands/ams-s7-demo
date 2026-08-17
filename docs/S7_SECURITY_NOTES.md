# S7 Control Centre — Security Notes

Demo-grade software, honestly scoped: single presenter, bound to 127.0.0.1,
no authentication (the role selector is a demonstration device, not an
identity system). What it does enforce, it enforces server-side:

- **Role-based action checks** in `factory/roles.py`, applied by every
  engine action. Frontend button state is a hint; the 403 is the rule.
- **Gate validation server-side** (`factory/gates.py`); no endpoint skips a
  gate, and the demo scenarios drive the same actions.
- **Path safety**: every path segment is validated against
  `^[A-Za-z0-9][A-Za-z0-9._-]*$` and resolved under the run directory;
  a browser-supplied run id cannot escape `artifacts/runs/`.
- **No shell interpretation of browser input**: subprocess calls (git, gh)
  are argument lists, never shell strings; in simulation and demo runs the
  engine writes JSON and markdown, nothing else. Live/replay runs do run
  `git clone` against a human-supplied repository URL — that URL is an
  operator decision, not untrusted input, but it is a real command run
  with a browser-supplied argument and is named here for that reason.
- **Append-only decision history**: provenance, activity, approvals and
  amendments are JSONL ledgers with no rewrite path in the store API.
- **Immutable signed versions**: the locked plan and release decisions are
  versioned; correction creates new versions, never edits.
- **Credentials**: simulation and demo runs make no network calls and need
  no keys. Live mode is a supported path (`POST /api/runs {"mode":
  "live"}`) and calls the configured LLM provider for intake analysis,
  clarification, routing, extraction and planning; keys stay in `.env`
  (gitignored) per hard rule 3 and are never persisted into any run
  artifact. Replay runs take the live code paths with the model layer
  pinned to committed recordings — no key, no network call.
- **External writes — the full list.** Three actions, all live-run only,
  all explicit human clicks, write outside this repository:
  1. `planning/push-delivery-branch` pushes a fresh, disposable
     `delivery/<run_id>` branch to the connected GitHub remote — verified
     in code against the repo's recorded default branch, not just naming;
  2. delivery-pack publication pushes an `s7/<run>-<team>` context branch,
     restricted to `AGENTS.md` + `.s7/**` + governed test roots, refusing
     default branches and foreign content (`factory/publication.py`);
  3. new-application approval runs `gh repo create --push`
     (`factory/scaffold.py`) — the only repo-creating call.
  Simulation, demo and replay runs never reach any of the three
  (publication is a pseudo-commit; repo creation is refused in replay).
  Merging anything into a working branch stays a manual human action.
- **Customer-safe surface**: no raw source, prompts, or logs; the technical
  evidence view is a sanitised summary (file names, refs, counts).

Known non-goals for the demo: authentication/authorization of real users,
TLS, multi-tenancy, audit-grade clock integrity (ledger order stands in for
trusted time).
