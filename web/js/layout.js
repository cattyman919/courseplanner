// Pure helpers (no DOM): replaying a recorded search and laying out graphs as SVG
// coordinates. Kept separate so they can be unit-tested with `node --test`.

/** Node statuses after replaying events[0..step], mirroring reasoning.trace.statuses_at. */
export function replay(events, step, path, goalNode) {
  const status = new Map();
  for (const event of events.slice(0, step + 1)) {
    if (event.node === null || event.node === undefined) continue;
    for (const [id, s] of status) if (s === "current") status.set(id, "expanded");
    status.set(event.node, event.status);
  }
  if (goalNode !== null && status.get(goalNode) === "goal") {
    for (const id of path) if (id !== goalNode) status.set(id, "path");
  }
  return status;
}

/**
 * Left-to-right tidy tree: x by depth, leaves get consecutive rows, a parent sits at the
 * middle of its children. `nodes` is [{id, parent, depth}], `keep(id)` filters nodes.
 */
export function layoutTree(nodes, keep = () => true, { dx = 200, dy = 54 } = {}) {
  const kids = new Map();
  const shown = nodes.filter((n) => keep(n.id));
  const ids = new Set(shown.map((n) => n.id));
  for (const n of shown) {
    if (n.parent !== null && ids.has(n.parent)) {
      if (!kids.has(n.parent)) kids.set(n.parent, []);
      kids.get(n.parent).push(n.id);
    }
  }
  const pos = new Map();
  let row = 0;
  let maxDepth = 0;
  const place = (id, depth) => {
    maxDepth = Math.max(maxDepth, depth);
    const children = kids.get(id) || [];
    let y;
    if (!children.length) y = row++;
    else {
      const ys = children.map((c) => place(c, depth + 1));
      y = (ys[0] + ys[ys.length - 1]) / 2;
    }
    pos.set(id, { x: depth * dx, y: y * dy });
    return y;
  };
  for (const n of shown) if (n.parent === null || !ids.has(n.parent)) place(n.id, 0);
  return { pos, width: (maxDepth + 1) * dx, height: Math.max(row, 1) * dy };
}

/** Longest prerequisite chain below each course (0 for courses with no prerequisites). */
export function prereqDepth(courses) {
  const byCode = new Map(courses.map((c) => [c.code, c]));
  const memo = new Map();
  const depth = (code) => {
    if (memo.has(code)) return memo.get(code);
    const c = byCode.get(code);
    const d = c && c.prereqs.length
      ? 1 + Math.max(...c.prereqs.filter((p) => byCode.has(p)).map(depth)) : 0;
    memo.set(code, d);
    return d;
  };
  courses.forEach((c) => depth(c.code));
  return memo;
}

/** Layered DAG layout: columns by prerequisite depth, rows ordered by barycenter. */
export function layoutDag(courses, { dx = 170, dy = 58 } = {}) {
  const depth = prereqDepth(courses);
  const layers = [];
  for (const c of courses) (layers[depth.get(c.code)] ||= []).push(c);
  const row = new Map();
  layers.forEach((layer, i) => {
    const order = (c) => {
      if (i === 0 || !c.prereqs.length) return Number.MAX_SAFE_INTEGER / 2 + row.size;
      const ys = c.prereqs.map((p) => row.get(p) ?? 0);
      return ys.reduce((a, b) => a + b, 0) / ys.length;
    };
    if (i === 0) layer.sort((a, b) => a.category.localeCompare(b.category)
      || a.code.localeCompare(b.code));
    else layer.sort((a, b) => order(a) - order(b) || a.code.localeCompare(b.code));
    layer.forEach((c, j) => row.set(c.code, j));
  });
  const tallest = Math.max(...layers.map((l) => l.length));
  const pos = new Map();
  layers.forEach((layer, i) => layer.forEach((c, j) => {
    const offset = (tallest - layer.length) / 2;
    pos.set(c.code, { x: i * dx, y: (j + offset) * dy });
  }));
  return { pos, width: layers.length * dx, height: tallest * dy };
}

/** Every course reachable by following `next(code)` links (excluding the start). */
export function closure(code, next) {
  const seen = new Set();
  const stack = [...next(code)];
  while (stack.length) {
    const c = stack.pop();
    if (seen.has(c)) continue;
    seen.add(c);
    stack.push(...next(c));
  }
  return seen;
}
