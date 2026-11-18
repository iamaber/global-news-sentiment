const PROPERTIES = new Set(["value", "checked"]);

export function h(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value == null || value === false) continue;
    if (typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (PROPERTIES.has(key)) node[key] = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  node.append(...children.flat(Infinity).filter((child) => child != null && child !== false));
  return node;
}

export function safeHref(url) {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
  } catch {
    return null;
  }
}

export function link(text, url) {
  const href = safeHref(url);
  if (!href) return h("span", {}, text);
  return h("a", { href, target: "_blank", rel: "noopener noreferrer" }, text);
}

export function signed(value, digits = 1) {
  const rounded = Number(value.toFixed(digits));
  if (rounded === 0) return (0).toFixed(digits);
  return (rounded > 0 ? "+" : "\u2212") + Math.abs(rounded).toFixed(digits);
}

export function signOf(value, digits = 1) {
  const rounded = Number(value.toFixed(digits));
  return rounded > 0 ? "positive" : rounded < 0 ? "negative" : "neutral";
}

export const percent = (share) => `${Math.round(share * 100)}%`;

export const plural = (n, one, many = `${one}s`) => `${n.toLocaleString("en")} ${n === 1 ? one : many}`;

export const mean = (values) => (values.length ? values.reduce((a, b) => a + b, 0) / values.length : null);

const DATE_TIME = new Intl.DateTimeFormat("en-US", {
  month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "UTC",
});
const TIME = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });

export const utcTime = (iso) => `${TIME.format(new Date(iso))} UTC`;
export const utcDateTime = (iso) => (iso ? DATE_TIME.format(new Date(iso)) : "");

export function indexValue(value, digits = 0) {
  return h(
    "span",
    { class: "ix", "data-sign": signOf(value, digits) },
    h("span", { class: "ix-num" }, signed(value, digits)),
    h("span", { class: "ix-bar", "aria-hidden": "true" },
      h("span", { style: `--v:${Math.max(-1, Math.min(1, value / 100))}` })),
  );
}

const LABELS = new Set(["negative", "neutral", "positive"]);

export function sentimentLabel(label) {
  return h("span", { class: "label", "data-label": LABELS.has(label) ? label : null }, label);
}

export function table(columns, rows, { label, className } = {}) {
  return h(
    "div",
    { class: `table-wrap ${className ?? ""}`, role: "region", "aria-label": label, tabindex: 0 },
    h(
      "table",
      {},
      h("thead", {}, h("tr", {}, columns.map((c) => h("th", { scope: "col", class: c.className }, c.label)))),
      h("tbody", {}, rows.map((row) => h("tr", {}, columns.map((c) => h("td", { class: c.className }, c.cell(row)))))),
    ),
  );
}

export function note(text, kind = "info") {
  return h("p", { class: `note note-${kind}` }, text);
}

export function segmented(name, options, current, onChange, label) {
  return h(
    "fieldset",
    { class: "segmented" },
    h("legend", {}, label),
    options.map((option) =>
      h(
        "label",
        {},
        h("input", {
          type: "radio", name, value: String(option.value), checked: option.value === current,
          onchange: () => onChange(option.value),
        }),
        h("span", {}, option.label),
      ),
    ),
  );
}
