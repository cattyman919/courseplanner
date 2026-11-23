// "Watch the search": fetch one recorded search run and replay it in the browser, event by
// event, like a debugger. The tree layout is fixed per run, so nodes appear in place.

import { api } from "./api.js";
import { replay, layoutTree } from "./layout.js";
import { ALGORITHMS, clear, fmt, h, segmented, stat, svg, toast } from "./util.js";

const KIND_ICON = { start: "🟦", expand: "🔶", push: "➕", duplicate: "✂️", worse: "✂️",
  stale: "♻️", limit: "⛔", goal: "🎯", exhausted: "❌" };
const SKIPPED = new Set(["skipped", "stale", "limit"]);
const NODE_W = 172;
const NODE_H = 46;

export function init(ctx, root) {
  const params = { ...ctx.params, max_credits: 12 };
  const st = { trace: null, step: 0, playing: false, delay: 600, timer: null, zoom: 1,
    showSkipped: true, follow: true, selected: null, els: null };
  let seq = 0;

  // --- controls ---------------------------------------------------------------------

  const profileSeg = segmented(ctx.profiles.map((p) => [p.name, p.name]), params.profile,
    (v) => { params.profile = v; params.track = ctx.profileByName.get(v).target_track; load(); },
    { small: true, label: "Student" });
  const creditValue = h("b", { class: "mono", text: String(params.max_credits) });
  const credits = h("input", { type: "range", min: 12, max: 21, value: params.max_credits,
    oninput: (e) => { creditValue.textContent = e.target.value; },
    onchange: (e) => { params.max_credits = Number(e.target.value); load(); } });
  const algoSeg = segmented(ALGORITHMS, params.algorithm,
    (v) => { params.algorithm = v; load(); }, { label: "Algorithm" });
  const idea = h("p", { class: "muted idea" });

  const button = (text, title, onclick, cls = "ghost-btn") => h("button", { type: "button",
    class: cls, title, onclick }, text);
  const playBtn = button("▶ Play", "Play / pause (space)", () => togglePlay(), "ghost-btn");
  const speed = h("input", { type: "range", min: 80, max: 1500, step: 20, value: 1580 - st.delay,
    "aria-label": "Speed", oninput: (e) => {
      st.delay = 1580 - Number(e.target.value);
      if (st.playing) { stop(); play(); }
    } });

  const banner = h("div", { class: "banner" });
  const statsRow = h("div", { class: "stats" });
  const scroller = h("div", { class: "tree-scroll" });
  const detail = h("div", { class: "card node-detail" });
  const log = h("ol", { class: "event-log" });
  const done = h("div");
  const scrub = h("input", { type: "range", min: 0, max: 0, value: 0, class: "scrub",
    "aria-label": "Step", oninput: (e) => goto(Number(e.target.value)) });

  clear(root,
    h("div", { class: "view-head" },
      h("div", {}, h("p", { class: "eyebrow", text: "Watch the search" }),
        h("h1", { text: "Step through the planner's search, one state at a time." }))),
    h("div", { class: "card watch-controls" },
      h("div", { class: "watch-settings" },
        h("div", {}, h("label", { text: "Student" }), profileSeg),
        h("div", {}, h("label", {}, "Max credits ", creditValue), credits),
        h("div", {}, h("label", { text: "Algorithm" }), algoSeg)),
      idea,
      h("div", { class: "player" },
        button("⏮", "Reset (Home)", () => goto(0)),
        button("◀ Back", "Back (←)", () => goto(st.step - 1)),
        button("Step ▶", "Step (→)", () => goto(st.step + 1), "primary-btn"),
        playBtn,
        button("⏭ Run to end", "Run to end (End)", () => goto(Infinity)),
        h("label", { class: "speed" }, "Speed", speed)),
      scrub),
    statsRow, banner,
    h("div", { class: "watch-grid" },
      h("div", { class: "card tree-card" },
        h("div", { class: "tree-tools" },
          h("div", { class: "legend" },
            ["current", "expanded", "frontier", "skipped", "path"].map((s) => h("span", {},
              h("i", { class: `sw st-${s}` }), { current: "being expanded",
                expanded: "expanded", frontier: "frontier (waiting)",
                skipped: "skipped", path: "solution path" }[s]))),
          h("div", { class: "btn-row" },
            h("label", { class: "check" }, h("input", { type: "checkbox", checked: true,
              onchange: (e) => { st.showSkipped = e.target.checked; paint(); } }),
            "Show skipped"),
            h("label", { class: "check" }, h("input", { type: "checkbox", checked: true,
              onchange: (e) => { st.follow = e.target.checked; } }), "Follow"),
            button("−", "Zoom out", () => zoom(0.8), "ghost-btn small"),
            button("+", "Zoom in", () => zoom(1.25), "ghost-btn small"))),
        scroller),
      h("div", { class: "side-col" }, detail,
        h("div", { class: "card" }, h("p", { class: "eyebrow", text: "Process log" }), log))),
    done);

  // --- data -------------------------------------------------------------------------

  async function load() {
    stop();
    const mine = ++seq;
    root.classList.add("busy");
    try {
      const trace = await api.trace(params);
      if (mine !== seq) return;
      st.trace = trace;
      st.trace.byId = new Map(trace.nodes.map((n) => [n.id, n]));
      st.step = 0;
      st.selected = null;
      idea.textContent = trace.idea;
      scrub.max = String(trace.events.length - 1);
      if (trace.truncated) toast("This search is very large; only the first events are shown.");
      build();
    } catch (err) {
      toast(err.message, "error");
    } finally {
      if (mine === seq) root.classList.remove("busy");
    }
  }

  // --- tree -------------------------------------------------------------------------

  const PAD = 14;
  const GAP_X = 34;
  const GAP_Y = 10;

  /** Create one SVG group per node and one path per edge; paint() positions them. */
  function build() {
    const t = st.trace;
    if (!t) return;
    const edges = svg("g", { class: "edges" });
    const nodes = svg("g", { class: "nodes" });
    const nodeEls = new Map();
    const edgeEls = new Map();
    for (const n of t.nodes) {
      if (n.parent !== null) {
        const e = svg("path", { class: "hidden" });
        edges.append(e);
        edgeEls.set(n.id, e);
      }
      const codes = n.combo.join(" ");
      const line2 = n.parent === null ? "start state"
        : codes ? `+ ${codes.length > 26 ? `${codes.slice(0, 25)}…` : codes}` : "(wait)";
      const f = t.algorithm === "astar" && n.h !== null
        ? `  h=${fmt(n.h)}  f=${fmt(n.g + n.h)}` : "";
      const g = svg("g", { class: "node hidden", dataset: { id: n.id },
        onclick: () => select(n.id) },
      svg("title", { text: `${n.title}\ng = ${fmt(n.g)}`
        + `${n.h !== null ? `, h = ${fmt(n.h)}` : ""}` }),
      svg("rect", { width: NODE_W, height: NODE_H, rx: 8 }),
      svg("text", { x: 8, y: 14, class: "t1", text: `#${n.id} ${n.parent === null ? "Start"
        : n.term}` }),
      svg("text", { x: 8, y: 28, class: "t2", text: line2 }),
      svg("text", { x: 8, y: 41, class: "t3", text: `g=${fmt(n.g)}${f}` }));
      nodes.append(g);
      nodeEls.set(n.id, g);
    }
    const tree = svg("svg", { class: "tree" }, edges, nodes);
    clear(scroller, tree);
    st.els = { tree, nodeEls, edgeEls, size: [0, 0] };
    paint();
  }

  /** Lay out only the nodes visible at this step, so the tree stays compact as it grows. */
  function place(status) {
    const t = st.trace;
    const visible = (id) => status.has(id) && (st.showSkipped || !SKIPPED.has(status.get(id)));
    const { pos, width, height } = layoutTree(t.nodes, visible,
      { dx: NODE_W + GAP_X, dy: NODE_H + GAP_Y });
    const W = width - GAP_X + PAD * 2;
    const H = height - GAP_Y + PAD * 2;
    st.els.size = [W, H];
    st.els.tree.setAttribute("viewBox", `0 0 ${W} ${H}`);
    zoom(1);
    for (const [id, el] of st.els.nodeEls) {
      const p = pos.get(id);
      if (!p) continue;
      const appearing = el.classList.contains("hidden");
      if (appearing) el.style.transition = "none"; // new nodes appear in place
      el.style.transform = `translate(${p.x + PAD}px, ${p.y + PAD}px)`;
      if (appearing) {
        el.getBoundingClientRect(); // commit the position before re-enabling transitions
        el.style.transition = "";
      }
    }
    for (const [id, el] of st.els.edgeEls) {
      const p = pos.get(id);
      const q = pos.get(t.byId.get(id).parent);
      if (!p || !q) continue;
      const x1 = q.x + NODE_W + PAD;
      const y1 = q.y + NODE_H / 2 + PAD;
      const x2 = p.x + PAD;
      const y2 = p.y + NODE_H / 2 + PAD;
      const mx = (x1 + x2) / 2;
      el.setAttribute("d", `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`);
    }
    return pos;
  }

  function zoom(factor) {
    st.zoom = Math.max(0.3, Math.min(2.5, st.zoom * factor));
    if (!st.els) return;
    const [W, H] = st.els.size;
    st.els.tree.setAttribute("width", W * st.zoom);
    st.els.tree.setAttribute("height", H * st.zoom);
  }

  function paint() {
    const t = st.trace;
    if (!t || !st.els) return;
    const last = t.events.length - 1;
    const event = t.events[st.step];
    const status = replay(t.events, st.step, t.path, t.goal_node);
    const pos = place(status);
    for (const [id, el] of st.els.nodeEls) {
      const s = status.get(id);
      el.setAttribute("class", `node${pos.has(id) ? ` st-${s}` : " hidden"}`
        + `${id === st.selected ? " selected" : ""}`);
    }
    for (const [id, el] of st.els.edgeEls) {
      const node = t.byId.get(id);
      const s = status.get(id);
      const onPath = (s === "path" || s === "goal") && status.get(node.parent) === "path";
      const shown = pos.has(id) && pos.has(node.parent);
      el.setAttribute("class", `${shown ? "" : "hidden"}${onPath ? " on-path" : ""}`);
    }
    const expanded = t.events.slice(0, st.step + 1).filter((e) => e.kind === "expand").length;
    clear(statsRow,
      stat("Step", `${st.step + 1} / ${last + 1}`),
      stat("Expanded", expanded, "States taken off the frontier"),
      stat("Frontier", event.frontier, "States generated but not yet expanded"),
      stat("Explored", event.closed, "States already expanded (closed set)"));
    banner.className = `banner k-${event.kind}`;
    clear(banner, h("b", { text: `${KIND_ICON[event.kind]} ${event.kind.toUpperCase()}` }),
      h("span", { text: event.text }));
    scrub.value = String(st.step);
    playBtn.textContent = st.playing ? "⏸ Pause" : "▶ Play";

    const from = Math.max(0, st.step - 15);
    clear(log, t.events.slice(from, st.step + 1).reverse().map((e) => h("li", {
      class: e.step === st.step ? "now" : "", onclick: () => goto(e.step) },
    h("span", { class: "mono faint", text: String(e.step + 1) }),
    h("span", { text: `${KIND_ICON[e.kind]} ${e.text}` }))));

    renderDetail(status);
    if (st.step === last && t.goal_node !== null) {
      const others = ALGORITHMS.filter(([a]) => a !== t.algorithm)
        .map(([a, name]) => `${name} ${t.expanded_by_algorithm[a]}`).join(", ");
      clear(done, h("div", { class: "card celebrate" },
        `🎯 ${t.algorithm_name} found a ${t.plan.terms.length}-term plan (cost `
        + `${fmt(t.plan.stats.cost)}) after expanding ${t.plan.stats.expanded} states. `
        + `Same student with the other algorithms: ${others} expanded.`));
    } else clear(done);

    const focus = pos.get(event.node);
    if (st.follow && focus) reveal(focus);
  }

  /** Scroll only the tree box (never the page) so the node's final position is in view. */
  function reveal(p) {
    const margin = 40;
    const left = (p.x + PAD) * st.zoom;
    const top = (p.y + PAD) * st.zoom;
    const right = left + NODE_W * st.zoom;
    const bottom = top + NODE_H * st.zoom;
    const view = { l: scroller.scrollLeft, t: scroller.scrollTop,
      r: scroller.scrollLeft + scroller.clientWidth, b: scroller.scrollTop + scroller.clientHeight };
    if (left >= view.l + margin && right <= view.r - margin && top >= view.t + margin
      && bottom <= view.b - margin) return;
    scroller.scrollTo({ left: (left + right - scroller.clientWidth) / 2,
      top: (top + bottom - scroller.clientHeight) / 2, behavior: st.playing ? "auto" : "smooth" });
  }

  function renderDetail(status) {
    const t = st.trace;
    const id = st.selected ?? t.events[st.step].node;
    const n = t.byId.get(id);
    if (!n) {
      clear(detail, h("p", { class: "eyebrow", text: "Node" }),
        h("p", { class: "muted", text: "Click a node in the tree to inspect it." }));
      return;
    }
    const taken = [];
    for (let cur = n; cur && cur.parent !== null; cur = t.byId.get(cur.parent)) {
      taken.unshift(...cur.combo.map((c) => [c, cur.term]));
    }
    const s = status.get(id) || "not generated yet";
    clear(detail,
      h("p", { class: "eyebrow", text: st.selected === null ? "Current node" : "Selected node" }),
      h("h3", { text: `#${n.id} · ${n.title}` }),
      h("p", {}, h("span", { class: `status-pill st-${s}`, text: s })),
      h("div", { class: "stats compact" }, stat("g", fmt(n.g), "cost so far"),
        stat("h", fmt(n.h), "heuristic estimate of the remaining cost"),
        stat("f", n.h === null ? "–" : fmt(n.g + n.h), "g + h")),
      h("p", { class: "muted small", text: `Terms used: ${n.depth}. Courses planned on the `
        + "path to this node:" }),
      h("div", { class: "chip-row" }, taken.length ? taken.map(([c, term]) => h("span", {
        class: "done-code", title: term, text: c })) : h("span", { class: "muted",
        text: "none yet" })),
      st.selected === null ? null : h("button", { type: "button", class: "ghost-btn small",
        text: "Follow the current node", onclick: () => { st.selected = null; paint(); } }));
  }

  function select(id) {
    st.selected = id;
    paint();
  }

  // --- playback ---------------------------------------------------------------------

  function goto(step) {
    if (!st.trace) return;
    const last = st.trace.events.length - 1;
    st.step = Math.max(0, Math.min(last, step));
    if (st.step === last) stop();
    paint();
  }

  function play() {
    st.playing = true;
    st.timer = setInterval(() => {
      if (st.step >= st.trace.events.length - 1) { stop(); paint(); return; }
      st.step += 1;
      paint();
    }, st.delay);
    paint();
  }

  function stop() {
    st.playing = false;
    clearInterval(st.timer);
    st.timer = null;
  }

  function togglePlay() {
    if (!st.trace) return;
    if (st.playing) { stop(); paint(); return; }
    if (st.step >= st.trace.events.length - 1) st.step = 0;
    play();
  }

  document.addEventListener("keydown", (e) => {
    if (document.body.dataset.view !== "watch" || e.target.closest("input, textarea")) return;
    if (e.key === " " && e.target.closest("button")) return; // the button handles it
    const keys = { ArrowRight: () => goto(st.step + 1), ArrowLeft: () => goto(st.step - 1),
      Home: () => goto(0), End: () => goto(Infinity), " ": () => togglePlay() };
    if (keys[e.key]) { e.preventDefault(); keys[e.key](); }
  });

  let started = false;
  return {
    show() {
      if (!started) { started = true; load(); }
    },
  };
}
