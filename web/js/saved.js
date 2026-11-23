// Saved plans: everything stored in SQLite. Load one back into the planner, or delete it
// (rule log rows go with it via ON DELETE CASCADE).

import { api } from "./api.js";
import { clear, fmt, h, toast } from "./util.js";

const NAMES = { astar: "A*", ucs: "UCS", bfs: "BFS" };

export function init(ctx, root) {
  let confirming = null;
  const body = h("div", { class: "card" });
  clear(root,
    h("div", { class: "view-head" },
      h("div", {}, h("p", { class: "eyebrow", text: "Saved plans" }),
        h("h1", { text: "Plans you saved, straight from SQLite." }))),
    body);

  async function refresh() {
    try {
      render(await api.savedPlans());
    } catch (err) {
      toast(err.message, "error");
    }
  }

  function render(rows) {
    if (!rows.length) {
      clear(body, h("p", { class: "muted", text: "No saved plans yet. Use “Save this plan” "
        + "in the AI planner." }), h("button", { type: "button", class: "ghost-btn",
        text: "Go to the AI planner", onclick: () => ctx.go("planner") }));
      return;
    }
    const head = ["#", "Student", "Track", "Algorithm", "Max cr", "Terms", "Credits", "Cost",
      "Expanded", "Saved", ""];
    clear(body, h("div", { class: "table-wrap" }, h("table", { class: "saved" },
      h("thead", {}, h("tr", {}, head.map((x) => h("th", { text: x })))),
      h("tbody", {}, rows.map((r) => h("tr", {},
        h("td", { class: "mono", text: String(r.id) }),
        h("td", { text: r.profile_name }), h("td", { text: r.target_track }),
        h("td", { text: NAMES[r.algorithm] || r.algorithm }),
        h("td", { class: "mono", text: String(r.max_credits) }),
        h("td", { class: "mono", text: String(r.total_terms) }),
        h("td", { class: "mono", text: String(r.total_credits) }),
        h("td", { class: "mono", text: fmt(r.cost) }),
        h("td", { class: "mono", text: String(r.expanded) }),
        h("td", { class: "muted", text: r.created_at }),
        h("td", { class: "actions" },
          h("button", { type: "button", class: "ghost-btn small", text: "Load",
            onclick: () => load(r.id) }),
          confirming === r.id
            ? h("button", { type: "button", class: "danger-btn small", text: "Confirm delete",
              onclick: () => remove(r.id) })
            : h("button", { type: "button", class: "ghost-btn small", text: "Delete",
              onclick: () => { confirming = r.id; render(rows); } }))))))));
  }

  async function load(id) {
    try {
      const saved = await api.loadPlan(id);
      ctx.emit("load-saved", saved);
      toast(`Loaded saved plan #${id}.`, "ok");
    } catch (err) {
      toast(err.message, "error");
    }
  }

  async function remove(id) {
    try {
      await api.deletePlan(id);
      confirming = null;
      toast(`Deleted plan #${id}.`, "ok");
      refresh();
    } catch (err) {
      toast(err.message, "error");
    }
  }

  ctx.on("saved", refresh);
  return { show: () => { confirming = null; refresh(); } };
}
