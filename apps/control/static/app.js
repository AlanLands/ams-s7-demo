/* S7 Delivery Control Centre — renders entirely from the run-state payload.
   No rule lives here: buttons reflect permissions and gate state, the server
   enforces them. Sections not yet implemented by the engine render an honest
   "not built in this phase" panel rather than a mock. */

(() => {
  "use strict";

  const API = "";
  const state = {
    runId: localStorage.getItem("s7cc.runId") || null,
    role: localStorage.getItem("s7cc.role") || "delivery_lead",
    section: localStorage.getItem("s7cc.section") || "overview",
    data: null,
    roles: [],
  };

  const $ = (id) => document.getElementById(id);
  const main = $("main");

  // --- tiny dom helpers ----------------------------------------------------

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v);
    }
    for (const child of children.flat()) {
      if (child == null) continue;
      node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    }
    return node;
  }

  function badge(status) {
    return el("span", { class: `badge st-${status}`, text: String(status).replaceAll("_", " ") });
  }

  function prov(p) {
    return p ? el("span", { class: `prov prov-${p}`, text: p.toUpperCase() }) : null;
  }

  function toast(message, isError = false) {
    const t = $("toast");
    t.textContent = message;
    t.classList.toggle("error", isError);
    t.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => t.classList.remove("show"), 3200);
  }

  // --- api -----------------------------------------------------------------

  async function api(path, options = {}) {
    const res = await fetch(API + path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch { /* text body */ }
      throw new Error(detail);
    }
    return res.json();
  }

  async function ensureRun() {
    const runs = await api("/api/runs");
    if (state.runId && runs.includes(state.runId)) return;
    if (runs.length) {
      state.runId = runs[runs.length - 1];
    } else {
      const created = await api("/api/runs", {
        method: "POST",
        body: JSON.stringify({ mode: "simulation" }),
      });
      state.runId = created.run.run_id;
    }
    localStorage.setItem("s7cc.runId", state.runId);
  }

  async function refresh() {
    try {
      await ensureRun();
      state.data = await api(`/api/runs/${state.runId}`);
      render();
    } catch (err) {
      toast(`Could not load run state: ${err.message}`, true);
    }
  }

  async function act(path, body = {}, okMessage = "Done", method = "POST") {
    try {
      state.data = await api(`/api/runs/${state.runId}${path}`, {
        method,
        body: JSON.stringify({ role: state.role, ...body }),
      });
      render();
      toast(okMessage);
    } catch (err) {
      toast(err.message, true);
    }
  }

  // --- chrome --------------------------------------------------------------

  const STAGES = [
    ["intake", "Intake"],
    ["planning", "Planning"],
    ["build_review", "Build & Review"],
    ["quality", "Quality"],
    ["release", "Release"],
  ];

  const NAV = [
    ["nav-run", "Run"],
    ["overview", "Overview"],
    ["intake", "Intake"],
    ["planning", "Planning"],
    ["build_review", "Build & Review"],
    ["quality", "Quality"],
    ["release", "Release"],
    ["nav-detail", "Detail"],
    ["stories", "Epics & Stories"],
    ["work", "Work Queue"],
    ["traceability", "Traceability"],
    ["artifacts", "Artifacts"],
    ["approvals", "Approvals"],
    ["nav-gov", "Governance"],
    ["activity", "Activity Log"],
    ["provenance", "Provenance"],
    ["risks", "Risks & Alerts"],
    ["reports", "Reports"],
    ["settings", "Settings"],
  ];

  function renderChrome() {
    const run = state.data?.run;
    $("modePill").textContent = `mode: ${run?.mode ?? "—"}`;
    $("runPill").textContent = `run: ${run?.run_id ?? "—"}`;

    const roleSel = $("roleSelect");
    if (roleSel.options.length === 0) {
      for (const r of state.roles) {
        roleSel.appendChild(el("option", { value: r.role, text: r.role.replaceAll("_", " ") }));
      }
      roleSel.value = state.role;
      roleSel.addEventListener("change", () => {
        state.role = roleSel.value;
        localStorage.setItem("s7cc.role", state.role);
        render();
      });
    }

    const stepper = $("stepper");
    stepper.replaceChildren();
    (run?.stages ?? []).forEach((s, i) => {
      if (i > 0) stepper.appendChild(el("span", { class: "step-arrow", text: "→" }));
      const label = STAGES.find(([k]) => k === s.stage)?.[1] ?? s.stage;
      stepper.appendChild(
        el("button", {
          class: `step ${s.status}`,
          onclick: () => go(s.stage),
        },
          el("span", { class: "dot", text: String(i + 1) }),
          label,
          el("span", { class: `badge st-${s.status}`, text: s.status.replaceAll("_", " ") }),
        )
      );
    });

    const nav = $("sidenav");
    nav.replaceChildren();
    for (const [key, label] of NAV) {
      if (key.startsWith("nav-")) {
        nav.appendChild(el("div", { class: "nav-group", text: label }));
        continue;
      }
      nav.appendChild(
        el("button", {
          class: key === state.section ? "active" : "",
          text: label,
          onclick: () => go(key),
        })
      );
    }
  }

  function go(section) {
    state.section = section;
    localStorage.setItem("s7cc.section", section);
    render();
  }

  // --- sections ------------------------------------------------------------

  function sectionTitle(title, hint) {
    return el("div", { class: "section-title" },
      el("h2", { text: title }),
      hint ? el("span", { class: "hint", text: hint }) : null,
    );
  }

  function notBuilt(name, phase) {
    return el("section", {},
      sectionTitle(name),
      el("div", { class: "card warn" },
        el("h3", { text: "Not built in this phase" }),
        el("p", { text: `${name} lands in ${phase} of the implementation plan. ` +
          "This panel is a placeholder, deliberately not a mock — nothing on " +
          "this surface pretends to be evidence it does not have." }),
      ),
    );
  }

  function renderOverview() {
    const d = state.data;
    const run = d.run;
    const summary = d.activity_summary ?? {};
    const counters = summary.counters ?? {};

    return el("section", {},
      sectionTitle("Delivery overview", d.scenario?.title ?? ""),
      el("div", { class: "grid cols-4" },
        el("div", { class: "card metric" },
          el("div", { class: "v", text: String(d.provenance?.length ?? 0) }),
          el("div", { class: "l", text: "Artifacts" })),
        el("div", { class: "card metric" },
          el("div", { class: "v", text: String(counters.human_approvals ?? 0) }),
          el("div", { class: "l", text: "Human approvals" })),
        el("div", { class: "card metric" },
          el("div", { class: "v", text: String(counters.gate_failures ?? 0) }),
          el("div", { class: "l", text: "Gate failures" })),
        el("div", { class: "card metric" },
          el("div", { class: "v", text: String(summary.total_events ?? 0) }),
          el("div", { class: "l", text: "Activity events" })),
      ),
      sectionTitle("Gates", "Progress is a set of explicit conditions, never a score"),
      el("div", { class: "gate-strip" },
        (d.gates ?? []).map((g) =>
          el("div", { class: "gate-card" },
            el("div", { class: "gid", text: g.gate_id }),
            el("div", { class: "glabel", text: g.label }),
            badge(g.status),
            g.decided_by ? el("div", { class: "hint", text: `by ${g.decided_by}` }) : null,
          )
        ),
      ),
      sectionTitle("Scenario"),
      el("div", { class: "card" },
        el("div", { class: "kv" },
          el("b", { text: "Scenario" }), el("span", { text: d.scenario?.title ?? "—" }),
          el("b", { text: "Description" }), el("span", { text: d.scenario?.description ?? "—" }),
          el("b", { text: "Epic source" }), el("code", { text: d.scenario?.epic_source ?? "—" }),
          el("b", { text: "Run created" }), el("span", { text: run.created_at }),
        ),
      ),
    );
  }

  function renderIntake() {
    const d = state.data;
    const req = d.intake?.requirement;
    const analysis = d.intake?.analysis;
    const epic = d.intake?.epic;

    const parts = [sectionTitle("Stage 1 — Intake", "Requirement capture, AI analysis, epic creation")];

    if (req) {
      parts.push(el("div", { class: "card highlight" },
        el("div", { class: "section-title" }, el("h3", { text: "Requirement summary" }), prov(req.provenance)),
        el("div", { class: "kv" },
          el("b", { text: "Request" }), el("span", { class: "mono", text: req.request_id }),
          el("b", { text: "Title" }), el("span", { text: req.title }),
          el("b", { text: "Business owner" }), el("span", { text: req.business_owner }),
          el("b", { text: "Domain" }), el("span", { text: req.domain }),
          el("b", { text: "Priority" }), el("span", { text: req.priority }),
          el("b", { text: "Requested" }), el("span", { text: req.requested_date }),
          el("b", { text: "Target release" }), el("span", { text: req.target_release }),
          el("b", { text: "Description" }), el("span", { text: req.description }),
        ),
      ));
    }

    if (analysis) {
      parts.push(el("div", { class: "card" },
        el("div", { class: "section-title" }, el("h3", { text: "AI intake analysis" }), prov(analysis.provenance)),
        el("div", { class: "kv" },
          el("b", { text: "Business impact" }), el("span", { text: analysis.business_impact }),
          el("b", { text: "Affected applications" }),
          el("span", {}, el("ul", { class: "plain" }, analysis.affected_applications.map((a) => el("li", { text: a })))),
          el("b", { text: "Dependencies" }),
          el("span", {}, el("ul", { class: "plain" }, analysis.dependencies.map((a) => el("li", { text: a })))),
          el("b", { text: "Risks" }),
          el("span", {}, el("ul", { class: "plain" }, analysis.risks.map((a) => el("li", { text: a })))),
          el("b", { text: "Open questions (SME)" }),
          el("span", {}, el("ul", { class: "plain" }, analysis.clarification_questions.map((a) => el("li", { text: a })))),
          el("b", { text: "Assumptions" }),
          el("span", {}, el("ul", { class: "plain" }, analysis.assumptions.map((a) => el("li", { text: a })))),
        ),
      ));
    }

    if (epic) {
      parts.push(el("div", { class: "card ok" },
        el("div", { class: "section-title" }, el("h3", { text: "Created epic" }), prov(epic.provenance)),
        el("div", { class: "kv" },
          el("b", { text: "Epic" }), el("span", { class: "mono", text: epic.epic_id }),
          el("b", { text: "Title" }), el("span", { text: epic.title }),
          el("b", { text: "Business outcome" }), el("span", { text: epic.business_outcome }),
          el("b", { text: "Estimated stories" }), el("span", { text: String(epic.estimated_stories) }),
          el("b", { text: "Created by" }), el("span", { text: epic.created_by }),
        ),
      ));
    }

    const gate = (d.gates ?? []).find((g) => g.gate_id === "G0");
    parts.push(el("div", { class: "card" },
      el("div", { class: "section-title" }, el("h3", { text: "Intake gate (G0)" }), badge(gate?.status ?? "not_started")),
      el("ul", { class: "plain" },
        (gate?.conditions ?? []).map((c) =>
          el("li", {}, `${c.met ? "✓" : "✗"} ${c.condition}`, c.detail ? el("span", { class: "hint", text: ` — ${c.detail}` }) : null)),
      ),
      el("div", { class: "actions-row" },
        el("button", { class: "primary", text: "Run intake analysis", onclick: () => act("/intake/analyse", {}, "Intake analysis complete") }),
        el("button", { class: "primary", text: "Create epic", onclick: () => act("/intake/create-epic", {}, "Epic created") }),
        el("button", { class: "primary approve", text: "Pass intake gate", onclick: () => act("/intake/pass-gate", {}, "Intake gate passed") }),
      ),
    ));

    return el("section", {}, parts);
  }

  const RENDERERS = {
    overview: renderOverview,
    intake: renderIntake,
    planning: renderPlanning,
    build_review: () => notBuilt("Build & Independent Review", "Phase 3"),
    quality: () => notBuilt("Quality", "Phase 4"),
    release: () => notBuilt("Release", "Phase 4"),
    stories: renderStories,
    work: () => notBuilt("Work Queue", "Phase 3"),
    traceability: () => notBuilt("Traceability", "Phase 5"),
    artifacts: renderArtifacts,
    approvals: renderApprovals,
    activity: renderActivity,
    provenance: renderProvenance,
    risks: () => notBuilt("Risks & Alerts", "Phase 4"),
    reports: () => notBuilt("Reports", "Phase 6"),
    settings: renderSettings,
  };

  const TEAMS = ["Portal Team", "Services Team", "Data Team",
    "Intake Integration Team", "QA Automation", "Platform Team", "Support Team"];

  function renderPlanning() {
    const d = state.data;
    const stories = d.planning?.stories ?? [];
    const plan = d.planning?.plan;
    const locked = d.run.plan_locked;
    const gate = (d.gates ?? []).find((g) => g.gate_id === "G1");

    const parts = [sectionTitle("Stage 2 — Planning",
      "Epic decomposed into testable stories, each with one accountable team")];

    if (stories.length === 0) {
      parts.push(el("div", { class: "card" },
        el("p", { text: "No plan yet. Decomposition opens once the intake gate (G0) has passed." }),
        el("div", { class: "actions-row" },
          el("button", { class: "primary", text: "Generate draft plan",
            onclick: () => act("/planning/generate", {}, "Draft plan generated") })),
      ));
      return el("section", {}, parts);
    }

    const acs = stories.flatMap((s) => s.acceptance_criteria);
    const deps = stories.flatMap((s) => s.dependencies);
    const teams = [...new Set(stories.map((s) => s.accountable_team))];
    const sprints = [...new Set(stories.map((s) => s.sprint))];

    parts.push(el("div", { class: "grid cols-4" },
      el("div", { class: "card metric" }, el("div", { class: "v", text: String(stories.length) }), el("div", { class: "l", text: "Stories" })),
      el("div", { class: "card metric" }, el("div", { class: "v", text: String(teams.length) }), el("div", { class: "l", text: "Teams" })),
      el("div", { class: "card metric" }, el("div", { class: "v", text: String(acs.length) }), el("div", { class: "l", text: "Acceptance criteria" })),
      el("div", { class: "card metric" }, el("div", { class: "v", text: String(sprints.length) }), el("div", { class: "l", text: "Sprints" })),
    ));

    // routing table with inline reviewer controls (spec §8B/§8F)
    const editable = !locked;
    parts.push(sectionTitle("Story routing",
      locked ? "Plan locked at sign-off — edits require an amendment" : "Editable until Gate 1 sign-off locks the plan"));
    parts.push(el("div", { class: "table-wrap" },
      el("table", {},
        el("thead", {}, el("tr", {},
          ["Story", "Title", "Accountable team", "Component", "Depends on", "Est", "Sprint", "Risk", "Quality"].map((h) => el("th", { text: h })))),
        el("tbody", {}, stories.map((s) => {
          const gaps = storyGaps(s);
          return el("tr", {},
            el("td", { class: "mono", text: s.story_id }),
            el("td", { text: s.title }),
            el("td", {}, editable
              ? el("select", { onchange: (e) => act(`/stories/${s.story_id}`, { patch: { accountable_team: e.target.value } }, `${s.story_id} reassigned`, "PATCH") },
                TEAMS.map((t) => Object.assign(el("option", { value: t, text: t }), { selected: t === s.accountable_team })))
              : el("span", { text: s.accountable_team })),
            el("td", { text: s.target_component }),
            el("td", { class: "mono", text: s.dependencies.join(", ") || "—" }),
            el("td", {}, editable
              ? el("select", { onchange: (e) => act(`/stories/${s.story_id}`, { patch: { estimate: Number(e.target.value) } }, `${s.story_id} re-estimated`, "PATCH") },
                [3, 5, 8, 13].map((n) => Object.assign(el("option", { value: String(n), text: `${n} pts` }), { selected: n === s.estimate })))
              : el("span", { text: `${s.estimate} pts` })),
            el("td", {}, editable
              ? el("select", { onchange: (e) => act(`/stories/${s.story_id}`, { patch: { sprint: Number(e.target.value) } }, `${s.story_id} moved`, "PATCH") },
                [1, 2, 3].map((n) => Object.assign(el("option", { value: String(n), text: `S${n}` }), { selected: n === s.sprint })))
              : el("span", { text: `S${s.sprint}` })),
            el("td", { text: s.risk }),
            el("td", {}, gaps.length === 0 ? badge("passed") : el("span", { class: "badge st-blocked", title: gaps.join("; "), text: `${gaps.length} gaps` })),
          );
        })),
      ),
    ));

    // dependency chain + routing by team
    parts.push(el("div", { class: "grid cols-2", style: "margin-top:14px" },
      el("div", { class: "card" },
        el("h3", { text: "Dependency chain" }),
        el("ul", { class: "plain" }, stories.map((s) =>
          el("li", {}, el("span", { class: "mono", text: s.story_id }),
            s.dependencies.length ? ` ← depends on ${s.dependencies.join(", ")}` : " — no upstream dependency"))),
      ),
      el("div", { class: "card" },
        el("h3", { text: "Routing by team" }),
        el("ul", { class: "plain" }, teams.map((t) => {
          const n = stories.filter((s) => s.accountable_team === t).length;
          return el("li", {}, `${t}: ${n} ${n === 1 ? "story" : "stories"}`);
        })),
      ),
    ));

    // revision + gate 1
    if (!locked) {
      const fb = el("textarea", { rows: "2", placeholder: "What should change? e.g. 'US-004 is underestimated; move status visibility into Sprint 1'" });
      parts.push(el("div", { class: "card", style: "margin-top:14px" },
        el("h3", { text: "Request AI revision" }),
        el("p", { class: "hint", text: "Records the revision request in the activity log. In simulation mode the draft is revised deterministically." }),
        fb,
        el("div", { class: "actions-row" },
          el("button", { class: "primary", text: "Request revision",
            onclick: () => act("/planning/revise", { feedback: fb.value }, "Revision requested") })),
      ));
    }

    const approver = el("input", { type: "text", placeholder: "Approver name (required)" });
    const note = el("input", { type: "text", placeholder: "Sign-off note (optional)" });
    parts.push(el("div", { class: `card ${gate?.status === "passed" ? "ok" : "highlight"}`, style: "margin-top:14px" },
      el("div", { class: "section-title" },
        el("h3", { text: "Gate 1 — Plan sign-off" }), badge(gate?.status ?? "not_started")),
      (gate?.conditions ?? []).length
        ? el("ul", { class: "plain" }, gate.conditions.map((c) =>
          el("li", {}, `${c.met ? "✓" : "✗"} ${c.condition}`,
            c.detail ? el("span", { class: "hint", text: ` — ${c.detail}` }) : null)))
        : el("p", { class: "hint", text: "Conditions evaluate at sign-off. Only the Business Owner role may sign." }),
      plan
        ? el("div", { class: "kv", style: "margin-top:10px" },
          el("b", { text: "Signed by" }), el("span", { text: plan.signed_by }),
          el("b", { text: "At" }), el("span", { class: "mono", text: plan.signed_at }),
          el("b", { text: "Plan version" }), el("span", { text: `v${plan.plan_version}` }),
          el("b", { text: "Contract" }), el("code", { text: "planning/plan.json · planning/plan.md" }))
        : el("div", {},
          el("label", { class: "fld", text: "Approver" }), approver,
          el("label", { class: "fld", text: "Note" }), note,
          el("div", { class: "actions-row" },
            el("button", { class: "primary approve", text: "Approve & lock plan",
              onclick: () => act("/planning/sign-off", { approver: approver.value, note: note.value }, "Plan signed and locked") }))),
    ));

    return el("section", {}, parts);
  }

  function storyGaps(s) {
    const gaps = [];
    if (!s.purpose) gaps.push("purpose missing");
    if (!s.acceptance_criteria?.length) gaps.push("no acceptance criteria");
    if (!s.accountable_team) gaps.push("no accountable team");
    if (!s.target_component) gaps.push("no target component");
    if (!s.rollback_plan) gaps.push("no rollback plan");
    if (!s.task_type) gaps.push("no task type");
    return gaps;
  }

  function renderStories() {
    const stories = state.data.planning?.stories ?? [];
    if (stories.length === 0) return notBuilt("Epics & Stories", "the Planning stage — generate the draft plan first");
    return el("section", {},
      sectionTitle("Epics & Stories", "EPIC-S7-001 decomposition — demonstration data"),
      el("div", { class: "grid cols-2" }, stories.map((s) =>
        el("div", { class: "card" },
          el("div", { class: "section-title" },
            el("h3", {}, el("span", { class: "mono", text: s.story_id + " " }), s.title),
            prov(s.provenance)),
          el("p", { class: "hint", text: s.purpose }),
          el("div", { class: "kv", style: "margin-top:10px" },
            el("b", { text: "Team" }), el("span", { text: s.accountable_team + (s.contributing_teams.length ? ` (+ ${s.contributing_teams.join(", ")})` : "") }),
            el("b", { text: "Component" }), el("span", { text: s.target_component }),
            el("b", { text: "Repository" }), el("code", { text: s.target_repository }),
            el("b", { text: "Feature flag" }), el("span", {}, s.feature_flag ? el("code", { text: s.feature_flag.name }) : "—"),
            el("b", { text: "Rollback" }), el("span", { text: s.rollback_plan?.method ?? "—" }),
            el("b", { text: "Version" }), el("span", { text: `v${s.version}` }),
          ),
          el("h3", { style: "margin-top:12px", text: "Acceptance criteria" }),
          el("ul", { class: "plain" }, s.acceptance_criteria.map((ac) =>
            el("li", {}, el("span", { class: "mono", text: ac.ac_id + " " }), ac.text)),
          ),
        ))),
    );
  }

  function renderArtifacts() {
    const rows = state.data.provenance ?? [];
    return el("section", {},
      sectionTitle("Artifacts", "Current version of every artifact this run has produced"),
      el("div", { class: "table-wrap" },
        el("table", {},
          el("thead", {}, el("tr", {},
            ["Artifact", "Type", "Version", "Author", "Created", "Status"].map((h) => el("th", { text: h })))),
          el("tbody", {},
            rows.map((r) => el("tr", {},
              el("td", { class: "mono", text: r.artifact_id }),
              el("td", { text: r.artifact_type }),
              el("td", { text: `v${r.version}` }),
              el("td", { text: r.author }),
              el("td", { class: "mono", text: r.timestamp }),
              el("td", {}, r.stale ? badge("stale") : badge("completed")),
            ))),
        ),
      ),
    );
  }

  function renderProvenance() {
    const rows = state.data.provenance_ledger ?? [];
    return el("section", {},
      sectionTitle("Provenance ledger", "Append-only. Every artifact version, hashed. History is never rewritten."),
      el("div", { class: "table-wrap" },
        el("table", {},
          el("thead", {}, el("tr", {},
            ["Event", "Artifact", "Type", "v", "SHA-256", "Author", "Stage", "Action", "Outcome", "Inputs"].map((h) => el("th", { text: h })))),
          el("tbody", {},
            rows.map((r) => el("tr", {},
              el("td", { class: "mono", text: r.event_id }),
              el("td", { class: "mono", text: r.artifact_id }),
              el("td", { text: r.artifact_type }),
              el("td", { text: String(r.version) }),
              el("td", { class: "mono", title: r.sha256, text: r.sha256.slice(0, 10) + "…" }),
              el("td", { text: r.author }),
              el("td", { text: r.stage }),
              el("td", { text: r.action }),
              el("td", { text: r.outcome }),
              el("td", { class: "mono", text: (r.inputs ?? []).join(", ") || "—" }),
            ))),
        ),
      ),
    );
  }

  function renderActivity() {
    const rows = [...(state.data.activity ?? [])].reverse();
    const s = state.data.activity_summary ?? {};
    return el("section", {},
      sectionTitle("Factory activity log", "Every workflow, gate event and human decision"),
      el("div", { class: "grid cols-3" },
        Object.entries(s.counters ?? {}).map(([k, v]) =>
          el("div", { class: "card metric" },
            el("div", { class: "v", text: String(v) }),
            el("div", { class: "l", text: k.replaceAll("_", " ") }))),
      ),
      el("div", { class: "table-wrap", style: "margin-top:14px" },
        el("table", {},
          el("thead", {}, el("tr", {},
            ["Time", "Stage", "Actor", "Type", "Workflow", "Outcome", "Details"].map((h) => el("th", { text: h })))),
          el("tbody", {},
            rows.map((r) => el("tr", {},
              el("td", { class: "mono", text: r.timestamp }),
              el("td", { text: r.stage }),
              el("td", { text: r.actor }),
              el("td", { text: r.actor_type }),
              el("td", { text: r.workflow || "—" }),
              el("td", { text: r.outcome || "—" }),
              el("td", { text: r.details || "—" }),
            ))),
        ),
      ),
    );
  }

  function renderApprovals() {
    const rows = state.data.approvals ?? [];
    return el("section", {},
      sectionTitle("Approvals", "Append-only record of every human decision"),
      rows.length === 0
        ? el("div", { class: "card" }, el("p", { text: "No approvals recorded yet in this run." }))
        : el("div", { class: "table-wrap" },
          el("table", {},
            el("thead", {}, el("tr", {},
              ["Id", "Subject", "Role", "Approver", "Decision", "Note", "When"].map((h) => el("th", { text: h })))),
            el("tbody", {},
              rows.map((r) => el("tr", {},
                el("td", { class: "mono", text: r.approval_id }),
                el("td", { text: r.subject }),
                el("td", { text: r.role }),
                el("td", { text: r.approver }),
                el("td", {}, badge(r.decision === "approved" ? "passed" : "failed")),
                el("td", { text: r.note || "—" }),
                el("td", { class: "mono", text: r.decided_at }),
              ))),
          ),
        ),
    );
  }

  function renderSettings() {
    const run = state.data.run;
    return el("section", {},
      sectionTitle("Settings"),
      el("div", { class: "card" },
        el("div", { class: "kv" },
          el("b", { text: "Run id" }), el("span", { class: "mono", text: run.run_id }),
          el("b", { text: "Demo mode" }), el("span", { text: run.mode }),
          el("b", { text: "Acting role" }), el("span", { text: state.role.replaceAll("_", " ") }),
          el("b", { text: "State storage" }), el("code", { text: `artifacts/runs/${run.run_id}/` }),
        ),
        el("div", { class: "actions-row" },
          el("button", { class: "primary", text: "New run", onclick: newRun }),
          el("button", { class: "ghost danger-ghost", text: "Reset this run", onclick: resetRun }),
        ),
      ),
    );
  }

  async function newRun() {
    try {
      const created = await api("/api/runs", { method: "POST", body: JSON.stringify({ mode: "simulation" }) });
      state.runId = created.run.run_id;
      localStorage.setItem("s7cc.runId", state.runId);
      state.data = created;
      render();
      toast(`Run ${state.runId} created`);
    } catch (err) { toast(err.message, true); }
  }

  async function resetRun() {
    await act("/reset", {}, "Run reset to seeded state");
  }

  // --- render --------------------------------------------------------------

  function render() {
    if (!state.data) return;
    renderChrome();
    const renderer = RENDERERS[state.section] ?? renderOverview;
    main.replaceChildren(renderer());
  }

  // --- boot ----------------------------------------------------------------

  $("refreshBtn").addEventListener("click", refresh);
  $("resetBtn").addEventListener("click", resetRun);

  (async () => {
    try {
      state.roles = await api("/api/roles");
    } catch { state.roles = []; }
    await refresh();
  })();
})();
