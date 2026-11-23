// Small DOM helpers shared by every view. No framework: h() builds elements, svg() builds
// SVG elements, and text is always set with textContent (never innerHTML).

const SVG_NS = "http://www.w3.org/2000/svg";

function apply(el, attrs) {
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") el.setAttribute("class", value);
    else if (key === "text") el.textContent = value;
    else if (key === "style" && typeof value === "object") Object.assign(el.style, value);
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, value);
  }
  return el;
}

function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function h(tag, attrs, ...children) {
  return append(apply(document.createElement(tag), attrs), children);
}

export function svg(tag, attrs, ...children) {
  return append(apply(document.createElementNS(SVG_NS, tag), attrs), children);
}

export function clear(el, ...children) {
  el.replaceChildren();
  return append(el, children);
}

let toastTimer;
export function toast(message, kind = "info") {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.className = `toast show ${kind}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = "toast"; }, 2600);
}

/** A row of toggle buttons; calls onChange(value) and marks the active one. */
export function segmented(options, value, onChange, { label, small } = {}) {
  const wrap = h("div", { class: `seg${small ? " small" : ""}`, role: "group",
    "aria-label": label });
  const buttons = options.map(([val, text, title]) => h("button", {
    type: "button", class: val === value ? "active" : "", title, dataset: { value: val },
    onclick: () => {
      buttons.forEach((b) => b.classList.toggle("active", b.dataset.value === val));
      onChange(val);
    },
  }, text));
  return append(wrap, buttons);
}

export const RULE_ICON = { OK: "✅", PRUNED: "⚠️", PREREQ: "🔒", OFFERING: "📅",
  CONFLICT: "❌", CREDIT_CAP: "❌", INFEASIBLE: "⛔" };

export const ALGORITHMS = [["astar", "A*"], ["ucs", "UCS"], ["bfs", "BFS"]];
export const TRACKS = [["ai", "AI"], ["systems", "Systems"], ["theory", "Theory"]];

export function fmt(x, digits = 2) {
  return x === null || x === undefined ? "–" : Number(x).toFixed(digits);
}

export function stat(label, value, hint) {
  return h("div", { class: "stat", title: hint }, h("span", { text: label }),
    h("b", { text: String(value) }));
}
