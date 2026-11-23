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

/** Stable identity of a focusable element, so focus can be put back after a re-render. */
function focusKey(el) {
  if (!el || el === document.body) return null;
  if (el.dataset?.key) return `key:${el.dataset.key}`;
  if (el.dataset?.code) return `code:${el.dataset.code}`;
  if (el.tagName === "INPUT") return `input:${el.type}:${el.getAttribute("aria-label") || el.placeholder || ""}`;
  return `${el.tagName}:${el.textContent.trim()}`;
}

/**
 * Run `render()` (which replaces children of `scope`) and move keyboard focus back to the
 * equivalent element afterwards; if it is gone or disabled, focus `fallback` instead.
 */
export function keepFocus(scope, render, fallback) {
  const active = document.activeElement;
  const inside = active && scope.contains(active) && active !== scope;
  const key = inside ? focusKey(active) : null;
  const selection = inside && active.tagName === "INPUT"
    ? [active.selectionStart, active.selectionEnd] : null;
  render();
  if (!key) return;
  const match = [...scope.querySelectorAll("button, input, [tabindex], a[href]")]
    .find((el) => focusKey(el) === key && !el.disabled);
  const target = match || (typeof fallback === "function" ? fallback() : fallback);
  if (!target) return;
  target.focus({ preventScroll: true });
  if (match && selection && match.setSelectionRange) {
    try { match.setSelectionRange(...selection); } catch { /* not a text input */ }
  }
}

/** Make a non-button element (e.g. an SVG group) operable with Enter and Space. */
export function pressable(el, label, onPress) {
  el.setAttribute("tabindex", "0");
  el.setAttribute("role", "button");
  el.setAttribute("aria-label", label);
  el.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPress(); }
  });
  return el;
}
