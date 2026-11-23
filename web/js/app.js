// CoursePath front end: loads the knowledge base from the API, then routes between views.
// Each view module exports init(ctx, root) and returns { show() }.

import { api } from "./api.js";
import { clear, h, toast } from "./util.js";
import * as planner from "./planner.js";
import * as builder from "./builder.js";
import * as watch from "./watch.js";

const VIEWS = [
  ["planner", "AI planner", planner],
  ["build", "Build my plan", builder],
  ["watch", "Watch the search", watch],
];

function bus() {
  const handlers = new Map();
  return {
    on(name, fn) { (handlers.get(name) || handlers.set(name, []).get(name)).push(fn); },
    emit(name, data) { (handlers.get(name) || []).forEach((fn) => fn(data)); },
  };
}

async function main() {
  const [catalog, profiles] = await Promise.all([api.catalog(), api.profiles()]);
  const ctx = {
    catalog,
    byCode: new Map(catalog.map((c) => [c.code, c])),
    profiles,
    profileByName: new Map(profiles.map((p) => [p.name, p])),
    params: { profile: profiles[0].name, track: profiles[0].target_track, max_credits: 18,
      algorithm: "astar" },
    plan: null,
    ...bus(),
  };
  const main = document.getElementById("main");
  const nav = document.getElementById("nav");
  const views = new Map();
  VIEWS.forEach(([id, label, module], i) => {
    const root = h("section", { class: "view", id: `view-${id}` });
    main.append(root);
    const button = h("button", { type: "button", class: "step", dataset: { view: id },
      onclick: () => { location.hash = id; } }, h("b", { text: String(i + 1) }), label);
    nav.append(button);
    views.set(id, { root, button, view: module.init(ctx, root) });
  });
  ctx.go = (id) => { location.hash = id; };
  document.getElementById("loading").remove();

  const route = () => {
    const id = views.has(location.hash.slice(1)) ? location.hash.slice(1) : VIEWS[0][0];
    for (const [key, v] of views) {
      const active = key === id;
      v.root.classList.toggle("active", active);
      v.button.classList.toggle("active", active);
      v.button.setAttribute("aria-current", active ? "page" : "false");
    }
    views.get(id).view.show?.();
    document.body.dataset.view = id;
  };
  window.addEventListener("hashchange", route);
  route();
}

main().catch((err) => {
  clear(document.getElementById("main"), h("div", { class: "loading error" },
    "Could not reach the CoursePath API. Start it with ", h("code", { text: "make run" }),
    ". ", h("small", { text: err.message })));
  toast(err.message, "error");
});
