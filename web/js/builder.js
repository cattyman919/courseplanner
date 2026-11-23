// "Build my plan": the student picks courses term by term. Every click is sent to the
// Python rule engine, which answers with a verdict per course and per term. The AI can
// pick a term or plan the rest from wherever the student is.

import { api } from "./api.js";
import { ALGORITHMS, RULE_ICON, TRACKS, clear, h, keepFocus, segmented, toast } from "./util.js";

const BLANK = "__blank__";
const GROUPS = [["required", "Required for your track"], ["elective", "Electives"],
  ["other", "Not needed for your goal"]];
const VERDICT_CLASS = { OK: "ok", PRUNED: "warn", PREREQ: "lock", OFFERING: "lock" };

function reason(v) {
  if (v.rule === "PREREQ") return `needs ${v.missing.join(", ")}`;
  if (v.rule === "OK") return "eligible now";
  return v.detail;
}

export function init(ctx, root) {
  const st = { base: ctx.profiles[0].name, cap: 18, algo: "astar", terms: [], picks: new Set(),
    suggestion: null, data: null, setupOpen: true };
  let seq = 0;

  function reset(base = st.base) {
    const p = ctx.profileByName.get(base);
    Object.assign(st, { base, completed: new Set(p ? p.completed : []),
      track: p ? p.target_track : "ai", start: p ? p.start_term : "fall",
      electives: p ? p.elective_credits_required : 9, terms: [], picks: new Set(),
      suggestion: null, setupOpen: true });
  }
  reset();

  const body = () => ({
    student: { completed: [...st.completed], target_track: st.track, start_term: st.start,
      elective_credits_required: st.electives, max_credits: st.cap },
    terms: st.terms, picks: [...st.picks].sort(), algorithm: st.algo,
  });

  async function refresh() {
    const mine = ++seq;
    try {
      const data = await api.check(body());
      if (mine !== seq) return;
      st.data = data;
      render();
    } catch (err) {
      toast(err.message, "error");
    }
  }

  const change = (fn) => (...args) => { fn(...args); refresh(); };

  const togglePick = change((code) => {
    st.picks.has(code) ? st.picks.delete(code) : st.picks.add(code);
  });
  const commit = change(() => {
    st.terms = [...st.terms, [...st.picks].sort()];
    st.picks = new Set();
    st.suggestion = null;
    st.setupOpen = false;
  });
  const skip = change(() => { st.terms = [...st.terms, []]; st.suggestion = null; });
  const undo = change(() => {
    const last = st.terms.at(-1) || [];
    st.terms = st.terms.slice(0, -1);
    st.picks = new Set(last);
    st.suggestion = null;
  });

  async function askAI(rest) {
    try {
      const plan = await api.suggest(body());
      if (rest) {
        st.suggestion = plan;
      } else if (plan.terms.length) {
        st.picks = new Set(plan.terms[0].courses);
        st.suggestion = null;
        toast(`${plan.algorithm_name} picked ${plan.terms[0].courses.join(", ")}.`, "ok");
      } else {
        toast(plan.infeasible || "Nothing left to plan.", "error");
      }
      refresh();
    } catch (err) {
      toast(err.message, "error");
    }
  }

  const accept = change(() => {
    st.terms = [...st.terms, ...st.suggestion.terms.map((t) => t.courses)];
    st.picks = new Set();
    st.suggestion = null;
    st.setupOpen = false;
  });

  // --- rendering --------------------------------------------------------------------

  function setup() {
    const locked = st.terms.length > 0;
    const presets = [...ctx.profiles.map((p) => [p.name, p.name]),
      [BLANK, "Blank student"]];
    const head = h("button", { type: "button", class: "setup-head",
      onclick: () => { st.setupOpen = !st.setupOpen; render(); } },
    h("span", { class: "eyebrow", text: "1 · Who are you?" }),
    h("span", { class: "muted", text: `${st.completed.size} completed · ${st.track} track · `
      + `starts ${st.start} · ${st.electives} elective cr · max ${st.cap} cr/term` }),
    h("span", { class: "chev", text: st.setupOpen ? "▴" : "▾" }));
    if (!st.setupOpen) return h("div", { class: "card setup collapsed" }, head);
    const capValue = h("b", { class: "mono", text: String(st.cap) });
    return h("div", { class: "card setup" }, head,
      locked ? h("p", { class: "notice", text: "Setup is locked while you have committed "
        + "terms. Press Start over to change it (the credit limit can still change)." }) : null,
      h("div", { class: "setup-grid" },
        h("div", {}, h("label", { text: "Start from" }),
          segmented(presets, st.base, change((v) => reset(v)), { small: true })),
        h("div", {}, h("label", { text: "Target track" }),
          locked ? h("b", { text: st.track })
            : segmented(TRACKS, st.track, change((v) => { st.track = v; }), { small: true })),
        h("div", {}, h("label", { text: "First term" }),
          locked ? h("b", { text: st.start })
            : segmented([["fall", "Fall"], ["spring", "Spring"]], st.start,
              change((v) => { st.start = v; }), { small: true })),
        h("div", {}, h("label", { text: "Elective credits required" }),
          h("input", { type: "number", min: 0, max: 21, step: 3, value: st.electives,
            disabled: locked, onchange: change((e) => {
              st.electives = Math.max(0, Math.min(21, Number(e.target.value) || 0));
            }) })),
        h("div", {}, h("label", {}, "Max credits per term ", capValue),
          h("input", { type: "range", min: 12, max: 21, value: st.cap,
            oninput: (e) => { capValue.textContent = e.target.value; },
            onchange: change((e) => { st.cap = Number(e.target.value); }) }))),
      h("label", { text: "Courses you have already completed (click to toggle)" }),
      h("div", { class: "done-grid" }, ctx.catalog.map((c) => h("button", {
        type: "button", disabled: locked, title: c.title,
        class: `done-toggle cat-${c.category}${st.completed.has(c.code) ? " on" : ""}`,
        onclick: change(() => {
          st.completed.has(c.code) ? st.completed.delete(c.code) : st.completed.add(c.code);
          st.picks.delete(c.code);
        }) }, c.code))));
  }

  function courseCard(c) {
    const v = c.verdict;
    const picked = st.picks.has(c.code);
    return h("button", {
      type: "button", class: `course-card v-${VERDICT_CLASS[v.rule] || "ok"}`
        + `${picked ? " picked" : ""}`,
      dataset: { code: c.code, missing: v.missing.join(" ") },
      title: `${v.rule}: ${v.detail}\nOffered: ${c.offered.join(", ")} · meets `
        + `${c.slots.join(", ") || "–"}`,
      "aria-pressed": picked ? "true" : "false",
      onclick: () => togglePick(c.code),
      onmouseenter: () => highlight(v.missing, true),
      onmouseleave: () => highlight(v.missing, false),
    },
    h("span", { class: "card-top" }, h("span", { class: "tick", text: picked ? "✓" : "" }),
      h("b", { text: c.code }), h("span", { class: "cr", text: `${c.credits} cr` })),
    h("span", { class: "title", text: c.title }),
    h("span", { class: "reason", text: `${RULE_ICON[v.rule]} ${reason(v)}` }),
    h("span", { class: "slots", text: c.slots.join(" · ") }));
  }

  function highlight(codes, on) {
    for (const code of codes) {
      root.querySelector(`.course-card[data-code="${code}"]`)?.classList.toggle("needed", on);
    }
  }

  function picker(data) {
    return h("div", { class: "picker" }, GROUPS.map(([key, title]) => {
      const courses = data.courses.filter((c) => c.group === key);
      if (!courses.length) return null;
      return h("div", { class: "group" }, h("p", { class: "eyebrow", text: title }),
        h("div", { class: "card-grid" }, courses.map(courseCard)));
    }));
  }

  function checks(data) {
    const check = data.check;
    const picks = Object.entries(check.per_course);
    const over = check.credits > check.max_credits;
    const lines = picks.map(([code, r]) => h("div", {
      class: `check-line ${r.ok ? "ok" : r.rule === "PRUNED" ? "warn" : "bad"}` },
    h("span", { class: `rule-pill r-${r.rule}`, text: r.rule }),
    h("span", {}, h("b", { text: code }), ` ${r.detail}`)));
    const schedule = check.schedule.map((r) => h("div", { class: "check-line bad" },
      h("span", { class: `rule-pill r-${r.rule}`, text: r.rule }),
      h("span", {}, h("b", { text: r.subject }), ` ${r.detail}`)));
    return h("aside", { class: "card check-panel" },
      h("p", { class: "eyebrow", text: "Rule check" }),
      picks.length ? null : h("p", { class: "muted", text: "Click courses to pick them. Every "
        + "pick is checked against the production rules." }),
      lines, schedule,
      h("div", { class: `meter${over ? " over" : ""}` },
        h("div", { class: "meter-fill",
          style: { width: `${Math.min(100, (100 * check.credits) / check.max_credits)}%` } })),
      h("p", { class: "mono meter-label", text: `${check.credits} / ${check.max_credits} credits` }),
      h("p", { class: "muted small", text: "Eligible and needed now: "
        + (data.available.join(", ") || "nothing this term") }),
      h("button", { type: "button", class: "primary-btn wide", disabled: !check.can_commit,
        title: "Allowed when no PREREQ, OFFERING, CONFLICT, or CREDIT_CAP rule fails.",
        onclick: commit }, `Commit ${data.term_label}`),
      data.available.length ? null : h("button", { type: "button", class: "ghost-btn wide",
        onclick: skip, text: "Skip this term (nothing to take)" }),
      h("div", { class: "ai-box" },
        h("p", { class: "eyebrow", text: "Ask the AI" }),
        segmented(ALGORITHMS, st.algo, (v) => { st.algo = v; }, { small: true }),
        h("div", { class: "btn-row" },
          h("button", { type: "button", class: "ghost-btn", onclick: () => askAI(false),
            title: "Ticks the first term of the AI's optimal plan from here" },
          "🤖 Pick this term"),
          h("button", { type: "button", class: "ghost-btn", onclick: () => askAI(true),
            title: "Searches from your current state to graduation" }, "🤖 Plan the rest"))));
  }

  function suggestion() {
    const s = st.suggestion;
    if (!s) return null;
    if (!s.terms.length) {
      return h("div", { class: "card suggestion bad" },
        h("b", { text: `${s.algorithm_name} found no plan from here.` }),
        h("p", { text: s.infeasible || "You already meet every requirement." }));
    }
    return h("div", { class: "card suggestion" },
      h("div", { class: "sugg-head" },
        h("div", {}, h("p", { class: "eyebrow", text: "AI suggestion" }),
          h("h3", { text: `${s.algorithm_name} needs ${s.terms.length} more term(s) · `
            + `cost ${s.stats.cost} · ${s.stats.expanded} states expanded` })),
        h("div", { class: "btn-row" },
          h("button", { type: "button", class: "primary-btn", onclick: accept,
            text: "Accept the AI's plan" }),
          h("button", { type: "button", class: "ghost-btn", text: "Dismiss",
            onclick: () => { st.suggestion = null; render(); } }))),
      h("div", { class: "term-row" }, s.terms.map((t) => h("div", { class: "term-card ghost" },
        h("div", { class: "term-head" }, h("b", { text: t.label }),
          h("span", { text: `${t.credits} cr` })),
        t.courses.map((c) => h("span", { class: "done-code", text: c }))))));
  }

  function timeline(data) {
    const p = data.progress;
    const need = Math.max(p.elective_need, 1);
    return h("div", { class: "card timeline" },
      h("div", { class: "log-head" },
        h("p", { class: "eyebrow", text: "Your plan so far" }),
        h("div", { class: "btn-row" },
          h("button", { type: "button", class: "ghost-btn small", disabled: !st.terms.length,
            onclick: undo, text: "↶ Undo last term" }),
          h("button", { type: "button", class: "ghost-btn small", text: "Start over",
            onclick: change(() => reset()) }))),
      st.terms.length ? h("div", { class: "term-row" }, st.terms.map((t, i) => h("div", {
        class: "term-card" },
      h("div", { class: "term-head" }, h("b", { text: `T${i + 1} · ${data.term_labels[i]}` }),
        h("span", { text: `${t.reduce((a, c) => a + ctx.byCode.get(c).credits, 0)} cr` })),
      t.length ? t.map((c) => h("span", { class: "done-code", text: c }))
        : h("span", { class: "muted", text: "skipped" }))))
        : h("p", { class: "muted", text: "Nothing committed yet." }),
      h("div", { class: "progress-row" },
        h("div", {}, h("span", { class: "muted", text: "Required courses left" }),
          h("b", { class: "big", text: String(p.required_left.length) }),
          h("div", { class: "chip-row" }, p.required_left.map((c) => h("span", {
            class: "done-code todo", text: c })))),
        h("div", {}, h("span", { class: "muted", text: "Elective credits" }),
          h("b", { class: "big", text: `${p.elective_have} / ${p.elective_need}` }),
          h("div", { class: "meter" }, h("div", { class: "meter-fill ok",
            style: { width: `${p.elective_need ? Math.min(100, 100 * p.elective_have / need)
              : 100}%` } })))),
      p.done ? h("div", { class: "celebrate", text: `🎓 Every requirement for the ${st.track} `
        + `track is met after ${st.terms.length} term(s).` }) : null);
  }

  function render() {
    const data = st.data;
    if (!data) return;
    const done = data.progress.done;
    // Redraw everything, but put keyboard focus back on the control that had it (or on the
    // term heading when that control is gone), so keyboard users are not sent to the top.
    keepFocus(root, () => clear(root,
      h("div", { class: "view-head" },
        h("div", {}, h("p", { class: "eyebrow", text: "Build my plan" }),
          h("h1", { tabindex: -1, text: "You choose the courses. The rule engine checks "
            + "every pick." }))),
      setup(),
      done ? null : h("div", { class: "build-head" },
        h("h2", { tabindex: -1 }, `2 · Term ${data.term_index + 1}: `, h("span", {
          class: "accent", text: data.term_label }))),
      done ? null : h("div", { class: "build-grid" }, picker(data), checks(data)),
      suggestion(),
      timeline(data)),
    () => root.querySelector(".build-head h2") || root.querySelector("h1"));
  }

  refresh();
  return {};
}
