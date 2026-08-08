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
    runs: [],
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
    for (const child of children.flat(Infinity)) {
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

  async function loadPlanningFiles() {
    try {
      state.planningFiles = await api(`/api/runs/${state.runId}/planning/files`);
    } catch { state.planningFiles = []; }
  }

  async function refresh() {
    try {
      await ensureRun();
      state.runs = await api("/api/runs");
      state.data = await api(`/api/runs/${state.runId}`);
      await loadPlanningFiles();
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
      await loadPlanningFiles();
      render();
      toast(okMessage);
      return true;
    } catch (err) {
      toast(err.message, true);
      return false;
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

  const PLANNING_SUBS = [
    ["epic_to_stories", "Epic to Stories"],
    ["dependency_map", "Dependency Map"],
    ["routing_by_team", "Routing by Team"],
    ["plan_summary", "Plan Summary"],
    ["plan_signoff", "Plan Sign-off"],
  ];

  const BUILD_SUBS = [
    ["build_work_queue", "Work Queue"],
    ["dev_progress", "Development Progress"],
    ["test_evidence", "Test Evidence"],
    ["independent_review", "Independent Review"],
  ];

  const NAV = [
    ["nav-run", "Run"],
    ["overview", "Overview", "▦"],
    ["intake", "Intake", "⭳"],
    ["planning", "Planning", "▤"],
    ["build_review", "Build & Review", "⚒"],
    ["quality", "Quality", "✓"],
    ["release", "Release", "➤"],
    ["nav-detail", "Detail"],
    ["stories", "Epics & Stories", "❖"],
    ["traceability", "Traceability", "⇄"],
    ["artifacts", "Artifacts", "▣"],
    ["approvals", "Approvals", "✍"],
    ["nav-gov", "Governance"],
    ["activity", "Activity Log", "◷"],
    ["provenance", "Provenance", "⛓"],
    ["risks", "Risks & Alerts", "⚠"],
    ["reports", "Reports", "▥"],
    ["settings", "Settings", "⚙"],
  ];

  const PLANNING_SECTIONS = new Set(["planning", ...PLANNING_SUBS.map(([k]) => k)]);
  const BUILD_SECTIONS = new Set(["build_review", ...BUILD_SUBS.map(([k]) => k)]);
  const GROUPS = {
    planning: { subs: PLANNING_SUBS, sections: PLANNING_SECTIONS, landing: "epic_to_stories" },
    build_review: { subs: BUILD_SUBS, sections: BUILD_SECTIONS, landing: "build_work_queue" },
  };

  function renderChrome() {
    const run = state.data?.run;

    const scenarioSel = $("scenarioSelect");
    scenarioSel.replaceChildren(
      el("option", { text: state.data?.scenario?.title ?? "—" }));

    const runSel = $("runSelect");
    runSel.replaceChildren(
      ...state.runs.map((r) =>
        Object.assign(el("option", { value: r, text: r }), { selected: r === run?.run_id })));
    runSel.onchange = () => {
      state.runId = runSel.value;
      localStorage.setItem("s7cc.runId", state.runId);
      refresh();
    };

    const envSel = $("envSelect");
    envSel.value = run?.mode ?? "simulation";
    envSel.onchange = async () => {
      const mode = envSel.value;
      if (mode === run?.mode) return;
      try {
        const created = await api("/api/runs", { method: "POST", body: JSON.stringify({ mode }) });
        state.runId = created.run.run_id;
        localStorage.setItem("s7cc.runId", state.runId);
        state.data = created;
        state.runs = await api("/api/runs");
        render();
        toast(`New ${mode} run ${state.runId} created`);
      } catch (err) {
        envSel.value = run?.mode ?? "simulation";
        toast(err.message, true);
      }
    };

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
    $("roleAvatar").textContent = state.role
      .split("_").map((w) => w[0]).join("").slice(0, 2).toUpperCase();

    const stepper = $("stepper");
    stepper.replaceChildren();
    (run?.stages ?? []).forEach((s, i) => {
      if (i > 0) {
        const prev = run.stages[i - 1];
        stepper.appendChild(el("span", {
          class: `step-arrow ${prev.status === "completed" ? "done" : ""}`,
          "aria-hidden": "true",
        }));
      }
      const label = STAGES.find(([k]) => k === s.stage)?.[1] ?? s.stage;
      const statusLabel = s.status === "completed" ? "Completed"
        : s.status === "not_started" ? "Pending"
          : s.status.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
      stepper.appendChild(
        el("button", {
          class: `step ${s.status}`,
          onclick: () => go(GROUPS[s.stage]?.landing ?? s.stage),
        },
          el("span", { class: "check", text: "✓" }),
          el("span", { class: "dot", text: String(i + 1) }),
          el("span", { class: "step-txt" },
            el("span", { text: label }),
            el("span", { class: "step-sub", text: statusLabel })),
        )
      );
    });

    const nav = $("sidenav");
    nav.replaceChildren();
    for (const [key, label, icon] of NAV) {
      if (key.startsWith("nav-")) {
        nav.appendChild(el("div", { class: "nav-group", text: label }));
        continue;
      }
      const group = GROUPS[key];
      const inGroup = group && group.sections.has(state.section);
      nav.appendChild(
        el("button", {
          class: (key === state.section || inGroup) ? "active" : "",
          onclick: () => go(group ? group.landing : key),
        },
          icon ? el("span", { class: "nav-ico", text: icon }) : null,
          label,
          group ? el("span", { class: "caret", text: inGroup ? "▲" : "▼" }) : null,
        )
      );
      if (group && inGroup) {
        for (const [sub, subLabel] of group.subs) {
          nav.appendChild(el("button", {
            class: `sub ${sub === state.section ? "active" : ""}`,
            text: subLabel,
            onclick: () => go(sub),
          }));
        }
      }
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

  function checkItem(ok, label, extra) {
    return el("li", {},
      el("span", { class: `tick ${ok ? "ok" : "no"}`, text: ok ? "✓" : "·" }),
      label,
      extra != null ? el("span", { class: "state ok mono", text: String(extra) }) : null);
  }

  function requirementDetail(req) {
    return el("div", { class: "kv", style: "grid-template-columns: 130px 1fr" },
      el("b", { text: "Request ID" }), el("span", { class: "mono", text: req.request_id }),
      el("b", { text: "Title" }), el("span", { text: req.title }),
      el("b", { text: "Requested By" }), el("span", { text: req.business_owner }),
      el("b", { text: "Priority" }), el("span", {}, el("span", { class: `chip priority-${(req.priority || "low").toLowerCase()}`, text: req.priority })),
      el("b", { text: "Requested On" }), el("span", { text: req.requested_date }),
      el("b", { text: "Target Release" }), el("span", { text: req.target_release }),
      el("b", { text: "Domain" }), el("span", { text: req.domain }),
      el("b", { text: "Description" }), el("span", { text: req.description }));
  }

  function documentList(req) {
    const docs = req.source_documents ?? [];
    if (!docs.length) return el("p", { class: "hint", text: "No documents attached yet." });
    return el("ul", { class: "plain" }, docs.map((name) =>
      el("li", {}, name.includes("/")
        ? el("span", { class: "mono", text: name })
        : el("a", { class: "mono", href: `${API}/api/runs/${state.runId}/intake/documents/${encodeURIComponent(name)}`, target: "_blank", rel: "noopener", text: name }))));
  }

  function uploadDocumentControl() {
    const input = el("input", { type: "file" });
    return el("div", { style: "display:flex; gap:8px; align-items:center; margin-top:10px; flex-wrap:wrap" },
      input,
      el("button", {
        class: "outline", text: "⬆ Upload",
        onclick: async () => {
          const file = input.files?.[0];
          if (!file) { toast("Choose a file first", true); return; }
          const form = new FormData();
          form.append("role", state.role);
          form.append("file", file);
          try {
            state.data = await api(`/api/runs/${state.runId}/intake/upload-document`, { method: "POST", headers: {}, body: form });
            render();
            toast(`${file.name} attached to the requirement`);
          } catch (err) { toast(err.message, true); }
        },
      }));
  }

  function renderIntake() {
    const d = state.data;
    const req = d.intake?.requirement;
    const analysis = d.intake?.analysis;
    const epic = d.intake?.epic;
    const gate = (d.gates ?? []).find((g) => g.gate_id === "G0");

    const reqCard = req ? el("div", { class: "card" },
      el("div", { class: "section-title" }, el("h3", { text: "Requirement Summary" }), prov(req.provenance)),
      el("div", { class: "kv", style: "grid-template-columns: 130px 1fr" },
        el("b", { text: "Request ID" }), el("span", { class: "mono", text: req.request_id }),
        el("b", { text: "Title" }), el("span", { text: req.title }),
        el("b", { text: "Priority" }), el("span", {}, el("span", { class: `chip priority-${(req.priority || "low").toLowerCase()}`, text: req.priority })),
        el("b", { text: "Description" }), el("span", { class: "clamp-2", text: req.description })),
      el("h4", { style: "margin-top:14px; font-size:12.5px; color:var(--muted)", text: "Documents" }),
      documentList(req),
      uploadDocumentControl(),
      el("button", {
        class: "outline block", style: "margin-top:12px",
        text: "⤢ View full requirement",
        onclick: () => openModal("Requirement Summary", prov(req.provenance), requirementDetail(req)),
      })) : null;

    const gateSummaryLine = (gate?.conditions ?? []).length
      ? `${gate.conditions.filter((c) => c.met).length} / ${gate.conditions.length} conditions met`
      : "Conditions appear once analysis has run.";

    const gateChecklist = (gate?.conditions ?? []).length
      ? el("ul", { class: "checklist" }, gate.conditions.map((c) => checkItem(c.met, c.condition)))
      : el("ul", { class: "checklist" },
        checkItem(Boolean(req), "Requirement captured"),
        checkItem(Boolean(req?.description), "Source available"),
        checkItem(Boolean(analysis), "Initial analysis completed"),
        checkItem(Boolean(analysis?.affected_applications?.length), "Scope identifiable"),
        checkItem(Boolean(req?.business_owner), "Business owner identified"),
        checkItem(Boolean(analysis), "No critical blockers"));

    const gateCard = el("div", { class: "card" },
      el("div", { class: "section-title" }, el("h3", { text: "Intake Gate" }), badge(gate?.status ?? "not_started")),
      el("p", { class: "hint", text: gateSummaryLine }),
      el("button", {
        class: "outline block", style: "margin-top:10px",
        text: "⤢ View gate checklist",
        onclick: () => openModal("Intake Gate", badge(gate?.status ?? "not_started"),
          el("p", { class: "hint", style: "margin-top:10px", text: "All items must be complete" }), gateChecklist),
      }));

    const aiCard = analysis ? el("div", { class: "card" },
      el("div", { class: "section-title" }, el("h3", { text: "AI Analysis (Completed)" }), prov(analysis.provenance)),
      el("ul", { class: "checklist" },
        checkItem(analysis.problem_understood, "Problem understood"),
        checkItem(Boolean(analysis.business_impact), "Business impact identified"),
        checkItem(analysis.affected_applications.length > 0, "Affected applications identified", analysis.affected_applications.length),
        checkItem(analysis.stakeholders.length > 0, "Stakeholders identified", analysis.stakeholders.length),
        checkItem(analysis.dependencies.length > 0, "Dependencies detected", analysis.dependencies.length),
        checkItem(analysis.risks.length > 0, "Risks identified", analysis.risks.length),
        checkItem(analysis.clarification_questions.length > 0, "Clarification questions generated", analysis.clarification_questions.length),
        checkItem(analysis.assumptions.length > 0, "Assumptions captured", analysis.assumptions.length)),
      analysis.confidence != null ? el("div", { class: "conf-row" },
        el("b", { text: "AI Confidence" }),
        el("span", {
          class: "info conf-v",
          title: "The analysis model's self-assessment. Simulated and deterministic in demo mode — not a measured outcome.",
          text: `${analysis.confidence}% ⓘ`,
        })) : null) : el("div", { class: "card" },
      el("p", { text: "No analysis yet — run the intake analysis." }));

    const clar = d.intake?.clarifications;
    const clarCard = clar?.pending?.length ? el("div", { class: "card" },
      el("div", { class: "section-title" }, el("h3", { text: "AI Clarification" }),
        el("span", { class: "chip", text: `round ${clar.rounds_used} of ${clar.max_rounds}` })),
      (() => {
        const inputs = clar.pending.map((q) =>
          ({ q, input: el("input", { type: "text", placeholder: "Answer (blank = stated assumption)" }) }));
        return el("div", {},
          ...inputs.map(({ q, input }) => el("div", { style: "margin-bottom:8px" },
            el("p", { text: q }), input)),
          el("button", {
            class: "primary sq", text: "Submit answers",
            onclick: () => act("/intake/clarify-answer",
              { answers: inputs.map(({ input }) => input.value) }, "Answers recorded"),
          }));
      })()) : null;

    const rulesCard = analysis?.business_rules?.length ? el("div", { class: "card" },
      el("div", { class: "section-title" }, el("h3", { text: "AI Extracted Business Rules" }), prov(analysis.provenance)),
      el("ul", { class: "plain" }, analysis.business_rules.map((r) =>
        el("li", {},
          el("span", { class: "chip priority-high", style: "margin-right:8px", text: r.rule_id }),
          r.text)))) : null;

    const epicCard = epic ? el("div", { class: "card ok" },
      el("div", { class: "section-title" }, el("h3", { text: "Created Epic" }), prov(epic.provenance)),
      el("div", { class: "kv", style: "grid-template-columns: 130px 1fr" },
        el("b", { text: "Epic ID" }), el("span", { class: "mono", text: epic.epic_id }),
        el("b", { text: "Epic Title" }), el("span", { text: epic.title }),
        el("b", { text: "Business Outcome" }), el("span", { text: epic.business_outcome }),
        el("b", { text: "Estimated Stories" }), el("span", { text: String(epic.estimated_stories) }),
        el("b", { text: "Created By" }), el("span", { text: epic.created_by }))) : null;

    const isLive = d.run?.mode === "live";
    const repos = d.intake?.repos ?? [];

    const repoCard = isLive ? el("div", { class: "card" },
      el("div", { class: "section-title" }, el("h3", { text: "Connected Repositories" }),
        el("span", { class: "chip", text: `${repos.length} connected` })),
      el("ul", { class: "plain" }, repos.map((r) =>
        el("li", {},
          el("span", { class: "mono", text: r.name }),
          el("span", { class: "hint", text: ` @ ${r.head_sha.slice(0, 10)} · ${r.file_count} files` })))),
      (() => {
        const url = el("input", { type: "text", placeholder: "https://github.com/<owner>/<repo>" });
        const btn = el("button", {
          class: "outline", text: "Connect repository",
          onclick: () => { if (url.value.trim()) act("/intake/connect-repo", { url: url.value.trim() }, "Repository connected"); },
        });
        return el("div", { class: "row", style: "margin-top:10px; display:flex; gap:8px" }, url, btn);
      })(),
      repos.length === 0 ? el("p", { class: "hint", text: "Live analysis is grounded in the connected repos — connect them before analysing." }) : null) : null;

    const routing = d.intake?.routing;
    const routingCard = isLive ? el("div", { class: "card" },
      el("div", { class: "section-title" }, el("h3", { text: "Requirement Routing" }),
        routing ? prov(routing.provenance) : null),
      routing
        ? el("div", {},
            el("div", { class: "kv", style: "grid-template-columns: 130px 1fr" },
              el("b", { text: "Verdict" }),
              el("span", {}, el("span", {
                class: `chip ${routing.verdict === "routable" ? "priority-low" : "priority-high"}`,
                text: routing.verdict === "routable" ? "Fits connected repos" : "New application needed",
              })),
              el("b", { text: "Reasoning" }), el("span", { text: routing.reasoning }),
              routing.candidate_repos?.length ? el("b", { text: "Candidate repos" }) : null,
              routing.candidate_repos?.length ? el("span", { text: routing.candidate_repos.join(", ") }) : null,
              routing.overridden_by ? el("b", { text: "Overridden by" }) : null,
              routing.overridden_by ? el("span", { text: `${routing.overridden_by} at ${routing.overridden_at}` }) : null),
            (() => {
              const sel = el("select", {},
                el("option", { value: "routable", text: "Routable" }),
                el("option", { value: "new_application_needed", text: "New application needed" }));
              sel.value = routing.verdict;
              return el("div", { style: "margin-top:10px; display:flex; gap:8px; align-items:center" },
                el("span", { class: "hint", text: "Override:" }), sel,
                el("button", {
                  class: "outline", text: "Apply override",
                  onclick: () => act("/intake/override-route", { verdict: sel.value }, "Routing verdict overridden"),
                }));
            })())
        : el("p", { class: "hint", text: "Run requirement routing to decide whether this fits the connected repos, or needs a new application." })) : null;

    const newApp = d.intake?.new_app;
    const scaffoldFiles = d.intake?.scaffold;
    const newAppCard = (isLive && routing?.verdict === "new_application_needed") ? el("div", { class: "card" },
      el("div", { class: "section-title" }, el("h3", { text: "New Application Setup" })),
      newApp?.name
        ? el("div", {},
            el("div", { class: "kv", style: "grid-template-columns: 130px 1fr" },
              el("b", { text: "Name" }), el("span", { class: "mono", text: newApp.name }),
              el("b", { text: "Description" }), el("span", { text: newApp.description }),
              el("b", { text: "Stack" }), el("span", { text: newApp.stack })),
            scaffoldFiles
              ? el("div", { style: "margin-top:10px" },
                  el("p", { class: "hint", text: "Scaffold generated — review before creating the repository." }),
                  ...Object.entries(scaffoldFiles).map(([name, content]) =>
                    el("details", { style: "margin-top:6px" },
                      el("summary", { text: name }),
                      el("pre", { class: "mono", style: "white-space:pre-wrap; font-size:12px", text: content }))),
                  el("button", {
                    class: "primary sq block", style: "margin-top:10px", text: "Create Repository",
                    onclick: () => act("/intake/create-new-app-repo", {}, "New application repository created"),
                  }))
              : el("button", {
                  class: "outline block", style: "margin-top:10px", text: "Generate Scaffold",
                  onclick: () => act("/intake/generate-scaffold", {}, "Scaffold generated"),
                }))
        : el("div", {},
            newApp?.pending?.length
              ? (() => {
                  const inputs = newApp.pending.map((q) =>
                    ({ q, input: el("input", { type: "text", placeholder: "Answer" }) }));
                  return el("div", {},
                    ...inputs.map(({ q, input }) => el("div", { style: "margin-bottom:8px" },
                      el("p", { text: q }), input)),
                    el("button", {
                      class: "primary sq", text: "Submit answers",
                      onclick: () => act("/intake/new-app-answer",
                        { answers: inputs.map(({ input }) => input.value) }, "Answers recorded"),
                    }));
                })()
              : el("button", {
                  class: "outline block", text: "Start New Application Setup",
                  onclick: () => act("/intake/new-app-setup", {}, "Setup started"),
                }))) : null;

    const rail = el("aside", { class: "rail" },
      el("div", { class: "card rail-card" },
        el("h3", { text: "Actions" }),
        isLive ? el("button", {
          class: "outline block", style: "margin-top:10px", text: "Route Requirement",
          onclick: () => act("/intake/route", {}, "Requirement routed"),
        }) : null,
        isLive
          ? el("button", {
              class: "outline block", style: "margin-top:10px", text: "Ask AI Clarification",
              onclick: () => act("/intake/clarify", {}, "Clarifying questions requested"),
            })
          : Object.assign(el("button", {
              class: "outline block", style: "margin-top:10px", text: "Ask AI Clarification",
              title: "Live clarification runs in live mode. In demo mode the analysis lists its open questions below — honestly disabled, not mocked.",
            }), { disabled: true }),
        el("button", {
          class: "outline block", style: "margin-top:8px", text: "⟳ Regenerate Analysis",
          onclick: () => act("/intake/analyse", {}, isLive ? "Live analysis regenerated" : "Intake analysis regenerated"),
        }),
        el("button", { class: "primary sq block", style: "margin-top:8px", text: "Generate Epic", onclick: () => act("/intake/create-epic", {}, "Epic created") }),
        el("button", { class: "primary sq block approve", style: "margin-top:8px", text: "✓ Pass Intake Gate", onclick: () => act("/intake/pass-gate", {}, "Intake gate passed") })),
      guidanceCard());

    return el("section", { class: "page-with-rail" },
      el("div", {},
        el("div", { class: "page-head", style: "margin-bottom:16px" },
          el("h2", { text: "Intake — AI Analysis" }),
          el("span", { class: "hint", text: "The analysis model reviews the requirement and extracts key information. A human passes the gate." })),
        repoCard ? el("div", { style: "margin-bottom:14px" }, repoCard) : null,
        routingCard ? el("div", { style: "margin-bottom:14px" }, routingCard) : null,
        newAppCard ? el("div", { style: "margin-bottom:14px" }, newAppCard) : null,
        reqCard,
        el("div", { style: "margin-top:14px" }, aiCard),
        clarCard ? el("div", { style: "margin-top:14px" }, clarCard) : null,
        rulesCard ? el("div", { style: "margin-top:14px" }, rulesCard) : null,
        analysis ? el("div", { class: "grid cols-2", style: "margin-top:14px" },
          el("div", { class: "card" },
            el("h3", { text: "Open questions (SME)" }),
            el("ul", { class: "plain" }, analysis.clarification_questions.map((q) => el("li", { text: q })))),
          el("div", { class: "card" },
            el("h3", { text: "Assumptions" }),
            el("ul", { class: "plain" }, analysis.assumptions.map((a) => el("li", { text: a }))))) : null,
        epicCard ? el("div", { style: "margin-top:14px" }, epicCard) : null,
        el("div", { style: "margin-top:14px" }, gateCard)),
      rail);
  }

  const RENDERERS = {
    overview: renderOverview,
    intake: renderIntake,
    planning: renderEpicToStories,
    epic_to_stories: renderEpicToStories,
    dependency_map: renderDependencyMap,
    routing_by_team: renderRoutingByTeam,
    plan_summary: renderPlanSummary,
    plan_signoff: renderPlanSignoff,
    build_review: renderBuildWorkQueue,
    build_work_queue: renderBuildWorkQueue,
    dev_progress: renderDevProgress,
    test_evidence: renderTestEvidence,
    independent_review: renderIndependentReview,
    quality: renderQuality,
    release: renderRelease,
    stories: renderStories,
    work: renderBuildWorkQueue,
    traceability: renderTraceability,
    artifacts: renderArtifacts,
    approvals: renderApprovals,
    activity: renderActivity,
    provenance: renderProvenance,
    risks: renderRisks,
    reports: renderReports,
    settings: renderSettings,
  };

  const TEAMS = ["Portal Team", "Services Team", "Data Team",
    "Intake Integration Team", "QA Automation", "Platform Team", "Support Team"];

  // --- planning: epic to stories (spec §8, layout per customer wireframe,
  // re-branded MapleSure per hard rule 2) ------------------------------------

  function teamChip(name) {
    if (!name) return el("span", { text: "—" });
    const initials = name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
    return el("span", { class: "team-chip" },
      el("span", { class: "avatar", text: initials }), name);
  }

  function planningStories() { return state.data.planning?.stories ?? []; }

  function planKpis(stories) {
    const teams = new Set();
    stories.forEach((s) => { teams.add(s.accountable_team); (s.contributing_teams ?? []).forEach((t) => teams.add(t)); });
    const complete = stories.filter((s) => storyGaps(s).length === 0).length;
    return {
      stories: stories.length,
      teams: teams.size,
      acs: stories.flatMap((s) => s.acceptance_criteria).length,
      deps: stories.flatMap((s) => s.dependencies).length,
      sprints: new Set(stories.map((s) => s.sprint)).size,
      completeness: stories.length ? Math.round((100 * complete) / stories.length) : 0,
    };
  }

  function exportStories(stories) {
    const blob = new Blob([JSON.stringify(stories, null, 2)], { type: "application/json" });
    const a = el("a", { href: URL.createObjectURL(blob), download: "plan-stories.json" });
    a.click();
    URL.revokeObjectURL(a.href);
    toast("Stories exported as plan-stories.json");
  }

  function epicDetailsCard() {
    const d = state.data;
    const epic = d.intake?.epic;
    const req = d.intake?.requirement;
    const locked = d.run.plan_locked;
    if (!epic) {
      return el("div", { class: "card" },
        el("p", { text: "No epic yet — complete the Intake stage first (analyse, create epic, pass gate G0)." }));
    }
    const priority = (req?.priority ?? "").toLowerCase();
    return el("div", { class: "card" },
      el("div", { class: "card-head" },
        el("h3", { text: "Epic Details" }),
        el("div", { class: "btns" },
          Object.assign(el("button", {
            class: "outline", text: "✦ AI Suggest Stories",
            title: locked ? "Plan locked at sign-off — changes require an amendment"
              : "Generates the draft decomposition through the engine (simulation mode is deterministic)",
            onclick: () => act("/planning/generate", {}, "Draft stories generated"),
          }), { disabled: locked }),
          Object.assign(el("button", {
            class: "outline", text: "⬆ Import Stories",
            title: locked ? "Plan locked at sign-off — changes require an amendment"
              : "Upload a JSON file of stories (the Export format works). Imported stories carry HUMAN provenance.",
            onclick: importStoriesDialog,
          }), { disabled: locked }),
          Object.assign(el("button", {
            class: "primary sq", text: "+ Add Story",
            title: locked ? "Plan locked at sign-off — changes require an amendment"
              : "Add a story by hand. Manual stories carry HUMAN provenance.",
            onclick: () => openAddStoryModal(),
          }), { disabled: locked }),
        ),
      ),
      el("div", { class: "epic-grid" },
        el("div", { class: "kv" },
          el("b", { text: "Epic ID" }), el("span", { class: "mono", text: epic.epic_id }),
          el("b", { text: "Epic Title" }), el("span", { text: epic.title }),
          el("b", { text: "Business Outcome" }), el("span", { text: epic.business_outcome }),
        ),
        el("div", { class: "kv" },
          el("b", { text: "Domain" }), el("span", { text: req?.domain ?? "—" }),
          el("b", { text: "Business Owner" }), el("span", { text: req?.business_owner ?? "—" }),
          el("b", { text: "Priority" }),
          el("span", {}, el("span", { class: `chip priority-${priority || "low"}`, text: req?.priority ?? "—" })),
        ),
        el("div", { class: "kv" },
          el("b", { text: "Estimated Stories" }), el("span", { text: String(epic.estimated_stories) }),
          el("b", { text: "Created On" }), el("span", { text: (epic.created_at ?? "").slice(0, 10) }),
          el("b", { text: "Created By" }), el("span", {}, epic.created_by, " ", prov(epic.provenance)),
        ),
      ),
    );
  }

  function kpiTiles(k) {
    const conf = state.data.planning?.confidence;
    return el("div", { class: "tiles" },
      el("div", { class: "tile t-red" }, el("div", { class: "v", text: String(k.stories) }), el("div", { class: "l", text: "Total Stories" })),
      el("div", { class: "tile t-green" }, el("div", { class: "v", text: String(k.teams) }), el("div", { class: "l", text: "Teams Involved" })),
      el("div", { class: "tile t-red" }, el("div", { class: "v", text: String(k.acs) }), el("div", { class: "l", text: "Acceptance Criteria" })),
      el("div", { class: "tile t-amber" }, el("div", { class: "v", text: String(k.deps) }), el("div", { class: "l", text: "Dependencies" })),
      el("div", { class: "tile t-amber" }, el("div", { class: "v", text: String(k.sprints) }), el("div", { class: "l", text: "Planned Sprints" })),
      el("div", { class: "tile t-blue" },
        el("div", { class: "v", text: conf ? `${conf.value}%` : "—" }),
        el("div", { class: "l" }, el("span", {
          class: "info",
          title: conf?.basis ?? "Available once the AI plan draft exists.",
          text: "AI Plan Confidence ⓘ",
        }))),
    );
  }

  // --- add / import stories -------------------------------------------------

  function closeModal() {
    document.getElementById("modal")?.remove();
  }

  function openModal(titleText, ...bodyNodes) {
    closeModal();
    const modal = el("div", { id: "modal", class: "modal-overlay", onclick: (e) => { if (e.target === modal) closeModal(); } },
      el("div", { class: "modal card" },
        el("div", { class: "card-head" },
          el("h3", { text: titleText }),
          el("button", { class: "kebab", text: "✕", onclick: closeModal })),
        ...bodyNodes));
    document.body.appendChild(modal);
    return modal;
  }

  function openAddStoryModal() {
    closeModal();
    const stories = planningStories();
    const field = (label, node) => el("div", {}, el("label", { class: "fld", text: label }), node);
    const title = el("input", { type: "text", placeholder: "e.g. Notify the sponsor when intake opens the file" });
    const purpose = el("textarea", { rows: "2", placeholder: "Why this story exists (defaults to the title)" });
    const team = el("select", {}, TEAMS.map((t) => el("option", { value: t, text: t })));
    const contributing = el("input", { type: "text", placeholder: "Comma-separated, optional" });
    const component = el("input", { type: "text", placeholder: "e.g. notification service" });
    const repository = el("input", { type: "text", placeholder: "e.g. sponsorconnect-api" });
    const sprint = el("select", {}, [1, 2, 3].map((n) => el("option", { value: String(n), text: `Sprint ${n}` })));
    const estimate = el("select", {}, [2, 3, 5, 8, 13].map((n) =>
      Object.assign(el("option", { value: String(n), text: `${n} pts` }), { selected: n === 3 })));
    const taskType = el("select", {},
      el("option", { value: "feature", text: "Feature" }),
      el("option", { value: "test", text: "Test / regression" }),
      el("option", { value: "operational", text: "Operational readiness" }));
    const deps = el("select", { multiple: "", size: "4" },
      stories.map((s) => el("option", { value: s.story_id, text: `${s.story_id} — ${s.title}` })));
    const acs = el("textarea", { rows: "4", placeholder: "One acceptance criterion per line (at least one)" });

    const modal = el("div", { id: "modal", class: "modal-overlay", onclick: (e) => { if (e.target === modal) closeModal(); } },
      el("div", { class: "modal card" },
        el("div", { class: "card-head" },
          el("h3", { text: "Add Story" }),
          el("button", { class: "kebab", text: "✕", onclick: closeModal })),
        el("p", { class: "hint", text: "Manual stories join the draft plan with HUMAN provenance and the same Gate 1 validation as AI-drafted ones." }),
        el("div", { class: "grid cols-2" },
          field("Title *", title), field("Accountable team *", team),
          field("Component / application *", component), field("Repository *", repository),
          field("Sprint", sprint), field("Estimate", estimate),
          field("Story type", taskType), field("Contributing teams", contributing),
          field("Depends on", deps),
        ),
        field("Purpose", purpose),
        field("Acceptance criteria *", acs),
        el("div", { class: "actions-row" },
          el("button", {
            class: "primary sq", text: "Add to draft plan",
            onclick: () => {
              const story = {
                title: title.value, purpose: purpose.value,
                accountable_team: team.value,
                contributing_teams: contributing.value.split(",").map((t) => t.trim()).filter(Boolean),
                target_component: component.value, target_repository: repository.value,
                sprint: Number(sprint.value), estimate: Number(estimate.value),
                task_type: taskType.value,
                dependencies: [...deps.selectedOptions].map((o) => o.value),
                acceptance_criteria: acs.value.split("\n").map((t) => t.trim()).filter(Boolean),
              };
              act("/stories", { story }, "Story added to the draft plan")
                .then((ok) => { if (ok) closeModal(); });
            },
          }),
          el("button", { class: "ghost", text: "Cancel", onclick: closeModal }),
        ),
      ));
    document.body.appendChild(modal);
    title.focus();
  }

  function importStoriesDialog() {
    const input = el("input", { type: "file", accept: ".json,application/json" });
    input.addEventListener("change", () => {
      const file = input.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        let items;
        try {
          const parsed = JSON.parse(reader.result);
          items = Array.isArray(parsed) ? parsed : parsed.stories;
        } catch {
          toast("Not a JSON file — export from this page for the expected shape", true);
          return;
        }
        if (!Array.isArray(items) || items.length === 0) {
          toast("The file has no stories — expected an array or {\"stories\": [...]}", true);
          return;
        }
        act("/stories/import", { stories: items }, `${items.length} stories imported`);
      };
      reader.readAsText(file);
    });
    input.click();
  }

  function storyDetailModal(s) {
    openModal(`${s.story_id} — ${s.title}`,
      prov(s.provenance),
      el("div", { class: "kv", style: "grid-template-columns: 160px 1fr; margin-top:10px" },
        el("b", { text: "Purpose" }), el("span", { text: s.purpose || "—" }),
        el("b", { text: "Accountable Team" }), el("span", {}, teamChip(s.accountable_team)),
        el("b", { text: "Contributing Teams" }), el("span", { text: (s.contributing_teams ?? []).join(", ") || "—" }),
        el("b", { text: "Target Application" }), el("span", { text: s.target_application || "—" }),
        el("b", { text: "Component" }), el("span", { text: s.target_component }),
        el("b", { text: "Repository" }), el("span", {}, el("code", { text: s.target_repository })),
        el("b", { text: "Depends On" }), el("span", { class: "mono", text: (s.dependencies ?? []).join(", ") || "—" }),
        el("b", { text: "Sprint" }), el("span", { text: `S${s.sprint}` }),
        el("b", { text: "Estimate" }), el("span", { text: `${s.estimate} pts` }),
        el("b", { text: "Task Type" }), el("span", { text: s.task_type }),
        el("b", { text: "Risk" }), el("span", { text: s.risk }),
        el("b", { text: "Status" }), el("span", {}, badge(s.status)),
        el("b", { text: "Routing Rationale" }), el("span", { class: "hint", text: s.provenance === "human"
          ? "Added by a person"
          : `Owns ${s.target_component} in ${s.target_repository}` }),
        s.feature_flag ? [el("b", { text: "Feature Flag" }),
          el("span", { class: "mono", text: `${s.feature_flag.name} (default: ${s.feature_flag.default_state})` })] : null,
        s.rollback_plan ? [el("b", { text: "Rollback Plan" }),
          el("span", { text: `${s.rollback_plan.method}${s.rollback_plan.tested ? " — tested" : ""}` })] : null,
      ),
      el("h4", { style: "margin-top:16px; font-size:12.5px; color:var(--muted)", text: "Acceptance Criteria" }),
      (s.acceptance_criteria ?? []).length
        ? el("ul", { class: "plain" }, s.acceptance_criteria.map((ac) =>
          el("li", {}, el("span", { class: "chip priority-high", style: "margin-right:8px", text: ac.ac_id }), ac.text)))
        : el("p", { class: "hint", text: "None defined." }),
      (s.impacts ?? []).length ? [
        el("h4", { style: "margin-top:16px; font-size:12.5px; color:var(--muted)", text: "Impacts" }),
        el("ul", { class: "plain" }, s.impacts.map((i) => el("li", { text: i }))),
      ] : null,
    );
  }

  function storyRow(s, editable) {
    const editing = state.editStory === s.story_id;
    const row = el("tr", { class: "row-click", onclick: () => storyDetailModal(s) },
      el("td", { class: "mono", text: s.story_id }),
      el("td", { text: s.title }),
      el("td", {}, teamChip(s.accountable_team)),
      el("td", { text: `S${s.sprint}` }),
      el("td", { text: `${s.estimate} pts` }),
      el("td", {}, badge(s.status)),
      el("td", {},
        el("button", {
          class: "kebab", text: "⋯",
          title: editable ? "Edit team / sprint / estimate" : "Plan locked at sign-off — changes require an amendment",
          onclick: (e) => {
            e.stopPropagation();
            if (!editable) { toast("Plan locked at sign-off — changes require an amendment", true); return; }
            state.editStory = editing ? null : s.story_id;
            render();
          },
        })),
    );
    if (!editing || !editable) return [row];
    const editRow = el("tr", { class: "edit-row" },
      el("td", { colspan: "7" },
        el("div", { class: "actions-row", style: "margin:0" },
          el("b", { text: `Edit ${s.story_id}:` }),
          el("label", {}, "Team ",
            el("select", { onchange: (e) => act(`/stories/${s.story_id}`, { patch: { accountable_team: e.target.value } }, `${s.story_id} reassigned`, "PATCH") },
              TEAMS.map((t) => Object.assign(el("option", { value: t, text: t }), { selected: t === s.accountable_team })))),
          el("label", {}, "Estimate ",
            el("select", { onchange: (e) => act(`/stories/${s.story_id}`, { patch: { estimate: Number(e.target.value) } }, `${s.story_id} re-estimated`, "PATCH") },
              [2, 3, 5, 8, 13].map((n) => Object.assign(el("option", { value: String(n), text: `${n} pts` }), { selected: n === s.estimate })))),
          el("label", {}, "Sprint ",
            el("select", { onchange: (e) => act(`/stories/${s.story_id}`, { patch: { sprint: Number(e.target.value) } }, `${s.story_id} moved`, "PATCH") },
              [1, 2, 3].map((n) => Object.assign(el("option", { value: String(n), text: `S${n}` }), { selected: n === s.sprint })))),
          el("button", { class: "ghost", text: "Close", onclick: () => { state.editStory = null; render(); } }),
        )));
    return [row, editRow];
  }

  function storiesPanel(stories, editable) {
    const filter = state.storyFilter ?? "";
    const shown = filter ? stories.filter((s) => s.accountable_team === filter) : stories;
    const teams = [...new Set(stories.map((s) => s.accountable_team))];
    const view = state.storyView ?? "table";

    const filterSel = el("select", {
      onchange: (e) => { state.storyFilter = e.target.value; render(); },
    },
      Object.assign(el("option", { value: "", text: "All teams" }), { selected: filter === "" }),
      teams.map((t) => Object.assign(el("option", { value: t, text: t }), { selected: t === filter })));

    const head = el("div", { class: "card-head" },
      el("h3", { text: `User Stories (${shown.length})` }),
      el("div", { class: "btns" },
        filterSel,
        el("button", { class: "outline", text: "⬇ Export", onclick: () => exportStories(shown) }),
        el("span", { class: "view-toggle" },
          el("button", { class: view === "table" ? "on" : "", text: "Table View", onclick: () => { state.storyView = "table"; render(); } }),
          el("button", { class: view === "board" ? "on" : "", text: "Board View", onclick: () => { state.storyView = "board"; render(); } }),
        ),
      ));

    if (view === "board") {
      const sprints = [...new Set(stories.map((s) => s.sprint))].sort();
      return el("div", { class: "card" }, head,
        el("div", { class: "board" }, sprints.map((sp) =>
          el("div", { class: "board-col" },
            el("h4", { text: `Sprint ${sp}` }),
            shown.filter((s) => s.sprint === sp).map((s) =>
              el("div", { class: "board-card" },
                el("div", { class: "mono", text: s.story_id }),
                el("div", { class: "t", text: s.title }),
                teamChip(s.accountable_team),
                el("div", { style: "margin-top:6px; display:flex; gap:6px; align-items:center" },
                  badge(s.status), el("span", { class: "hint", text: `${s.estimate} pts` })),
              ))))));
    }

    return el("div", { class: "card" }, head,
      el("p", { class: "hint", style: "margin:-4px 0 10px", text: "Click a row for the full story detail — purpose, targets, dependencies and acceptance criteria." }),
      el("div", { class: "table-wrap" },
        el("table", {},
          el("thead", {}, el("tr", {},
            ["Story ID", "Title", "Accountable Team", "Sprint", "Estimate", "Status", "Actions"].map((h) => el("th", { text: h })))),
          el("tbody", {}, shown.flatMap((s) => storyRow(s, editable))),
        )),
      el("div", { class: "table-foot" },
        el("span", { class: "hint", text: shown.length ? `Showing 1 to ${shown.length} of ${shown.length} stories` : "No stories match the filter" }),
        el("span", { class: "pager" },
          Object.assign(el("button", { class: "icon-btn", text: "‹" }), { disabled: true }),
          el("span", { class: "page-chip", text: "1" }),
          Object.assign(el("button", { class: "icon-btn", text: "›" }), { disabled: true }),
        )));
  }

  function gate1Rail() {
    const d = state.data;
    const gate = (d.gates ?? []).find((g) => g.gate_id === "G1");
    const plan = d.planning?.plan;
    const locked = d.run.plan_locked;

    // The engine evaluates Gate 1 conditions at sign-off. Before that, show a
    // preview computed from the same plan data (same precedent as storyGaps) —
    // labelled as a preview, never presented as the gate's own verdict.
    let conditions = gate?.conditions ?? [];
    let preview = false;
    if (conditions.length === 0) {
      preview = true;
      const stories = planningStories();
      const ids = new Set(stories.map((s) => s.story_id));
      conditions = [
        { condition: "Epic defined", met: Boolean(d.intake?.epic) },
        { condition: "Stories decomposed", met: stories.length > 0 },
        { condition: "Acceptance criteria defined", met: stories.length > 0 && stories.every((s) => s.acceptance_criteria?.length) },
        { condition: "Teams assigned", met: stories.length > 0 && stories.every((s) => s.accountable_team) },
        { condition: "Dependencies mapped", met: stories.length > 0 && stories.every((s) => s.dependencies.every((x) => ids.has(x))) },
        { condition: "Estimates provided", met: stories.length > 0 && stories.every((s) => s.estimate > 0) },
        { condition: "Story quality validated", met: stories.length > 0 && stories.every((s) => storyGaps(s).length === 0) },
        { condition: "Named approver", met: false, detail: "Recorded at sign-off" },
      ];
    }
    const checklist = el("ul", { class: "checklist" },
      conditions.map((c) =>
        el("li", { title: c.detail || "" },
          el("span", { class: `tick ${c.met ? "ok" : "no"}`, text: c.met ? "✓" : "·" }),
          c.condition,
          el("span", { class: `state ${c.met ? "ok" : "no"}`, text: c.met ? "Complete" : "Pending" }))),
      preview ? el("li", {}, el("span", { class: "hint", text: "Preview — the gate formally evaluates these at sign-off." })) : null,
    );

    const checkCard = el("div", { class: "card rail-card" },
      el("h3", {}, el("span", { class: "lock", text: locked ? "🔒" : "🔓" }), "Gate 1: Plan Sign-off"),
      el("p", { class: "hint", text: "Human approval required to lock the plan and proceed to execution." }),
      el("div", { class: "section-title", style: "margin:12px 0 0" },
        el("h3", { text: "Gate Checklist" }), badge(gate?.status ?? "not_started")),
      el("p", { class: "hint", text: "All items must be complete" }),
      checklist,
    );

    if (plan) {
      return [checkCard,
        el("div", { class: "card ok rail-card" },
          el("h3", { text: "Plan Sign-off" }),
          el("div", { class: "kv", style: "grid-template-columns: 110px 1fr; margin-top:10px" },
            el("b", { text: "Signed by" }), el("span", { text: plan.signed_by }),
            el("b", { text: "At" }), el("span", { class: "mono", text: plan.signed_at }),
            el("b", { text: "Version" }), el("span", { text: `v${plan.plan_version}` }),
            el("b", { text: "Note" }), el("span", { text: plan.note || "—" }),
          ),
          el("div", { class: "sig-box", text: plan.signed_by }),
        )];
    }

    const approverSel = el("select", {},
      el("option", { value: "business_owner", text: "Business Owner" }));
    const nameInput = el("input", { type: "text", placeholder: "Approver name (required)" });
    const noteArea = el("textarea", { rows: "3", maxlength: "500", placeholder: "Approval note (required)" });
    const counter = el("div", { class: "char-count", text: "0 / 500" });
    const sig = el("div", { class: "sig-box empty", text: "E-signature renders here as you type the approver name" });
    nameInput.addEventListener("input", () => {
      const v = nameInput.value.trim();
      sig.textContent = v || "E-signature renders here as you type the approver name";
      sig.classList.toggle("empty", !v);
    });
    noteArea.addEventListener("input", () => { counter.textContent = `${noteArea.value.length} / 500`; });

    const feedback = el("textarea", { rows: "2", placeholder: "What should the AI change? e.g. 'US-004 is underestimated'" });

    const signCard = el("div", { class: "card rail-card" },
      el("h3", { text: "Plan Sign-off" }),
      el("label", { class: "fld", text: "Approver *" }), approverSel,
      el("label", { class: "fld", text: "Approver name *" }), nameInput,
      el("label", { class: "fld", text: "Approval Note *" }), noteArea, counter,
      el("label", { class: "fld", text: "E-Signature" }), sig,
      el("div", { class: "sig-actions" },
        el("button", { text: "Clear", onclick: () => { nameInput.value = ""; nameInput.dispatchEvent(new Event("input")); } })),
      el("div", { class: "actions-row" },
        el("button", {
          class: "primary sq block", text: "🔒 Approve Plan & Lock",
          title: "Signs Gate 1 under the Business Owner role and locks the plan",
          onclick: () => act("/planning/sign-off",
            { role: approverSel.value, approver: nameInput.value, note: noteArea.value },
            "Plan signed and locked"),
        })),
      el("details", { style: "margin-top:12px" },
        el("summary", { class: "hint", text: "Request AI Revision" }),
        feedback,
        el("div", { class: "actions-row" },
          el("button", {
            class: "outline block", text: "⟳ Request AI Revision",
            onclick: () => act("/planning/revise", { feedback: feedback.value }, "Revision requested"),
          }))),
    );
    return [checkCard, signCard];
  }

  function planningAssistantCards(stories) {
    const d = state.data;
    const conf = d.planning?.confidence;
    const rationale = d.planning?.rationale;
    const allSimulated = stories.every((s) => s.provenance === "simulated");
    const acs = stories.flatMap((s) => s.acceptance_criteria).length;
    const deps = stories.flatMap((s) => s.dependencies).length;
    const teams = new Set(stories.map((s) => s.accountable_team)).size;
    const rollbacks = stories.filter((s) => s.rollback_plan).length;
    const risks = d.intake?.analysis?.risk_register?.length ?? d.intake?.analysis?.risks?.length ?? 0;
    return el("div", { class: "grid cols-2", style: "margin-top:14px" },
      el("div", { class: "card" },
        el("div", { class: "section-title" },
          el("h3", { text: "✦ AI Planning Assistant" }),
          el("span", { class: "hint", text: allSimulated ? "AI decomposition" : "AI + human stories" })),
        el("ul", { class: "checklist" },
          checkItem(true, "Epic analysed"),
          checkItem(stories.length > 0, "Stories generated", stories.length),
          checkItem(acs > 0, "Acceptance criteria generated", acs),
          checkItem(true, "Dependencies identified", deps),
          checkItem(teams > 0, "Teams mapped", teams),
          checkItem(true, "Planned sprints", new Set(stories.map((s) => s.sprint)).size),
          checkItem(risks > 0, "Risks identified", risks),
          checkItem(rollbacks === stories.length, "Rollback plans defined", `${rollbacks}/${stories.length}`))),
      el("div", { class: "card" },
        el("h3", { text: "AI Planning Rationale" }),
        el("p", { class: "hint", style: "margin-top:8px", text: rationale?.text ?? "The rationale is produced with the AI decomposition — generate the draft plan to see it." }),
        conf ? el("div", { class: "conf-row" },
          el("b", { text: "AI Confidence" }),
          el("span", { class: "info conf-v", title: conf.basis, text: `${conf.value}% ⓘ` })) : null));
  }

  function renderEpicToStories() {
    const stories = planningStories();
    const locked = state.data.run.plan_locked;

    const content = el("div", {},
      el("div", { class: "page-head", style: "margin-bottom:16px" },
        el("h2", { text: "Epic to Stories (AI Decomposition)" }),
        el("span", { class: "hint", text: "The planning model decomposes the epic into testable user stories and maps teams and dependencies. Humans edit, extend and sign off." })),
      epicDetailsCard(),
      stories.length
        ? [planningAssistantCards(stories), kpiTiles(planKpis(stories)), storiesPanel(stories, !locked)]
        : el("div", { class: "card", style: "margin-top:14px" },
          el("p", { text: "No stories yet. Use “AI Suggest Stories” above once the intake gate (G0) has passed." })),
    );

    return el("section", { class: "page-with-rail" },
      content,
      el("aside", { class: "rail" }, gate1Rail()),
    );
  }

  // --- dependency graph helpers ---------------------------------------------

  const TEAM_COLORS = ["#2c5f8f", "#7a4b9b", "#1e7a46", "#a8781f", "#b0243a", "#0f766e", "#5a6b7d"];

  function teamColor(name) {
    let i = TEAMS.indexOf(name);
    if (i === -1) i = [...String(name)].reduce((a, c) => a + c.charCodeAt(0), 0);
    return TEAM_COLORS[i % TEAM_COLORS.length];
  }

  function depGraph(stories) {
    const byId = Object.fromEntries(stories.map((s) => [s.story_id, s]));
    const depth = {};
    const resolving = new Set();
    const depthOf = (id) => {
      if (depth[id] != null) return depth[id];
      if (resolving.has(id)) return 0; // cycle guard; the engine prevents these
      resolving.add(id);
      const deps = (byId[id]?.dependencies ?? []).filter((x) => byId[x]);
      depth[id] = deps.length ? Math.max(...deps.map(depthOf)) + 1 : 0;
      resolving.delete(id);
      return depth[id];
    };
    stories.forEach((s) => depthOf(s.story_id));

    const memo = {};
    const chainOf = (id) => {
      if (memo[id]) return memo[id];
      let best = [];
      for (const dep of (byId[id]?.dependencies ?? []).filter((x) => byId[x])) {
        const c = chainOf(dep);
        if (c.length > best.length) best = c;
      }
      memo[id] = [...best, id];
      return memo[id];
    };
    let critical = [];
    stories.forEach((s) => {
      const c = chainOf(s.story_id);
      if (c.length > critical.length) critical = c;
    });

    const edges = [];
    for (const s of stories) {
      for (const dep of s.dependencies) {
        if (!byId[dep]) continue;
        edges.push({
          from: dep, to: s.story_id,
          cross: byId[dep].accountable_team !== s.accountable_team,
        });
      }
    }
    return { depth, critical, edges };
  }

  function drawDepArrows(container, edges, vertical) {
    const svg = container.querySelector("svg.dep-arrows");
    if (!svg) return;
    const ns = "http://www.w3.org/2000/svg";
    const box = container.getBoundingClientRect();
    svg.setAttribute("width", container.scrollWidth);
    svg.setAttribute("height", container.scrollHeight);
    svg.replaceChildren();
    const defs = document.createElementNS(ns, "defs");
    defs.innerHTML =
      '<marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">' +
      '<path d="M0,0 L8,4 L0,8 z" fill="#64707a"/></marker>';
    svg.appendChild(defs);
    for (const e of edges) {
      const a = container.querySelector(`[data-story="${e.from}"]`);
      const b = container.querySelector(`[data-story="${e.to}"]`);
      if (!a || !b) continue;
      const ra = a.getBoundingClientRect();
      const rb = b.getBoundingClientRect();
      let x1, y1, x2, y2;
      if (vertical) {
        x1 = ra.left - box.left + ra.width / 2 + container.scrollLeft;
        y1 = ra.bottom - box.top + container.scrollTop;
        x2 = rb.left - box.left + rb.width / 2 + container.scrollLeft;
        y2 = rb.top - box.top + container.scrollTop;
      } else {
        x1 = ra.right - box.left + container.scrollLeft;
        y1 = ra.top - box.top + ra.height / 2 + container.scrollTop;
        x2 = rb.left - box.left + container.scrollLeft;
        y2 = rb.top - box.top + rb.height / 2 + container.scrollTop;
      }
      const path = document.createElementNS(ns, "path");
      const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
      path.setAttribute("d", vertical
        ? `M ${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2}`
        : `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`);
      path.setAttribute("fill", "none");
      path.setAttribute("stroke", "#64707a");
      path.setAttribute("stroke-width", "1.6");
      path.setAttribute("marker-end", "url(#arr)");
      if (e.cross) path.setAttribute("stroke-dasharray", "5 4");
      svg.appendChild(path);
    }
  }

  function renderDependencyMap() {
    const all = planningStories();
    if (!all.length) return notBuilt("Dependency Map", "the Planning stage — generate the draft plan first");
    const filter = state.depFilter ?? "";
    const vertical = (state.depLayout ?? "ttb") === "ttb";
    const stories = filter ? all.filter((s) => s.accountable_team === filter) : all;
    const { depth, critical, edges } = depGraph(stories);
    const graphAll = depGraph(all);
    const teams = [...new Set(all.map((s) => s.accountable_team))];
    const maxDepth = Math.max(0, ...Object.values(depth));

    const columns = [];
    for (let d = 0; d <= maxDepth; d++) {
      const col = stories.filter((s) => depth[s.story_id] === d);
      if (!col.length) continue;
      columns.push(el("div", { class: "dep-col" }, col.map((s) =>
        el("div", { class: "dep-card", "data-story": s.story_id, style: `border-color:${teamColor(s.accountable_team)}` },
          el("div", { class: "mono dep-id", style: `color:${teamColor(s.accountable_team)}`, text: s.story_id }),
          el("div", { class: "dep-title", text: s.title }),
          el("div", { class: "dep-meta" },
            el("span", { class: "hint", text: s.accountable_team }),
            el("span", { class: "sprint-chip", text: `S${s.sprint}` })),
        ))));
    }
    const graph = el("div", { class: `dep-graph ${vertical ? "vertical" : ""}` },
      Object.assign(document.createElementNS("http://www.w3.org/2000/svg", "svg"),
        {}) , columns);
    const svg = graph.firstChild;
    svg.setAttribute("class", "dep-arrows");
    requestAnimationFrame(() => drawDepArrows(graph, edges, vertical));

    const viewSel = el("select", { onchange: (e) => { state.depFilter = e.target.value; render(); } },
      Object.assign(el("option", { value: "", text: "All Stories" }), { selected: filter === "" }),
      teams.map((t) => Object.assign(el("option", { value: t, text: t }), { selected: t === filter })));
    const layoutSel = el("select", { onchange: (e) => { state.depLayout = e.target.value === "Top to Bottom" ? "ttb" : "ltr"; render(); } },
      Object.assign(el("option", { text: "Left to Right" }), { selected: !vertical }),
      Object.assign(el("option", { text: "Top to Bottom" }), { selected: vertical }));

    const legend = el("div", { class: "dep-legend" },
      teams.map((t) => el("span", { class: "legend-item" },
        el("span", { class: "legend-dot", style: `background:${teamColor(t)}` }), t)),
      el("span", { class: "legend-item" }, el("span", { class: "legend-line solid" }), "Dependency"),
      el("span", { class: "legend-item" }, el("span", { class: "legend-line dashed" }), "Cross Dependency"),
    );

    const crossCount = graphAll.edges.filter((e) => e.cross).length;
    const rail = el("aside", { class: "rail" },
      el("div", { class: "card rail-card" },
        el("h3", { text: "Map Summary" }),
        el("ul", { class: "checklist" },
          [["Total Stories", all.length],
            ["Dependencies", graphAll.edges.length],
            ["Cross Dependencies", crossCount],
            ["Teams Involved", teams.length],
            ["Planned Sprints", new Set(all.map((s) => s.sprint)).size],
          ].map(([label, v]) => el("li", {}, label, el("span", { class: "state ok", text: String(v) }))))),
      el("div", { class: "card rail-card" },
        el("h3", { text: "Critical Path" }),
        el("p", { class: "hint", text: "The longest dependency chain — computed from the plan's edges." }),
        el("ol", { class: "critical-path" }, graphAll.critical.map((id) =>
          el("li", {}, el("span", { class: "mono", text: id }))))),
    );

    return el("section", { class: "page-with-rail" },
      el("div", {},
        el("div", { class: "page-head", style: "margin-bottom:16px" },
          el("h2", { text: `Dependency Map ${all.every((s) => s.provenance === "simulated") ? "(AI Generated)" : "(AI + Human)"}` }),
          el("span", { class: "hint", text: "The planning model identified the dependencies and delivery sequence; human stories join the same graph." })),
        el("div", { class: "card" },
          el("div", { class: "card-head" },
            el("div", { class: "btns" },
              el("label", { class: "hdr-field" }, el("span", { class: "hdr-label", text: "View" }), viewSel),
              el("label", { class: "hdr-field" }, el("span", { class: "hdr-label", text: "Layout" }), layoutSel)),
            el("button", {
              class: "outline", text: "⚑ Legend",
              onclick: () => { state.depLegend = !(state.depLegend ?? true); render(); },
            })),
          graph,
          (state.depLegend ?? true) ? legend : null,
        )),
      rail,
    );
  }

  function renderRoutingByTeam() {
    const stories = planningStories();
    if (!stories.length) return notBuilt("Routing by Team", "the Planning stage — generate the draft plan first");
    const teams = [...new Set(stories.map((s) => s.accountable_team))];
    const k = planKpis(stories);
    return el("section", {},
      el("div", { class: "page-head", style: "margin-bottom:16px" },
        el("h2", { text: "Routing by Team" }),
        el("span", { class: "hint", text: "Stories grouped by accountable team with planned delivery." })),
      el("div", { class: "tiles tiles-4" },
        el("div", { class: "tile t-green" }, el("div", { class: "v", text: String(teams.length) }), el("div", { class: "l", text: "Teams Involved" })),
        el("div", { class: "tile t-red" }, el("div", { class: "v", text: String(k.stories) }), el("div", { class: "l", text: "Total Stories" })),
        el("div", { class: "tile t-red" }, el("div", { class: "v", text: String(k.acs) }), el("div", { class: "l", text: "Acceptance Criteria" })),
        el("div", { class: "tile t-amber" }, el("div", { class: "v", text: String(k.sprints) }), el("div", { class: "l", text: "Planned Sprints" })),
      ),
      el("div", { class: "team-cols" }, teams.map((t) => {
        const own = stories.filter((s) => s.accountable_team === t);
        const pts = own.reduce((a, s) => a + s.estimate, 0);
        return el("div", { class: "card team-col" },
          el("div", { class: "team-col-head", style: `border-color:${teamColor(t)}` },
            el("h3", {}, el("span", { class: "legend-dot", style: `background:${teamColor(t)}` }), t),
            el("span", { class: "hint", text: `${own.length} ${own.length === 1 ? "Story" : "Stories"}` })),
          own.map((s) => el("div", { class: "board-card" },
            el("div", { class: "mono", style: `color:${teamColor(t)}`, text: s.story_id }),
            el("div", { class: "t", text: s.title }),
            el("div", { class: "dep-meta" },
              el("span", { class: "hint mono", text: s.target_component }),
              el("button", { class: "pts-chip", title: "View the estimate breakdown", text: `${s.estimate} pts`, onclick: () => storyDetailModal(s) })))),
          el("div", { class: "hint", style: "margin-top:4px" },
            el("b", { text: "AI Rationale: " }),
            `Owns ${[...new Set(own.map((s) => s.target_component))].join(", ")}.`),
          el("div", { class: "team-col-foot", text: `Total: ${pts} pts` }));
      })),
    );
  }

  // --- plan summary ---------------------------------------------------------

  const SUMMARY_TABS = [
    ["summary", "Summary"], ["stories", "Stories"], ["dependencies", "Dependencies"],
    ["risks", "Risks"], ["assumptions", "Assumptions"], ["impacts", "Impacts"],
    ["artifacts", "Artifacts"],
  ];

  function donut(stories) {
    const teams = [...new Set(stories.map((s) => s.accountable_team))];
    let acc = 0;
    const stops = [];
    for (const t of teams) {
      const n = stories.filter((s) => s.accountable_team === t).length;
      const from = (360 * acc) / stories.length;
      acc += n;
      const to = (360 * acc) / stories.length;
      stops.push(`${teamColor(t)} ${from}deg ${to}deg`);
    }
    return el("div", { class: "donut-wrap" },
      el("div", { class: "donut", style: `background: conic-gradient(${stops.join(", ")})` },
        el("div", { class: "donut-hole" },
          el("div", { class: "v", text: String(stories.length) }),
          el("div", { class: "l", text: "Stories" }))),
      el("ul", { class: "donut-legend" }, teams.map((t) =>
        el("li", {},
          el("span", { class: "legend-dot", style: `background:${teamColor(t)}` }),
          `${t} (${stories.filter((s) => s.accountable_team === t).length})`))),
    );
  }

  function sprintPlanCard(stories) {
    const sprints = [...new Set(stories.map((s) => s.sprint))].sort();
    const totalPts = stories.reduce((a, s) => a + s.estimate, 0) || 1;
    return el("div", { class: "card" },
      el("h3", { text: "Sprint Plan" }),
      sprints.map((sp) => {
        const own = stories.filter((s) => s.sprint === sp);
        const pts = own.reduce((a, s) => a + s.estimate, 0);
        return el("div", { class: "sprint-row" },
          el("div", { class: "sprint-row-head" },
            el("b", { text: `Sprint ${sp}` }),
            el("span", { class: "hint", text: `${own.length} ${own.length === 1 ? "story" : "stories"} · ${pts} pts` })),
          el("div", { class: "bar" },
            el("div", { class: "bar-fill", style: `width:${Math.round((100 * pts) / totalPts)}%` })));
      }),
      el("p", { class: "hint", text: "Bar shows each sprint's share of planned points. Sprint dates are set at execution, not invented here." }),
    );
  }

  function renderPlanSummary() {
    const stories = planningStories();
    if (!stories.length) return notBuilt("Plan Summary", "the Planning stage — generate the draft plan first");
    const d = state.data;
    const plan = d.planning?.plan;
    const epic = d.intake?.epic;
    const analysis = d.intake?.analysis;
    const conf = d.planning?.confidence;
    const tab = state.summaryTab ?? "summary";
    const graph = depGraph(stories);

    const tabs = el("div", { class: "tabs" }, SUMMARY_TABS.map(([key, label]) =>
      el("button", {
        class: key === tab ? "on" : "",
        text: label,
        onclick: () => { state.summaryTab = key; render(); },
      })));

    let body;
    if (tab === "stories") {
      body = storiesPanel(stories, false);
    } else if (tab === "dependencies") {
      body = el("div", { class: "table-wrap" },
        el("table", {},
          el("thead", {}, el("tr", {}, ["Story", "Depends on", "Blocks", "Cross-team"].map((h) => el("th", { text: h })))),
          el("tbody", {}, stories.map((s) => el("tr", {},
            el("td", { class: "mono", text: s.story_id }),
            el("td", { class: "mono", text: s.dependencies.join(", ") || "—" }),
            el("td", { class: "mono", text: graph.edges.filter((e) => e.from === s.story_id).map((e) => e.to).join(", ") || "—" }),
            el("td", { text: graph.edges.some((e) => (e.to === s.story_id) && e.cross) ? "yes" : "—" }),
          )))));
    } else if (tab === "risks") {
      body = el("div", { class: "card" },
        el("h3", { text: "Risks named at intake" }),
        el("ul", { class: "plain" }, (analysis?.risks ?? []).map((r) => el("li", { text: r }))));
    } else if (tab === "assumptions") {
      body = el("div", { class: "card" },
        el("h3", { text: "Assumptions carried by the plan" }),
        el("ul", { class: "plain" }, (analysis?.assumptions ?? []).map((a) => el("li", { text: a }))));
    } else if (tab === "impacts") {
      body = el("div", { class: "grid cols-2" },
        el("div", { class: "card" },
          el("h3", { text: "Affected applications" }),
          el("ul", { class: "plain" }, (analysis?.affected_applications ?? []).map((a) => el("li", { text: a })))),
        el("div", { class: "card" },
          el("h3", { text: "External dependencies" }),
          el("ul", { class: "plain" }, (analysis?.dependencies ?? []).map((a) => el("li", { text: a })))));
    } else if (tab === "artifacts") {
      body = artifactsCard(false);
    } else {
      body = el("div", {},
        el("div", { class: "grid cols-3" },
          el("div", { class: "card" },
            el("h3", { text: "Plan Overview" }),
            el("div", { class: "kv", style: "grid-template-columns: 130px 1fr; margin-top:10px" },
              el("b", { text: "Epic" }), el("span", { text: epic?.title ?? "—" }),
              el("b", { text: "Epic ID" }), el("span", { class: "mono", text: epic?.epic_id ?? "—" }),
              el("b", { text: "Plan Version" }), el("span", { text: plan ? `v${plan.plan_version}` : "draft (unsigned)" }),
              el("b", { text: "Created On" }), el("span", { text: (epic?.created_at ?? "").slice(0, 10) || "—" }),
              el("b", { text: "Created By" }), el("span", { text: epic?.created_by ?? "—" }),
              el("b", { text: "Signed" }), el("span", { text: plan ? `${plan.signed_by} · ${plan.signed_at.slice(0, 16).replace("T", " ")}` : "not yet" }),
              el("b", { text: "AI Plan Confidence" }),
              el("span", {}, el("span", {
                class: "info", title: conf?.basis ?? "",
                text: conf ? `${conf.value}% ⓘ` : "—",
              })))),
          el("div", { class: "card" },
            el("h3", { text: "Delivery Breakdown" }),
            donut(stories)),
          sprintPlanCard(stories),
        ),
        (() => {
          const ids = new Set(stories.map((s) => s.story_id));
          const acyclic = graph.critical.length <= stories.length;
          const depsOk = stories.every((s) => s.dependencies.every((x) => ids.has(x)));
          const rollbacksOk = stories.every((s) => s.rollback_plan);
          const acsOk = stories.every((s) => s.acceptance_criteria?.length);
          const register = analysis?.risk_register ?? [];
          return el("div", { class: "grid cols-2", style: "margin-top:14px" },
            el("div", { class: "card" },
              el("h3", { text: "✦ AI Key Observations" }),
              el("p", { class: "hint", text: "Each observation is checked against the plan data, not asserted." }),
              el("ul", { class: "checklist" },
                checkItem(acsOk, "All stories are covered by acceptance criteria"),
                checkItem(depsOk && acyclic, "Dependencies are valid and free of cycles"),
                checkItem(acsOk, "Test coverage planned for every acceptance criterion"),
                checkItem(rollbacksOk, "Rollback plans defined for all stories"),
                checkItem(new Set(stories.map((s) => s.sprint)).size <= 2, `Plan is feasible within ${new Set(stories.map((s) => s.sprint)).size} sprint(s)`)),
              el("h3", { style: "margin-top:12px", text: "Key Assumptions" }),
              el("ul", { class: "plain" }, (analysis?.assumptions ?? []).map((a) => el("li", { text: a })))),
            el("div", { class: "card" },
              el("h3", { text: "⚠ AI Identified Risks" }),
              register.length
                ? register.map((r) => el("div", { class: `risk-line ${r.severity === "high" ? "red" : "amber"}` },
                  el("b", { text: r.severity.toUpperCase() }),
                  el("span", { text: r.text })))
                : el("ul", { class: "plain" }, (analysis?.risks ?? []).map((r) => el("li", { text: r })))));
        })());
    }

    return el("section", {},
      el("div", { class: "page-head", style: "margin-bottom:12px" },
        el("h2", { text: "Plan Summary" }),
        el("span", { class: "hint", text: "Review the complete plan at a glance." })),
      tabs,
      body,
    );
  }

  // --- plan sign-off page ---------------------------------------------------

  const ARTIFACT_DESCRIPTIONS = {
    "plan.json": "Signed plan in machine-readable format",
    "plan.md": "Human-readable plan",
    "stories.json": "User stories and details",
    "design.json": "Design decisions the stories derive from",
    "confidence.json": "Planning model self-assessment (simulated)",
    "revision-notes.json": "Requested AI revisions",
  };

  function downloadPlanningFile(name) {
    const a = el("a", { href: `/api/runs/${state.runId}/planning/files/${name}`, download: name });
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function artifactsCard(showDownloadAll = true) {
    const files = state.planningFiles ?? [];
    const locked = state.data.run.plan_locked;
    return el("div", { class: "card" },
      el("div", { class: "card-head" },
        el("h3", { text: `Plan Artifacts ${locked ? "(Locked on Approval)" : "(Draft)"}` }),
        showDownloadAll && files.length ? el("button", {
          class: "outline", text: "⬇ Download All Artifacts",
          onclick: () => files.forEach((f, i) => setTimeout(() => downloadPlanningFile(f.name), i * 250)),
        }) : null),
      files.length === 0
        ? el("p", { class: "hint", text: "No planning artifacts on disk yet — generate the draft plan first." })
        : el("ul", { class: "artifact-list" }, files.map((f) =>
          el("li", {},
            el("span", { class: "file-ico", text: f.name.endsWith(".md") ? "▤" : "{}" }),
            el("div", { class: "file-meta" },
              el("code", { text: `planning/${f.name}` }),
              el("span", { class: "hint", text: ARTIFACT_DESCRIPTIONS[f.name] ?? "Planning artifact" })),
            el("span", { class: "hint mono", text: `${Math.max(1, Math.round(f.bytes / 1024))} KB` }),
            el("button", { class: "icon-btn", text: "⬇", title: `Download ${f.name}`, onclick: () => downloadPlanningFile(f.name) }),
          ))),
    );
  }

  function renderPlanSignoff() {
    const d = state.data;
    const isLive = d.run?.mode === "live";
    const stories = planningStories();
    const plan = d.planning?.plan;
    const conf = d.planning?.confidence;
    const analysis = d.intake?.analysis;
    const graph = stories.length ? depGraph(stories) : { edges: [] };
    const complete = stories.filter((s) => storyGaps(s).length === 0).length;
    const acs = stories.flatMap((s) => s.acceptance_criteria).length;
    const ready = stories.length > 0 && complete === stories.length;

    const estimatesOk = stories.filter((s) => s.estimate > 0).length;
    const rollbacksOk = stories.filter((s) => s.rollback_plan).length;
    const readiness = el("div", { class: "card" },
      el("div", { class: "section-title" },
        el("h3", { text: "✦ AI Plan Assessment" }),
        el("span", { class: "hint", text: "AI recommendation and human approval required to lock the plan" })),
      el("div", { class: "readiness" },
        el("div", { class: "readiness-rows" },
          [["Story completeness", stories.length ? `${Math.round((100 * complete) / stories.length)}%` : "—"],
            ["Stories ready", `${complete} / ${stories.length}`],
            ["Acceptance criteria testable", `${acs} / ${acs}`],
            ["Dependencies mapped", `${graph.edges.length} / ${graph.edges.length}`],
            ["Estimates provided", `${estimatesOk} / ${stories.length}`],
            ["Rollback plans defined", `${rollbacksOk} / ${stories.length}`],
            ["Risks identified", String((analysis?.risk_register ?? analysis?.risks ?? []).length)],
            ["Assumptions documented", String((analysis?.assumptions ?? []).length)],
            ["AI Plan Confidence", conf ? `${conf.value}%` : "—"],
          ].map(([label, v]) => el("div", { class: "readiness-row" },
            el("span", { text: label }), el("b", { text: v })))),
        el("div", { class: `readiness-verdict ${ready ? "ok" : "warn"}` },
          el("span", { class: "big-check", text: ready ? "✓" : "…" }),
          el("p", { text: ready
            ? (plan ? "Plan is signed and locked." : "Plan is ready for sign-off. All mandatory requirements are complete.")
            : "Not ready — every story must pass quality validation first." }),
          el("p", { class: "hint", text: ready && !plan ? "AI Recommendation: READY FOR PLAN APPROVAL — derived from the validation rules on the left, decided by the human on the right." : "" }))),
    );

    const approvals = (d.approvals ?? []).filter((a) => a.subject === "plan");
    const historyRows = approvals.length
      ? approvals.map((a) => [a.approver, a.role.replaceAll("_", " "), a.decision, a.decided_at])
      : (plan ? [[plan.signed_by, "business owner", "approved", plan.signed_at]] : []);
    const history = el("div", { class: "card" },
      el("h3", { text: "Approval History" }),
      historyRows.length === 0
        ? el("p", { class: "hint", text: "No approvals yet — the sign-off below records the first." })
        : el("div", { class: "table-wrap", style: "margin-top:10px" },
          el("table", {},
            el("thead", {}, el("tr", {}, ["Approver", "Role", "Status", "Date & Time"].map((h) => el("th", { text: h })))),
            el("tbody", {}, historyRows.map(([who, role, status, at]) => el("tr", {},
              el("td", { text: who }),
              el("td", { text: role }),
              el("td", {}, badge(status === "approved" ? "passed" : "failed")),
              el("td", { class: "mono", text: at }),
            ))))),
    );

    const repoNames = [...new Set(stories.map((s) => s.target_repository))];
    const handoffCard = d.run?.plan_locked && isLive ? el("div", { class: "card" },
      el("div", { class: "section-title" }, el("h3", { text: "Delivery Handoff" }),
        el("span", { class: "hint", text: "Portable, per-team packages — no .claude/ tooling" })),
      el("div", { class: "actions-row", style: "gap:8px; flex-wrap:wrap" },
        el("button", {
          class: "outline", text: "Export Artifacts",
          onclick: () => act("/planning/export-artifacts", {}, "Artifacts exported"),
        }),
        el("button", {
          class: "outline", text: "Write to Clone",
          onclick: () => act("/planning/write-to-clone", {}, "Committed locally to each target repo"),
        }),
        el("button", {
          class: "outline", text: "⬇ Download Zip",
          onclick: () => { window.location.href = `${API}/api/runs/${state.runId}/planning/export.zip`; },
        })),
      el("p", { class: "hint", style: "margin-top:10px", text:
        "Pushing creates delivery/" + state.runId + " on each target repo — a fresh, disposable branch, never the default branch. Merging it into your own working branch is a manual step; nothing here does that for you." }),
      el("div", { class: "actions-row", style: "gap:8px; flex-wrap:wrap; margin-top:8px" },
        ...repoNames.map((repo) => el("button", {
          class: "primary sq", text: `Push delivery branch → ${repo}`,
          onclick: () => act("/planning/push-delivery-branch", { repo_name: repo }, `Pushed to ${repo}`),
        }))),
    ) : null;

    return el("section", { class: "page-with-rail" },
      el("div", {},
        el("div", { class: "page-head", style: "margin-bottom:16px" },
          el("h2", { text: "Plan Sign-off (Gate 1)" }),
          el("span", { class: "hint", text: "Review and approve the plan to lock it and proceed to execution." })),
        readiness,
        el("div", { style: "margin-top:14px" }, history),
        handoffCard ? el("div", { style: "margin-top:14px" }, handoffCard) : null,
        el("div", { style: "margin-top:14px" }, artifactsCard(true)),
      ),
      el("aside", { class: "rail" }, gate1Rail()),
    );
  }

  // --- build & review pages (customer wireframes, MapleSure-branded) --------

  function buildTasks() { return state.data.build?.tasks ?? []; }

  function currentTask() {
    const tasks = buildTasks();
    return tasks.find((t) => t.task_id === state.taskId)
      ?? tasks.find((t) => t.status === "in_progress")
      ?? tasks.find((t) => t.status !== "completed")
      ?? tasks[0];
  }

  function storyOf(task) {
    return planningStories().find((s) => s.story_id === task?.story_id);
  }

  function reviewsFor(taskId) {
    return (state.data.build?.reviews ?? []).filter((r) => r.task_id === taskId);
  }

  function latestReviewFor(taskId) {
    const reviews = reviewsFor(taskId);
    return reviews[reviews.length - 1];
  }

  function taskActivity(taskId) {
    return (state.data.activity ?? []).filter((a) => a.artifact === taskId);
  }

  function hhmm(iso) { return (iso ?? "").slice(11, 16) || "—"; }

  function buildEmpty(name) {
    return el("section", {},
      sectionTitle(name),
      el("div", { class: "card" },
        el("p", { text: "The work queue is seeded when the plan is signed at Gate 1." })));
  }

  function guidanceCard() {
    return el("div", { class: "card rail-card guidance" },
      el("h3", { text: "✓ Customer-safe guidance" }),
      el("p", { class: "hint", text: "This is a customer-safe view. No IDE, code, CLI, logs, or system internals are shown." }),
      el("p", { class: "hint", text: "Only governed execution evidence and status are visible." }),
      el("p", { class: "hint", text: "All work is traceable, human-approved and audit-ready." }));
  }

  function pauseButton() {
    return Object.assign(el("button", {
      class: "outline block", text: "⏸ Pause Run",
      title: "The demo engine advances in discrete governed steps — there is no long-running process to pause, so this control is honestly disabled rather than mocked.",
    }), { disabled: true });
  }

  const AGENT_PIPELINE = [
    ["⚗", "AI Test Engineer", "Generates tests from ACs"],
    ["⌨", "AI Developer", "Implements code against tests"],
    ["▶", "AI Test Engineer", "Executes tests and verifies"],
    ["◈", "Independent AI Reviewer", "Validates changes independently"],
    ["✍", "Human Approval", "Approves or returns for changes"],
  ];

  function agentPipelineCard() {
    return el("div", { class: "card" },
      el("div", { class: "section-title" },
        el("h3", { text: "AI agents collaborate to implement, test and independently review changes" }),
        el("span", { class: "hint", text: "Roles enforced by the engine — no phase self-approves" })),
      el("div", { class: "agent-flow" }, AGENT_PIPELINE.flatMap(([ico, name, desc], i) => [
        i > 0 ? el("span", { class: "agent-arrow", text: "→" }) : null,
        el("div", { class: `agent-box ${i === AGENT_PIPELINE.length - 1 ? "human" : ""}` },
          el("span", { class: "agent-ico", text: ico }),
          el("b", { text: name }),
          el("span", { class: "hint", text: desc })),
      ])));
  }

  function relTime(iso) {
    const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 90) return "just now";
    if (s < 3600) return `${Math.round(s / 60)}m ago`;
    if (s < 86400) return `${Math.round(s / 3600)}h ago`;
    return iso.slice(0, 10);
  }

  function buildAiPanels(tasks) {
    const acts = (state.data.activity ?? [])
      .filter((a) => a.actor_type === "simulation" && a.artifact?.startsWith("TASK-"))
      .slice(-4).reverse();
    const tests = tasks.flatMap((t) => t.tests ?? []);
    const green = tests.filter((t) => t.current_result === "passed").length;
    const majors = (state.data.build?.reviews ?? []).reduce((a, r) => a + r.major_gaps, 0);
    const plan = state.data.planning?.plan;
    const planned = new Set(plan?.story_ids ?? []);
    const inScope = tasks.every((t) => planned.has(t.story_id));
    return el("div", { class: "grid cols-2", style: "margin-top:14px" },
      el("div", { class: "card" },
        el("h3", { text: "AI Activity (Live)" }),
        acts.length ? el("ul", { class: "checklist" }, acts.map((a) =>
          el("li", {},
            el("span", { class: "tick ok", text: "✓" }),
            `${a.artifact} — ${WORKFLOW_LABELS[a.workflow] ?? a.workflow}`,
            el("span", { class: "state ok", text: relTime(a.timestamp) }))))
          : el("p", { class: "hint", text: "No agent activity yet — start a task." })),
      el("div", { class: "card" },
        el("h3", { text: "Key AI Insights" }),
        el("p", { class: "hint", text: "Computed from run evidence, never asserted." }),
        el("ul", { class: "checklist" },
          checkItem(tests.length > 0, `${tests.length ? Math.round((100 * green) / tests.length) : 0}% of targeted tests passing across started stories`),
          checkItem(majors === 0, majors === 0 ? "No major findings open from independent review" : `${majors} major finding(s) raised by the reviewer`),
          checkItem(inScope, "All changes map to stories in the signed plan"))));
  }

  function renderBuildWorkQueue() {
    const tasks = buildTasks();
    if (!tasks.length) return buildEmpty("Build & Independent Review");
    const search = (state.taskSearch ?? "").toLowerCase();
    const shown = search
      ? tasks.filter((t) => `${t.task_id} ${t.story_id} ${t.summary} ${t.accountable_team}`.toLowerCase().includes(search))
      : tasks;
    const task = currentTask();
    const story = storyOf(task);
    const count = (st) => tasks.filter((t) => t.status === st).length;
    const readiness = Math.round(tasks.reduce((a, t) => a + t.progress_pct, 0) / tasks.length);
    const depsDone = (t) => t.dependencies.every((d) => tasks.find((x) => x.task_id === d)?.status === "completed");
    const readyToStart = tasks.filter((t) => ["ready", "not_started"].includes(t.status) && depsDone(t));
    const teams = [...new Set(tasks.map((t) => t.accountable_team))];

    const searchBox = el("input", {
      type: "text", class: "search-box", placeholder: "Search tasks...", value: state.taskSearch ?? "",
      oninput: (e) => { state.taskSearch = e.target.value; render(); },
    });
    searchBox.value = state.taskSearch ?? "";

    const table = el("div", { class: "card" },
      el("div", { class: "card-head" },
        el("h3", { text: "Work Queue" }), searchBox),
      el("p", { class: "hint", style: "margin:-4px 0 10px", text: "Click a row to focus it — owner, component and dependencies appear in Current Focus." }),
      el("div", { class: "table-wrap" },
        el("table", {},
          el("thead", {}, el("tr", {},
            ["Task", "Accountable Team", "Status", "Last Activity", "Actions"].map((h) => el("th", { text: h })))),
          el("tbody", {}, shown.map((t) => {
            return el("tr", {
              class: t.task_id === task?.task_id ? "sel" : "",
              style: "cursor:pointer",
              onclick: () => { state.taskId = t.task_id; render(); },
            },
              el("td", {},
                el("div", { class: "mono", text: t.task_id }),
                el("div", { text: t.summary }),
                el("div", { class: "hint mono", text: t.story_id })),
              el("td", {}, teamChip(t.accountable_team)),
              el("td", {}, badge(t.status)),
              el("td", { class: "mono", text: hhmm(t.last_activity) }),
              el("td", {}, el("button", {
                class: "kebab", text: "⋯", title: "Open in Development Progress",
                onclick: (e) => { e.stopPropagation(); state.taskId = t.task_id; go("dev_progress"); },
              })));
          })))),
      el("div", { class: "table-foot" },
        el("span", { class: "hint", text: `Showing 1 to ${shown.length} of ${tasks.length} tasks` }),
        el("span", { class: "pager" },
          Object.assign(el("button", { class: "icon-btn", text: "‹" }), { disabled: true }),
          el("span", { class: "page-chip", text: "1" }),
          Object.assign(el("button", { class: "icon-btn", text: "›" }), { disabled: true }))));

    const blockedCards = tasks.filter((t) => t.status === "blocked").map((t) =>
      el("div", { class: "risk-line red" },
        el("b", { text: `${t.task_id} is blocked` }),
        el("span", { class: "hint", text: t.current_activity || "Waiting on an upstream dependency" })));
    const waiting = tasks.filter((t) => t.status !== "completed" && !depsDone(t)).map((t) =>
      el("div", { class: "risk-line amber" },
        el("b", { text: `${t.task_id} depends on ${t.dependencies.join(", ")}` }),
        el("span", { class: "hint", text: `Delays upstream may impact ${t.story_id}` })));

    const bottom = el("div", { class: "grid cols-3", style: "margin-top:14px" },
      el("div", { class: "card" },
        el("h3", { text: "Tasks by Team" }),
        el("div", { class: "donut-wrap" },
          el("div", { class: "donut", style: `background: conic-gradient(${(() => {
            let acc = 0; const stops = [];
            for (const t of teams) {
              const n = tasks.filter((x) => x.accountable_team === t).length;
              stops.push(`${teamColor(t)} ${(360 * acc) / tasks.length}deg ${(360 * (acc + n)) / tasks.length}deg`);
              acc += n;
            }
            return stops.join(", ");
          })()})` },
            el("div", { class: "donut-hole" },
              el("div", { class: "v", text: String(tasks.length) }),
              el("div", { class: "l", text: "Tasks" }))),
          el("ul", { class: "donut-legend" }, teams.map((t) => {
            const n = tasks.filter((x) => x.accountable_team === t).length;
            return el("li", {},
              el("span", { class: "legend-dot", style: `background:${teamColor(t)}` }),
              `${t} — ${n} (${Math.round((100 * n) / tasks.length)}%)`);
          })))),
      el("div", { class: "card" },
        el("h3", { text: "⚠ Dependency Risks" }),
        blockedCards.length || waiting.length
          ? [blockedCards, waiting]
          : el("p", { class: "hint", text: "No blocked tasks and every dependency is satisfied." })),
      el("div", { class: "card" },
        el("div", { class: "card-head" },
          el("h3", { text: "Ready-to-start Tasks" }),
          el("span", { class: "page-chip", text: String(readyToStart.length) })),
        readyToStart.length
          ? el("ul", { class: "plain" }, readyToStart.map((t) =>
            el("li", { style: "cursor:pointer", onclick: () => { state.taskId = t.task_id; render(); } },
              el("span", { class: "mono", text: t.task_id + " " }), t.summary)))
          : el("p", { class: "hint", text: "Nothing waiting — tasks unlock as dependencies complete." })));

    const rail = el("aside", { class: "rail" },
      task ? el("div", { class: "card rail-card" },
        el("h3", { text: "◎ Current Focus" }),
        el("div", { class: "kv", style: "grid-template-columns: 130px 1fr; margin-top:10px" },
          el("b", { text: "Task ID" }), el("span", { class: "mono", style: "color:var(--red)", text: task.task_id }),
          el("b", { text: "Story" }), el("span", { class: "mono", text: task.story_id }),
          el("b", { text: "Task Title" }), el("span", { text: task.summary }),
          el("b", { text: "Status" }), el("span", {}, badge(task.status)),
          el("b", { text: "Owner" }), el("span", { text: task.owner || "—" }),
          el("b", { text: "Accountable Team" }), el("span", { text: task.accountable_team }),
          el("b", { text: "Target Component" }), el("span", { text: story?.target_component ?? "—" }),
          el("b", { text: "Dependencies" }), el("span", { class: "mono", text: task.dependencies.join(", ") || "—" }),
          el("b", { text: "Last Activity" }), el("span", { class: "mono", text: hhmm(task.last_activity) }),
          el("b", { text: "Feature Flag" }), el("span", {}, story?.feature_flag ? el("code", { text: story.feature_flag.name }) : "—"),
          el("b", { text: "Rollback Method" }), el("span", { text: story?.rollback_plan?.method ?? "—" })),
        el("label", { class: "fld", text: "Next Action" }),
        el("button", { class: "outline block", text: "Open Development Progress ↗", onclick: () => go("dev_progress") })) : null,
      task ? el("div", { class: "card rail-card" },
        el("h3", { text: "⚙ Build Controls" }),
        el("div", { class: "actions-row", style: "margin-top:10px" },
          el("button", { class: "primary sq", text: "▶ Start Task", onclick: () => act(`/tasks/${task.task_id}/start`, {}, `${task.task_id} started`) }),
          pauseButton()),
        el("button", { class: "outline block", style: "margin-top:8px", text: "⚗ Generate Tests", onclick: () => act(`/tasks/${task.task_id}/generate-tests`, {}, "Red baseline recorded") }),
        el("button", { class: "outline block", style: "margin-top:8px", text: "Run to Review (all steps)", title: "start → red tests → develop → verify → submit, each step logged", onclick: () => act(`/tasks/${task.task_id}/run-to-review`, {}, `${task.task_id} submitted for review`) }),
        el("button", { class: "outline block", style: "margin-top:8px", text: "⬆ Submit for Review", onclick: () => act(`/tasks/${task.task_id}/submit-review`, {}, "Submitted for independent review") })) : null,
      guidanceCard());

    return el("section", { class: "page-with-rail" },
      el("div", {},
        el("div", { class: "page-head", style: "margin-bottom:16px" },
          el("h2", { text: "Build & Independent Review" }),
          el("span", { class: "hint", text: "Customer-safe execution view for development, test-first validation and independent review." })),
        el("div", { class: "tiles" },
          el("div", { class: "tile t-red" }, el("div", { class: "v", text: String(count("not_started") + count("ready")) }), el("div", { class: "l", text: "Tasks in Queue" })),
          el("div", { class: "tile t-blue" }, el("div", { class: "v", text: String(count("in_progress") + count("waiting_for_approval")) }), el("div", { class: "l", text: "Tasks In Progress" })),
          el("div", { class: "tile t-amber" }, el("div", { class: "v", text: String(count("blocked")) }), el("div", { class: "l", text: "Blocked Tasks" })),
          el("div", { class: "tile t-green" }, el("div", { class: "v", text: String(count("completed")) }), el("div", { class: "l", text: "Completed Tasks" })),
          el("div", { class: "tile t-red" }, el("div", { class: "v", text: String(new Set(tasks.map((t) => t.story_id)).size) }), el("div", { class: "l", text: "Stories in Build" })),
          el("div", { class: "tile t-green" }, el("div", { class: "v", text: `${readiness}%` }), el("div", { class: "l", text: "Overall Build Readiness" }))),
        agentPipelineCard(),
        buildAiPanels(tasks),
        el("div", { style: "margin-top:14px" }, table),
        bottom),
      rail);
  }

  const WORKFLOW_STEPS = [
    ["task-start", "Task Selected", "AI Developer"],
    ["test-first", "Test-First (Generate Tests)", "AI Test Engineer"],
    ["development", "Development (Implement)", "AI Developer"],
    ["developer-verification", "Dev Verify (Self-Check)", "AI Test Engineer"],
    ["independent-review-gate", "Independent Review", "Independent AI Reviewer"],
    ["human-approval", "Human Approval", "Human"],
  ];

  function workflowStepper(task) {
    const acts = taskActivity(task.task_id);
    const review = latestReviewFor(task.task_id);
    const done = new Set(acts.map((a) => a.workflow));
    if (review?.result === "passed") done.add("independent-review-gate");
    const flags = WORKFLOW_STEPS.map(([key]) => {
      if (key === "independent-review-gate") return done.has("independent-review-gate");
      if (key === "human-approval") return false;
      return done.has(key);
    });
    const active = flags.indexOf(false);
    return el("div", { class: "wf-stepper" }, WORKFLOW_STEPS.map(([key, label, agent], i) => {
      const blocked = key === "independent-review-gate" && review?.result === "blocked";
      const cls = blocked ? "blocked" : (flags[i] ? "done" : (i === active ? "active" : ""));
      let status = null;
      if (blocked) status = `BLOCKED · ${review.major_gaps} Major Gap${review.major_gaps === 1 ? "" : "s"}`;
      else if (key === "independent-review-gate" && review?.result === "passed") status = "Passed";
      return el("div", { class: `wf-step ${cls}` },
        i > 0 ? el("span", { class: `wf-line ${flags[i - 1] ? "done" : ""}` }) : null,
        el("span", { class: "wf-dot", text: blocked ? "!" : (flags[i] ? "✓" : "●") }),
        el("span", { class: "wf-label", text: label }),
        el("span", { class: "wf-agent", text: agent }),
        status ? el("span", { class: `wf-status ${blocked ? "bad" : "ok"}`, text: status }) : null);
    }));
  }

  // Ordered developer-workflow checklist (wireframe screen 8): every step is
  // shown — Completed with its time, the next one In Progress, the rest Pending.
  const DEV_CHECKLIST = [
    ["task-start", "Context analysed"],
    ["test-first", "Tests generated & red baseline captured"],
    ["development", "Code changes implemented"],
    ["developer-verification", "Build and targeted tests executed"],
    ["submit-review", "Submitted for independent review"],
  ];

  function devChecklist(task) {
    const acts = taskActivity(task.task_id);
    const at = (wf) => acts.find((a) => a.workflow === wf)?.timestamp;
    let firstMissing = DEV_CHECKLIST.findIndex(([wf]) => !at(wf));
    return el("ul", { class: "checklist" }, DEV_CHECKLIST.map(([wf, label], i) => {
      const ts = at(wf);
      const stateTxt = ts ? hhmm(ts) : (i === firstMissing && task.status !== "not_started" ? "In Progress" : "Pending");
      return el("li", {},
        el("span", { class: `tick ${ts ? "ok" : "no"}`, text: ts ? "✓" : "·" }),
        label,
        el("span", { class: `state ${ts ? "ok" : "no"} mono`, text: stateTxt }));
    }));
  }

  const WORKFLOW_LABELS = {
    "task-start": "Workspace created and context analysed",
    "test-first": "Tests generated and red baseline captured",
    "development": "Code changes implemented",
    "developer-verification": "Build and targeted tests executed",
    "submit-review": "Submitted for independent review",
    "independent-review-gate": "Independent review executed",
    "return-to-development": "Returned to development",
  };

  const TECHNICAL_ROLES = new Set(["engineering_lead", "qa_lead"]);

  function agentForWorkflow(workflow) {
    return WORKFLOW_STEPS.find(([key]) => key === workflow)?.[2] ?? "—";
  }

  function openTechnicalDetailModal(task, acts) {
    openModal(`Technical Detail — ${task.task_id}`,
      el("p", { class: "hint", style: "color:var(--red-dark)", text: "Engineering view — visible to engineering lead / QA lead roles only. Not part of the customer-safe surface." }),
      el("h4", { style: "margin-top:14px; font-size:12.5px; color:var(--muted)", text: "Step-by-step process" }),
      el("div", { class: "table-wrap" },
        el("table", {},
          el("thead", {}, el("tr", {}, ["Time", "Step", "Skill / Agent", "Duration", "Outcome"].map((h) => el("th", { text: h })))),
          el("tbody", {}, acts.map((a) => el("tr", {},
            el("td", { class: "mono", text: hhmm(a.timestamp) }),
            el("td", { text: WORKFLOW_LABELS[a.workflow] ?? a.workflow ?? "—" }),
            el("td", { text: a.skill || agentForWorkflow(a.workflow) }),
            el("td", { class: "mono", text: a.duration_s ? `${a.duration_s}s` : "—" }),
            el("td", { text: a.details || a.outcome || "—" }))))),
      ),
      el("h4", { style: "margin-top:16px; font-size:12.5px; color:var(--muted)", text: "Files changed" }),
      (task.changed_files ?? []).length
        ? el("ul", { class: "plain" }, task.changed_files.map((f) => el("li", {}, el("code", { text: f }))))
        : el("p", { class: "hint", text: "No files recorded for this task." }),
      el("h4", { style: "margin-top:16px; font-size:12.5px; color:var(--muted)", text: "Change summary" }),
      el("p", { text: task.change_summary || "—" }),
      el("div", { class: "kv", style: "grid-template-columns: 140px 1fr; margin-top:10px" },
        el("b", { text: "Commit" }), el("span", {}, el("code", { text: task.commit_ref || "—" })),
        el("b", { text: "Pull Request" }), el("span", {}, el("code", { text: task.pr_ref || "—" })),
        el("b", { text: "Coverage" }), el("span", { text: task.coverage_pct ? `${task.coverage_pct}%` : "—" })),
    );
  }

  function renderDevProgress() {
    const tasks = buildTasks();
    if (!tasks.length) return buildEmpty("Development Progress");
    const task = currentTask();
    const story = storyOf(task);
    const tests = task.tests ?? [];
    const passed = tests.filter((t) => t.current_result === "passed").length;
    const acts = taskActivity(task.task_id);

    const isTechnicalRole = TECHNICAL_ROLES.has(state.role);
    const taskSwitcher = el("select", {
      class: "mono", style: "margin-left:auto",
      onchange: (e) => { state.taskId = e.target.value; render(); },
    }, tasks.map((t) => Object.assign(
      el("option", { value: t.task_id, text: `${t.task_id} — ${t.summary}` }),
      { selected: t.task_id === task.task_id })));

    return el("section", { class: "page-with-rail" },
      el("div", {},
        el("div", { class: "page-head", style: "margin-bottom:16px; display:flex; align-items:flex-start; gap:16px; flex-wrap:wrap" },
          el("div", {},
            el("h2", { text: "Development Progress" }),
            el("span", { class: "hint", text: isTechnicalRole
              ? "Engineering view: includes step-level technical detail alongside the customer-safe progress tracking."
              : "Customer-safe progress tracking for AI-assisted development and developer verification." })),
          taskSwitcher,
          el("button", {
            class: "outline", text: "⚙ Technical Detail",
            title: isTechnicalRole
              ? "Skills used, files changed and the step-by-step process for this task."
              : "Available to engineering lead / QA lead roles — switch role to view.",
            onclick: () => {
              if (!isTechnicalRole) { toast("Technical detail is available to engineering lead / QA lead roles", true); return; }
              openTechnicalDetailModal(task, acts);
            },
          })),
        el("div", { class: "tiles" },
          el("div", { class: "tile t-red" }, el("div", { class: "v mono", text: task.task_id }), el("div", { class: "l", text: "Current Task" })),
          el("div", { class: "tile t-blue" }, el("div", { class: "v", text: String(task.files_changed) }), el("div", { class: "l", text: "Files Changed" })),
          el("div", { class: "tile t-amber" }, el("div", { class: "v", text: String(tests.length) }), el("div", { class: "l", text: "Targeted Tests" })),
          el("div", { class: "tile t-green" }, el("div", { class: "v", text: tests.length ? `${passed} / ${tests.length}` : "—" }), el("div", { class: "l", text: "Tests Passed" })),
          el("div", { class: "tile t-blue" }, el("div", { class: "v", text: task.coverage_pct ? `${task.coverage_pct}%` : "—" }), el("div", { class: "l", text: "Coverage" })),
          el("div", { class: "tile t-green" }, el("div", { class: "v", text: `${task.progress_pct}%` }), el("div", { class: "l", text: "Task Progress" }))),
        el("div", { class: "grid cols-2" },
          el("div", { class: "card" },
            el("h3", { text: "▣ Current Development Task" }),
            el("div", { class: "kv", style: "grid-template-columns: 140px 1fr; margin-top:10px" },
              el("b", { text: "Task ID" }), el("span", { class: "mono", style: "color:var(--red)", text: task.task_id }),
              el("b", { text: "Story" }), el("span", { text: `${task.story_id} — ${story?.title ?? ""}` }),
              el("b", { text: "Accountable Team" }), el("span", { text: task.accountable_team }),
              el("b", { text: "Target Component" }), el("span", { text: story?.target_component ?? "—" }),
              el("b", { text: "Repository" }), el("span", {}, el("code", { text: story?.target_repository ?? "—" })),
              el("b", { text: "Feature Flag" }), el("span", {}, story?.feature_flag ? el("code", { text: story.feature_flag.name }) : "—"),
              el("b", { text: "Rollback Method" }), el("span", { text: story?.rollback_plan?.method ?? "—" }),
              el("b", { text: "Owner" }), el("span", { text: task.owner || "AI developer (simulated)" }),
              el("b", { text: "Evidence" }), el("span", {}, prov(task.provenance)))),
          el("div", { class: "card" },
            el("h3", { text: "▦ Execution Workflow" }),
            workflowStepper(task),
            el("div", { class: "grid cols-2", style: "margin-top:12px" },
              el("div", {},
                el("h3", { style: "font-size:13.5px", text: "Development Workflow" }),
                devChecklist(task)),
              el("div", {},
                el("h3", { style: "font-size:13.5px", text: "Code Change Summary" }),
                el("div", { class: "kv", style: "grid-template-columns: 1fr auto; margin-top:8px" },
                  el("b", { text: "Files Changed" }), el("span", { text: String(task.files_changed) }),
                  el("b", { text: "Lines Added" }), el("span", { style: "color:var(--green)", text: `+${task.lines_added}` }),
                  el("b", { text: "Lines Removed" }), el("span", { style: "color:var(--red-dark)", text: `−${task.lines_removed}` }),
                  el("b", { text: "Components" }), el("span", { text: String((task.changed_files ?? []).length) }),
                  el("b", { text: "Coverage (Targeted)" }), el("span", { text: task.coverage_pct ? `${task.coverage_pct}%` : "—" }),
                  el("b", { text: "Scope Status" }),
                  el("span", {
                    style: `color:${(state.data.planning?.plan?.story_ids ?? []).includes(task.story_id) ? "var(--green)" : "var(--red-dark)"}; font-weight:800`,
                    text: (state.data.planning?.plan?.story_ids ?? []).includes(task.story_id) ? "Within Plan" : "Outside Plan",
                  }),
                  el("b", { text: "Pull Request" }), el("span", {}, el("code", { text: task.pr_ref || "—" })),
                  el("b", { text: "Commit" }), el("span", {}, el("code", { text: task.commit_ref || "—" }))))),
            (task.changed_files ?? []).length ? el("div", { style: "margin-top:10px" },
              el("h3", { style: "font-size:13.5px", text: "Changed Components" }),
              el("ul", { class: "plain" }, task.changed_files.map((f) => el("li", {},
                el("code", { text: f }), " ",
                badge(task.status === "completed" || task.progress_pct >= 80 ? "completed" : "in_progress"))))) : null)),
        el("div", { class: "grid cols-2", style: "margin-top:14px" },
          el("div", { class: "card" },
            el("h3", { text: "✦ AI Implementation Approach" }),
            el("p", { class: "hint", text: "Derived from the story's acceptance criteria — the approach is the criteria, in build order." }),
            el("ul", { class: "plain" }, (story?.acceptance_criteria ?? []).map((ac, i) =>
              el("li", {}, el("b", { text: `${i + 1}. ` }), `Implement and verify: ${ac.text}`)),
              el("li", {}, el("b", { text: `${(story?.acceptance_criteria ?? []).length + 1}. ` }),
                `Preserve existing behaviour — rollback path: ${story?.rollback_plan?.method ?? "feature flag"}`))),
          el("div", { class: "card" },
            el("h3", { text: "Acceptance Criteria Status" }),
            el("ul", { class: "checklist" }, (story?.acceptance_criteria ?? []).map((ac) => {
              const test = tests.find((t) => t.ac_id === ac.ac_id);
              const review = latestReviewFor(task.task_id);
              const flagged = review?.result === "blocked"
                && (review.findings ?? []).some((f) => f.ac_id === ac.ac_id);
              const done = !flagged && test?.current_result === "passed";
              const started = Boolean(test);
              return el("li", { title: ac.text },
                el("span", { class: `tick ${done ? "ok" : "no"}`, text: done ? "✓" : (flagged ? "!" : "·") }),
                `${ac.ac_id} — ${ac.text.length > 56 ? ac.text.slice(0, 56) + "…" : ac.text}`,
                el("span", {
                  class: `state ${done ? "ok" : "no"}`,
                  style: flagged ? "color:var(--red-dark)" : "",
                  text: flagged ? "Review" : (done ? "Completed" : (started ? "In Progress" : "Pending")),
                }));
            })),
            el("div", { class: "actions-row" },
              el("button", { class: "outline", text: "View Evidence", onclick: () => go("test_evidence") }),
              el("button", { class: "primary sq", text: "Run Developer Verification", onclick: () => act(`/tasks/${task.task_id}/verify`, {}, "Developer verification executed") })))),
        el("div", { class: "card", style: "margin-top:14px" },
          el("div", { class: "card-head" },
            el("h3", { text: "Activity Log" }),
            el("button", { class: "outline", text: "View full activity log →", onclick: () => go("activity") })),
          el("div", { class: "table-wrap" },
            el("table", {},
              el("thead", {}, el("tr", {}, ["Time", "Event", "Actor", "Details"].map((h) => el("th", { text: h })))),
              el("tbody", {}, [...acts].reverse().map((a) => el("tr", {},
                el("td", { class: "mono", text: hhmm(a.timestamp) }),
                el("td", { text: WORKFLOW_LABELS[a.workflow] ?? a.workflow ?? "—" }),
                el("td", { text: a.actor }),
                el("td", { text: a.details || a.outcome || "—" }))))))),
      ),
      el("aside", { class: "rail" },
        el("div", { class: "card rail-card" },
          el("h3", { text: "✓ What the customer sees" }),
          el("ul", { class: "checklist" },
            [["Stage progression", "Real-time visibility into the AI-assisted development workflow."],
              ["Evidence review", "Test evidence and code-change summaries for each task."],
              ["Approval controls", "Human approval gates before changes move forward."],
              ["Traceability snapshot", "Full traceability from story to tests, code, and results."],
              ["No IDE / CLI shown", "All execution happens behind the scenes."],
            ].map(([t, d]) => el("li", { title: d }, el("span", { class: "tick ok", text: "✓" }), t))),
          isTechnicalRole ? el("p", { class: "hint", style: "margin-top:8px", text: "Acting as an engineering / QA role: the Technical Detail button above is additional and not part of the customer-safe guarantee for other roles." }) : null),
        el("div", { class: "card rail-card" },
          pauseButton(),
          el("button", { class: "outline block", style: "margin-top:8px", text: "▤ View Test Evidence →", onclick: () => go("test_evidence") }),
          el("button", { class: "primary sq block", style: "margin-top:8px", text: "✓ Submit for Review", onclick: () => act(`/tasks/${task.task_id}/submit-review`, {}, "Submitted for independent review") })),
        guidanceCard()));
  }

  function renderTestEvidence() {
    const tasks = buildTasks();
    if (!tasks.length) return buildEmpty("Test Evidence");
    const task = currentTask();
    const story = storyOf(task);
    const tests = task.tests ?? [];
    const acs = story?.acceptance_criteria ?? [];
    const initialFailures = tests.filter((t) => t.initial_result === "failed").length;
    const passes = tests.filter((t) => t.current_result === "passed").length;
    const failing = tests.filter((t) => t.current_result !== "passed");
    const acText = (id) => acs.find((a) => a.ac_id === id)?.text ?? "";
    const acts = taskActivity(task.task_id);
    const at = (wf) => acts.find((a) => a.workflow === wf)?.timestamp;

    const timeline = el("div", { class: "card" },
      el("h3", { text: "Red → Code → Green Timeline (Current Task)" }),
      el("div", { class: "rcg" },
        [["red", "Red", at("test-first"), `Initial tests written · ${initialFailures} failures expected`],
          ["code", "Code", at("development"), "Code changes implemented"],
          ["green", "Green", at("developer-verification"), `${passes} of ${tests.length} passing`],
        ].map(([cls, label, ts, note], i) => [
          i > 0 ? el("span", { class: "rcg-line" }) : null,
          el("div", { class: `rcg-node ${cls} ${ts ? "" : "pending"}` },
            el("span", { class: "rcg-dot" }),
            el("b", { text: label }),
            el("span", { class: "mono hint", text: ts ? hhmm(ts) : "pending" }),
            el("span", { class: "hint", text: note })),
        ])));

    return el("section", { class: "page-with-rail" },
      el("div", {},
        el("div", { class: "page-head", style: "margin-bottom:16px" },
          el("h2", { text: "Test Evidence" }),
          el("span", { class: "hint", text: "Acceptance-criteria-based test-first evidence for the current build task." })),
        el("div", { class: "tiles" },
          el("div", { class: "tile t-red" }, el("div", { class: "v", text: String(acs.length) }), el("div", { class: "l", text: "Acceptance Criteria" })),
          el("div", { class: "tile t-blue" }, el("div", { class: "v", text: String(tests.length) }), el("div", { class: "l", text: "Tests Generated" })),
          el("div", { class: "tile t-amber" }, el("div", { class: "v", text: String(initialFailures) }), el("div", { class: "l", text: "Initial Failures" })),
          el("div", { class: "tile t-green" }, el("div", { class: "v", text: String(passes) }), el("div", { class: "l", text: "Current Passes" })),
          el("div", { class: "tile t-red" }, el("div", { class: "v", text: String(failing.length) }), el("div", { class: "l", text: "Open Failures" })),
          el("div", { class: "tile t-blue" }, el("div", { class: "v", text: task.coverage_pct ? `${task.coverage_pct}%` : "—" }), el("div", { class: "l", text: "Coverage" }))),
        el("div", { class: "grid", style: "grid-template-columns: minmax(0,2fr) minmax(0,1fr)" },
          el("div", { class: "card" },
            el("h3", { text: "Acceptance Criteria to Test Mapping" }),
            tests.length ? el("div", { class: "table-wrap", style: "margin-top:10px" },
              el("table", {},
                el("thead", {}, el("tr", {}, ["AC ID", "Acceptance Criterion", "Test Name", "Initial Result", "Current Result", "Evidence"].map((h) => el("th", { text: h })))),
                el("tbody", {}, tests.map((t) => el("tr", {},
                  el("td", { class: "mono", text: t.ac_id }),
                  el("td", { text: acText(t.ac_id) }),
                  el("td", { class: "mono", text: t.name }),
                  el("td", {}, el("span", { class: `dotlbl ${t.initial_result === "failed" ? "red" : "green"}` },
                    t.initial_result === "failed" ? "Failed as expected" : "Passed baseline")),
                  el("td", {}, el("span", { class: `dotlbl ${t.current_result === "passed" ? "green" : "amber"}` },
                    t.current_result === "passed" ? "Passed" : "Review issue")),
                  el("td", { class: "mono", text: t.evidence_ref || t.test_id }))))))
              : el("p", { class: "hint", text: "No tests yet — generate the red baseline first." })),
          el("div", {},
            el("div", { class: "card" },
              el("h3", { text: "⚑ Test-First Baseline" }),
              el("div", { class: "tile t-red", style: "border:0; box-shadow:none; text-align:left; padding:6px 0" },
                el("div", { class: "v", text: String(initialFailures) }),
                el("div", { class: "l", text: "Expected failures established from ACs before code changes" }))),
            el("div", { class: "card", style: "margin-top:14px" },
              el("h3", { text: "Test Execution Summary" }),
              el("ul", { class: "checklist" },
                el("li", {}, el("span", { class: `tick ${passes === tests.length && tests.length ? "ok" : "no"}`, text: passes === tests.length && tests.length ? "✓" : "·" }),
                  "Targeted Tests", el("span", { class: "state ok mono", text: `${passes} / ${tests.length}` })),
                el("li", {}, el("span", { class: `tick ${task.coverage_pct ? "ok" : "no"}`, text: task.coverage_pct ? "✓" : "·" }),
                  "Targeted Coverage", el("span", { class: "state ok mono", text: task.coverage_pct ? `${task.coverage_pct}%` : "—" }))),
              el("p", { class: "hint", text: "Only categories the demo engine actually runs are listed — nothing is padded." })))),
        el("div", { class: "grid cols-2", style: "margin-top:14px" },
          el("div", { class: "card" },
            el("h3", { text: "⚠ Failure & Exception Detail" }),
            failing.length
              ? failing.map((t) => el("div", { class: "risk-line amber" },
                el("b", { text: `REVIEW ISSUE · ${t.ac_id}` }),
                el("span", { class: "hint", text: `${t.name} is not passing — ${acText(t.ac_id)}` })))
              : el("p", { class: "hint", text: "No open failures for this task." })),
          timeline)),
      el("aside", { class: "rail" },
        guidanceCard(),
        el("div", { class: "card rail-card" },
          el("button", { class: "primary sq block", text: "▶ Run Targeted Tests", title: "Runs developer verification for the current task", onclick: () => act(`/tasks/${task.task_id}/verify`, {}, "Targeted tests executed") }),
          Object.assign(el("button", { class: "outline block", style: "margin-top:8px", text: "⟳ Run Full Regression", title: "The demo engine runs targeted verification only; a separate full-regression harness is not part of the demonstration and this control is honestly disabled." }), { disabled: true }),
          el("button", { class: "outline block", style: "margin-top:8px", text: "◉ View Technical Evidence", onclick: () => go("dev_progress") }),
          el("button", { class: "outline block", style: "margin-top:8px", text: "⬆ Submit for Independent Review", onclick: () => act(`/tasks/${task.task_id}/submit-review`, {}, "Submitted for independent review") }))));
  }

  function renderIndependentReview() {
    const tasks = buildTasks();
    if (!tasks.length) return buildEmpty("Independent Review");
    const d = state.data;
    const task = currentTask();
    const story = storyOf(task);
    const reviews = reviewsFor(task.task_id);
    const review = latestReviewFor(task.task_id);
    const plan = d.planning?.plan;
    const tests = task.tests ?? [];
    const acs = story?.acceptance_criteria ?? [];
    const sevCount = (s) => review ? { critical: review.critical_gaps, major: review.major_gaps, minor: review.minor_gaps }[s] ?? 0 : 0;
    const trace = (d.traceability ?? []).find((r) => r.task === task.task_id);
    const sevClass = { critical: "red", major: "red", minor: "amber", info: "" };

    function reviewFindingsBlock(rv) {
      return [
        el("div", { class: "kv", style: "grid-template-columns: 130px 1fr; margin-top:8px" },
          el("b", { text: "Review ID" }), el("span", { class: "mono", text: rv.review_id }),
          el("b", { text: "Reviewer Agent" }), el("span", { text: rv.reviewer }),
          el("b", { text: "Author Agent" }), el("span", { text: task.owner || "AI developer (simulated)" }),
          el("b", { text: "Reviewed On" }), el("span", { class: "mono", text: (rv.created_at ?? "").slice(0, 16).replace("T", " ") }),
          el("b", { text: "Artifacts Reviewed" }), el("span", { text: String((rv.verified_against ?? []).length || "—") }),
          el("b", { text: "Result" }), el("span", {}, badge(rv.result === "passed" ? "passed" : "blocked"))),
        el("div", { class: "findings-grid" },
          [["Critical", rv.critical_gaps], ["Major", rv.major_gaps], ["Minor", rv.minor_gaps], ["Info", 0]].map(([label, n]) =>
            el("div", { class: "finding-cell" },
              el("b", { text: label }),
              el("span", { class: "v", text: String(n) })))),
        (rv.findings ?? []).map((f) => el("div", { class: `risk-line ${sevClass[f.severity] ?? "amber"}` },
          el("b", { text: `${f.finding_id ?? ""} ${f.severity.toUpperCase()} · ${f.ac_id} — ${f.summary}` }),
          f.expected ? el("div", { class: "finding-detail" },
            el("div", {}, el("b", { text: "Acceptance Criterion: " }), f.ac_id),
            el("div", {}, el("b", { text: "Expected Behaviour: " }), f.expected),
            el("div", {}, el("b", { text: "Observed Implementation: " }), f.observed),
            el("div", {}, el("b", { text: "Impact: " }), f.impact),
            el("div", {}, el("b", { text: "Recommendation: " }), f.recommendation),
            (f.evidence ?? []).length ? el("div", {}, el("b", { text: "Evidence: " }),
              f.evidence.flatMap((e, i) => [i > 0 ? ", " : null, el("code", { text: e })])) : null,
          ) : el("span", { class: "hint", text: f.detail }))),
        (rv.findings ?? []).length === 0 ? el("p", { class: "hint", text: "No findings — the change verified clean against the criteria." }) : null,
      ];
    }

    return el("section", { class: "page-with-rail" },
      el("div", {},
        el("div", { class: "page-head", style: "margin-bottom:16px" },
          el("h2", { text: "Independent Review" }),
          el("span", { class: "hint", text: "Isolated review of code, tests, and acceptance criteria. No phase self-approves." })),
        el("div", { class: "tiles" },
          el("div", { class: "tile t-red" }, el("div", { class: "v", text: review ? "1" : "0" }), el("div", { class: "l", text: review ? "Review Package · Complete" : "Review Package" })),
          el("div", { class: "tile t-red" }, el("div", { class: "v", text: String(sevCount("critical")) }), el("div", { class: "l", text: "Critical Gaps" })),
          el("div", { class: "tile t-amber" }, el("div", { class: "v", text: String(sevCount("major")) }), el("div", { class: "l", text: "Major Gaps" })),
          el("div", { class: "tile t-blue" }, el("div", { class: "v", text: String(sevCount("minor")) }), el("div", { class: "l", text: "Minor Gaps" })),
          el("div", { class: `tile ${review?.result === "passed" ? "t-green" : "t-amber"}` },
            el("div", { class: "v", text: review ? review.result.toUpperCase() : "—" }),
            el("div", { class: "l", text: "Review Result" })),
          el("div", { class: "tile t-green" }, el("div", { class: "v", text: `${task.progress_pct}%` }), el("div", { class: "l", text: "Task Readiness" }))),
        el("div", { class: "grid cols-2" },
          el("div", { class: "card" },
            el("h3", { text: "▣ Review Package" }),
            el("ul", { class: "checklist" },
              el("li", {}, el("span", { class: `tick ${plan ? "ok" : "no"}`, text: plan ? "✓" : "·" }), "Signed Plan", el("span", { class: "state ok mono", text: plan ? `v${plan.plan_version}` : "—" })),
              el("li", {}, el("span", { class: "tick ok", text: "✓" }), "Story", el("span", { class: "state ok mono", text: task.story_id })),
              el("li", {}, el("span", { class: `tick ${acs.length ? "ok" : "no"}`, text: acs.length ? "✓" : "·" }), "Acceptance Criteria",
                el("span", { class: "state ok mono", text: acs.length ? `${acs[0].ac_id} – ${acs[acs.length - 1].ac_id}` : "—" })),
              el("li", {}, el("span", { class: `tick ${task.files_changed ? "ok" : "no"}`, text: task.files_changed ? "✓" : "·" }), "Change Summary", el("span", { class: "state ok mono", text: `${task.files_changed} files` })),
              el("li", {}, el("span", { class: `tick ${tests.length ? "ok" : "no"}`, text: tests.length ? "✓" : "·" }), "Test Evidence", el("span", { class: "state ok mono", text: `${tests.length} targeted tests` })),
              el("li", {}, el("span", { class: `tick ${trace ? "ok" : "no"}`, text: trace ? "✓" : "·" }), "Traceability Evidence", el("span", { class: "state ok", text: trace ? "Current" : "—" })))),
          el("div", { class: "card" },
            el("h3", { text: "▥ Review Findings" }),
            reviews.length === 0
              ? el("p", { class: "hint", text: "No review executed yet for this task. Submit for review, then execute it." })
              : reviews.length === 1
                ? reviewFindingsBlock(reviews[0])
                : reviews.map((rv, i) => el("div", {
                    style: i > 0 ? "margin-top:18px; padding-top:14px; border-top:1px dashed var(--border)" : "",
                  },
                    el("div", { style: "display:flex; align-items:center; gap:8px; margin-bottom:2px" },
                      el("b", { text: `Review v${rv.version ?? i + 1}` }),
                      i === reviews.length - 1
                        ? el("span", { class: "hint", text: "current" })
                        : el("span", { class: "hint", text: "superseded — corrected below" })),
                    ...reviewFindingsBlock(rv))))),
        el("div", { class: "grid cols-2", style: "margin-top:14px" },
          el("div", { class: "card" },
            el("h3", { text: "⛓ Traceability Snapshot" }),
            trace ? el("div", { class: "trace-chain" },
              [trace.requirement, trace.design, trace.story, trace.ac, trace.task, trace.pr, ...(trace.tests ?? []), trace.review]
                .filter(Boolean).flatMap((id, i) => [
                  i > 0 ? el("span", { class: "trace-arrow", text: "→" }) : null,
                  el("span", { class: "trace-node mono", text: id }),
                ])) : el("p", { class: "hint", text: "The chain appears once the task has evidence." })),
          el("div", { class: "card" },
            el("h3", { text: "⚖ Approval Rule" }),
            el("p", { text: "The independent reviewer cannot change the implementation." }),
            el("p", { text: "The development workflow cannot approve its own output." }),
            el("p", { class: "hint", text: "Enforced by the engine's role model — not a convention." }))),
        el("div", { class: "actions-row", style: "margin-top:16px" },
          el("button", { class: "outline", text: "← Return to Development", onclick: () => act(`/reviews/${task.task_id}/return-to-development`, {}, "Returned to development") }),
          el("button", { class: "primary sq", text: "➤ Execute Independent Review", onclick: () => act(`/reviews/${task.task_id}/execute`, {}, "Independent review executed") }),
          review?.result === "blocked" ? el("button", {
            class: "primary sq", text: "⟳ Re-develop & Re-submit for Review",
            title: "Orchestrates the correction loop across its three actors — the reviewer returns the task, the developer re-implements and re-verifies, the reviewer re-executes. Each step is ledgered under its own role.",
            onclick: async () => {
              if (await act(`/reviews/${task.task_id}/return-to-development`, { role: "independent_reviewer" }, "Reviewer returned the task to development"))
                if (await act(`/tasks/${task.task_id}/run-to-review`, { role: "delivery_lead" }, "Correction implemented and re-submitted"))
                  await act(`/reviews/${task.task_id}/execute`, { role: "independent_reviewer" }, "Independent review re-executed");
            },
          }) : null),
      ),
      el("aside", { class: "rail" },
        el("div", { class: "card rail-card" },
          el("h3", { text: "Findings Summary" }),
          el("ul", { class: "checklist" },
            [["Critical", sevCount("critical"), "red"], ["Major", sevCount("major"), "red"], ["Minor", sevCount("minor"), "amber"], ["Info", 0, ""]].map(([label, n]) =>
              el("li", {}, label, el("span", { class: "state ok mono", text: String(n) }))),
            el("li", {}, el("b", { text: "Total findings" }), el("span", { class: "state ok mono", text: String((latestReviewFor(task.task_id)?.findings ?? []).length) })))),
        el("div", { class: "card rail-card" },
          el("h3", { text: "Review Governance" }),
          el("p", { class: "hint", text: "Independent review runs isolated from development. Separation of duties is enforced by the role model." })),
        el("div", { class: "card rail-card" },
          el("h3", { text: "Human Approval comes next" }),
          el("p", { class: "hint", text: "After this review, human approvers decide at the quality and release gates." })),
        el("div", { class: "card rail-card" },
          el("h3", { text: "No code editor exposed" }),
          el("p", { class: "hint", text: "Only evidence and status are visible. Implementation details remain behind the surface." })),
        (() => {
          const history = taskActivity(task.task_id)
            .filter((a) => ["submit-review", "independent-review-gate", "return-to-development"].includes(a.workflow));
          return history.length ? el("div", { class: "card rail-card" },
            el("h3", { text: "Review History" }),
            el("ul", { class: "checklist" }, history.map((a) =>
              el("li", {},
                el("span", { class: "mono hint", style: "margin-right:6px", text: hhmm(a.timestamp) }),
                a.details || a.outcome || a.workflow)))) : null;
        })(),
        guidanceCard()));
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

  function gatePanel(gateId, title, hint) {
    const gate = (state.data.gates ?? []).find((g) => g.gate_id === gateId);
    return el("div", { class: `card ${gate?.status === "passed" ? "ok" : "highlight"}`, style: "margin-top:14px" },
      el("div", { class: "section-title" }, el("h3", { text: title }), badge(gate?.status ?? "not_started")),
      (gate?.conditions ?? []).length
        ? el("ul", { class: "plain" }, gate.conditions.map((c) =>
          el("li", {}, `${c.met ? "✓" : "✗"} ${c.condition}`,
            c.detail ? el("span", { class: "hint", text: ` — ${c.detail}` }) : null)))
        : el("p", { class: "hint", text: hint }),
      gate?.decided_by ? el("p", { class: "hint", text: `Decided by ${gate.decided_by} at ${gate.decided_at}` }) : null,
    );
  }

  function renderQuality() {
    const d = state.data;
    const report = d.quality;
    const parts = [sectionTitle("Stage 4 — Quality",
      "Evidence aggregated across every story. The gate is explicit conditions, never the score.")];

    if (!report) {
      parts.push(el("div", { class: "card" },
        el("p", { text: "Quality aggregation opens once the independent-review gate (G2) has passed for every task." }),
        el("div", { class: "actions-row" },
          el("button", { class: "primary", text: "Run quality checks",
            onclick: () => act("/quality/run", {}, "Quality checks aggregated") })),
      ));
      return el("section", {}, parts);
    }

    const checks = report.checks ?? [];
    const passed = checks.filter((c) => c.status === "passed").length;
    parts.push(el("div", { class: "grid cols-4" },
      el("div", { class: "card metric" }, el("div", { class: "v", text: `${passed}/${checks.filter((c) => c.status !== "not_applicable").length}` }), el("div", { class: "l", text: "Checks passed" })),
      el("div", { class: "card metric" }, el("div", { class: "v", text: String(report.risks?.length ?? 0) }), el("div", { class: "l", text: "Open risks" })),
      el("div", { class: "card metric" }, el("div", { class: "v", text: String(report.exceptions?.length ?? 0) }), el("div", { class: "l", text: "Approved exceptions" })),
      el("div", { class: "card metric" },
        el("div", { class: "v", text: `${report.quality_score}` }),
        el("div", { class: "l", text: "Score (informational)" })),
    ));
    parts.push(el("p", { class: "hint", style: "margin-top:6px", text: report.score_note }));

    parts.push(sectionTitle("Quality evidence"));
    parts.push(el("div", { class: "table-wrap" },
      el("table", {},
        el("thead", {}, el("tr", {}, ["Check", "Name", "Status", "Evidence", "Owner"].map((h) => el("th", { text: h })))),
        el("tbody", {}, checks.map((c) => el("tr", {},
          el("td", { class: "mono", text: c.check_id }),
          el("td", { text: c.name }),
          el("td", {}, badge(c.status === "not_applicable" ? "not_started" : c.status)),
          el("td", { text: c.evidence || "—" }),
          el("td", { text: c.owner }),
        ))),
      ),
    ));

    parts.push(el("div", { class: "grid cols-2", style: "margin-top:14px" },
      el("div", { class: "card warn" },
        el("h3", { text: "Risks" }),
        el("ul", { class: "plain" }, (report.risks ?? []).map((r) =>
          el("li", {}, el("b", { text: `${r.risk_id} (${r.severity}): ` }), r.description))),
      ),
      el("div", { class: "card" },
        el("h3", { text: "Approved exceptions" }),
        el("ul", { class: "plain" }, (report.exceptions ?? []).map((x) =>
          el("li", {}, el("b", { text: `${x.exception_id}: ` }), x.description,
            el("span", { class: "hint", text: ` — approved by ${x.approved_by}` })))),
      ),
    ));

    parts.push(el("div", { class: "card", style: "margin-top:14px" },
      el("h3", { text: "Release recommendation" }),
      el("p", { text: report.recommendation }),
      el("div", { class: "actions-row" },
        el("button", { class: "ghost", text: "Re-run checks", onclick: () => act("/quality/run", {}, "Quality checks re-aggregated") }),
        el("button", { class: "primary approve", text: "Decide quality gate (QA Lead)",
          onclick: () => act("/quality/decide", {}, "Quality gate decided") })),
    ));
    parts.push(gatePanel("G3", "Gate 3 — Quality",
      "Conditions evaluate when the QA Lead decides the gate."));
    return el("section", {}, parts);
  }

  function renderRelease() {
    const d = state.data;
    const rec = d.release;
    const parts = [sectionTitle("Stage 5 — Release",
      "A genuine blocking human gate: named approvals, then deployment, then handover")];

    if (!rec) {
      parts.push(el("div", { class: "card" },
        el("p", { text: "Release opens after the quality gate (G3) passes." }),
        el("div", { class: "actions-row" },
          el("button", { class: "primary", text: "Request release approval",
            onclick: () => act("/release/request-approval", {}, "Release approval requested") })),
      ));
      return el("section", {}, parts);
    }

    parts.push(el("div", { class: "grid cols-2" },
      el("div", { class: "card highlight" },
        el("h3", { text: "Release summary" }),
        el("div", { class: "kv", style: "margin-top:8px" },
          el("b", { text: "Release" }), el("span", { class: "mono", text: rec.release_id }),
          el("b", { text: "Epic" }), el("span", { class: "mono", text: rec.epic_id }),
          el("b", { text: "Version" }), el("span", { text: rec.version }),
          el("b", { text: "Environment" }), el("span", { text: rec.environment }),
          el("b", { text: "Window" }), el("span", { text: rec.release_window }),
          el("b", { text: "Feature flag" }), el("code", { text: rec.feature_flag }),
          el("b", { text: "Rollback" }), el("span", { text: rec.rollback_plan }),
          el("b", { text: "Status" }), el("span", {}, badge(rec.status)),
        ),
      ),
      el("div", { class: "card" },
        el("h3", { text: "Required approvals" }),
        el("p", { class: "hint", text: "Business Owner, Engineering Lead, QA Lead and Release Manager must each approve under their own role. Switch the acting role in the header to record each one." }),
        renderApprovalMatrix(),
        renderApprovalForm(),
      ),
    ));

    if (rec.deployment) {
      const dep = rec.deployment;
      parts.push(el("div", { class: "card ok", style: "margin-top:14px" },
        el("div", { class: "section-title" }, el("h3", { text: "Deployment" }), badge(dep.status)),
        el("div", { class: "kv", style: "margin-top:8px" },
          el("b", { text: "Deployment" }), el("span", { class: "mono", text: dep.deployment_id }),
          el("b", { text: "Pipeline" }), el("span", { text: dep.pipeline_ref }),
          el("b", { text: "Strategy" }), el("span", { text: dep.strategy }),
          el("b", { text: "Artifacts" }), el("span", { text: String(dep.artifact_count) }),
          el("b", { text: "Smoke tests" }), el("span", { text: dep.smoke_test_status }),
          el("b", { text: "Post-deployment" }),
          el("span", {}, el("ul", { class: "plain" }, dep.post_checks.map((p) => el("li", { text: p })))),
          el("b", { text: "Deployed at" }), el("span", { class: "mono", text: dep.deployed_at }),
        ),
      ));
    }

    if (rec.handover) {
      const h = rec.handover;
      parts.push(el("div", { class: "card ok", style: "margin-top:14px" },
        el("h3", { text: "Support handover" }),
        el("div", { class: "kv", style: "margin-top:8px" },
          el("b", { text: "Support team" }), el("span", { text: h.support_team }),
          el("b", { text: "Runbook" }), el("code", { text: h.runbook_ref }),
          el("b", { text: "Knowledge article" }), el("span", { text: h.knowledge_article_ref }),
          el("b", { text: "Monitoring alerts" }),
          el("span", {}, el("ul", { class: "plain" }, h.monitoring_alerts.map((a) => el("li", { text: a })))),
          el("b", { text: "Escalation" }), el("span", { text: h.escalation_path }),
          el("b", { text: "Known limitations" }),
          el("span", {}, el("ul", { class: "plain" }, h.known_limitations.map((a) => el("li", { text: a })))),
          el("b", { text: "Hypercare" }), el("span", { text: `${h.hypercare_days} days` }),
          el("b", { text: "Accepted by" }), el("span", { text: `${h.accepted_by} at ${h.accepted_at}` }),
        ),
      ));
    }

    parts.push(el("div", { class: "actions-row", style: "margin-top:14px" },
      el("button", { class: "primary", text: "Deploy to production (Release Manager)",
        onclick: () => act("/release/deploy", {}, "Deployment complete") }),
      el("button", { class: "primary approve", text: "Complete support handover",
        onclick: () => act("/release/handover", {}, "Handover accepted — run complete") }),
    ));
    parts.push(gatePanel("G4", "Gate 4 — Release",
      "Conditions evaluate at deployment: all gates green, all approvals present, nothing stale."));
    return el("section", {}, parts);
  }

  function renderApprovalMatrix() {
    const releaseApprovals = (state.data.approvals ?? []).filter((a) => a.subject === "release");
    const required = ["business_owner", "engineering_lead", "qa_lead", "release_manager"];
    return el("ul", { class: "plain" }, required.map((r) => {
      const got = releaseApprovals.filter((a) => a.role === r).pop();
      return el("li", {},
        el("b", { text: r.replaceAll("_", " ") + ": " }),
        got ? el("span", {}, badge(got.decision === "approved" ? "passed" : "failed"),
          ` ${got.approver} — ${got.decided_at}`) : badge("waiting_for_approval"));
    }));
  }

  function renderApprovalForm() {
    const name = el("input", { type: "text", placeholder: "Approver name (required)" });
    const note = el("input", { type: "text", placeholder: "Note (optional)" });
    return el("div", { style: "margin-top:10px" },
      el("label", { class: "fld", text: "Approver" }), name,
      el("label", { class: "fld", text: "Note" }), note,
      el("div", { class: "actions-row" },
        el("button", { class: "primary approve", text: "Approve as current role",
          onclick: () => act("/release/approve", { approver: name.value, note: note.value, decision: "approved" }, "Approval recorded") }),
        el("button", { class: "ghost danger-ghost", text: "Reject release",
          onclick: () => act("/release/approve", { approver: name.value, note: note.value, decision: "rejected" }, "Rejection recorded") }),
      ),
    );
  }

  function renderRisks() {
    const report = state.data.quality;
    const risks = report?.risks ?? [];
    const stale = state.data.staleness ?? [];
    const amendments = state.data.amendments ?? [];
    const design = state.data.design;
    const parts = [sectionTitle("Risks & Alerts",
      "Staleness is detected from upstream pointers and hashes in the provenance ledger")];

    if (risks.length === 0 && stale.length === 0 && amendments.length === 0) {
      parts.push(el("div", { class: "card" },
        el("p", { text: "No open risks, staleness alerts or amendments in this run yet." })));
    }

    if (stale.length) {
      parts.push(el("div", { class: "card bad" },
        el("h3", { text: `Release gate blocked — ${stale.length} stale artifact(s)` }),
        el("p", { class: "hint", text: "An upstream artifact changed after these were produced. Each must be re-validated as a new version before release; nothing is silently updated." })));
      parts.push(el("div", { class: "table-wrap", style: "margin-top:10px" },
        el("table", {},
          el("thead", {}, el("tr", {}, ["Artifact", "Type", "Version", "Status", "Reason"].map((h) => el("th", { text: h })))),
          el("tbody", {}, stale.map((s) => el("tr", {},
            el("td", { class: "mono", text: s.artifact_id }),
            el("td", { text: s.artifact_type }),
            el("td", { text: `v${s.version}` }),
            el("td", {}, badge("stale")),
            el("td", { text: s.reason }),
          ))))));
    }

    risks.forEach((r) => parts.push(el("div", { class: "card warn", style: "margin-top:10px" },
      el("h3", { text: `${r.risk_id} — ${r.severity}` }), el("p", { text: r.description }))));

    if (amendments.length) {
      parts.push(sectionTitle("Amendments", "Controlled change management — append-only"));
      const seen = new Set();
      [...amendments].reverse().forEach((a) => {
        if (seen.has(a.amendment_id)) return;
        seen.add(a.amendment_id);
        parts.push(el("div", { class: `card ${a.implementation_status === "completed" ? "ok" : "warn"}` },
          el("div", { class: "section-title" },
            el("h3", { text: `${a.amendment_id} — ${a.reason}` }),
            badge(a.implementation_status === "completed" ? "completed" : "in_progress")),
          el("div", { class: "kv", style: "margin-top:8px" },
            el("b", { text: "Initiator" }), el("span", { text: a.initiator }),
            el("b", { text: "Impact" }), el("span", { text: a.impact_assessment }),
            el("b", { text: "Affected" }), el("span", { class: "mono", text: (a.affected_artifacts ?? []).join(", ") || "—" }),
            el("b", { text: "Required changes" }),
            el("span", {}, el("ul", { class: "plain" }, (a.required_changes ?? []).map((c) => el("li", { text: c })))),
            el("b", { text: "Verification" }), el("span", {}, badge(a.verification_status === "completed" ? "passed" : a.verification_status)),
          )));
      });
    }

    parts.push(el("div", { class: "card", style: "margin-top:14px" },
      el("h3", { text: "Demonstration controls" }),
      el("p", { class: "hint", text: design?.version > 1
        ? "Upstream change applied: DES-001 is at v2 (SME ruling on draft retention)."
        : "Simulate the SME ruling that changes DES-001 after downstream work exists — downstream artifacts go stale and release blocks." }),
      el("div", { class: "actions-row" },
        el("button", { class: "primary", text: "Apply upstream SME ruling",
          onclick: () => act("/change/upstream", {}, "DES-001 amended — downstream marked stale") }),
        el("button", { class: "primary approve", text: "Run self-correction workflow",
          onclick: () => act("/change/self-correct", {}, "Self-correction complete") }),
      )));
    return el("section", {}, parts);
  }

  function renderTraceability() {
    const rows = state.data.traceability ?? [];
    if (!rows.length) return notBuilt("Traceability", "the Planning stage — the chain builds as artifacts exist");
    const sel = state.traceSel;
    const selected = rows.find((r) => r.ac === sel);
    return el("section", {},
      sectionTitle("Traceability matrix",
        "Requirement → design → story → criterion → task → change → test → review → quality → deployment → handover"),
      selected ? el("div", { class: "card highlight", style: "margin-bottom:14px" },
        el("h3", { text: `Chain for ${selected.ac}` }),
        el("p", { class: "mono", style: "margin-top:8px", text: [
          selected.requirement, selected.design, selected.story, selected.ac,
          selected.task, selected.pr, ...(selected.tests ?? []), selected.review,
          selected.quality, selected.deployment, selected.handover,
        ].filter(Boolean).join(" → ") })) : null,
      el("div", { class: "table-wrap" },
        el("table", {},
          el("thead", {}, el("tr", {},
            ["Story", "Criterion", "Task", "Change", "Tests", "Review", "Quality", "Deploy", "Handover"].map((h) => el("th", { text: h })))),
          el("tbody", {}, rows.map((r) => el("tr", { style: "cursor:pointer", onclick: () => { state.traceSel = r.ac; render(); } },
            el("td", { class: "mono", text: r.story }),
            el("td", { class: "mono", text: r.ac }),
            el("td", { class: "mono", text: r.task ?? "—" }),
            el("td", { class: "mono", text: r.pr ?? "—" }),
            el("td", { class: "mono", text: (r.tests ?? []).join(", ") || "—" }),
            el("td", {}, r.review ? el("span", {}, el("span", { class: "mono", text: r.review + " " }),
              badge(r.review_result === "passed" ? "passed" : "blocked")) : "—"),
            el("td", { class: "mono", text: r.quality ?? "—" }),
            el("td", { class: "mono", text: r.deployment ?? "—" }),
            el("td", { class: "mono", text: r.handover ?? "—" }),
          ))),
        ),
      ),
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

  function renderReports() {
    const s = state.data.activity_summary ?? {};
    const run = state.data.run;
    const stageTime = s.stage_time_s ?? {};
    const total = Object.values(stageTime).reduce((a, b) => a + b, 0);
    const stageLabel = (k) => (STAGES.find(([key]) => key === k)?.[1]) ?? k;
    return el("section", {},
      sectionTitle("Reports", "Computed from the activity ledger — durations are simulated workflow durations"),
      el("div", { class: "grid cols-4" },
        el("div", { class: "card metric" }, el("div", { class: "v", text: `${Math.round(total)}s` }), el("div", { class: "l", text: "Total workflow time" })),
        el("div", { class: "card metric" }, el("div", { class: "v", text: String(s.counters?.ai_workflows ?? 0) }), el("div", { class: "l", text: "Automated workflows" })),
        el("div", { class: "card metric" }, el("div", { class: "v", text: String(s.counters?.human_approvals ?? 0) }), el("div", { class: "l", text: "Human decisions" })),
        el("div", { class: "card metric" }, el("div", { class: "v", text: run.status.replaceAll("_", " ") }), el("div", { class: "l", text: "Run outcome" })),
      ),
      sectionTitle("Bottleneck insights", "Where workflow time accrued, by stage"),
      el("div", { class: "card" },
        el("ul", { class: "plain" },
          Object.entries(stageTime).map(([k, v]) => el("li", {},
            el("b", { text: stageLabel(k) + ": " }),
            `${Math.round(v)}s`,
            el("span", { class: "hint", text: total ? ` — ${Math.round((100 * v) / total)}%` : "" }))))),
      sectionTitle("Ledger counters"),
      el("div", { class: "grid cols-3" },
        Object.entries(s.counters ?? {}).map(([k, v]) =>
          el("div", { class: "card metric" },
            el("div", { class: "v", text: String(v) }),
            el("div", { class: "l", text: k.replaceAll("_", " ") })))),
    );
  }

  const DEMO_SCENARIOS = [
    ["happy-path", "Happy path — full successful run to handover"],
    ["review-failure", "Independent review failure — US-003 blocked"],
    ["missing-test-coverage", "Missing test coverage — quality gate blocks"],
    ["staleness", "Upstream change — downstream stale, release blocked"],
    ["release-rejected", "Release approval rejected by Business Owner"],
  ];

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
      sectionTitle("Load demo scenario", "Each creates a fresh run driven to a known state through the real engine — gates, roles and ledgers all execute"),
      el("div", { class: "grid cols-2" },
        DEMO_SCENARIOS.map(([key, label]) =>
          el("div", { class: "card" },
            el("h3", { text: label }),
            el("div", { class: "actions-row" },
              el("button", { class: "primary", text: "Load", onclick: () => loadDemo(key) })))),
      ),
    );
  }

  async function loadDemo(action) {
    try {
      const created = await api(`/api/demo/${action}`, { method: "POST", body: "{}" });
      state.runId = created.run.run_id;
      localStorage.setItem("s7cc.runId", state.runId);
      state.data = created;
      state.section = "overview";
      render();
      toast(`Scenario '${action}' loaded as ${state.runId}`);
    } catch (err) { toast(err.message, true); }
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
  $("copyRunBtn").addEventListener("click", async () => {
    if (!state.runId) return;
    try {
      await navigator.clipboard.writeText(state.runId);
      toast(`${state.runId} copied`);
    } catch { toast("Clipboard unavailable", true); }
  });

  function tickClock() {
    const now = new Date();
    $("clock").textContent = now.toLocaleString("en-GB", {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  }
  tickClock();
  setInterval(tickClock, 30_000);

  (async () => {
    try {
      state.roles = await api("/api/roles");
    } catch { state.roles = []; }
    await refresh();
  })();
})();
