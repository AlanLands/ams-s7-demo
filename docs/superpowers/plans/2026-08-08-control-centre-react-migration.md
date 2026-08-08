# Control Centre React Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `apps/control/` from a single hand-rolled vanilla-JS file (`static/app.js`, 3124 lines) to a React + TypeScript + Vite app, and use that migration to ship the redesigned Intake page (upload/paste → AI extraction → review → create epic → proceed to planning) matching the supplied reference screenshot's information architecture.

**Architecture:** A new `apps/control/web/` source tree (mirroring the sibling `../ams-s3-demo/apps/console/web/` precedent exactly: Vite + React 19 + TypeScript, `@vitejs/plugin-react`, dev-server proxy to the FastAPI backend on `/api`, production build output consumed by the same FastAPI process). The backend (`apps/control/server.py`, `s7_delivery/factory/*`) does not change its business logic — only the static-file mount switches from `static/` to `web/dist/` once every page has parity, plus one SPA-fallback route. All 24 existing vanilla-JS view functions get ported 1:1 (same DOM, same CSS classes, same behavior) **except** Intake, which is redesigned. The two frontends (`static/` vanilla and `web/` React) coexist during migration; production keeps serving `static/` until Phase 4's explicit cutover, so the app is never broken mid-migration.

**Tech Stack:** React 19, TypeScript, Vite, `@vitejs/plugin-react`. No react-router (the current app has no URL-addressable routes to preserve — section switching is in-memory `state.section`, kept as React state for the same reason: adding routing is new scope, not a like-for-like port). No CSS framework — port `styles.css` verbatim as `theme.css`, same custom properties, same square-corner/hairline-border/warm-ink MapleSure design language.

## Global Constraints

- Hard rule 1 (CLAUDE.md/AGENTS.md): no real client data. Not implicated — no data changes here.
- Hard rule 2: no client names; fictional insurer stays **MapleSure Insurance**. Brand mark, kicker text, footer copy port verbatim.
- Hard rule 3: no secrets in code. Not implicated.
- **Hard rule 4 is being amended by this plan** (Task 0.5): from "no build step" to "a pinned, vendored-dependency build step is acceptable when the built output is committed-reproducible and documented" — because this migration adds Vite/npm. Both `CLAUDE.md` and `AGENTS.md` must be edited in the same commit (their own stated sync rule).
- Hard rule 5: demo reliability beats cleverness — simulation mode stays the default; nothing here changes `LLM_MODE` behavior.
- Branding: primary accent is **red** (`--red: #a20a29`), not the reference screenshot's blue. Square corners (`--radius-*: 0`) throughout. Source Sans 3 self-hosted from local `.woff2` files — no CDN, no Google Fonts.
- Provenance labelling: every AI-derived value on screen carries a `prov-*` badge (`prov-human`, `prov-simulated`, `prov-live_ai`, `prov-replayed_ai`, `prov-rule_based`, `prov-staged`). Simulation-mode extraction is labelled "Extraction (Rule-Based)" and badged `RULE_BASED` — never "AI Extraction" in that mode. Live mode is labelled "AI Extraction" and badged `LIVE_AI`/`REPLAYED_AI`.
- Backend contract is frozen for this plan: `POST /intake/upload-source`, `POST /intake/paste-source`, `PATCH /intake/extraction`, `POST /intake/finalize-epic`, `POST /intake/pass-gate`, `POST /intake/analyse`, `POST /intake/create-epic`, `POST /intake/route`, `POST /intake/override-route`, `POST /intake/connect-repo`, `POST /intake/clarify`, `POST /intake/clarify-answer`, `POST /intake/new-app-setup`, `POST /intake/new-app-answer`, `POST /intake/generate-scaffold`, `POST /intake/create-new-app-repo` — no new routes, no changed request/response shapes.
- Existing pytest suite (327 tests as of this plan, `tests/`) must stay green throughout — it exercises the API layer, not the DOM, so it is unaffected by the frontend rewrite unless a backend route changes (none should).
- No third-party agent skills/marketplace packages (AGENTS.md § Cache-efficient agent architecture, decision 6) — not implicated; Vite/React/TypeScript are ordinary pinned npm dependencies, not agent skills.

---

## Design decision: where the non-screenshot Intake functionality goes

The reference screenshot shows a 2-responsibility Intake page (accept requirement, extract with AI). The **existing** `intake` stage/section in this codebase does more than that: AI Analysis (risks, stakeholders, dependencies, confidence), a capped clarification chat, requirement routing (routable vs. new-application-needed), new-application onboarding, repository connection, a G0 gate checklist, and five rail buttons (`Route Requirement`, `Ask AI Clarification`, `⟳ Regenerate Analysis`, `Generate Epic`, `✓ Pass Intake Gate`). None of this is a mock — it is real, tested, backend-enforced functionality (`tests/test_control_api.py`, `tests/test_live_intake.py`), and G0 is "load-bearing, not optional" per `CLAUDE.md` § Surfaces.

Deleting it would violate "reuse existing backend/API services," "do not replace the application architecture," and "existing tests continue to pass." Silently keeping it all visible would violate the spec's explicit exclusion list ("Do NOT add: risk analysis, dependency analysis, ... clarification workflow, confidence scoring, approval gates") and the screenshot's visual hierarchy.

**Resolution, implemented in Task 2.6:**

1. The **primary CTA** ("Create Epic & Proceed to Planning →") calls `POST /intake/finalize-epic` (creates the epic, running analysis first if it hasn't run) and then, on success, `POST /intake/pass-gate` — in sequence, before navigating to Planning. `intake_finalize`'s own docstring already frames it as "the upload/paste panel's 'Create Epic & Proceed to Planning' button"; chaining `pass-gate` after it is new **frontend** behavior only (zero backend changes) and makes the click do what its label already claims. By the time `finalize-epic` has run, every G0 condition (`gates.intake_gate` in `s7_delivery/factory/gates.py:19`) is satisfied: requirement captured, source available (set by `intake_set_source`), analysis completed, scope identifiable, business owner identified (seeded), epic created. The human's click **is** the gate decision — it just isn't rendered as a separate checklist, matching the screenshot and satisfying "the review gate is the hinge... a click is a decision" from `CLAUDE.md` § Surfaces without weakening enforcement.
2. Everything else (AI Analysis, clarification chat, business rules, routing, repo connect, new-app setup, the gate checklist, the five rail buttons) moves into a single collapsed `<details>` section titled **"Advanced: Live Analysis & Governance"** below the primary content, closed by default. This keeps every existing capability reachable (nothing is deleted, no test breaks) while the *default, visible-in-30-seconds* page is exactly the screenshot's two-panel flow. This section is explicitly out of the "match the screenshot" scope — it is ported with its **existing** vanilla-JS visual design (Task 2.6 reuses the same card/kv/checklist CSS classes), not redesigned, consistent with "Do NOT redesign Planning... or unrelated pages" applied to functionality that was never part of the screenshot's ask in the first place.

State it plainly to the plan's reviewer: this is a judgment call, not something the screenshot or the spec text resolved directly. If the reviewer wants the advanced section relocated to Planning instead of collapsed-on-Intake, that is a bigger change (Planning's stage boundary in the backend is `Stage.PLANNING`, distinct from `Stage.INTAKE`, so "Route Requirement" etc. would need new Planning-stage UI wired to the same still-Intake-stage backend calls) and is flagged here rather than decided unilaterally.

---

## File Structure

```
apps/control/
  server.py                       # MODIFIED (Task 4.1 only — static mount + SPA fallback)
  static/                         # UNCHANGED until Task 4.2 removes it post-cutover
  web/                             # NEW — everything below is new
    package.json
    vite.config.ts
    tsconfig.json / tsconfig.app.json / tsconfig.node.json
    index.html
    public/
      fonts/source-sans-3-latin.woff2       # copied byte-for-byte from static/fonts/
      fonts/source-sans-3-latin-ext.woff2   # copied byte-for-byte from static/fonts/
      favicon.svg                            # new, minimal — "MS" mark on red, mirrors .brand-mark
    src/
      main.tsx
      theme.css                    # ported verbatim from static/styles.css, then extended for Intake
      types.ts                     # TS interfaces for the run-state JSON payload
      api.ts                       # api(), act(), ensureRun() — ported from app.js:58-118
      state/RunContext.tsx         # React context replacing the `state` singleton
      components/
        Header.tsx                 # app.js renderChrome()'s header half
        Stepper.tsx                # app.js renderChrome()'s stepper half
        SideNav.tsx                # app.js renderChrome()'s sidenav half
        Toast.tsx
        Badge.tsx                  # badge()/prov() helpers, app.js:39-45
        GuidanceCard.tsx           # app.js:1863-1869
        NotYetPorted.tsx           # dev-only placeholder for Phase-3 pages not yet ported
      pages/
        Overview.tsx               # Phase 1 — proves the plumbing end to end
        intake/
          IntakePage.tsx
          SourceRequirementCard.tsx
          ExtractionCard.tsx
          EditExtractionDrawer.tsx
          AiActivityPanel.tsx
          AdvancedAnalysisSection.tsx
        # Phase 3 — one file per remaining app.js render function, see table below
        planning/EpicToStories.tsx, DependencyMap.tsx, RoutingByTeam.tsx, PlanSummary.tsx, PlanSignoff.tsx
        build/BuildWorkQueue.tsx, DevProgress.tsx, TestEvidence.tsx, IndependentReview.tsx
        Quality.tsx, Release.tsx, Stories.tsx, Traceability.tsx, Artifacts.tsx,
        Approvals.tsx, Activity.tsx, Provenance.tsx, Risks.tsx, Reports.tsx, Settings.tsx
      App.tsx                      # page-map dispatch, replaces app.js:777-802 RENDERERS + app.js:3089 render()
tests/
  (unchanged — API-level tests already cover the intake contract this plan reuses)
CLAUDE.md                          # MODIFIED — hard rule 4 (Task 0.5)
AGENTS.md                          # MODIFIED — hard rule 4, same commit (Task 0.5)
```

---

# Phase 0 — Build tooling foundation

Nothing in this phase changes what a browser hitting `demo/run_control.sh` sees. It only makes `apps/control/web/` buildable and previewable via `npm run dev`.

### Task 0.1: Scaffold `apps/control/web/` package and TypeScript config

**Files:**
- Create: `apps/control/web/package.json`
- Create: `apps/control/web/tsconfig.json`
- Create: `apps/control/web/tsconfig.app.json`
- Create: `apps/control/web/tsconfig.node.json`
- Create: `apps/control/web/vite.config.ts`
- Create: `apps/control/web/.gitignore`

**Interfaces:**
- Produces: an `npm run dev` script (Vite dev server) and `npm run build` script (`tsc -b && vite build`, output to `apps/control/web/dist/`) that later tasks depend on.

- [ ] **Step 1: Write `package.json`**, matching the sibling S3 console's dependency versions exactly (same repo family, same Node/npm environment, avoids two different React major versions in one machine's node_modules caches):

```json
{
  "name": "control-centre-web",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^19.2.7",
    "react-dom": "^19.2.7"
  },
  "devDependencies": {
    "@types/node": "^24.13.2",
    "@types/react": "^19.2.17",
    "@types/react-dom": "^19.2.3",
    "@vitejs/plugin-react": "^6.0.3",
    "typescript": "~6.0.2",
    "vite": "^8.1.1"
  }
}
```

- [ ] **Step 2: Write `vite.config.ts`**, proxying `/api` to the FastAPI dev server (default port 8720, per `demo/run_control.sh`), overridable by environment the same way S3's does:

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const DEV_PORT = Number(process.env.VITE_DEV_PORT ?? 5173)
const API_PROXY_TARGET = process.env.VITE_DEV_API_PROXY ?? 'http://127.0.0.1:8720'

export default defineConfig({
  plugins: [react()],
  server: {
    port: DEV_PORT,
    proxy: {
      '/api': API_PROXY_TARGET,
    },
  },
})
```

- [ ] **Step 3: Write `tsconfig.json`** (project references, mirrors S3):

```json
{
  "files": [],
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" }
  ]
}
```

- [ ] **Step 4: Write `tsconfig.app.json`**:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "verbatimModuleSyntax": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedSideEffectImports": true
  },
  "include": ["src"]
}
```

- [ ] **Step 5: Write `tsconfig.node.json`**:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "verbatimModuleSyntax": true,
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 6: Write `.gitignore`**:

```
node_modules
dist
*.local
```

- [ ] **Step 7: Install and verify**

Run: `cd apps/control/web && npm install`
Expected: installs cleanly, creates `package-lock.json` and `node_modules/` (gitignored).

- [ ] **Step 8: Commit**

```bash
git add apps/control/web/package.json apps/control/web/package-lock.json apps/control/web/tsconfig*.json apps/control/web/vite.config.ts apps/control/web/.gitignore
git commit -m "control: scaffold Vite/React/TS tooling for the Control Centre frontend"
```

---

### Task 0.2: Port fonts, favicon, and `index.html`

**Files:**
- Create: `apps/control/web/public/fonts/source-sans-3-latin.woff2` (copy of `apps/control/static/fonts/source-sans-3-latin.woff2`)
- Create: `apps/control/web/public/fonts/source-sans-3-latin-ext.woff2` (copy of `apps/control/static/fonts/source-sans-3-latin-ext.woff2`)
- Create: `apps/control/web/public/favicon.svg`
- Create: `apps/control/web/index.html`

**Interfaces:**
- Produces: the HTML shell React mounts into (`#root`), matching S3's SPA entry pattern.

- [ ] **Step 1: Copy the font files verbatim** (byte-identical — no re-encoding, no CDN substitute; hard rule 4)

Run: `cp apps/control/static/fonts/*.woff2 apps/control/web/public/fonts/`

- [ ] **Step 2: Write `public/favicon.svg`** — a minimal square "MS" mark on the brand red, matching `.brand-mark`'s look (`--red: #a20a29`, white text, Georgia serif):

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" fill="#a20a29"/>
  <text x="16" y="21" font-family="Georgia, 'Times New Roman', serif" font-size="13" font-weight="600" fill="#ffffff" text-anchor="middle">MS</text>
</svg>
```

- [ ] **Step 3: Write `index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>S7 Delivery Control Centre — MapleSure</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 4: Commit**

```bash
git add apps/control/web/public apps/control/web/index.html
git commit -m "control: port fonts, favicon and HTML entry to the React app"
```

---

### Task 0.3: Port `theme.css`

**Files:**
- Create: `apps/control/web/src/theme.css` (starts as a byte-identical copy of `apps/control/static/styles.css`)

**Interfaces:**
- Produces: every CSS custom property and class name Phases 1-3 rely on (`--red`, `--ink`, `--border`, `--radius-*`, `.card`, `.chip`, `.badge`, `.kv`, `.pill`, `.dropzone` [new, added in Task 2.2], etc.) — unchanged names so ported components need no CSS renaming.

- [ ] **Step 1: Copy the stylesheet verbatim**

Run: `cp apps/control/static/styles.css apps/control/web/src/theme.css`

- [ ] **Step 2: Fix the font `url()` paths** — `static/styles.css` references `fonts/source-sans-3-latin.woff2` relative to `static/`; in the Vite app the same files live at `public/fonts/`, served from the site root, so the path becomes absolute:

Find in `theme.css`: `src: url('fonts/source-sans-3-latin.woff2') format('woff2');`
Replace with: `src: url('/fonts/source-sans-3-latin.woff2') format('woff2');`

(Same fix for the `-latin-ext` face.)

- [ ] **Step 3: Verify no other relative asset paths exist**

Run: `grep -n "url(" apps/control/web/src/theme.css`
Expected: only the two font `url()` lines, both now absolute (`/fonts/...`).

- [ ] **Step 4: Commit**

```bash
git add apps/control/web/src/theme.css
git commit -m "control: port theme.css to the React app, fix font asset paths"
```

---

### Task 0.4: `main.tsx` smoke-test shell

**Files:**
- Create: `apps/control/web/src/main.tsx`
- Create: `apps/control/web/src/App.tsx` (stub — replaced fully in Task 1.4)

**Interfaces:**
- Consumes: `theme.css` (Task 0.3)
- Produces: `App` component default export — the shape every later task's `App.tsx` edit builds on.

- [ ] **Step 1: Write the stub `App.tsx`**

```tsx
export default function App() {
  return <p>Control Centre — React shell loading…</p>
}
```

- [ ] **Step 2: Write `main.tsx`**

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './theme.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

- [ ] **Step 3: Verify the dev server renders the stub**

Run: `cd apps/control/web && npm run dev` (leave running), then in a second terminal:
Run: `curl -s http://127.0.0.1:5173/ | grep -o '<title>[^<]*</title>'`
Expected: `<title>S7 Delivery Control Centre — MapleSure</title>`

Then load `http://127.0.0.1:5173/` in the browser (Chrome MCP or manual) and confirm "Control Centre — React shell loading…" renders styled in Source Sans 3 with the warm cream background (`--bg: #f0f0ec`) — proves fonts and theme tokens loaded.

- [ ] **Step 4: Commit**

```bash
git add apps/control/web/src/main.tsx apps/control/web/src/App.tsx
git commit -m "control: React app renders a styled smoke-test shell"
```

---

### Task 0.5: Amend hard rule 4 in `CLAUDE.md` and `AGENTS.md`

**Files:**
- Modify: `/Users/alanlands/Documents/ams-s7-demo/CLAUDE.md` (hard rule 4, and add a dated note like every other reversed decision in the doc)
- Modify: `/Users/alanlands/Documents/ams-s7-demo/AGENTS.md` (hard rule 4, same commit — the file's own header says "kept in sync deliberately")

**Interfaces:**
- Produces: no code interface — this is documentation, but it's a required task because shipping a build step while the doc says "no build step... non-negotiable" is exactly the kind of silent-drift `CLAUDE.md` warns against elsewhere in this same file (§ Staged output, § Determinism).

- [ ] **Step 1: Edit `CLAUDE.md` hard rule 4**

Find:
```
4. **Must survive a port to a locked-down environment.** Plain Python +
   CSV/SQLite + static/simple web UI preferred. No cloud-managed services, no
   Docker-required paths, no OS-specific hacks. Pin dependencies.
```

Replace with:
```
4. **Must survive a port to a locked-down environment.** Plain Python +
   CSV/SQLite preferred. No cloud-managed services, no Docker-required paths,
   no OS-specific hacks. Pin dependencies.

   **Amended 2026-08-08 for the Control Centre frontend.** The Control Centre
   (`apps/control/`) moved from a hand-rolled vanilla-JS single file to
   React + TypeScript + Vite, matching the sibling S3 console's own
   `apps/console/web/` precedent (`../ams-s3-demo`), which already carried this
   exact stack under the identically-worded rule without either repo
   revisiting the wording until now. The build step is acceptable under this
   rule because: dependencies are pinned (`package-lock.json` committed), the
   build has no network dependency at build time beyond the initial `npm
   install` (same class of one-time setup as `pip install -r
   requirements.txt`), and the **built output** (`apps/control/web/dist/`) is
   what the locked-down environment actually runs — `apps/control/server.py`
   serves static files, same as before. No CDN imports, no fonts fetched at
   runtime (`public/fonts/*.woff2` stays self-hosted). If the target sandbox
   cannot run `npm install`/`npm run build` at all, the build must happen
   before the port and the committed `dist/` output ships as-is — Node is then
   a build-time tool, not a runtime dependency.
```

- [ ] **Step 2: Edit `AGENTS.md` hard rule 4**, same wording change, condensed to match that file's terser style:

Find:
```
4. Keep the project portable to a locked-down sandbox: plain Python,
   CSV/SQLite, simple UI, pinned dependencies, no Docker-required flow, no
   machine-specific paths.
```

Replace with:
```
4. Keep the project portable to a locked-down sandbox: plain Python,
   CSV/SQLite, pinned dependencies, no Docker-required flow, no
   machine-specific paths. **Amended 2026-08-08:** the Control Centre frontend
   (`apps/control/web/`) is React + TypeScript + Vite with a pinned,
   committed-lockfile build step, matching `../ams-s3-demo/apps/console/web/`.
   Node is a build-time tool; the sandbox runs the committed `dist/` output,
   not `npm`. Full rationale in `CLAUDE.md` hard rule 4.
```

- [ ] **Step 3: Verify both files mention the same date and point at each other**

Run: `grep -n "Amended 2026-08-08" CLAUDE.md AGENTS.md`
Expected: one match in each file.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md AGENTS.md
git commit -m "docs: amend hard rule 4 for the Control Centre's React/Vite build step"
```

---

# Phase 1 — App shell in React

Ports `renderChrome()` (`app.js:173-281`) and the section-dispatch loop (`app.js:777-802`, `3089-...`), validated end-to-end with the simplest real page (Overview) before Intake's complexity.

### Task 1.1: `types.ts` — run-state payload shapes

**Files:**
- Create: `apps/control/web/src/types.ts`

**Interfaces:**
- Consumes: nothing (leaf module)
- Produces: `RunState`, `Requirement`, `RequirementExtraction`, `ExtractedRequirement`, `IntakeAnalysis`, `EpicRecord`, `Gate`, `GateCondition`, `RoutingVerdict`, `RepoRecord`, `Role` — used by every later task that touches `state.data`.

- [ ] **Step 1: Write `types.ts`**, mirroring `s7_delivery/factory/models.py` field-for-field (read during planning: `Requirement` at models.py:102, `RequirementExtraction` at models.py:169, `IntakeAnalysis` at models.py:140, `EpicRecord` at models.py:158, `RoutingVerdict` at models.py:128, `RepoRecord` at models.py:116):

```ts
export type Provenance =
  | 'human' | 'live_ai' | 'replayed_ai' | 'staged' | 'simulated' | 'rule_based'

export interface ExtractedRequirement {
  rule_id: string
  text: string
}

export interface RequirementExtraction {
  epic_title: string
  business_objective: string
  requirement_summary: string
  extracted_requirements: ExtractedRequirement[]
  method: 'rule_based' | 'live_llm'
  provenance: Provenance
  generated_at: string
  edited_by: string | null
  edited_at: string | null
}

export interface Requirement {
  request_id: string
  title: string
  business_owner: string
  domain: string
  priority: string
  requested_date: string
  target_release: string
  description: string
  source_type: string
  source_documents: string[]
  provenance: Provenance
}

export interface IntakeAnalysis {
  problem_understood: boolean
  business_impact: string
  affected_applications: string[]
  stakeholders: string[]
  dependencies: string[]
  risks: string[]
  clarification_questions: string[]
  assumptions: string[]
  business_rules: { rule_id: string; text: string }[]
  risk_register: Record<string, unknown>[]
  confidence: number | null
  provenance: Provenance
  generated_at: string
}

export interface EpicRecord {
  epic_id: string
  title: string
  business_outcome: string
  estimated_stories: number
  status: string
  created_by: string
  created_at: string
  provenance: Provenance
}

export interface GateCondition {
  condition: string
  met: boolean
  detail: string
}

export interface Gate {
  gate_id: string
  label: string
  status: string
  conditions: GateCondition[]
  decided_by?: string
  decided_at?: string
}

export interface RoutingVerdict {
  verdict: 'routable' | 'new_application_needed'
  reasoning: string
  candidate_repos: string[]
  confidence: number | null
  overridden_by: string
  overridden_at: string
  provenance: Provenance
}

export interface RepoRecord {
  url: string
  name: string
  head_sha: string
  default_branch: string
  file_count: number
  cloned_at: string
  provenance: Provenance
}

export interface SourceRecord {
  text: string
  filename: string | null
  source_kind: 'upload' | 'paste'
  set_at: string
}

export interface ClarificationState {
  pending: string[]
  rounds_used: number
  max_rounds: number
}

export interface NewAppState {
  name?: string
  description?: string
  stack?: string
  pending?: string[]
}

export interface IntakeState {
  requirement?: Requirement
  analysis?: IntakeAnalysis
  epic?: EpicRecord
  extraction?: RequirementExtraction
  source?: SourceRecord
  repos?: RepoRecord[]
  routing?: RoutingVerdict
  clarifications?: ClarificationState
  new_app?: NewAppState
  scaffold?: Record<string, string>
}

export interface StageState {
  stage: string
  status: string
}

export interface RunRecord {
  run_id: string
  mode: 'simulation' | 'replay' | 'live'
  created_at: string
  stages: StageState[]
  plan_locked?: boolean
}

export interface RunState {
  run: RunRecord
  scenario?: { title: string; description: string; epic_source: string }
  intake?: IntakeState
  gates?: Gate[]
  provenance?: unknown[]
  activity_summary?: { counters?: Record<string, number>; total_events?: number }
  [section: string]: unknown
}

export interface RoleInfo {
  role: string
  actions: string[]
}
```

- [ ] **Step 2: Type-check**

Run: `cd apps/control/web && npx tsc -b --noEmit`
Expected: no errors (only file that exists so far besides stubs).

- [ ] **Step 3: Commit**

```bash
git add apps/control/web/src/types.ts
git commit -m "control: add TypeScript types for the run-state payload"
```

---

### Task 1.2: `api.ts` — HTTP client

**Files:**
- Create: `apps/control/web/src/api.ts`

**Interfaces:**
- Consumes: `RunState`, `RoleInfo` from `types.ts` (Task 1.1)
- Produces: `apiGet<T>(path)`, `apiPost<T>(path, body)`, `apiUpload<T>(path, formData)`, `apiPatch<T>(path, body)` — the primitives `RunContext` (Task 1.3) builds `refresh()`/`act()` on top of.

- [ ] **Step 1: Write `api.ts`**, a typed equivalent of `app.js:58-69`'s `api()`:

```ts
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    headers: options.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path)
}

export function apiPost<T>(path: string, body: Record<string, unknown> = {}): Promise<T> {
  return request<T>(path, { method: 'POST', body: JSON.stringify(body) })
}

export function apiPatch<T>(path: string, body: Record<string, unknown>): Promise<T> {
  return request<T>(path, { method: 'PATCH', body: JSON.stringify(body) })
}

export function apiUpload<T>(path: string, form: FormData): Promise<T> {
  return request<T>(path, { method: 'POST', body: form })
}
```

- [ ] **Step 2: Type-check**

Run: `cd apps/control/web && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add apps/control/web/src/api.ts
git commit -m "control: add typed API client primitives"
```

---

### Task 1.3: `RunContext` — replaces the `state` singleton

**Files:**
- Create: `apps/control/web/src/state/RunContext.tsx`

**Interfaces:**
- Consumes: `apiGet`, `apiPost` (Task 1.2), `RunState`, `RoleInfo` (Task 1.1)
- Produces: `RunProvider` component, `useRun()` hook returning `{ data, runId, role, setRole, runs, roles, section, goTo, refresh, act, uploadAct }` — every page component in Phases 1-3 consumes this instead of reading `state.data` directly.

- [ ] **Step 1: Write `RunContext.tsx`**, porting `app.js:10-17` (state shape), `71-84` (`ensureRun`), `92-102` (`refresh`), `104-118` (`act`):

```tsx
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { apiGet, apiPost, apiUpload } from '../api'
import type { RunState, RoleInfo } from '../types'

interface RunContextValue {
  data: RunState | null
  runId: string | null
  role: string
  setRole: (role: string) => void
  runs: string[]
  roles: RoleInfo[]
  section: string
  goTo: (section: string) => void
  refresh: () => Promise<void>
  act: (path: string, body?: Record<string, unknown>, okMessage?: string) => Promise<boolean>
  uploadAct: (path: string, form: FormData, okMessage?: string) => Promise<boolean>
  toast: { message: string; isError: boolean } | null
}

const RunContext = createContext<RunContextValue | null>(null)

export function RunProvider({ children }: { children: ReactNode }) {
  const [runId, setRunId] = useState<string | null>(localStorage.getItem('s7cc.runId'))
  const [role, setRoleState] = useState(localStorage.getItem('s7cc.role') || 'delivery_lead')
  const [section, setSection] = useState(localStorage.getItem('s7cc.section') || 'overview')
  const [data, setData] = useState<RunState | null>(null)
  const [runs, setRuns] = useState<string[]>([])
  const [roles, setRoles] = useState<RoleInfo[]>([])
  const [toast, setToast] = useState<{ message: string; isError: boolean } | null>(null)

  const showToast = useCallback((message: string, isError = false) => {
    setToast({ message, isError })
    setTimeout(() => setToast(null), 3200)
  }, [])

  const setRole = useCallback((next: string) => {
    setRoleState(next)
    localStorage.setItem('s7cc.role', next)
  }, [])

  const goTo = useCallback((next: string) => {
    setSection(next)
    localStorage.setItem('s7cc.section', next)
  }, [])

  const ensureRun = useCallback(async (): Promise<string> => {
    const list = await apiGet<string[]>('/api/runs')
    setRuns(list)
    if (runId && list.includes(runId)) return runId
    if (list.length) {
      const last = list[list.length - 1]
      setRunId(last)
      localStorage.setItem('s7cc.runId', last)
      return last
    }
    const created = await apiPost<{ run: { run_id: string } } & RunState>('/api/runs', { mode: 'simulation' })
    setRunId(created.run.run_id)
    localStorage.setItem('s7cc.runId', created.run.run_id)
    return created.run.run_id
  }, [runId])

  const refresh = useCallback(async () => {
    try {
      const id = await ensureRun()
      const [freshRuns, freshData] = await Promise.all([
        apiGet<string[]>('/api/runs'),
        apiGet<RunState>(`/api/runs/${id}`),
      ])
      setRuns(freshRuns)
      setData(freshData)
    } catch (err) {
      showToast(`Could not load run state: ${(err as Error).message}`, true)
    }
  }, [ensureRun, showToast])

  const act = useCallback(async (path: string, body: Record<string, unknown> = {}, okMessage = 'Done') => {
    try {
      const next = await apiPost<RunState>(`/api/runs/${runId}${path}`, { role, ...body })
      setData(next)
      showToast(okMessage)
      return true
    } catch (err) {
      showToast((err as Error).message, true)
      return false
    }
  }, [runId, role, showToast])

  const uploadAct = useCallback(async (path: string, form: FormData, okMessage = 'Done') => {
    form.append('role', role)
    try {
      const next = await apiUpload<RunState>(`/api/runs/${runId}${path}`, form)
      setData(next)
      showToast(okMessage)
      return true
    } catch (err) {
      showToast((err as Error).message, true)
      return false
    }
  }, [runId, role, showToast])

  useEffect(() => {
    apiGet<RoleInfo[]>('/api/roles').then(setRoles).catch(() => setRoles([]))
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <RunContext.Provider value={{ data, runId, role, setRole, runs, roles, section, goTo, refresh, act, uploadAct, toast }}>
      {children}
    </RunContext.Provider>
  )
}

export function useRun(): RunContextValue {
  const ctx = useContext(RunContext)
  if (!ctx) throw new Error('useRun must be used within a RunProvider')
  return ctx
}
```

**Note on `uploadAct`'s form field:** it must NOT set `Content-Type` — `apiUpload` already skips that header for `FormData` bodies (Task 1.2), so the browser sets the multipart boundary itself. This mirrors `app.js:396`'s `headers: {}` override.

- [ ] **Step 2: Type-check**

Run: `cd apps/control/web && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add apps/control/web/src/state/RunContext.tsx
git commit -m "control: add RunContext replacing the vanilla-JS state singleton"
```

---

### Task 1.4: `Header`, `Stepper`, `SideNav`, `Toast`, `Badge` components + `App.tsx` shell

**Files:**
- Create: `apps/control/web/src/components/Badge.tsx`
- Create: `apps/control/web/src/components/Toast.tsx`
- Create: `apps/control/web/src/components/Stepper.tsx`
- Create: `apps/control/web/src/components/SideNav.tsx`
- Create: `apps/control/web/src/components/Header.tsx`
- Modify: `apps/control/web/src/App.tsx` (replace the Task 0.4 stub)

**Interfaces:**
- Consumes: `useRun()` (Task 1.3), `RunState`/`Gate` types (Task 1.1)
- Produces: `Badge`, `Prov` components used by every later page; `App` wraps `RunProvider` and renders the full shell, with a page-map dispatch matching `app.js:777-802`.

- [ ] **Step 1: Write `Badge.tsx`**, porting `app.js:39-45`:

```tsx
export function Badge({ status }: { status?: string }) {
  const label = String(status ?? 'not_started')
  return <span className={`badge st-${label}`}>{label.replaceAll('_', ' ')}</span>
}

export function Prov({ provenance }: { provenance?: string }) {
  if (!provenance) return null
  return <span className={`prov prov-${provenance}`}>{provenance.toUpperCase()}</span>
}
```

- [ ] **Step 2: Write `Toast.tsx`**, porting `app.js:47-54`:

```tsx
import { useRun } from '../state/RunContext'

export function Toast() {
  const { toast } = useRun()
  return (
    <div className={`toast${toast ? ' show' : ''}${toast?.isError ? ' error' : ''}`} role="status" aria-live="polite">
      {toast?.message ?? ''}
    </div>
  )
}
```

- [ ] **Step 3: Write `Stepper.tsx`**, porting `app.js:122-128` (`STAGES`) and `224-250` (the render loop) and `168-171` (`GROUPS` landing sections):

```tsx
import { useRun } from '../state/RunContext'

const STAGES: [string, string][] = [
  ['intake', 'Intake'],
  ['planning', 'Planning'],
  ['build_review', 'Build & Review'],
  ['quality', 'Quality'],
  ['release', 'Release'],
]

const GROUP_LANDING: Record<string, string> = {
  planning: 'epic_to_stories',
  build_review: 'build_work_queue',
}

export function Stepper() {
  const { data, goTo } = useRun()
  const stages = data?.run?.stages ?? []

  return (
    <nav className="stepper" aria-label="Delivery stages">
      {stages.map((s, i) => {
        const label = STAGES.find(([k]) => k === s.stage)?.[1] ?? s.stage
        const statusLabel = s.status === 'completed' ? 'Completed'
          : s.status === 'not_started' ? 'Pending'
          : s.status.replaceAll('_', ' ').replace(/^./, (c) => c.toUpperCase())
        const prev = i > 0 ? stages[i - 1] : null
        return (
          <div key={s.stage} style={{ display: 'contents' }}>
            {prev && <span className={`step-arrow ${prev.status === 'completed' ? 'done' : ''}`} aria-hidden="true" />}
            <button
              type="button"
              className={`step ${s.status}`}
              onClick={() => goTo(GROUP_LANDING[s.stage] ?? s.stage)}
            >
              <span className="check">✓</span>
              <span className="dot">{i + 1}</span>
              <span className="step-txt">
                <span>{label}</span>
                <span className="step-sub">{statusLabel}</span>
              </span>
            </button>
          </div>
        )
      })}
    </nav>
  )
}
```

- [ ] **Step 4: Write `SideNav.tsx`**, porting `app.js:130-171` (`PLANNING_SUBS`, `BUILD_SUBS`, `NAV`, `GROUPS`) and `252-280` (render loop):

```tsx
import { useRun } from '../state/RunContext'

const PLANNING_SUBS: [string, string][] = [
  ['epic_to_stories', 'Epic to Stories'],
  ['dependency_map', 'Dependency Map'],
  ['routing_by_team', 'Routing by Team'],
  ['plan_summary', 'Plan Summary'],
  ['plan_signoff', 'Plan Sign-off'],
]
const BUILD_SUBS: [string, string][] = [
  ['build_work_queue', 'Work Queue'],
  ['dev_progress', 'Development Progress'],
  ['test_evidence', 'Test Evidence'],
  ['independent_review', 'Independent Review'],
]
const NAV: [string, string, string?][] = [
  ['nav-run', 'Run'],
  ['overview', 'Overview', '▦'],
  ['intake', 'Intake', '⭳'],
  ['planning', 'Planning', '▤'],
  ['build_review', 'Build & Review', '⚒'],
  ['quality', 'Quality', '✓'],
  ['release', 'Release', '➤'],
  ['nav-detail', 'Detail'],
  ['stories', 'Epics & Stories', '❖'],
  ['traceability', 'Traceability', '⇄'],
  ['artifacts', 'Artifacts', '▣'],
  ['approvals', 'Approvals', '✍'],
  ['nav-gov', 'Governance'],
  ['activity', 'Activity Log', '◷'],
  ['provenance', 'Provenance', '⛓'],
  ['risks', 'Risks & Alerts', '⚠'],
  ['reports', 'Reports', '▥'],
  ['settings', 'Settings', '⚙'],
]
const GROUPS: Record<string, { subs: [string, string][]; sections: Set<string>; landing: string }> = {
  planning: { subs: PLANNING_SUBS, sections: new Set(['planning', ...PLANNING_SUBS.map(([k]) => k)]), landing: 'epic_to_stories' },
  build_review: { subs: BUILD_SUBS, sections: new Set(['build_review', ...BUILD_SUBS.map(([k]) => k)]), landing: 'build_work_queue' },
}

export function SideNav() {
  const { section, goTo } = useRun()
  return (
    <nav className="sidenav" aria-label="Sections">
      {NAV.map(([key, label, icon]) => {
        if (key.startsWith('nav-')) {
          return <div className="nav-group" key={key}>{label}</div>
        }
        const group = GROUPS[key]
        const inGroup = Boolean(group && group.sections.has(section))
        return (
          <div key={key} style={{ display: 'contents' }}>
            <button
              type="button"
              className={key === section || inGroup ? 'active' : ''}
              onClick={() => goTo(group ? group.landing : key)}
            >
              {icon && <span className="nav-ico">{icon}</span>}
              {label}
              {group && <span className="caret">{inGroup ? '▲' : '▼'}</span>}
            </button>
            {group && inGroup && group.subs.map(([sub, subLabel]) => (
              <button
                key={sub}
                type="button"
                className={`sub ${sub === section ? 'active' : ''}`}
                onClick={() => goTo(sub)}
              >
                {subLabel}
              </button>
            ))}
          </div>
        )
      })}
    </nav>
  )
}
```

- [ ] **Step 5: Write `Header.tsx`**, porting `app.js:11-53` (the static markup from `index.html`) merged with `176-222` (dynamic wiring):

```tsx
import { useRun } from '../state/RunContext'
import { apiPost } from '../api'
import type { RunState } from '../types'

export function Header() {
  const { data, runs, runId, role, setRole, roles, refresh } = useRun()
  const run = data?.run

  const roleAvatar = role.split('_').map((w) => w[0]).join('').slice(0, 2).toUpperCase()

  return (
    <header className="top">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">MS</span>
        <div>
          <div className="brand-kicker">MapleSure Insurance</div>
          <h1>S7 Delivery Control Centre</h1>
        </div>
      </div>
      <div className="hdr-fields">
        <label className="hdr-field">
          <span className="hdr-label">Scenario</span>
          <select disabled value={data?.scenario?.title ?? ''}>
            <option>{data?.scenario?.title ?? '—'}</option>
          </select>
        </label>
        <div className="hdr-field">
          <span className="hdr-label">Run ID</span>
          <span className="run-id-wrap">
            <select
              className="mono"
              value={run?.run_id ?? ''}
              onChange={(e) => {
                localStorage.setItem('s7cc.runId', e.target.value)
                window.location.reload()
              }}
            >
              {runs.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <button
              type="button"
              className="icon-btn"
              title="Copy run id"
              aria-label="Copy run id"
              onClick={() => run && navigator.clipboard.writeText(run.run_id)}
            >⧉</button>
          </span>
        </div>
        <label className="hdr-field">
          <span className="hdr-label">Environment</span>
          <select
            value={run?.mode ?? 'simulation'}
            onChange={async (e) => {
              const mode = e.target.value
              if (mode === run?.mode) return
              const created = await apiPost<{ run: { run_id: string } } & RunState>('/api/runs', { mode })
              localStorage.setItem('s7cc.runId', created.run.run_id)
              window.location.reload()
            }}
          >
            <option value="simulation">Demo</option>
            <option value="replay">Replay</option>
            <option value="live">Live</option>
          </select>
        </label>
      </div>
      <div className="top-controls">
        <span className="pill safe" title="No IDE, terminal, prompts, credentials or raw logs are exposed on this surface">✓ Customer-safe view</span>
        <div className="hdr-clock">
          <span>{new Date().toLocaleTimeString()}</span>
          <button type="button" className="icon-btn" title="Re-fetch run state" aria-label="Refresh" onClick={() => refresh()}>⟳</button>
        </div>
        <div className="hdr-user">
          <span className="role-avatar" aria-hidden="true">{roleAvatar}</span>
          <label className="role-select">
            <select aria-label="Acting role" value={role} onChange={(e) => setRole(e.target.value)}>
              {roles.map((r) => (
                <option key={r.role} value={r.role}>{r.role.replaceAll('_', ' ')}</option>
              ))}
            </select>
          </label>
        </div>
      </div>
    </header>
  )
}
```

- [ ] **Step 6: Rewrite `App.tsx`**, replacing the Task 0.4 stub, porting `app.js:59-70` (`<div class="layout">`), `74` (footer markup from `index.html:74-97`), and the `RENDERERS`/`render()` dispatch (`app.js:777-802`, `3089+`) — with only `overview` wired to a real page; every other key uses the `NotYetPorted` placeholder until Phases 2-3 land:

```tsx
import { RunProvider, useRun } from './state/RunContext'
import { Header } from './components/Header'
import { Stepper } from './components/Stepper'
import { SideNav } from './components/SideNav'
import { Toast } from './components/Toast'
import { NotYetPorted } from './components/NotYetPorted'
import { Overview } from './pages/Overview'

const PAGES: Record<string, () => React.ReactElement> = {
  overview: Overview,
  // intake: IntakePage,               — wired in Task 2.7
  // epic_to_stories: EpicToStories,   — wired in Phase 3
  // ...remaining Phase-3 pages wired as each is ported
}

function Shell() {
  const { section } = useRun()
  const Page = PAGES[section] ?? (() => <NotYetPorted section={section} />)
  return (
    <>
      <Header />
      <Stepper />
      <div className="layout">
        <SideNav />
        <main id="main">
          <Page />
        </main>
      </div>
      <Toast />
      <footer className="foot">
        <div className="foot-row">
          <span className="foot-brand">S7 Delivery Control Centre&ensp;·&ensp;v2.1.0&ensp;·&ensp;🛡 Secure</span>
          <span className="foot-badges">
            <span className="foot-badge">👥 Governed</span>
            <span className="foot-badge">⛓ Traceable</span>
            <span className="foot-badge">✍ Human-approved</span>
            <span className="foot-badge">▤ Audit-ready</span>
            <span className="foot-badge">✓ Release-safe</span>
          </span>
          <span className="foot-right">Demo Environment</span>
        </div>
        <div className="foot-row small">
          <span className="foot-ai">AI generated · Rules validated · Human governed · Evidence recorded</span>
          <span className="foot-center">
            MapleSure Insurance is fictional; all data on this surface is demonstration data. Artifacts are
            labelled with their provenance — <span className="prov prov-simulated">SIMULATED</span> evidence is
            produced by the deterministic demo engine, <span className="prov prov-human">HUMAN</span> marks a
            person's own input. All times in local time.
          </span>
        </div>
      </footer>
    </>
  )
}

export default function App() {
  return (
    <RunProvider>
      <Shell />
    </RunProvider>
  )
}
```

- [ ] **Step 7: Write `NotYetPorted.tsx`** (dev-only placeholder, not shipped past Phase 3 — Task 4.3's checklist confirms zero uses remain before cutover):

```tsx
export function NotYetPorted({ section }: { section: string }) {
  return (
    <section>
      <div className="section-title"><h2>{section}</h2></div>
      <div className="card warn">
        <h3>Not yet ported to React</h3>
        <p>This section still exists in the vanilla-JS Control Centre (`apps/control/static/app.js`) and has not been migrated to the new React app yet. It is not user-visible — production continues to serve the vanilla app until every section is ported (see the migration plan's Phase 4).</p>
      </div>
    </section>
  )
}
```

- [ ] **Step 8: Type-check**

Run: `cd apps/control/web && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add apps/control/web/src/components apps/control/web/src/App.tsx
git commit -m "control: React app shell — header, stepper, sidenav, footer, page dispatch"
```

---

### Task 1.5: Port `Overview` and verify the shell end to end

**Files:**
- Create: `apps/control/web/src/pages/Overview.tsx`

**Interfaces:**
- Consumes: `useRun()` (Task 1.3), `Badge` (Task 1.4)
- Produces: `Overview` component, registered in `App.tsx`'s `PAGES` map (already referenced in Task 1.4 Step 6).

- [ ] **Step 1: Write `Overview.tsx`**, porting `app.js:310-353` exactly (same classes, same structure):

```tsx
import { useRun } from '../state/RunContext'
import { Badge } from '../components/Badge'

export function Overview() {
  const { data } = useRun()
  if (!data) return null
  const run = data.run
  const summary = data.activity_summary ?? {}
  const counters = summary.counters ?? {}
  const gates = data.gates ?? []

  return (
    <section>
      <div className="section-title">
        <h2>Delivery overview</h2>
        <span className="hint">{data.scenario?.title ?? ''}</span>
      </div>
      <div className="grid cols-4">
        <div className="card metric"><div className="v">{data.provenance?.length ?? 0}</div><div className="l">Artifacts</div></div>
        <div className="card metric"><div className="v">{counters.human_approvals ?? 0}</div><div className="l">Human approvals</div></div>
        <div className="card metric"><div className="v">{counters.gate_failures ?? 0}</div><div className="l">Gate failures</div></div>
        <div className="card metric"><div className="v">{summary.total_events ?? 0}</div><div className="l">Activity events</div></div>
      </div>
      <div className="section-title"><h2>Gates</h2><span className="hint">Progress is a set of explicit conditions, never a score</span></div>
      <div className="gate-strip">
        {gates.map((g) => (
          <div className="gate-card" key={g.gate_id}>
            <div className="gid">{g.gate_id}</div>
            <div className="glabel">{g.label}</div>
            <Badge status={g.status} />
            {g.decided_by && <div className="hint">by {g.decided_by}</div>}
          </div>
        ))}
      </div>
      <div className="section-title"><h2>Scenario</h2></div>
      <div className="card">
        <div className="kv">
          <b>Scenario</b><span>{data.scenario?.title ?? '—'}</span>
          <b>Description</b><span>{data.scenario?.description ?? '—'}</span>
          <b>Epic source</b><code>{data.scenario?.epic_source ?? '—'}</code>
          <b>Run created</b><span>{run.created_at}</span>
        </div>
      </div>
    </section>
  )
}
```

- [ ] **Step 2: Type-check and build**

Run: `cd apps/control/web && npx tsc -b --noEmit && npm run build`
Expected: no errors, `dist/` produced.

- [ ] **Step 3: Manual verification against the real backend**

Run: `demo/run_control.sh &` (starts FastAPI on :8720), then `cd apps/control/web && npm run dev`
Then load `http://127.0.0.1:5173/` — use the `run` skill or Chrome MCP per the project's "verify each UI step live" convention.
Expected: header shows MapleSure branding and a real run ID from `/api/runs`; stepper shows 5 stages with correct statuses; sidenav shows all groups; Overview renders real artifact/approval/gate-failure counts and the gate strip populated from the live backend — not mocked data. Click each sidenav item that isn't `overview` and confirm `NotYetPorted` renders without a console error.

- [ ] **Step 4: Commit**

```bash
git add apps/control/web/src/pages/Overview.tsx
git commit -m "control: port Overview page, verifying the shell end to end"
```

---

# Phase 2 — Intake page redesign

This is the actual visual redesign — the reference screenshot's information architecture, built as reusable components per the "Design decision" section above.

### Task 2.1: `IntakePage.tsx` shell and layout

**Files:**
- Create: `apps/control/web/src/pages/intake/IntakePage.tsx`
- Modify: `apps/control/web/src/theme.css` (add the layout/panel styles listed in Step 2)
- Modify: `apps/control/web/src/App.tsx` (register `intake: IntakePage` in `PAGES`)

**Interfaces:**
- Consumes: `useRun()`, `Requirement`/`RequirementExtraction` types
- Produces: the page frame — header (title, subtitle, Epic ID), 42/58 two-column grid, bottom info bar — that Tasks 2.2-2.6 fill in.

- [ ] **Step 1: Write `IntakePage.tsx`**

```tsx
import { useRun } from '../../state/RunContext'
import { SourceRequirementCard } from './SourceRequirementCard'
import { ExtractionCard } from './ExtractionCard'
import { AiActivityPanel } from './AiActivityPanel'
import { AdvancedAnalysisSection } from './AdvancedAnalysisSection'

export function IntakePage() {
  const { data } = useRun()
  if (!data) return null
  const epic = data.intake?.epic

  return (
    <section className="page-with-rail intake-page">
      <div>
        <div className="page-head intake-head">
          <div>
            <h2>Intake — Requirement Input</h2>
            <p className="hint">Upload your business epic or requirement. AI will extract key information and structure it for planning.</p>
          </div>
          <div className="epic-id-chip">
            <span className="hdr-label">Epic ID</span>
            {epic ? <span className="mono">{epic.epic_id}</span> : <span className="hint">Not created</span>}
          </div>
        </div>

        <div className="intake-grid">
          <SourceRequirementCard />
          <span className="intake-arrow" aria-hidden="true">→</span>
          <ExtractionCard />
        </div>

        <AdvancedAnalysisSection />

        <div className="card info-bar">
          <p>The extracted epic will be used by AI Planner to create stories, acceptance criteria, dependencies and route work to teams.</p>
        </div>
      </div>
      <AiActivityPanel />
    </section>
  )
}
```

- [ ] **Step 2: Add layout CSS to `theme.css`**, matching the existing design language (square corners, hairline borders, warm ink, red accent) rather than inventing new visual conventions:

```css
/* --- intake redesign ------------------------------------------------------*/

.intake-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.epic-id-chip { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; }

.intake-grid {
  display: grid;
  grid-template-columns: 42fr auto 58fr;
  align-items: start;
  gap: 20px;
  margin: 20px 0;
}
.intake-arrow {
  align-self: center;
  font-size: 22px;
  color: var(--red);
  padding-top: 60px;
}
@media (max-width: 980px) {
  .intake-grid { grid-template-columns: 1fr; }
  .intake-arrow { display: none; }
}

.info-bar { background: var(--surface-2); border-color: var(--border); }
.info-bar p { color: var(--muted); font-size: 13.5px; }
```

- [ ] **Step 3: Register the page in `App.tsx`**

In `apps/control/web/src/App.tsx`, add the import and map entry:

```tsx
import { IntakePage } from './pages/intake/IntakePage'
// ...
const PAGES: Record<string, () => React.ReactElement> = {
  overview: Overview,
  intake: IntakePage,
}
```

- [ ] **Step 4: Type-check** (components it imports don't exist yet — expected to fail until Task 2.5; note this and proceed, or stub empty exports for `SourceRequirementCard`/`ExtractionCard`/`AiActivityPanel`/`AdvancedAnalysisSection` returning `null` so the build passes now and each subsequent task fills one in)

Run: `cd apps/control/web && npx tsc -b --noEmit`
Expected: passes once the four stub components below exist.

Create minimal stubs so this task is independently testable:
`SourceRequirementCard.tsx`: `export function SourceRequirementCard() { return <div className="card">TODO</div> }`
`ExtractionCard.tsx`: `export function ExtractionCard() { return <div className="card">TODO</div> }`
`AiActivityPanel.tsx`: `export function AiActivityPanel() { return <aside className="rail" /> }`
`AdvancedAnalysisSection.tsx`: `export function AdvancedAnalysisSection() { return null }`

- [ ] **Step 5: Commit**

```bash
git add apps/control/web/src/pages/intake apps/control/web/src/theme.css apps/control/web/src/App.tsx
git commit -m "control: Intake page layout shell (42/58 grid, header, info bar)"
```

---

### Task 2.2: `SourceRequirementCard` — upload/paste tabs

**Files:**
- Modify: `apps/control/web/src/pages/intake/SourceRequirementCard.tsx` (replace the Task 2.1 stub)
- Modify: `apps/control/web/src/theme.css` (dropzone + file-chip styles)

**Interfaces:**
- Consumes: `useRun()` — reads `data.intake?.source`; calls `uploadAct('/intake/upload-source', form)` and `act('/intake/paste-source', { text })`
- Produces: `SourceRequirementCard` — no props (reads context directly), matching the pattern every Intake sub-component in this phase uses.

- [ ] **Step 1: Write the component**

```tsx
import { useRef, useState } from 'react'
import { useRun } from '../../state/RunContext'

const ACCEPT = '.txt,.md,.pdf,.docx'
const MAX_BYTES = 10 * 1024 * 1024

function extForName(name: string) {
  return name.split('.').pop()?.toUpperCase() ?? 'FILE'
}

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

export function SourceRequirementCard() {
  const { data, uploadAct, act } = useRun()
  const [tab, setTab] = useState<'upload' | 'paste'>('upload')
  const [dragOver, setDragOver] = useState(false)
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [pasteText, setPasteText] = useState('')
  const [busy, setBusy] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const source = data?.intake?.source

  async function submitFile(file: File) {
    if (file.size > MAX_BYTES) return
    setBusy(true)
    const form = new FormData()
    form.append('file', file)
    await uploadAct('/intake/upload-source', form, `${file.name} extracted`)
    setBusy(false)
    setPendingFile(null)
  }

  function handleFiles(files: FileList | null) {
    const file = files?.[0]
    if (!file) return
    setPendingFile(file)
    submitFile(file)
  }

  async function submitPaste() {
    if (!pasteText.trim()) return
    setBusy(true)
    await act('/intake/paste-source', { text: pasteText }, 'Text extracted')
    setBusy(false)
  }

  return (
    <div className="card">
      <h3>1. Source Requirement</h3>
      <p className="hint">Upload file or paste requirement text</p>
      <div className="tabs" style={{ marginTop: 10 }}>
        <button type="button" className={tab === 'upload' ? 'on' : ''} onClick={() => setTab('upload')}>Upload File</button>
        <button type="button" className={tab === 'paste' ? 'on' : ''} onClick={() => setTab('paste')}>Paste Text</button>
      </div>

      {tab === 'upload' ? (
        <div>
          <div
            className={`dropzone${dragOver ? ' drag-over' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files) }}
          >
            <div className="dropzone-icon" aria-hidden="true">⬆</div>
            <p>Drag &amp; drop your file here</p>
            <p className="hint">or</p>
            <button type="button" className="outline" onClick={() => inputRef.current?.click()}>Browse File</button>
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT}
              style={{ display: 'none' }}
              onChange={(e) => handleFiles(e.target.files)}
            />
            <p className="hint" style={{ marginTop: 10 }}>Supported formats: PDF, DOCX, TXT, MD</p>
            <p className="hint">Max file size: 10 MB</p>
          </div>

          {(pendingFile || source?.filename) && (
            <div className="file-row">
              <span className="chip tag">{extForName(pendingFile?.name ?? source?.filename ?? '')}</span>
              <span className="mono">{pendingFile?.name ?? source?.filename}</span>
              {pendingFile && <span className="hint">{formatBytes(pendingFile.size)}</span>}
              {busy ? <span className="hint">Uploading…</span> : source && <span className="prov prov-human">✓ Uploaded</span>}
            </div>
          )}
          {source && !source.filename && (
            <div className="file-row">
              <span className="mono">(pasted text)</span>
              <span className="chip tag">{source.text.length.toLocaleString()} chars</span>
            </div>
          )}
        </div>
      ) : (
        <div>
          <label className="fld" htmlFor="intake-paste">Paste epic / requirement</label>
          <textarea
            id="intake-paste"
            rows={8}
            placeholder="Paste your business epic, change request or requirement here…"
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
          />
          <button type="button" className="primary sq block" style={{ marginTop: 10 }} disabled={busy || !pasteText.trim()} onClick={submitPaste}>
            Extract with AI
          </button>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Add dropzone/file-chip CSS to `theme.css`**

```css
.dropzone {
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-md);
  padding: 32px 20px;
  text-align: center;
  background: var(--surface-2);
}
.dropzone.drag-over { border-color: var(--red); background: var(--red-pale); }
.dropzone-icon { font-size: 28px; color: var(--muted); margin-bottom: 6px; }
.dropzone p { margin: 2px 0; }

.file-row {
  display: flex; align-items: center; gap: 10px;
  margin-top: 10px; padding: 8px 10px;
  border: 1px solid var(--border); background: var(--surface-2);
}
```

- [ ] **Step 3: Type-check**

Run: `cd apps/control/web && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 4: Manual verification**

With `npm run dev` and `demo/run_control.sh` both running, navigate to Intake, drag a `.txt` file onto the dropzone — confirm it uploads and the file chip shows "✓ Uploaded". Switch to Paste Text, paste a paragraph, click "Extract with AI" — confirm `data.intake.source` updates (visible once Task 2.3 renders the extraction result).

- [ ] **Step 5: Commit**

```bash
git add apps/control/web/src/pages/intake/SourceRequirementCard.tsx apps/control/web/src/theme.css
git commit -m "control: Intake Source Requirement panel — upload/paste tabs, dropzone"
```

---

### Task 2.3: `ExtractionCard` — the six AI-extraction states

**Files:**
- Modify: `apps/control/web/src/pages/intake/ExtractionCard.tsx` (replace the Task 2.1 stub)
- Modify: `apps/control/web/src/theme.css` (requirement-row + expand styles)

**Interfaces:**
- Consumes: `useRun()` — reads `data.intake?.source`, `data.intake?.extraction`, `data.run?.mode`; calls `act('/intake/re-extract')` for retry.
- Produces: `ExtractionCard`. Also renders the "Edit Extracted Epic" trigger button (opens the drawer built in Task 2.4 — trigger state is local `useState` here, drawer itself is a sibling component receiving `open`/`onClose` props).

**Six states, mapped directly from the backend fields already in `types.ts`:**
1. **Empty** — no `data.intake?.source` yet.
2. **Uploaded, not yet extracted** — cannot actually occur with the current backend (`upload-source`/`paste-source` always extract in the same call, confirmed in `server.py:259-296`), so this state is presentational-only, shown only mid-request via the `busy` flag `SourceRequirementCard` sets — handled here as "Extracting" below, not a separate persisted state.
3. **Extracting** — local `busy` state passed down (see Step 3's prop wiring in Task 2.1... actually simpler: lift `busy` into `IntakePage` via context-free prop drilling is unnecessary; `RunContext`'s `act`/`uploadAct` are async and the whole page can show a shared "extracting" indicator sourced from a small local hook). Implemented as a `useSyncedBusy()` local hook reading a ref set by `SourceRequirementCard` — **simplify:** track `extracting` in `IntakePage` local state and pass to both children as props, since the alternative (global busy in `RunContext`) would affect unrelated pages.
4. **Complete** — `data.intake?.extraction` present and `extraction.edited_by` is falsy.
5. **Failed** — `act`/`uploadAct` already surface failures via `toast`; the card also needs a retryable local error state since a failed extraction leaves `source` set but `extraction` absent.
6. **Edited** — `extraction.edited_by` present.

Because "extracting" is genuinely shared UI state between the left and right panels, revise Task 2.1/2.2 to lift it:

- [ ] **Step 1: Lift `extracting`/`extractError` state into `IntakePage.tsx`**, pass down as props

Modify `apps/control/web/src/pages/intake/IntakePage.tsx`:

```tsx
import { useState } from 'react'
import { useRun } from '../../state/RunContext'
import { SourceRequirementCard } from './SourceRequirementCard'
import { ExtractionCard } from './ExtractionCard'
import { AiActivityPanel } from './AiActivityPanel'
import { AdvancedAnalysisSection } from './AdvancedAnalysisSection'

export function IntakePage() {
  const { data } = useRun()
  const [extracting, setExtracting] = useState(false)
  const [extractError, setExtractError] = useState<string | null>(null)
  if (!data) return null
  const epic = data.intake?.epic

  return (
    <section className="page-with-rail intake-page">
      <div>
        <div className="page-head intake-head">
          <div>
            <h2>Intake — Requirement Input</h2>
            <p className="hint">Upload your business epic or requirement. AI will extract key information and structure it for planning.</p>
          </div>
          <div className="epic-id-chip">
            <span className="hdr-label">Epic ID</span>
            {epic ? <span className="mono">{epic.epic_id}</span> : <span className="hint">Not created</span>}
          </div>
        </div>

        <div className="intake-grid">
          <SourceRequirementCard
            extracting={extracting}
            onExtractStart={() => { setExtracting(true); setExtractError(null) }}
            onExtractEnd={(ok, message) => { setExtracting(false); if (!ok) setExtractError(message ?? 'Extraction failed') }}
          />
          <span className="intake-arrow" aria-hidden="true">→</span>
          <ExtractionCard extracting={extracting} extractError={extractError} onRetry={() => setExtractError(null)} />
        </div>

        <AdvancedAnalysisSection />

        <div className="card info-bar">
          <p>The extracted epic will be used by AI Planner to create stories, acceptance criteria, dependencies and route work to teams.</p>
        </div>
      </div>
      <AiActivityPanel />
    </section>
  )
}
```

- [ ] **Step 2: Update `SourceRequirementCard`'s signature** to accept and call the new props (edit the file from Task 2.2: add `interface Props { extracting: boolean; onExtractStart: () => void; onExtractEnd: (ok: boolean, message?: string) => void }`, call `onExtractStart()` before `submitFile`/`submitPaste`'s `uploadAct`/`act` call and `onExtractEnd(ok, ok ? undefined : 'Extraction could not be completed')` after — `uploadAct`/`act` already return `boolean`, so this is a direct wire-through, not new logic).

- [ ] **Step 3: Write `ExtractionCard.tsx`**

```tsx
import { useState } from 'react'
import { useRun } from '../../state/RunContext'
import { Prov } from '../../components/Badge'
import { EditExtractionDrawer } from './EditExtractionDrawer'

interface Props {
  extracting: boolean
  extractError: string | null
  onRetry: () => void
}

export function ExtractionCard({ extracting, extractError, onRetry }: Props) {
  const { data, act } = useRun()
  const [expanded, setExpanded] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const source = data?.intake?.source
  const ext = data?.intake?.extraction
  const isLive = data?.run?.mode === 'live'

  const title = !source
    ? '2. AI Extraction'
    : ext
      ? (ext.method === 'live_llm' ? '2. AI Extraction (Completed)' : '2. Extraction (Rule-Based) (Completed)')
      : (ext ? '2. AI Extraction' : '2. AI Extraction')

  return (
    <div className="card">
      <div className="section-title">
        <h3>{title}</h3>
        {ext && !extracting && (
          <span className="chip priority-low">✓ {ext.method === 'live_llm' ? 'Extraction Complete' : 'Extraction Complete'}</span>
        )}
      </div>

      {!source && (
        <p className="hint">Upload or paste a requirement to begin.</p>
      )}

      {source && extracting && (
        <ul className="checklist">
          <li>Reading document…</li>
          <li>Extracting requirement…</li>
          <li>Structuring Epic…</li>
        </ul>
      )}

      {source && !extracting && extractError && !ext && (
        <div>
          <p className="hint">Extraction could not be completed.</p>
          <button type="button" className="outline" onClick={onRetry}>Retry Extraction</button>
        </div>
      )}

      {ext && !extracting && (
        <div>
          <p className="hint">AI has extracted and structured the requirement.</p>
          <div className="kv" style={{ gridTemplateColumns: '160px 1fr', marginTop: 10 }}>
            <b>Epic Title</b><span>{ext.epic_title}</span>
            <b>Business Objective</b><span>{ext.business_objective}</span>
            <b>Requirement Summary</b><span>{ext.requirement_summary}</span>
          </div>

          <h4 style={{ marginTop: 14, fontSize: 12.5, color: 'var(--muted)' }}>Extracted Requirements</h4>
          <ul className="plain req-rows">
            {ext.extracted_requirements.slice(0, expanded ? undefined : 3).map((r) => (
              <li key={r.rule_id} className="req-row">
                <span className="chip req-id">{r.rule_id}</span>
                <span>{r.text}</span>
              </li>
            ))}
          </ul>
          {ext.extracted_requirements.length > 3 && (
            <button type="button" className="link-btn" onClick={() => setExpanded((v) => !v)}>
              {expanded ? 'Show fewer requirements ↑' : 'View Full Extracted Content ↓'}
            </button>
          )}

          {ext.edited_by ? (
            <p className="hint" style={{ marginTop: 8 }}>
              <span className="chip tag">AI Generated • Human Edited</span>{' '}
              by {ext.edited_by} at {ext.edited_at}
            </p>
          ) : (
            <Prov provenance={ext.provenance} />
          )}

          <div className="actions-row" style={{ marginTop: 14 }}>
            <button type="button" className="outline" onClick={() => setDrawerOpen(true)}>✎ Edit Extracted Epic</button>
            <button
              type="button"
              className="primary sq"
              onClick={async () => {
                const ok = await act('/intake/finalize-epic', {}, 'Epic created')
                if (ok) await act('/intake/pass-gate', {}, 'Intake gate passed')
              }}
            >
              Create Epic &amp; Proceed to Planning →
            </button>
          </div>

          {!isLive && (
            <p className="hint" style={{ marginTop: 10 }}>
              Simulation mode demonstrates extraction from your actual document; downstream planning still
              follows the rehearsed demo scenario, exactly as it does for every run in simulation mode today.
            </p>
          )}
        </div>
      )}

      {ext && <EditExtractionDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} extraction={ext} />}
    </div>
  )
}
```

**Design note on the primary CTA's navigation:** unlike `app.js:522-523` (which called `go("epic_to_stories")` after `finalize-epic` alone), this version does not navigate automatically — it stays on Intake showing the now-passed gate implicitly via the Epic ID chip and the Stepper (Task 1.4) updating to show Intake as `completed`. The user clicks "Planning" in the Stepper or SideNav to proceed. Navigating automatically was considered but rejected: `finalize-epic` and `pass-gate` are two sequential network calls, and auto-navigating away mid-sequence (if `pass-gate` fails, e.g. a role permission edge case) would strand the user on a page that no longer reflects what happened. Surfacing both results and letting the human choose when to move on matches "App = where a human decides" more literally than the old auto-navigate did.

- [ ] **Step 4: Add requirement-row CSS**

```css
.req-rows { margin-top: 4px; }
.req-row { display: flex; gap: 10px; align-items: baseline; padding: 6px 0; border-bottom: 1px solid var(--border); }
.req-row:last-child { border-bottom: none; }
.chip.req-id { background: var(--green-pale); color: var(--green); font-weight: 600; }
.link-btn { background: none; border: none; color: var(--red); font-size: 13px; padding: 6px 0; text-decoration: underline; }
```

- [ ] **Step 5: Type-check**

Run: `cd apps/control/web && npx tsc -b --noEmit`
Expected: fails until `EditExtractionDrawer` exists — add a stub returning `null` for now, replaced in Task 2.4.

- [ ] **Step 6: Manual verification**

Upload a multi-requirement `.txt` file (simulation mode). Confirm: extracting state shows the three-line checklist briefly; on completion the structured fields and requirement rows render with green `REQ-*` chips; if more than 3 requirements, "View Full Extracted Content ↓" appears and expands/collapses; clicking "Create Epic & Proceed to Planning →" creates the epic (Epic ID chip populates) and the Stepper's Intake step flips to `completed`.

- [ ] **Step 7: Commit**

```bash
git add apps/control/web/src/pages/intake/IntakePage.tsx apps/control/web/src/pages/intake/SourceRequirementCard.tsx apps/control/web/src/pages/intake/ExtractionCard.tsx apps/control/web/src/theme.css
git commit -m "control: Intake AI Extraction panel — six-state rendering, bundled epic+gate CTA"
```

---

### Task 2.4: `EditExtractionDrawer` — right-side drawer

**Files:**
- Modify: `apps/control/web/src/pages/intake/EditExtractionDrawer.tsx` (replace stub)
- Modify: `apps/control/web/src/theme.css` (drawer styles — new pattern, none exists yet in this app)

**Interfaces:**
- Consumes: `useRun()` — calls `apiPatch`-backed `act`-equivalent for `/intake/extraction` (note: `RunContext.act` posts with `POST`; this needs `PATCH`, so this task adds a small `patchAct` helper alongside it, mirroring `act`'s error/toast handling exactly).
- Produces: `EditExtractionDrawer` — props `{ open: boolean; onClose: () => void; extraction: RequirementExtraction }`.

- [ ] **Step 1: Add `patchAct` to `RunContext.tsx`** (Task 1.3's file), same pattern as `act`:

```tsx
// add to RunContextValue interface:
  patchAct: (path: string, patch: Record<string, unknown>, okMessage?: string) => Promise<boolean>

// add to RunProvider, alongside `act`:
  const patchAct = useCallback(async (path: string, patch: Record<string, unknown>, okMessage = 'Saved') => {
    try {
      const next = await apiPatch<RunState>(`/api/runs/${runId}${path}`, { role, patch })
      setData(next)
      showToast(okMessage)
      return true
    } catch (err) {
      showToast((err as Error).message, true)
      return false
    }
  }, [runId, role, showToast])

// add `patchAct` to the returned context value object
```

- [ ] **Step 2: Write `EditExtractionDrawer.tsx`**, porting the field set from `app.js:404-442`'s modal (same three text fields + requirements-as-lines textarea, same `PATCH /intake/extraction` shape validated by `Engine.intake_edit_extraction` at `engine.py:633-664`), restyled as a right-side drawer per the spec's preference:

```tsx
import { useEffect, useState } from 'react'
import { useRun } from '../../state/RunContext'
import type { RequirementExtraction } from '../../types'

interface Props {
  open: boolean
  onClose: () => void
  extraction: RequirementExtraction
}

export function EditExtractionDrawer({ open, onClose, extraction }: Props) {
  const { patchAct } = useRun()
  const [title, setTitle] = useState(extraction.epic_title)
  const [objective, setObjective] = useState(extraction.business_objective)
  const [summary, setSummary] = useState(extraction.requirement_summary)
  const [reqText, setReqText] = useState(extraction.extracted_requirements.map((r) => r.text).join('\n'))
  const [saving, setSaving] = useState(false)

  // Reset local edit state whenever the drawer is (re)opened against fresh data —
  // avoids carrying stale edits from a previous open/close cycle.
  useEffect(() => {
    if (!open) return
    setTitle(extraction.epic_title)
    setObjective(extraction.business_objective)
    setSummary(extraction.requirement_summary)
    setReqText(extraction.extracted_requirements.map((r) => r.text).join('\n'))
  }, [open, extraction])

  if (!open) return null

  function resetToAiExtraction() {
    setTitle(extraction.epic_title)
    setObjective(extraction.business_objective)
    setSummary(extraction.requirement_summary)
    setReqText(extraction.extracted_requirements.map((r) => r.text).join('\n'))
  }

  async function save() {
    const lines = reqText.split('\n').map((t) => t.trim()).filter(Boolean)
    setSaving(true)
    const ok = await patchAct('/intake/extraction', {
      epic_title: title.trim(),
      business_objective: objective.trim(),
      requirement_summary: summary.trim(),
      extracted_requirements: lines.map((text, i) => ({ rule_id: `REQ-${String(i + 1).padStart(2, '0')}`, text })),
    }, 'Extraction updated')
    setSaving(false)
    if (ok) onClose()
  }

  return (
    <div className="drawer-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <aside className="drawer" role="dialog" aria-label="Edit Extracted Epic">
        <div className="card-head">
          <h3>Edit Extracted Epic</h3>
          <button type="button" className="kebab" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <p className="hint"><span className="chip tag">AI-generated — Editable</span></p>

        <label className="fld" htmlFor="edit-title">Epic Title</label>
        <input id="edit-title" type="text" value={title} onChange={(e) => setTitle(e.target.value)} />

        <label className="fld" htmlFor="edit-objective">Business Objective</label>
        <textarea id="edit-objective" rows={3} value={objective} onChange={(e) => setObjective(e.target.value)} />

        <label className="fld" htmlFor="edit-summary">Requirement Summary</label>
        <textarea id="edit-summary" rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} />

        <label className="fld" htmlFor="edit-reqs">Extracted Requirements (one per line)</label>
        <textarea id="edit-reqs" rows={8} value={reqText} onChange={(e) => setReqText(e.target.value)} />

        <div className="actions-row" style={{ marginTop: 14 }}>
          <button type="button" className="ghost" onClick={resetToAiExtraction}>Reset to AI Extraction</button>
          <button type="button" className="ghost" onClick={onClose}>Cancel</button>
          <button type="button" className="primary sq" disabled={saving || !title.trim() || !objective.trim() || !summary.trim()} onClick={save}>
            Save Changes
          </button>
        </div>
      </aside>
    </div>
  )
}
```

- [ ] **Step 3: Add drawer CSS**

```css
.drawer-overlay {
  position: fixed; inset: 0; background: rgba(54, 54, 47, 0.32);
  display: flex; justify-content: flex-end; z-index: 40;
}
.drawer {
  width: min(440px, 100%); height: 100%; background: var(--surface);
  border-left: 1px solid var(--border); box-shadow: var(--shadow);
  padding: 20px; overflow-y: auto;
  display: flex; flex-direction: column; gap: 10px;
}
.drawer input, .drawer textarea { width: 100%; margin-bottom: 8px; }
```

- [ ] **Step 4: Type-check**

Run: `cd apps/control/web && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 5: Manual verification**

Open the drawer from "✎ Edit Extracted Epic", change the epic title, click "Save Changes" — confirm the card updates to show "AI Generated • Human Edited" and the edited title. Reopen, click "Reset to AI Extraction" — confirm fields revert to the original AI values without a network call (local-only, per spec: "Changes should remain local to the current run until saved"). Click outside the drawer or "Cancel" — confirm it closes without persisting.

- [ ] **Step 6: Commit**

```bash
git add apps/control/web/src/state/RunContext.tsx apps/control/web/src/pages/intake/EditExtractionDrawer.tsx apps/control/web/src/theme.css
git commit -m "control: Edit Extracted Epic as a right-side drawer"
```

---

### Task 2.5: `AiActivityPanel`

**Files:**
- Modify: `apps/control/web/src/pages/intake/AiActivityPanel.tsx` (replace stub)

**Interfaces:**
- Consumes: `useRun()` — reads `data.intake?.source`, `data.intake?.extraction`, `data.intake?.epic` to derive the four customer-safe ticks; `goTo('activity')` to link to the (Phase-3-ported) Activity Log page.

- [ ] **Step 1: Write the component** — no raw prompts, chain-of-thought, CLI output, or model responses (spec's explicit exclusion list); only the four named execution events plus a link:

```tsx
import { useRun } from '../../state/RunContext'

export function AiActivityPanel() {
  const { data, goTo } = useRun()
  const source = data?.intake?.source
  const ext = data?.intake?.extraction
  const epic = data?.intake?.epic

  const steps: [string, boolean][] = [
    ['Document read', Boolean(source)],
    ['Content extracted', Boolean(ext)],
    ['Requirements structured', Boolean(ext?.extracted_requirements?.length)],
    ['Epic created', Boolean(epic)],
  ]

  return (
    <aside className="rail">
      <div className="card rail-card">
        <h3>AI Activity</h3>
        <p className="hint"><span className="chip priority-low">● Active</span></p>
        <ul className="checklist">
          {steps.map(([label, done]) => (
            <li key={label}>
              <span className={`tick ${done ? 'ok' : 'no'}`}>{done ? '✓' : '○'}</span>
              {done ? label : `${label} pending`}
            </li>
          ))}
        </ul>
        <button type="button" className="outline block" style={{ marginTop: 10 }} onClick={() => goTo('activity')}>
          View AI Activity Log
        </button>
      </div>
    </aside>
  )
}
```

- [ ] **Step 2: Type-check**

Run: `cd apps/control/web && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 3: Manual verification**

Confirm the four ticks flip from `○ ... pending` to `✓ ...` in order as a run progresses through upload → extract → (edit, optional) → create epic. Confirm "View AI Activity Log" navigates to the Activity section (shows `NotYetPorted` until Phase 3 — expected at this point in the plan).

- [ ] **Step 4: Commit**

```bash
git add apps/control/web/src/pages/intake/AiActivityPanel.tsx
git commit -m "control: Intake AI Activity panel — customer-safe execution ticks only"
```

---

### Task 2.6: `AdvancedAnalysisSection` — everything the screenshot excludes, preserved

**Files:**
- Modify: `apps/control/web/src/pages/intake/AdvancedAnalysisSection.tsx` (replace stub)

**Interfaces:**
- Consumes: `useRun()` — reads/writes everything `app.js:533-775`'s `renderIntake()` handled beyond the extraction front door: `analysis`, `req` (full requirement detail), `gate` (G0), `clar` (clarification), `repos`, `routing`, `newApp`/`scaffold`.

This is the direct, behavior-preserving port of the parts of the old `renderIntake()` this redesign's "Design decision" section (above) decided to keep but de-emphasize. Reuses the same CSS classes as the rest of the app (`.card`, `.kv`, `.checklist`, `.chip`) — **not** restyled, per "Do not redesign... unrelated" functionality.

- [ ] **Step 1: Write the component**, folding in `app.js:362-372` (`requirementDetail`), `374-381` (`documentList`), `580-631` (AI analysis/rules/epic cards), `600-615` (clarification), `634-682` (repos/routing), `684-726` (new-app), and the five rail buttons from `728-750`:

```tsx
import { useState } from 'react'
import { useRun } from '../../state/RunContext'
import { Prov } from '../../components/Badge'

export function AdvancedAnalysisSection() {
  const { data, act } = useRun()
  const [open, setOpen] = useState(false)
  const [clarAnswers, setClarAnswers] = useState<string[]>([])
  const [newAppAnswers, setNewAppAnswers] = useState<string[]>([])
  const [routeOverride, setRouteOverride] = useState('')
  const [repoUrl, setRepoUrl] = useState('')

  if (!data) return null
  const isLive = data.run?.mode === 'live'
  const req = data.intake?.requirement
  const analysis = data.intake?.analysis
  const gate = (data.gates ?? []).find((g) => g.gate_id === 'G0')
  const clar = data.intake?.clarifications
  const repos = data.intake?.repos ?? []
  const routing = data.intake?.routing
  const newApp = data.intake?.new_app
  const scaffold = data.intake?.scaffold

  return (
    <details className="card advanced-section" open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>Advanced: Live Analysis &amp; Governance</summary>
      <div style={{ marginTop: 14 }}>

        {req && (
          <div className="card" style={{ marginBottom: 12 }}>
            <div className="section-title"><h3>Requirement Summary</h3><Prov provenance={req.provenance} /></div>
            <div className="kv" style={{ gridTemplateColumns: '130px 1fr' }}>
              <b>Request ID</b><span className="mono">{req.request_id}</span>
              <b>Title</b><span>{req.title}</span>
              <b>Priority</b><span><span className={`chip priority-${(req.priority || 'low').toLowerCase()}`}>{req.priority}</span></span>
              <b>Business Owner</b><span>{req.business_owner}</span>
              <b>Domain</b><span>{req.domain}</span>
              <b>Description</b><span className="clamp-2">{req.description}</span>
            </div>
          </div>
        )}

        <div className="card" style={{ marginBottom: 12 }}>
          {analysis ? (
            <>
              <div className="section-title"><h3>AI Analysis (Completed)</h3><Prov provenance={analysis.provenance} /></div>
              <ul className="checklist">
                <li><span className={`tick ${analysis.problem_understood ? 'ok' : 'no'}`}>{analysis.problem_understood ? '✓' : '·'}</span>Problem understood</li>
                <li><span className="tick ok">✓</span>Affected applications <span className="state ok mono">{analysis.affected_applications.length}</span></li>
                <li><span className="tick ok">✓</span>Stakeholders <span className="state ok mono">{analysis.stakeholders.length}</span></li>
                <li><span className="tick ok">✓</span>Dependencies <span className="state ok mono">{analysis.dependencies.length}</span></li>
                <li><span className="tick ok">✓</span>Risks <span className="state ok mono">{analysis.risks.length}</span></li>
              </ul>
              {analysis.confidence != null && (
                <div className="conf-row"><b>AI Confidence</b><span className="info conf-v">{analysis.confidence}% ⓘ</span></div>
              )}
            </>
          ) : <p>No analysis yet — run the intake analysis.</p>}
        </div>

        {clar?.pending?.length ? (
          <div className="card" style={{ marginBottom: 12 }}>
            <div className="section-title"><h3>AI Clarification</h3><span className="chip">round {clar.rounds_used} of {clar.max_rounds}</span></div>
            {clar.pending.map((q, i) => (
              <div key={q} style={{ marginBottom: 8 }}>
                <p>{q}</p>
                <input
                  type="text"
                  placeholder="Answer (blank = stated assumption)"
                  value={clarAnswers[i] ?? ''}
                  onChange={(e) => setClarAnswers((prev) => { const next = [...prev]; next[i] = e.target.value; return next })}
                />
              </div>
            ))}
            <button type="button" className="primary sq" onClick={() => act('/intake/clarify-answer', { answers: clarAnswers }, 'Answers recorded')}>
              Submit answers
            </button>
          </div>
        ) : null}

        {isLive && (
          <div className="card" style={{ marginBottom: 12 }}>
            <div className="section-title"><h3>Connected Repositories</h3><span className="chip">{repos.length} connected</span></div>
            <ul className="plain">
              {repos.map((r) => (
                <li key={r.name}><span className="mono">{r.name}</span> <span className="hint">@ {r.head_sha.slice(0, 10)} · {r.file_count} files</span></li>
              ))}
            </ul>
            <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
              <input type="text" placeholder="https://github.com/<owner>/<repo>" value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} />
              <button type="button" className="outline" onClick={() => repoUrl.trim() && act('/intake/connect-repo', { url: repoUrl.trim() }, 'Repository connected')}>
                Connect repository
              </button>
            </div>
          </div>
        )}

        {isLive && (
          <div className="card" style={{ marginBottom: 12 }}>
            <div className="section-title"><h3>Requirement Routing</h3>{routing && <Prov provenance={routing.provenance} />}</div>
            {routing ? (
              <>
                <div className="kv" style={{ gridTemplateColumns: '130px 1fr' }}>
                  <b>Verdict</b>
                  <span><span className={`chip ${routing.verdict === 'routable' ? 'priority-low' : 'priority-high'}`}>
                    {routing.verdict === 'routable' ? 'Fits connected repos' : 'New application needed'}
                  </span></span>
                  <b>Reasoning</b><span>{routing.reasoning}</span>
                </div>
                <div style={{ marginTop: 10, display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span className="hint">Override:</span>
                  <select value={routeOverride || routing.verdict} onChange={(e) => setRouteOverride(e.target.value)}>
                    <option value="routable">Routable</option>
                    <option value="new_application_needed">New application needed</option>
                  </select>
                  <button type="button" className="outline" onClick={() => act('/intake/override-route', { verdict: routeOverride || routing.verdict }, 'Routing verdict overridden')}>
                    Apply override
                  </button>
                </div>
              </>
            ) : (
              <button type="button" className="outline block" onClick={() => act('/intake/route', {}, 'Requirement routed')}>Route Requirement</button>
            )}
          </div>
        )}

        {isLive && routing?.verdict === 'new_application_needed' && (
          <div className="card" style={{ marginBottom: 12 }}>
            <h3>New Application Setup</h3>
            {newApp?.name ? (
              <div className="kv" style={{ gridTemplateColumns: '130px 1fr' }}>
                <b>Name</b><span className="mono">{newApp.name}</span>
                <b>Description</b><span>{newApp.description}</span>
                <b>Stack</b><span>{newApp.stack}</span>
              </div>
            ) : newApp?.pending?.length ? (
              <div>
                {newApp.pending.map((q, i) => (
                  <div key={q} style={{ marginBottom: 8 }}>
                    <p>{q}</p>
                    <input type="text" placeholder="Answer" value={newAppAnswers[i] ?? ''}
                      onChange={(e) => setNewAppAnswers((prev) => { const next = [...prev]; next[i] = e.target.value; return next })} />
                  </div>
                ))}
                <button type="button" className="primary sq" onClick={() => act('/intake/new-app-answer', { answers: newAppAnswers }, 'Answers recorded')}>
                  Submit answers
                </button>
              </div>
            ) : (
              <button type="button" className="outline block" onClick={() => act('/intake/new-app-setup', {}, 'Setup started')}>
                Start New Application Setup
              </button>
            )}
            {newApp?.name && !scaffold && (
              <button type="button" className="outline block" style={{ marginTop: 10 }} onClick={() => act('/intake/generate-scaffold', {}, 'Scaffold generated')}>
                Generate Scaffold
              </button>
            )}
            {scaffold && (
              <button type="button" className="primary sq block" style={{ marginTop: 10 }} onClick={() => act('/intake/create-new-app-repo', {}, 'New application repository created')}>
                Create Repository
              </button>
            )}
          </div>
        )}

        <div className="card">
          <div className="section-title"><h3>Intake Gate (G0)</h3></div>
          <p className="hint">{gate?.status ?? 'not_started'}</p>
          <ul className="checklist">
            {(gate?.conditions ?? []).map((c) => (
              <li key={c.condition}><span className={`tick ${c.met ? 'ok' : 'no'}`}>{c.met ? '✓' : '·'}</span>{c.condition}</li>
            ))}
          </ul>
          <div className="actions-row" style={{ marginTop: 10 }}>
            {isLive && <button type="button" className="outline" onClick={() => act('/intake/clarify', {}, 'Clarifying questions requested')}>Ask AI Clarification</button>}
            <button type="button" className="outline" onClick={() => act('/intake/analyse', {}, isLive ? 'Live analysis regenerated' : 'Intake analysis regenerated')}>⟳ Regenerate Analysis</button>
            <button type="button" className="outline" onClick={() => act('/intake/create-epic', {}, 'Epic created')}>Generate Epic</button>
            <button type="button" className="outline approve" onClick={() => act('/intake/pass-gate', {}, 'Intake gate passed')}>✓ Pass Intake Gate</button>
          </div>
        </div>
      </div>
    </details>
  )
}
```

- [ ] **Step 2: Add `<details>` styling** to `theme.css` (summary as a clickable header matching `.card h3` typography, collapsed by default):

```css
.advanced-section > summary {
  cursor: pointer; font-weight: 600; font-size: 15px; color: var(--ink);
  list-style: none;
}
.advanced-section > summary::-webkit-details-marker { display: none; }
.advanced-section > summary::before { content: '▶ '; color: var(--muted); }
.advanced-section[open] > summary::before { content: '▼ '; }
.advanced-section { margin: 20px 0; }
```

- [ ] **Step 3: Type-check**

Run: `cd apps/control/web && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 4: Manual verification (both modes)**

In simulation mode: confirm the section is collapsed by default, expands to show Requirement Summary + AI Analysis + Intake Gate + rail buttons, and every button still works (Regenerate Analysis, Generate Epic, Pass Intake Gate) exactly as it did in the vanilla app. In live mode (`LLM_MODE=replay` per project convention): confirm Connected Repositories, Requirement Routing, and New Application Setup also render and their actions still call the same endpoints.

- [ ] **Step 5: Commit**

```bash
git add apps/control/web/src/pages/intake/AdvancedAnalysisSection.tsx apps/control/web/src/theme.css
git commit -m "control: preserve AI analysis/routing/clarification/gate UI in a collapsed advanced section"
```

---

### Task 2.7: Intake page integration test pass (manual, documented)

**Files:**
- Create: `docs/INTAKE_REDESIGN.md` (required by the original spec — documents the before/after, files changed, API surface, component structure)

**Interfaces:**
- Consumes: nothing new — this task is verification + documentation of Tasks 2.1-2.6.

- [ ] **Step 1: Write `docs/INTAKE_REDESIGN.md`** covering (concretely, not as a template — fill in each section with the actual state after Tasks 2.1-2.6 land):
  - Existing implementation: the vanilla-JS `renderIntake()` (`apps/control/static/app.js:533-775`) and its helpers — what it did before this plan.
  - Files changed: the full list from Tasks 2.1-2.6's **Files** blocks.
  - API surface: confirm zero backend routes added/changed — list the 16 existing `/intake/*` routes this page calls, unchanged.
  - State flow: `RunContext` → `IntakePage` → child components, with the `extracting`/`extractError` lift explained (Task 2.3 Step 1).
  - Component structure: the tree from `IntakePage` down to `EditExtractionDrawer`.
  - Test coverage: reference to Task 2.7 Step 2's manual pass and Phase 4's pytest re-run (no new pytest tests are added by this plan for the frontend — see the note on JS testing below).

- [ ] **Step 2: Run the full manual scenario walkthrough**, using the `run` skill / Chrome MCP per project convention ("verify each UI step live"), covering every item in the original spec's "FUNCTIONAL REQUIREMENTS" and "ACCEPTANCE CRITERIA" sections:
  - Upload File tab is the default on page load.
  - Paste Text can be selected and reverts correctly.
  - A `.txt`/`.md` file uploads, extracts, and populates the AI Extraction panel (real, not staged — simulation mode's rule-based parser).
  - An unsupported file type (e.g. `.png`) is rejected by the file input's `accept` attribute at the browser level; if forced via drag-drop, confirm the backend's existing 400 response surfaces as a toast, not a crash.
  - Extraction loading state (three-line checklist) is visible for the extraction's duration.
  - Extraction failure (simulate by stopping the backend mid-request, or reading `test_factory_intake_extraction.py`'s failure-mode tests) shows "Extraction could not be completed" with a working "Retry Extraction" button, no stack trace.
  - Edit Extracted Epic drawer opens, edits save via `PATCH /intake/extraction`, "AI Generated • Human Edited" badge appears afterward.
  - "Reset to AI Extraction" in the drawer reverts local edits without a network call.
  - "Create Epic & Proceed to Planning" is effectively disabled before extraction exists (the button only renders once `ext` is truthy — confirms acceptance criterion 	"Create Epic disabled before extraction").
  - After clicking it, Epic ID chip populates, Stepper's Intake stage shows `completed`, and Planning becomes reachable (still `NotYetPorted` at this point in the plan — Phase 3 lands it).
  - A page refresh (`F5`) preserves the extraction (backend persistence via `artifacts/runs/<run-id>/intake/extraction.json` — already true of the existing backend, `RunContext`'s `refresh()` on mount re-fetches it).
  - No IDE/CLI/model-reasoning text appears anywhere on the page (visually scan the Advanced section too).

- [ ] **Step 3: Commit**

```bash
git add docs/INTAKE_REDESIGN.md
git commit -m "docs: document the Intake page React redesign"
```

---

## Note on automated frontend tests

The original spec's "TESTS" section asks for automated coverage of upload/paste/extraction/edit/error states. This codebase's stated philosophy (`AGENTS.md` § Surfaces: *"the CLI... makes the ledger testable — text is assertable in pytest, DOM is not"*) has, until now, meant **zero DOM-level tests exist anywhere in this repo** — all 327 existing tests assert against the JSON API, never the rendered page. Adding a JS test runner (Vitest + React Testing Library) is a real option now that Vite exists, but it's a second tooling decision beyond "port to React," not implied by it. **This plan does not add one** — Task 2.7's manual walkthrough is the verification path, consistent with how every other page in this app has been verified to date. Flagging this explicitly rather than silently skipping the spec's test section: if automated DOM tests are wanted, that is a follow-up task (add `vitest` + `@testing-library/react` to `package.json`'s devDependencies, one `*.test.tsx` per component) that should be scoped and confirmed separately.

---

# Phase 3 — Port the remaining 19 pages (mechanical, codex-assisted)

**Every task in this phase follows the identical pattern**, verified by Phase 1's Overview port (Task 1.5) and reusable by any bulk-generation tool: reproduce the existing vanilla-JS function's DOM structure, CSS classes, copy and behavior as a React component — **no visual redesign**, since these pages are explicitly out of scope for the reference-screenshot redesign ("Do not redesign Planning, Build & Review, Quality, Release"). Each task is independently testable (loads without console errors, matches the vanilla version's rendered output and interactions) and independently committable.

Per the earlier decision on Codex's role: **codex exec generates each component from its source function; every one is reviewed, integrated, type-checked, and manually smoke-tested before commit** — same review bar as a human-written PR, not a delegated-and-trusted output.

| # | Source (`apps/control/static/app.js`) | Target file | Notes |
|---|---|---|---|
| 3.1 | `renderEpicToStories` (1285-1406) + `openAddStoryModal` (933-...) | `pages/planning/EpicToStories.tsx` | Largest single page in the app — split into sub-components if it exceeds ~300 lines, per this plan's file-structure guidance (small, focused files) |
| 3.2 | `renderDependencyMap` (1406-1490) | `pages/planning/DependencyMap.tsx` | |
| 3.3 | `renderRoutingByTeam` (1490-1576) | `pages/planning/RoutingByTeam.tsx` | |
| 3.4 | `renderPlanSummary` (1576-1727) | `pages/planning/PlanSummary.tsx` | |
| 3.5 | `renderPlanSignoff` (1727-1936) | `pages/planning/PlanSignoff.tsx` | |
| 3.6 | `renderBuildWorkQueue` (1936-2157) + `openTechnicalDetailModal` (2157-2184) | `pages/build/BuildWorkQueue.tsx` | |
| 3.7 | `renderDevProgress` (2184-2327) | `pages/build/DevProgress.tsx` | |
| 3.8 | `renderTestEvidence` (2327-2416) | `pages/build/TestEvidence.tsx` | |
| 3.9 | `renderIndependentReview` (2416-2567) | `pages/build/IndependentReview.tsx` | |
| 3.10 | `renderStories` (2567-2607) | `pages/Stories.tsx` | |
| 3.11 | `renderQuality` (2607-2676) | `pages/Quality.tsx` | |
| 3.12 | `renderRelease` (2676-2761) | `pages/Release.tsx` | |
| 3.13 | `renderTraceability` (2856-2892) | `pages/Traceability.tsx` | |
| 3.14 | `renderArtifacts` (2892-2914) | `pages/Artifacts.tsx` | |
| 3.15 | `renderProvenance` (2914-2940) | `pages/Provenance.tsx` | |
| 3.16 | `renderActivity` (2940-2970) | `pages/Activity.tsx` | |
| 3.17 | `renderApprovals` (2970-2995) + `renderApprovalMatrix`/`renderApprovalForm` (2761-2788) | `pages/Approvals.tsx` | |
| 3.18 | `renderRisks` (2788-2856) | `pages/Risks.tsx` | |
| 3.19 | `renderReports` (2995-3033) | `pages/Reports.tsx` | |
| 3.20 | `renderSettings` (3033-3089) | `pages/Settings.tsx` | |

**Each of Tasks 3.1-3.20:**

- [ ] **Step 1: Re-read the source function** at the given line range in `apps/control/static/app.js` (line numbers will drift slightly as earlier Phase-3 tasks are not expected to touch `app.js`, so they stay accurate — verify with `grep -n "function renderX"` before starting each task, since this table was generated before any Phase-3 task ran).
- [ ] **Step 2: Dispatch `codex exec`** with the source function's full text and this instruction: *"Port this vanilla-JS DOM-builder function to a React functional component. Preserve every CSS class name, every piece of copy, and every API call (same paths, same `act`/`uploadAct` semantics as `RunContext.tsx`) exactly. Do not redesign, restyle, or rename anything. Output a single `.tsx` file."* Provide `RunContext.tsx`, `types.ts`, and `Badge.tsx` as reference context.
- [ ] **Step 3: Review the generated component** against the source function line-by-line: every `el(...)` call has a corresponding JSX element with the same tag, class, and text; every `act(...)`/`api(...)` call maps to the same endpoint with the same body shape; every conditional (`?:`, `&&`, `.map()`) preserves the same show/hide logic.
- [ ] **Step 4: Type-check**

  Run: `cd apps/control/web && npx tsc -b --noEmit`
  Expected: no errors.

- [ ] **Step 5: Register the page** in `App.tsx`'s `PAGES` map (and any `GROUPS` sub-key it belongs to, already defined in `SideNav.tsx`/`Stepper.tsx` from Task 1.4 — no changes needed there since the key names are unchanged).
- [ ] **Step 6: Manual side-by-side smoke test** — load the same run in the old vanilla app (`demo/run_control.sh`) and the new React app (`npm run dev`) in two tabs, navigate both to the equivalent section, confirm visually identical rendering and that every button/input produces the same state change in both.
- [ ] **Step 7: Commit**

  ```bash
  git add apps/control/web/src/pages/<path>
  git commit -m "control: port <SectionName> to React (behavior-identical)"
  ```

---

# Phase 4 — Cutover

Only starts once every `PAGES` entry in `App.tsx` is real (zero remaining `NotYetPorted` uses in the normal navigation flow) and Phase 3's full side-by-side smoke pass is complete.

### Task 4.1: Switch `server.py`'s static mount to the built React app

**Files:**
- Modify: `apps/control/server.py` (lines 35, 622-625 per this plan's initial reading — re-verify exact line numbers at execution time)

**Interfaces:**
- Consumes: `apps/control/web/dist/` (built output from `npm run build`, Task 0.1's script)
- Produces: the production-served frontend switches from `static/` to `web/dist/`, with an SPA fallback so any client-side path still resolves to `index.html` (this app has no client-side routes today, so the fallback is defensive, matching S3's pattern rather than because it's strictly needed here).

- [ ] **Step 1: Build the production bundle**

  Run: `cd apps/control/web && npm run build`
  Expected: `apps/control/web/dist/` contains `index.html`, hashed JS/CSS assets, and `fonts/`.

- [ ] **Step 2: Edit `server.py`**

  Find (near the top, `STATIC_DIR` definition):
  ```python
  STATIC_DIR = Path(__file__).resolve().parent / "static"
  ```
  Replace with:
  ```python
  STATIC_DIR = Path(__file__).resolve().parent / "web" / "dist"
  ```

  Find (the mount at the bottom of the file):
  ```python
  # --- static shell -----------------------------------------------------------

  if STATIC_DIR.is_dir():
      app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="control")
  ```
  Replace with (adds an SPA history-mode fallback, matching `../ams-s3-demo`'s pattern referenced in its `api/main.py`, so a future client-side route addition doesn't require another backend change):
  ```python
  # --- static shell -----------------------------------------------------------
  #
  # The Control Centre has no client-side routes today (section switching is
  # in-memory React state, not the URL), so this fallback is defensive rather
  # than load-bearing — matches the sibling S3 console's api/main.py pattern
  # in case that changes later.

  if STATIC_DIR.is_dir():
      app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="control-assets")
      app.mount("/fonts", StaticFiles(directory=STATIC_DIR / "fonts"), name="control-fonts")

      @app.get("/{full_path:path}")
      async def _spa_fallback(full_path: str) -> FileResponse:
          candidate = STATIC_DIR / full_path
          if full_path and candidate.is_file():
              return FileResponse(candidate)
          return FileResponse(STATIC_DIR / "index.html")
  ```

  **Note:** this fallback route must be the **last** route FastAPI registers (Python route order matters — earlier `@app.get`/`@app.post` routes under `/api/...` still take precedence since FastAPI matches path templates, not just prefixes, but placing this at the literal end of the file, after every other route, avoids any ambiguity). Confirm no existing route uses a bare `/{full_path:path}` pattern before adding this (`grep -n 'full_path' apps/control/server.py` should show zero matches pre-edit).

- [ ] **Step 3: Verify the full pytest suite still passes** (this touches `server.py`, so it's the one Phase-4 step that can regress the backend)

  Run: `.venv/bin/python -m pytest tests/ -q`
  Expected: `327 passed` (or more, if Phase 0-3 added none — this plan adds no new pytest tests, confirmed in the Phase 2 note above) — same count as this plan's baseline run.

- [ ] **Step 4: Manual verification of the cutover**

  Run: `demo/run_control.sh` (now serving `web/dist/`)
  Load `http://127.0.0.1:8720/` directly (no Vite dev server involved) — confirm the full app loads and every page (all 5 stages + all sub-sections) renders and functions identically to the pre-cutover `npm run dev` smoke tests.

- [ ] **Step 5: Commit**

  ```bash
  git add apps/control/server.py apps/control/web/dist
  git commit -m "control: cut production over to the built React frontend"
  ```

  (Whether `dist/` is committed or gitignored-and-built-at-deploy-time is a call for the plan's reviewer — committing it matches hard rule 4's amended text in Task 0.5, "the sandbox runs the committed dist/ output", and guarantees a fresh clone with no `npm install` step still runs, mirroring the LLM-replay-recordings precedent in `CLAUDE.md` § Determinism. If the reviewer prefers a `.gitignore`'d `dist/` with a build step documented in `README.md` instead, flag that here before this task runs.)

---

### Task 4.2: Retire `apps/control/static/`

**Files:**
- Delete: `apps/control/static/app.js`, `apps/control/static/index.html`, `apps/control/static/styles.css`, `apps/control/static/fonts/`

**Interfaces:**
- Consumes: confirmation from Task 4.1 that nothing references `apps/control/static/` anymore.

- [ ] **Step 1: Search for any remaining reference to `apps/control/static`**

  Run: `grep -rn "apps/control/static\|apps\.control\.static" --include="*.py" --include="*.md" --include="*.sh" .`
  Expected: no matches outside this plan document and (if kept) the git history — `server.py`'s `STATIC_DIR` no longer points there after Task 4.1.

- [ ] **Step 2: Delete the directory**

  Run: `git rm -r apps/control/static`

- [ ] **Step 3: Re-run the full pytest suite**

  Run: `.venv/bin/python -m pytest tests/ -q`
  Expected: `327 passed` — confirms no test depended on the vanilla static files existing.

- [ ] **Step 4: Commit**

  ```bash
  git commit -m "control: remove the superseded vanilla-JS frontend"
  ```

---

## Self-Review

**Spec coverage** (against the original detailed screenshot-redesign spec):
- Left application navigation, persistent 5-stage stepper — Task 1.4 (`SideNav`, `Stepper`).
- Two-column 42/58 Intake workspace, Source Requirement left / AI Extraction right, arrow connector — Task 2.1.
- Upload/paste tabs, dropzone, file chip — Task 2.2.
- Six extraction states, structured fields, requirement rows, view-full-content expand — Task 2.3.
- Edit drawer (right-side, per the spec's stated preference), AI-generated/editable labelling, Cancel/Save/Reset — Task 2.4.
- Large primary "Create Epic & Proceed to Planning" CTA, disabled until extraction exists — Task 2.3 (button only renders when `ext` is truthy).
- AI Activity visible-but-secondary panel, customer-safe events only — Task 2.5.
- Bottom info bar — Task 2.1.
- No risk/dependency/team/sprint/story/AC/clarification/confidence/gate UI on the *visible* page — Task 2.1-2.5 render none of it; all of it is preserved-but-collapsed in Task 2.6, with the tension explicitly named in "Design decision" rather than silently resolved.
- Reuse existing shell/header/sidebar/nav/theme/backend/AI abstraction — Phase 0-1 (theme tokens ported verbatim, zero new backend routes, `RunContext` wraps the same API surface).
- `docs/INTAKE_REDESIGN.md` — Task 2.7.
- Tests — addressed via the explicit "Note on automated frontend tests" rather than silently ignored, since this repo has no DOM-test precedent to extend.
- Desktop-first, no horizontal scroll, stacks under 980px — Task 2.1 Step 2's media query.
- React scope (whole app) + build step + hard-rule-4 amendment + codex's bulk-generation role — Phases 0, 3, and Task 0.5, per the three explicit user decisions this plan was scoped against.

**Placeholder scan:** every task has concrete file paths, real code, and a runnable verification step, except Phase 3's 19 pages, which are deliberately mechanical (exact source line ranges + an unambiguous "reproduce exactly, do not redesign" instruction) rather than hand-written here — flagged explicitly in the Phase 3 preamble as a scope/time tradeoff, not hidden.

**Type consistency:** `RunState`, `Requirement`, `RequirementExtraction`, `Gate`, `RoutingVerdict` etc. (Task 1.1) are the single source of type truth every later task imports from `types.ts` — no task redefines a shape locally. `useRun()`'s return shape (Task 1.3) is extended exactly once more (`patchAct`, Task 2.4) rather than redefined.
