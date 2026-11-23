// Prerequisite graph: every course as a node in columns by prerequisite depth, coloured by
// the term the current plan takes it in. Click (or hover) a course to light up the whole
// chain of prerequisites it needs and the courses it unlocks.

import { closure, layoutDag } from "./layout.js";
import { clear, h, keepFocus, pressable, svg } from "./util.js";

const NODE_W = 132;
const NODE_H = 40;
const PAD = 16;
const TERM_COLORS = ["#2f5fd0", "#0f8a7a", "#8b5cf6", "#d97706", "#c0392b", "#0e7490",
  "#a21caf", "#4d7c0f"];

export function init(ctx, root) {
  const prereqs = (code) => ctx.byCode.get(code)?.prereqs.filter((p) => ctx.byCode.has(p)) || [];
  const unlocksMap = new Map(ctx.catalog.map((c) => [c.code, []]));
  ctx.catalog.forEach((c) => prereqs(c.code).forEach((p) => unlocksMap.get(p).push(c.code)));
  const unlocks = (code) => unlocksMap.get(code) || [];
  let selected = null;
  let hovered = null;

  const legend = h("div", { class: "legend graph-legend" });
  const panel = h("div", { class: "card node-detail", tabindex: -1 });
  const caption = h("p", { class: "muted" });
  const { pos, width, height } = layoutDag(ctx.catalog, { dx: NODE_W + 46, dy: NODE_H + 16 });
  const W = width - 46 + PAD * 2;
  const H = height - 16 + PAD * 2;

  const edgeEls = [];
  const edges = svg("g", { class: "edges" });
  for (const c of ctx.catalog) {
    for (const p of prereqs(c.code)) {
      const a = pos.get(p);
      const b = pos.get(c.code);
      const x1 = a.x + NODE_W + PAD;
      const y1 = a.y + NODE_H / 2 + PAD;
      const x2 = b.x + PAD;
      const y2 = b.y + NODE_H / 2 + PAD;
      const mx = (x1 + x2) / 2;
      const path = svg("path", { d: `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`,
        "marker-end": "url(#arrow)" });
      edges.append(path);
      edgeEls.push({ from: p, to: c.code, el: path });
    }
  }
  const nodeEls = new Map();
  const nodes = svg("g", { class: "nodes" });
  for (const c of ctx.catalog) {
    const p = pos.get(c.code);
    const tag = svg("text", { x: NODE_W - 8, y: 16, class: "tag", "text-anchor": "end" });
    const g = svg("g", { class: "gnode", transform: `translate(${p.x + PAD},${p.y + PAD})`,
      onclick: () => { selected = selected === c.code ? null : c.code; paint(); },
      onfocus: () => { hovered = c.code; paint(); },
      onblur: () => { hovered = null; paint(); },
      onmouseenter: () => { hovered = c.code; paint(); },
      onmouseleave: () => { hovered = null; paint(); } },
    svg("title", { text: `${c.code} · ${c.title}` }),
    svg("rect", { width: NODE_W, height: NODE_H, rx: 9 }),
    svg("rect", { class: "stripe", width: 5, height: NODE_H, rx: 2 }),
    svg("text", { x: 12, y: 16, class: "code", text: c.code }),
    svg("text", { x: 12, y: 31, class: "name",
      text: c.title.length > 19 ? `${c.title.slice(0, 18)}…` : c.title }),
    tag);
    pressable(g, `${c.code} ${c.title}`, () => {
      selected = selected === c.code ? null : c.code;
      paint();
    });
    nodes.append(g);
    nodeEls.set(c.code, { g, tag });
  }
  const defs = svg("defs", {}, svg("marker", { id: "arrow", viewBox: "0 0 10 10", refX: 9,
    refY: 5, markerWidth: 8, markerHeight: 8, markerUnits: "userSpaceOnUse",
    orient: "auto-start-reverse" },
  svg("path", { d: "M0,0 L10,5 L0,10 z", class: "arrow" })));
  const graph = svg("svg", { class: "dag", viewBox: `0 0 ${W} ${H}`, width: W, height: H },
    defs, edges, nodes);

  clear(root,
    h("div", { class: "view-head" },
      h("div", {}, h("p", { class: "eyebrow", text: "Prerequisite graph" }),
        h("h1", { text: "The knowledge base as a graph: who needs whom." }), caption)),
    h("div", { class: "watch-grid" },
      h("div", { class: "card tree-card" }, h("div", { class: "tree-tools" }, legend),
        h("div", { class: "tree-scroll dag-scroll" }, graph)),
      h("div", { class: "side-col" }, panel)));

  function termOf(plan) {
    const map = new Map();
    plan?.terms.forEach((t, i) => t.courses.forEach((c) => map.set(c, i)));
    return map;
  }

  function paint() {
    const plan = ctx.plan;
    const term = termOf(plan);
    const done = new Set(plan?.profile?.completed || []);
    const required = new Set(plan?.required || []);
    const focus = hovered || selected;
    const up = focus ? closure(focus, prereqs) : new Set();
    const down = focus ? closure(focus, unlocks) : new Set();

    for (const [code, { g, tag }] of nodeEls) {
      const c = ctx.byCode.get(code);
      let state = "unneeded";
      let color = "#b8b2a6";
      tag.textContent = "";
      if (done.has(code)) { state = "done"; color = "#1f8a4c"; tag.textContent = "✓"; }
      else if (term.has(code)) {
        state = "planned";
        color = TERM_COLORS[term.get(code) % TERM_COLORS.length];
        tag.textContent = `T${term.get(code) + 1}`;
      } else if (required.has(code) || c.category === "elective") state = "open";
      const rel = !focus ? "" : code === focus ? " focus" : up.has(code) ? " up"
        : down.has(code) ? " down" : " faded";
      g.setAttribute("class", `gnode s-${state}${rel}${code === selected ? " selected" : ""}`);
      g.style.setProperty("--c", color);
    }
    for (const { from, to, el } of edgeEls) {
      const onChain = focus && ((up.has(from) && (up.has(to) || to === focus))
        || ((down.has(to) || from === focus) && (down.has(from) || from === focus)));
      const cls = !focus ? "" : onChain ? (up.has(from) ? "up" : "down") : "faded";
      el.setAttribute("class", cls);
    }

    const terms = plan?.terms || [];
    clear(legend,
      h("span", {}, h("i", { class: "sw", style: { background: "#def3e5",
        borderColor: "#1f8a4c" } }), "completed"),
      terms.map((t, i) => h("span", {}, h("i", { class: "sw", style: {
        background: TERM_COLORS[i % TERM_COLORS.length],
        borderColor: TERM_COLORS[i % TERM_COLORS.length] } }), `T${i + 1} ${t.label}`)),
      h("span", {}, h("i", { class: "sw", style: { background: "#fff",
        borderColor: "#b8b2a6", borderStyle: "dashed" } }), "not needed"));
    caption.textContent = plan
      ? `Coloured by the ${plan.algorithm_name} plan for ${plan.profile?.name || "the student"}`
        + ` (${plan.profile?.target_track || ""} track). Arrows point from a prerequisite to `
        + "the course that needs it."
      : "Generate a plan in the AI planner to colour the graph by term.";
    keepFocus(panel, () => renderPanel(focus, up, down, term, done), panel);
  }

  function renderPanel(focus, up, down, term, done) {
    if (!focus) {
      clear(panel, h("p", { class: "eyebrow", text: "Course" }),
        h("p", { class: "muted", text: "Hover or click a course. Its prerequisite chain "
          + "lights up in amber and everything it unlocks in blue." }),
        h("p", { class: "muted small", text: "The longest chain decides the minimum "
          + "number of terms: that is one half of the A* heuristic." }));
      return;
    }
    const c = ctx.byCode.get(focus);
    const status = done.has(focus) ? "already completed"
      : term.has(focus) ? `planned in T${term.get(focus) + 1} (${ctx.plan.terms[term.get(focus)].label})`
        : "not in the plan";
    const codes = (set) => set.size ? h("div", { class: "chip-row" }, [...set].sort().map((x) =>
      h("button", { type: "button", class: `done-code${done.has(x) ? "" : " todo"}`, text: x,
        onclick: () => { selected = x; paint(); } })))
      : h("p", { class: "muted small", text: "none" });
    clear(panel,
      h("p", { class: "eyebrow", text: selected === focus ? "Selected course" : "Course" }),
      h("h3", { text: `${c.code} · ${c.title}` }),
      h("p", { class: "facts" }, `${c.credits} credits · ${c.category}`
        + `${c.track ? ` (${c.track})` : ""} · offered ${c.offered.join(" & ")} · meets `
        + `${c.slots.join(", ") || "–"}`),
      h("p", { class: "verdict", text: status }),
      h("p", { class: "eyebrow", text: `Needs first (${up.size})` }), codes(up),
      h("p", { class: "eyebrow spaced", text: `Unlocks (${down.size})` }), codes(down),
      selected ? h("button", { type: "button", class: "ghost-btn small spaced", text: "Clear",
        onclick: () => { selected = null; paint(); } }) : null);
  }

  ctx.on("plan", paint);
  paint();
  return { show: paint };
}
