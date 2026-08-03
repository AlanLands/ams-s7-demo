(function () {
  "use strict";

  const app = document.getElementById("app");
  const connectionStatus = document.getElementById("connection-status");
  const stageButtons = Array.from(document.querySelectorAll("[data-stage-target]"));
  let currentState = null;
  let mermaidLoadAttempted = false;
  let mermaidReady = false;

  const stageConfig = [
    { id: "stage-epic", key: "epic", label: "EPIC" },
    { id: "stage-assess", key: "assessment", label: "ASSESS" },
    { id: "stage-design", key: "design", label: "DESIGN" },
    { id: "stage-gate", key: "gate", label: "GATE" },
    { id: "stage-stories", key: "stories", label: "STORIES" }
  ];

  const provenanceLabels = {
    human: "Human reviewed input",
    live_ai: "Live AI output",
    replayed_ai: "Recorded AI output",
    staged: "STAGED - prepared ahead of time, not live AI output"
  };

  const coverageLabels = {
    agentic: "Agentic",
    ai_assisted_external: "AI-assisted external",
    manual: "Manual"
  };

  const streamLabels = {
    frontend: "Frontend",
    api: "API/services",
    database: "Database",
    document_intake: "Document intake",
    system_of_record: "System of record",
    test: "Test"
  };

  function text(value) {
    return value === null || value === undefined ? "" : String(value);
  }

  function el(tag, options) {
    const node = document.createElement(tag);
    const opts = options || {};

    if (opts.className) {
      node.className = opts.className;
    }
    if (opts.id) {
      node.id = opts.id;
    }
    if (opts.text !== undefined) {
      node.textContent = text(opts.text);
    }
    if (opts.attrs) {
      Object.keys(opts.attrs).forEach((name) => {
        const value = opts.attrs[name];
        if (value !== false && value !== null && value !== undefined) {
          node.setAttribute(name, String(value));
        }
      });
    }
    if (opts.children) {
      opts.children.forEach((child) => {
        if (child) {
          node.appendChild(child);
        }
      });
    }
    return node;
  }

  function append(parent, children) {
    children.forEach((child) => {
      if (child) {
        parent.appendChild(child);
      }
    });
    return parent;
  }

  function badge(kind, value) {
    const normalized = text(value) || "unknown";
    if (kind === "provenance") {
      return el("span", {
        className: `provenance-badge provenance-${normalized}`,
        text: provenanceLabels[normalized] || `Provenance: ${normalized}`
      });
    }
    if (kind === "coverage") {
      return el("span", {
        className: `coverage-pill coverage-${normalized}`,
        text: coverageLabels[normalized] || normalized
      });
    }
    if (kind === "stream") {
      return el("span", {
        className: "stream-pill",
        text: streamLabels[normalized] || normalized
      });
    }
    return el("span", { className: "status-badge", text: normalized });
  }

  function sectionShell(id, number, title, subtitle, provenance) {
    const section = el("section", { id, className: "stage-section", attrs: { tabindex: "-1" } });
    const heading = el("div", { className: "section-heading" });
    const titleBlock = el("div");
    append(titleBlock, [
      el("p", { className: "section-kicker", text: `${number} ${title}` }),
      el("h2", { text: subtitle || title })
    ]);
    append(heading, [titleBlock, provenance ? badge("provenance", provenance) : null]);
    section.appendChild(heading);
    return section;
  }

  function renderMeta(label, value) {
    return el("div", {
      className: "meta-item",
      children: [
        el("p", { className: "meta-label", text: label }),
        el("p", { className: "meta-value", text: value || "Not provided" })
      ]
    });
  }

  // The server sends prose pre-parsed into blocks, so this console needs no
  // markdown parser of its own — one less thing to vendor for the locked-down
  // environment. `body` is the raw markdown and is only a fallback.
  // Gate timestamps arrive as ISO-8601 with microseconds. Shown raw they read
  // as debug output; the reviewer and the time they decided are meant to be
  // read by a room, not parsed.
  function formatDecidedAt(value) {
    if (!value) {
      return "Not recorded";
    }
    const parsed = new Date(value);
    if (isNaN(parsed.getTime())) {
      return value;
    }
    const date = parsed.toLocaleDateString(undefined, {
      day: "numeric", month: "short", year: "numeric"
    });
    const time = parsed.toLocaleTimeString(undefined, {
      hour: "2-digit", minute: "2-digit"
    });
    return `${date}, ${time}`;
  }

  function renderProseBlocks(item) {
    const blocks = Array.isArray(item.blocks) ? item.blocks : [];
    if (!blocks.length) {
      return item.body ? [el("p", { text: item.body })] : [];
    }
    return blocks.map((block) => {
      if (block.type === "list") {
        const list = el(block.ordered ? "ol" : "ul", { className: "prose-list" });
        (block.items || []).forEach((entry) => {
          list.appendChild(el("li", { text: entry }));
        });
        return list;
      }
      return el("p", { text: block.text || "" });
    });
  }

  function renderEpic(epic) {
    const section = sectionShell("stage-epic", "1", "EPIC", epic.title, epic.provenance);
    append(section, [
      el("div", {
        className: "meta-grid",
        children: [
          renderMeta("Epic ID", epic.id),
          renderMeta("Target application", epic.application),
          renderMeta("Delivery mode", "S7 full-scale delivery")
        ]
      }),
      el("div", {
        className: "summary-card",
        children: [el("h3", { text: "Summary" }), el("p", { text: epic.summary })]
      })
    ]);

    const sections = Array.isArray(epic.sections) ? epic.sections : [];
    if (sections.length) {
      const grid = el("div", { className: "content-grid" });
      sections.forEach((item) => {
        grid.appendChild(el("article", {
          className: "content-card",
          children: [
            el("h3", { text: item.heading || "Epic section" })
          ].concat(renderProseBlocks(item))
        }));
      });
      section.appendChild(grid);
    }

    const questions = Array.isArray(epic.open_questions) ? epic.open_questions : [];
    const questionBlock = el("aside", {
      className: "open-questions",
      children: [
        el("h3", { text: "Open questions - require SME validation" }),
        el("p", { text: "These items remain unresolved and must be validated before detailed delivery assumptions are treated as confirmed." })
      ]
    });
    const list = el("ul", { className: "open-question-list" });
    questions.forEach((question) => {
      list.appendChild(el("li", { text: question }));
    });
    if (!questions.length) {
      list.appendChild(el("li", { text: "No open questions were returned in the run state." }));
    }
    questionBlock.appendChild(list);
    section.appendChild(questionBlock);

    return section;
  }

  function formatPercent(share) {
    const numeric = Number(share);
    if (!Number.isFinite(numeric)) {
      return "0%";
    }
    return `${Math.round(numeric * 100)}%`;
  }

  function formatDays(days) {
    const numeric = Number(days);
    if (!Number.isFinite(numeric)) {
      return "0 days";
    }
    return `${numeric.toFixed(numeric % 1 === 0 ? 0 : 1)} days`;
  }

  function renderAssessment(assessment) {
    const section = sectionShell("stage-assess", "2", "ASSESS", "Assessment and stream routing", assessment.provenance);
    const totals = assessment.totals || {};
    section.appendChild(el("div", {
      className: "meta-grid",
      children: [
        renderMeta("Epic ID", assessment.epic_id),
        renderMeta("Task count", totals.task_count),
        renderMeta("Total estimate", formatDays(totals.estimate_days))
      ]
    }));

    const grid = el("div", { className: "assessment-grid" });
    const coveragePanel = el("article", { className: "coverage-panel" });
    append(coveragePanel, [
      el("h3", { text: "Coverage by effort" }),
      el("p", { className: "coverage-subtitle", text: "Weighted by effort, not task count." })
    ]);
    const coverageList = el("div", { className: "coverage-list" });
    (assessment.coverage_breakdown || []).forEach((item) => {
      const coverage = text(item.coverage);
      const percent = formatPercent(item.share);
      const row = el("div", { className: `coverage-row coverage-${coverage}` });
      append(row, [
        el("div", {
          className: "coverage-row-header",
          children: [
            el("span", { text: coverageLabels[coverage] || coverage }),
            el("span", { text: `${percent} / ${formatDays(item.days)}` })
          ]
        }),
        el("div", {
          className: "bar-track",
          attrs: {
            role: "img",
            "aria-label": `${coverageLabels[coverage] || coverage}: ${percent}, ${formatDays(item.days)}`
          },
          children: [
            el("div", {
              className: "bar-fill",
              attrs: { style: `width: ${Math.max(0, Math.min(100, Number(item.share) * 100 || 0))}%` }
            })
          ]
        })
      ]);
      coverageList.appendChild(row);
    });
    coveragePanel.appendChild(coverageList);

    const tasksPanel = el("article", { className: "tasks-panel" });
    append(tasksPanel, [el("h3", { text: "Stream-routed tasks" }), renderTasksTable(assessment.tasks || [])]);
    if (assessment.integration_note) {
      tasksPanel.appendChild(el("aside", {
        className: "integration-note",
        children: [
          el("h4", { text: "Integration point" }),
          el("p", { text: assessment.integration_note })
        ]
      }));
    }

    append(grid, [coveragePanel, tasksPanel]);
    section.appendChild(grid);
    return section;
  }

  function renderTasksTable(tasks) {
    const table = el("table");
    const thead = el("thead");
    thead.appendChild(el("tr", {
      children: ["ID", "Summary", "Stream", "Coverage", "Estimate"].map((heading) => el("th", { text: heading }))
    }));
    const tbody = el("tbody");
    tasks.forEach((task) => {
      const summaryCell = el("td");
      summaryCell.appendChild(el("strong", { text: task.summary || "" }));
      if (task.blocked_by_external) {
        summaryCell.appendChild(el("span", {
          className: "blocked-note",
          text: "Warning: other streams queue behind this externally blocked task."
        }));
      }
      if (task.rationale) {
        summaryCell.appendChild(el("p", { className: "form-hint", text: task.rationale }));
      }
      tbody.appendChild(el("tr", {
        className: task.blocked_by_external ? "is-blocked" : "",
        children: [
          el("td", { text: task.id }),
          summaryCell,
          el("td", { children: [badge("stream", task.stream)] }),
          el("td", { children: [badge("coverage", task.coverage)] }),
          el("td", { text: formatDays(task.estimate_days) })
        ]
      }));
    });
    if (!tasks.length) {
      tbody.appendChild(el("tr", {
        children: [el("td", { attrs: { colspan: "5" }, text: "No stream-routed tasks were returned in the run state." })]
      }));
    }
    append(table, [thead, tbody]);
    return el("div", { className: "table-wrap", children: [table] });
  }

  function renderDesign(designArtifacts) {
    const section = sectionShell("stage-design", "3", "DESIGN", "Design artifacts", null);
    const list = el("div", { className: "design-list" });
    (designArtifacts || []).forEach((artifact, index) => {
      const article = el("article", { className: "design-artifact" });
      append(article, [
        el("div", {
          className: "artifact-header",
          children: [
            el("div", {
              children: [
                el("p", { className: "section-kicker", text: `${artifact.id || `ARTIFACT-${index + 1}`} / ${artifact.kind || "design"}` }),
                el("h3", { text: artifact.title || "Design artifact" })
              ]
            }),
            badge("provenance", artifact.provenance)
          ]
        })
      ]);
      if (artifact.notes) {
        article.appendChild(el("p", { className: "lead", text: artifact.notes }));
      }
      if (artifact.format === "mermaid") {
        article.appendChild(renderMermaidArtifact(artifact, index));
      } else {
        article.appendChild(el("pre", { className: "artifact-source", text: artifact.source || "" }));
      }
      list.appendChild(article);
    });
    if (!designArtifacts || !designArtifacts.length) {
      list.appendChild(el("article", {
        className: "design-artifact",
        children: [el("h3", { text: "No design artifacts were returned in the run state." })]
      }));
    }
    section.appendChild(list);
    return section;
  }

  function renderMermaidArtifact(artifact, index) {
    const wrapper = el("div", { className: "diagram-wrapper" });
    const source = el("pre", { className: "artifact-source", text: artifact.source || "" });
    const note = el("p", {
      className: "diagram-note",
      text: "Source view shown. Rendered diagram appears when vendor/mermaid.min.js is available next to this console."
    });
    append(wrapper, [source, note]);
    wrapper.dataset.mermaidSource = artifact.source || "";
    wrapper.dataset.mermaidId = `mermaid-artifact-${index}`;
    return wrapper;
  }

  function loadMermaidIfPresent() {
    if (mermaidLoadAttempted) {
      return Promise.resolve(mermaidReady);
    }
    mermaidLoadAttempted = true;
    return new Promise((resolve) => {
      const script = document.createElement("script");
      script.src = "vendor/mermaid.min.js";
      script.async = true;
      script.onload = () => {
        mermaidReady = Boolean(window.mermaid);
        if (mermaidReady && window.mermaid.initialize) {
          window.mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });
        }
        resolve(mermaidReady);
      };
      script.onerror = () => {
        mermaidReady = false;
        resolve(false);
      };
      document.head.appendChild(script);
    });
  }

  function enhanceMermaid() {
    const wrappers = Array.from(document.querySelectorAll("[data-mermaid-source]"));
    if (!wrappers.length) {
      return;
    }
    loadMermaidIfPresent().then((ready) => {
      if (!ready || !window.mermaid || !window.mermaid.render) {
        return;
      }
      // Rendered one at a time, deliberately. Mermaid renders through a shared
      // temporary container, so firing every diagram off at once races them and
      // one silently loses its SVG — which looked like "the flowchart is broken"
      // when in fact it renders perfectly on its own.
      // Rendered one at a time: mermaid renders through a shared temporary
      // container, so firing every diagram at once can race them.
      function renderDiagram(wrapper) {
        const source = wrapper.dataset.mermaidSource || "";
        const id = wrapper.dataset.mermaidId || `mermaid-${Date.now()}`;
        return window.mermaid.render(id, source).then((result) => {
          // Parsed as HTML, not image/svg+xml. Mermaid puts node labels inside
          // <foreignObject> as HTML, which strict XML parsing rejects — and it
          // rejects it by returning a <parsererror> document rather than
          // throwing, so the flowchart silently fell through to its source view
          // while the stricter-markup entity diagram rendered fine. The HTML
          // parser is lenient and handles both.
          const parsed = new DOMParser().parseFromString(result.svg, "text/html");
          const svg = parsed.querySelector("svg");
          if (!svg) {
            throw new Error("no <svg> in mermaid output");
          }
          const rendered = el("div", { className: "diagram-rendered" });
          rendered.appendChild(document.importNode(svg, true));
          wrapper.replaceChildren(rendered);
        }).catch(() => {
          const note = wrapper.querySelector(".diagram-note");
          if (note) {
            note.textContent = "Rendered Mermaid view failed; source view is retained for the demo.";
          }
        });
      }

      wrappers.reduce(
        (chain, wrapper) => chain.then(() => renderDiagram(wrapper)),
        Promise.resolve()
      );
    });
  }

  function renderGate(gate) {
    const section = sectionShell("stage-gate", "4", "GATE", "Human review gate", null);
    const panel = el("article", { className: "gate-panel" });
    const statusText = gate.decision === "approved" ? "Approved - stories may proceed" :
      gate.decision === "rejected" ? "Rejected - stories remain locked" :
        "Pending - reviewer decision required";

    append(panel, [
      el("div", {
        className: "artifact-header",
        children: [
          el("div", {
            children: [
              el("h3", { text: statusText }),
              el("p", { className: "lead", text: "A named reviewer is required before the delivery console unlocks story breakdown." })
            ]
          }),
          badge("status", gate.decision || "pending")
        ]
      }),
      renderGateForm()
    ]);

    if (gate.decision && gate.decision !== "pending") {
      panel.appendChild(renderDecisionPanel(gate));
    }
    section.appendChild(panel);
    return section;
  }

  function renderGateForm() {
    const form = el("form", { className: "gate-form", attrs: { id: "gate-form" } });
    const reviewer = el("input", {
      attrs: {
        id: "reviewer",
        name: "reviewer",
        autocomplete: "name",
        required: "required",
        placeholder: "Reviewer name"
      }
    });
    const comment = el("textarea", {
      attrs: {
        id: "gate-comment",
        name: "comment",
        placeholder: "Optional review comment"
      }
    });
    const approve = el("button", {
      className: "action-button",
      text: "Approve",
      attrs: { type: "submit", value: "approved", disabled: "disabled" }
    });
    const reject = el("button", {
      className: "action-button reject",
      text: "Reject",
      attrs: { type: "submit", value: "rejected", disabled: "disabled" }
    });
    const reset = el("button", {
      className: "action-button secondary",
      text: "Reset",
      attrs: { type: "button", id: "reset-run" }
    });
    const error = el("p", { className: "error-text", attrs: { id: "gate-error", role: "status", "aria-live": "polite" } });

    append(form, [
      el("div", {
        className: "field-grid",
        children: [
          el("div", {
            className: "form-field",
            children: [
              el("label", { text: "Reviewer name", attrs: { for: "reviewer" } }),
              reviewer
            ]
          }),
          el("div", {
            className: "form-field",
            children: [
              el("label", { text: "Comment", attrs: { for: "gate-comment" } }),
              comment
            ]
          })
        ]
      }),
      el("p", { className: "form-hint", text: "Approve unlocks stories. Reject keeps story breakdown locked and records the review comment." }),
      el("div", { className: "button-row", children: [approve, reject, reset] }),
      error
    ]);

    reviewer.addEventListener("input", () => {
      const enabled = reviewer.value.trim().length > 0;
      approve.disabled = !enabled;
      reject.disabled = !enabled;
    });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const submitter = event.submitter;
      const decision = submitter ? submitter.value : "";
      submitGateDecision(decision, reviewer.value, comment.value, error);
    });
    reset.addEventListener("click", () => resetRun(error));
    return form;
  }

  function renderDecisionPanel(gate) {
    const panel = el("aside", { className: `decision-panel ${gate.decision}` });
    append(panel, [
      el("h3", { text: gate.decision === "approved" ? "Gate approved" : "Gate rejected" }),
      el("p", { text: `Reviewer: ${gate.reviewer || "Not recorded"}` }),
      el("p", { text: `Decision time: ${formatDecidedAt(gate.decided_at)}` }),
      el("p", { text: `Comment: ${gate.comment || "No comment provided."}` })
    ]);
    return panel;
  }

  function renderStories(stories, lockedReason) {
    const section = sectionShell("stage-stories", "5", "STORIES", "Delivery stories", null);
    if (!stories || !stories.length) {
      section.appendChild(el("div", {
        className: "locked-panel",
        children: [
          el("h3", { text: "Stories locked" }),
          el("p", { text: lockedReason || "Story breakdown is locked until the review gate is approved." })
        ]
      }));
      return section;
    }

    const grid = el("div", { className: "stories-grid" });
    stories.forEach((story) => {
      const article = el("article", { className: "story-card" });
      append(article, [
        el("div", {
          className: "artifact-header",
          children: [
            el("div", {
              children: [
                el("p", { className: "section-kicker", text: story.id || "Story" }),
                el("h3", { text: story.title || "Untitled story" })
              ]
            }),
            badge("provenance", story.provenance)
          ]
        }),
        el("p", { className: "story-narrative", text: story.narrative || "" }),
        renderStoryMeta(story),
        renderAcceptance(story.acceptance || []),
        renderAssumptions(story.assumptions || [])
      ]);
      grid.appendChild(article);
    });
    section.appendChild(grid);
    return section;
  }

  function renderStoryMeta(story) {
    const meta = el("div", { className: "story-meta" });
    (story.streams || []).forEach((stream) => meta.appendChild(badge("stream", stream)));
    meta.appendChild(el("span", { className: "status-badge", text: `${story.estimate_points || 0} points` }));
    return meta;
  }

  function renderAcceptance(items) {
    const block = el("div", { className: "content-card" });
    block.appendChild(el("h4", { text: "Acceptance criteria" }));
    const list = el("ul", { className: "criteria-list" });
    items.forEach((item) => {
      list.appendChild(el("li", { text: `${item.id ? `${item.id}: ` : ""}${item.text || ""}` }));
    });
    if (!items.length) {
      list.appendChild(el("li", { text: "No acceptance criteria returned." }));
    }
    block.appendChild(list);
    return block;
  }

  function renderAssumptions(items) {
    const block = el("aside", {
      className: "assumption-note",
      children: [
        el("h4", { text: "Resting on an unvalidated assumption" })
      ]
    });
    const list = el("ul", { className: "assumption-list" });
    items.forEach((item) => list.appendChild(el("li", { text: item })));
    if (!items.length) {
      list.appendChild(el("li", { text: "No unvalidated assumptions returned for this story." }));
    }
    block.appendChild(list);
    return block;
  }

  function renderState(state) {
    currentState = state;
    app.replaceChildren();
    append(app, [
      renderEpic(state.epic || {}),
      renderAssessment(state.assessment || {}),
      renderDesign(state.design || []),
      renderGate(state.gate || {}),
      renderStories(state.stories || [], state.stories_locked_reason)
    ]);
    updateStageRail(state);
    enhanceMermaid();
  }

  function updateStageRail(state) {
    const mayProceed = Boolean(state.gate && state.gate.may_proceed);
    stageButtons.forEach((button, index) => {
      button.classList.remove("is-complete", "is-current", "is-locked");
      if (index < 3 || (index === 3 && mayProceed)) {
        button.classList.add("is-complete");
      }
      if (index === 4 && !mayProceed) {
        button.classList.add("is-locked");
        button.setAttribute("aria-label", "STORIES locked until gate approval");
      } else {
        button.removeAttribute("aria-label");
      }
    });
  }

  function showOffline(message) {
    currentState = null;
    connectionStatus.textContent = "Backend not running";
    connectionStatus.classList.add("is-offline");
    app.replaceChildren(el("section", {
      className: "offline-panel",
      children: [
        el("h2", { text: "Backend not running" }),
        el("p", { text: message || "The console could not load GET /api/run. Start the FastAPI backend and refresh this page." })
      ]
    }));
  }

  function setOnlineStatus() {
    connectionStatus.textContent = "Pipeline state loaded";
    connectionStatus.classList.remove("is-offline");
  }

  function fetchRun() {
    return fetch("/api/run", { headers: { Accept: "application/json" } })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`GET /api/run returned ${response.status}`);
        }
        return response.json();
      });
  }

  function submitGateDecision(decision, reviewer, comment, errorNode) {
    if (!reviewer.trim()) {
      errorNode.textContent = "Reviewer name is required.";
      return;
    }
    errorNode.textContent = "";
    fetch("/api/gate", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ decision, reviewer: reviewer.trim(), comment: comment || "" })
    }).then((response) => {
      if (!response.ok) {
        return response.json().catch(() => ({})).then((body) => {
          throw new Error(body.detail || `POST /api/gate returned ${response.status}`);
        });
      }
      return response.json();
    }).then((state) => {
      setOnlineStatus();
      renderState(state);
      document.getElementById("stage-gate").focus();
    }).catch((error) => {
      errorNode.textContent = error.message || "Gate decision failed.";
    });
  }

  function resetRun(errorNode) {
    if (errorNode) {
      errorNode.textContent = "";
    }
    fetch("/api/reset", {
      method: "POST",
      headers: { Accept: "application/json" }
    }).then((response) => {
      if (!response.ok) {
        throw new Error(`POST /api/reset returned ${response.status}`);
      }
      return response.json();
    }).then((state) => {
      setOnlineStatus();
      renderState(state);
      document.getElementById("stage-gate").focus();
    }).catch((error) => {
      if (errorNode) {
        errorNode.textContent = error.message || "Reset failed.";
      } else {
        showOffline("The console could not reset the run because the backend is not reachable.");
      }
    });
  }

  function bindStageRail() {
    stageButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const target = document.getElementById(button.dataset.stageTarget);
        if (target) {
          stageButtons.forEach((item) => item.classList.remove("is-current"));
          button.classList.add("is-current");
          target.scrollIntoView({ behavior: "smooth", block: "start" });
          target.focus({ preventScroll: true });
        }
      });
    });
  }

  bindStageRail();
  fetchRun().then((state) => {
    setOnlineStatus();
    renderState(state);
  }).catch(() => {
    showOffline("The console could not load GET /api/run. Start the FastAPI backend and refresh this page.");
  });
}());
