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

  async function act(path, body = {}, okMessage = "Done") {
    try {
      state.data = await api(`/api/runs/${state.runId}${path}`, {
        method: "POST",
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
    planning: () => notBuilt("Planning", "Phase 2"),
    build_review: () => notBuilt("Build & Independent Review", "Phase 3"),
    quality: () => notBuilt("Quality", "Phase 4"),
    release: () => notBuilt("Release", "Phase 4"),
    stories: () => notBuilt("Epics & Stories", "Phase 2"),
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
