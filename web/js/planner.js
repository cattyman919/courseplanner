// AI planner view: choose a student and settings, the search engine plans every term, and
// the rule log explains each decision. Re-plans live whenever a setting changes.

import { api } from "./api.js";
import { ALGORITHMS, RULE_ICON, TRACKS, clear, fmt, h, segmented, stat, toast } from "./util.js";

const RULES = ["OK", "PREREQ", "OFFERING", "CONFLICT", "PRUNED", "CREDIT_CAP", "INFEASIBLE"];
const RULE_HELP = {
  OK: "A rule fired and allowed something (eligible, or the bundle taken that term).",
  PREREQ: "A prerequisite is missing, so the course is held back.",
  OFFERING: "The course is not offered in that term.",
  CONFLICT: "Two eligible courses meet at the same time; the planner can take only one.",
  PRUNED: "Not needed for the goal, so the search never considers it.",
  CREDIT_CAP: "The bundle would exceed the credit limit.",
  INFEASIBLE: "No plan exists within the term limit.",
};

export function describeProfile(p) {
  const done = p.completed.length ? `${p.completed.length} courses done` : "nothing done yet";
  return `${p.target_track} track · starts ${p.start_term} · ${done} · `
    + `${p.elective_credits_required} elective cr`;
}

export function init(ctx, root) {
  let seq = 0;
  let loaded = null; // saved-plan metadata when showing a plan from the database
  let selected = null; // course code whose explanation is open
  const filters = new Set(RULES);
  let query = "";

  const els = {
    summary: h("div", { class: "card summary-card" }),
    terms: h("div", { class: "term-row" }),
    compare: h("div", { class: "card" }),
    why: h("div", { class: "card why-card" }),
    log: h("div", { class: "card log-card" }),
  };

  const profileButtons = ctx.profiles.map((p) => h("button", {
    type: "button", class: "profile-btn", dataset: { name: p.name },
    onclick: () => {
      ctx.params.profile = p.name;
      ctx.params.track = p.target_track;
      trackSeg.querySelectorAll("button").forEach((b) => b.classList.toggle("active",
        b.dataset.value === p.target_track));
      refresh();
    },
  }, h("b", { text: p.name }), h("span", { text: describeProfile(p) })));

  const trackSeg = segmented(TRACKS, ctx.params.track, (v) => { ctx.params.track = v; refresh(); },
    { label: "Target track" });
  const creditValue = h("b", { class: "mono", text: String(ctx.params.max_credits) });
  const credits = h("input", { type: "range", min: 12, max: 21, value: ctx.params.max_credits,
    "aria-label": "Max credits per term",
    oninput: (e) => { creditValue.textContent = e.target.value; },
    onchange: (e) => { ctx.params.max_credits = Number(e.target.value); refresh(); } });
  const algoSeg = segmented(ALGORITHMS, ctx.params.algorithm,
    (v) => { ctx.params.algorithm = v; refresh(); }, { label: "Algorithm" });

  const controls = h("aside", { class: "card controls" },
    h("p", { class: "eyebrow", text: "1 · Student" }), ...profileButtons,
    h("p", { class: "eyebrow", text: "2 · Target track" }), trackSeg,
    h("p", { class: "eyebrow" }, "3 · Max credits per term ", creditValue), credits,
    h("div", { class: "range-ticks" }, h("span", { text: "12" }), h("span", { text: "21" })),
    h("p", { class: "eyebrow", text: "4 · Search algorithm" }), algoSeg,
    h("button", { type: "button", class: "primary-btn wide", onclick: save },
      "💾 Save this plan"),
    h("p", { class: "hint", text: "The plan updates as soon as you change a setting. "
      + "Click any course to see which rules fired for it." }));

  clear(root, h("div", { class: "planner-grid" }, controls,
    h("div", { class: "planner-main" }, els.summary, els.terms,
      h("div", { class: "two-col" }, els.why, els.compare), els.log)));

  function syncControls() {
    profileButtons.forEach((b) => b.classList.toggle("active",
      b.dataset.name === ctx.params.profile));
    credits.value = ctx.params.max_credits;
    creditValue.textContent = String(ctx.params.max_credits);
    for (const [seg, value] of [[trackSeg, ctx.params.track],
      [algoSeg, ctx.params.algorithm]]) {
      seg.querySelectorAll("button").forEach((b) => b.classList.toggle("active",
        b.dataset.value === value));
    }
  }

  async function refresh() {
    syncControls();
    loaded = null;
    const mine = ++seq;
    root.classList.add("busy");
    try {
      const plan = await api.plan({ ...ctx.params, compare: true });
      if (mine !== seq) return;
      show(plan);
    } catch (err) {
      toast(err.message, "error");
    } finally {
      if (mine === seq) root.classList.remove("busy");
    }
  }

  function show(plan) {
    ctx.plan = plan;
    if (selected && !plan.log.some((r) => r.subject === selected)) selected = null;
    renderSummary(plan);
    renderTerms(plan);
    renderWhy(plan);
    renderCompare(plan);
    renderLog(plan);
    ctx.emit("plan", plan);
  }

  function renderSummary(plan) {
    const s = plan.stats;
    const headline = plan.terms.length
      ? `${plan.terms.length} terms · ${plan.total_credits} credits`
      : "No plan found";
    clear(els.summary,
      h("div", { class: "summary-head" },
        h("div", {},
          h("p", { class: "eyebrow", text: loaded
            ? `Saved plan #${loaded.id} · loaded from SQLite`
            : `${plan.algorithm_name} plan for ${ctx.params.profile}` }),
          h("h1", { text: headline }),
          h("p", { class: "muted", text: plan.infeasible
            || (plan.top_pruned.length ? "Most held-back courses: " + plan.top_pruned
              .map((t) => `${t.code} (${t.count}×)`).join(", ") : "") })),
        h("div", { class: "stats" },
          stat("Path cost", fmt(s.cost), "Sum of 1 + 0.05 × credits per term (BFS: 1 per term)"),
          stat("Expanded", s.expanded, "States taken off the frontier and expanded"),
          stat("Generated", s.generated, "Successor states created"),
          stat("Time", `${fmt(s.ms, 1)} ms`))));
  }

  function courseChip(code, extra = {}) {
    const c = ctx.byCode.get(code);
    return h("button", { type: "button",
      class: `course-chip cat-${c.category}${selected === code ? " selected" : ""}`,
      title: `${c.title} · ${c.credits} cr · prereqs: ${c.prereqs.join(", ") || "none"}`,
      onclick: () => { selected = selected === code ? null : code; show(ctx.plan); },
      ...extra },
    h("b", { text: code }), h("span", { text: c.title }), h("i", { text: `${c.credits}` }));
  }

  function renderTerms(plan) {
    const profile = ctx.profileByName.get(ctx.params.profile);
    const start = h("div", { class: "term-card start" },
      h("div", { class: "term-head" }, h("b", { text: "Already done" }),
        h("span", { text: `${profile.completed.length}` })),
      profile.completed.length ? profile.completed.map((c) => h("span", { class: "done-code",
        text: c })) : h("span", { class: "muted", text: "Nothing yet" }));
    const terms = plan.terms.map((t, i) => h("div", { class: "term-card" },
      h("div", { class: "term-head" }, h("b", { text: `T${i + 1} · ${t.label}` }),
        h("span", { text: `${t.credits} cr` })),
      t.courses.length ? t.courses.map((code) => h("div", { class: "chip-wrap" },
        courseChip(code),
        plan.inserted.includes(code)
          ? h("span", { class: "badge amber", title: "A prerequisite you were missing; "
            + "the planner inserted it before the course that needs it",
          text: "catch-up" }) : null))
        : h("span", { class: "muted", text: "Wait: nothing eligible this term" })));
    clear(els.terms, start, terms);
  }

  function renderWhy(plan) {
    if (!selected) {
      clear(els.why, h("p", { class: "eyebrow", text: "Why this course?" }),
        h("p", { class: "muted", text: "Click a course in the plan to trace the rules that "
          + "fired for it, term by term." }),
        h("div", { class: "rule-legend" }, RULES.slice(0, 5).map((r) => h("div", {},
          h("span", { class: `rule-pill r-${r}`, text: `${RULE_ICON[r]} ${r}` }),
          h("span", { class: "muted", text: RULE_HELP[r] })))));
      return;
    }
    const c = ctx.byCode.get(selected);
    const rows = plan.log.filter((r) => r.subject === selected
      || r.subject.split("/").includes(selected));
    const term = plan.terms.findIndex((t) => t.courses.includes(selected));
    clear(els.why,
      h("div", { class: "why-head" },
        h("div", {}, h("p", { class: "eyebrow", text: "Why this course?" }),
          h("h2", {}, `${c.code} `, h("span", { class: "muted", text: c.title }))),
        h("button", { type: "button", class: "ghost-btn small", text: "Close",
          onclick: () => { selected = null; show(ctx.plan); } })),
      h("p", { class: "facts" },
        `${c.credits} credits · ${c.category}${c.track ? ` (${c.track})` : ""} · offered `
        + `${c.offered.join(" & ")} · meets ${c.slots.join(", ") || "–"} · prerequisites: `
        + `${c.prereqs.join(", ") || "none"}`),
      h("p", { class: "verdict", text: term >= 0
        ? `Planned in T${term + 1} (${plan.terms[term].label}).`
        : "Not in the plan." }),
      h("ol", { class: "why-list" }, rows.map((r) => h("li", {},
        h("span", { class: `rule-pill r-${r.rule}`, text: `${RULE_ICON[r.rule] || ""} ${r.rule}` }),
        h("span", { text: r.detail })))));
  }

  function renderCompare(plan) {
    const cmp = plan.comparison || {};
    const max = Math.max(1, ...Object.values(cmp).map((p) => p.stats.expanded));
    clear(els.compare, h("p", { class: "eyebrow", text: "Same student, three algorithms" }),
      ALGORITHMS.map(([a, name]) => {
        const p = cmp[a];
        if (!p) return null;
        return h("div", { class: `bar-row${a === plan.algorithm ? " current" : ""}` },
          h("b", { text: name }),
          h("div", { class: "bar" }, h("div", { class: `fill a-${a}`,
            style: { width: `${(100 * p.stats.expanded) / max}%` } })),
          h("span", { class: "mono", text: `${p.stats.expanded} expanded` }),
          h("span", { class: "muted mono",
            text: `${p.terms.length} terms · cost ${fmt(p.stats.cost)}` }));
      }),
      h("p", { class: "hint", text: "UCS and A* always agree on the cost (A* is optimal "
        + "because h never overestimates); A* gets there by expanding fewer states. BFS "
        + "minimises the number of terms and ignores credits." }));
  }

  function renderLog(plan) {
    const counts = Object.fromEntries(RULES.map((r) => [r, 0]));
    plan.log.forEach((r) => { counts[r.rule] = (counts[r.rule] || 0) + 1; });
    const chips = RULES.filter((r) => counts[r]).map((r) => h("button", {
      type: "button", class: `rule-pill r-${r} toggle${filters.has(r) ? "" : " off"}`,
      title: RULE_HELP[r],
      onclick: () => { filters.has(r) ? filters.delete(r) : filters.add(r); renderLog(plan); },
    }, `${RULE_ICON[r]} ${r} `, h("small", { text: String(counts[r]) })));
    const q = query.trim().toLowerCase();
    const rows = plan.log.map((r, i) => [r, i]).filter(([r]) => filters.has(r.rule)
      && (!q || `${r.subject} ${r.detail}`.toLowerCase().includes(q)));
    const search = h("input", { type: "search", placeholder: "Filter, e.g. CS301 or Fall 2027",
      value: query, oninput: (e) => {
        query = e.target.value;
        renderLog(plan);
        const again = els.log.querySelector("input[type=search]");
        again.focus();
        again.setSelectionRange(query.length, query.length);
      } });
    clear(els.log,
      h("div", { class: "log-head" },
        h("div", {}, h("p", { class: "eyebrow", text: "Rule & inference log" }),
          h("p", { class: "muted", text: `${rows.length} of ${plan.log.length} rule firings, `
            + "in the order the planner reasoned about the final plan." })), search),
      h("div", { class: "chip-row" }, chips),
      h("div", { class: "log-table" }, rows.map(([r, i]) => h("div", {
        class: `log-row${r.ok ? "" : " fail"}`,
        onclick: () => {
          if (ctx.byCode.has(r.subject)) { selected = r.subject; show(ctx.plan); }
        } },
      h("span", { class: "mono faint", text: String(i + 1) }),
      h("span", { class: `rule-pill r-${r.rule}`, text: r.rule }),
      h("b", { class: "mono", text: r.subject }),
      h("span", { text: r.detail })))));
  }

  async function save() {
    try {
      const { id } = await api.savePlan(ctx.params);
      toast(`Saved plan #${id} to SQLite.`, "ok");
      ctx.emit("saved", id);
    } catch (err) {
      toast(err.message, "error");
    }
  }

  ctx.on("load-saved", ({ meta, plan }) => {
    ctx.params.profile = meta.profile_name;
    ctx.params.track = meta.target_track;
    ctx.params.max_credits = meta.max_credits;
    ctx.params.algorithm = meta.algorithm;
    syncControls();
    seq++;
    loaded = meta;
    show(plan);
    ctx.go("planner");
  });

  refresh();
  return {};
}
