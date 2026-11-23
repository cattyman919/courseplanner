// Unit tests for the pure front-end helpers. Run: node --test tests/web/*.mjs
import assert from "node:assert/strict";
import { test } from "node:test";
import { closure, layoutDag, layoutTree, prereqDepth, replay } from "../../web/js/layout.js";

const events = [
  { node: 0, status: "frontier" },
  { node: 0, status: "current" },
  { node: 1, status: "frontier" },
  { node: 2, status: "skipped" },
  { node: 1, status: "current" },
  { node: 1, status: "goal" },
];

test("replay demotes the previous current node to expanded", () => {
  assert.equal(replay(events, 1, [0, 1], 1).get(0), "current");
  const s = replay(events, 2, [0, 1], 1);
  assert.equal(s.get(0), "expanded"); // any later event ends the expansion step
  assert.equal(s.get(1), "frontier");
  const later = replay(events, 4, [0, 1], 1);
  assert.equal(later.get(0), "expanded");
  assert.equal(later.get(1), "current");
  assert.equal(later.get(2), "skipped");
});

test("replay marks the solution path once the goal is reached", () => {
  const s = replay(events, 5, [0, 1], 1);
  assert.deepEqual([s.get(0), s.get(1)], ["path", "goal"]);
  assert.equal(replay(events, 4, [0, 1], 1).get(0), "expanded");
});

test("events without a node are ignored", () => {
  const s = replay([...events.slice(0, 2), { node: null, status: null }], 2, [], null);
  assert.equal(s.size, 1);
});

test("layoutTree puts children right of parents and centres parents", () => {
  const nodes = [{ id: 0, parent: null }, { id: 1, parent: 0 }, { id: 2, parent: 0 },
    { id: 3, parent: 1 }];
  const { pos, width, height } = layoutTree(nodes, () => true, { dx: 100, dy: 10 });
  assert.equal(pos.get(1).x, 100);
  assert.equal(pos.get(3).x, 200);
  assert.equal(pos.get(0).y, (pos.get(1).y + pos.get(2).y) / 2);
  assert.deepEqual([width, height], [300, 20]);
});

test("layoutTree skips filtered nodes and their subtrees", () => {
  const nodes = [{ id: 0, parent: null }, { id: 1, parent: 0 }, { id: 2, parent: 1 }];
  const { pos } = layoutTree(nodes, (id) => id !== 1);
  assert.ok(pos.has(0) && !pos.has(1));
  assert.ok(pos.has(2)); // orphaned nodes become their own roots
});

const courses = [
  { code: "A", prereqs: [], category: "core" },
  { code: "B", prereqs: ["A"], category: "core" },
  { code: "C", prereqs: ["B", "A"], category: "core" },
  { code: "D", prereqs: [], category: "math" },
];

test("prereqDepth is the longest chain below a course", () => {
  const d = prereqDepth(courses);
  assert.deepEqual([d.get("A"), d.get("B"), d.get("C"), d.get("D")], [0, 1, 2, 0]);
});

test("layoutDag puts each course in its depth column", () => {
  const { pos } = layoutDag(courses, { dx: 10, dy: 10 });
  assert.deepEqual(["A", "B", "C", "D"].map((c) => pos.get(c).x), [0, 10, 20, 0]);
});

test("closure follows links transitively", () => {
  const prereqs = new Map(courses.map((c) => [c.code, c.prereqs]));
  assert.deepEqual([...closure("C", (c) => prereqs.get(c))].sort(), ["A", "B"]);
  assert.equal(closure("A", (c) => prereqs.get(c)).size, 0);
});
