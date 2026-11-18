import { h, link, note, plural, signOf, signed, table } from "../dom.js";
import { byIndexDesc } from "../model.js";
import { headlineColumns } from "./country.js";

const LABELS = ["positive", "neutral", "negative"];
const CSV_FIELDS = ["title", "source", "region", "published", "link", "sentiment", "index", "positive", "neutral", "negative"];
const FORMULA_START = /^[=+\-@\t\r]/;

function csvCell(value) {
  let text = value == null ? "" : String(value);
  if (typeof value === "string" && FORMULA_START.test(text)) text = `'${text}`;
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function downloadCsv(items, reg, takenAt) {
  const rows = items.map((item) => [
    item.title, item.source, reg.regionByKey.get(item.region)?.name ?? item.region, item.published, item.link,
    item.label, item.index, item.scores.positive, item.scores.neutral, item.scores.negative,
  ]);
  const text = [CSV_FIELDS, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n");
  const stamp = takenAt.slice(0, 16).replace(/[-:]/g, "").replace("T", "_");
  const url = URL.createObjectURL(new Blob(["\ufeff", text], { type: "text/csv;charset=utf-8" }));
  const anchor = h("a", { href: url, download: `news_sentiment_${stamp}.csv` });
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function chips(legend, options, selected, onChange) {
  return h(
    "fieldset",
    { class: "chips" },
    h("legend", {}, legend),
    options.map((o) =>
      h("label", {},
        h("input", {
          type: "checkbox", value: o.value, checked: selected.has(o.value),
          onchange: (event) => {
            if (event.target.checked) selected.add(o.value);
            else selected.delete(o.value);
            onChange();
          },
        }),
        h("span", { "data-label": o.label === o.value ? o.value : null }, o.label))),
  );
}

function extremes(title, items, reg) {
  return h(
    "section",
    { class: "extremes" },
    h("h3", {}, title),
    items.length
      ? h("ol", {}, items.map((item) =>
          h("li", {},
            h("span", { class: "badge", "data-sign": signOf(item.index, 0) }, signed(item.index, 0)),
            h("div", {}, link(item.title, item.link),
              h("p", { class: "caption" }, `${item.source}, ${reg.regionByKey.get(item.region)?.name ?? item.region}`)))))
      : h("p", { class: "caption" }, "No headlines match the filters."),
  );
}

export function render(root, { reg, snap, ui }) {
  const state = (ui.headlines ??= { regions: new Set(), labels: new Set(), query: "" });
  const slot = h("div", { class: "headline-results" });
  const filtered = () => {
    const query = state.query.trim().toLocaleLowerCase();
    return snap.headlines.filter((item) =>
      (!state.regions.size || state.regions.has(item.region)) &&
      (!state.labels.size || state.labels.has(item.label)) &&
      (!query || item.title.toLocaleLowerCase().includes(query)));
  };
  const update = () => {
    const shown = filtered();
    const ranked = [...shown].sort(byIndexDesc);
    slot.replaceChildren(
      h("div", { class: "extremes-pair" },
        extremes("Most positive", ranked.slice(0, 5), reg),
        extremes("Most negative", ranked.slice(-5).reverse(), reg)),
      h("div", { class: "table-head" },
        h("p", { class: "caption", "aria-live": "polite" }, `Showing ${shown.length} of ${plural(snap.headlines.length, "headline")}.`),
        h("button", { class: "button", type: "button", disabled: !shown.length, onclick: () => downloadCsv(shown, reg, snap.taken_at) },
          "Download CSV")),
      shown.length
        ? table(headlineColumns({ region: true }, reg), shown, { label: "Filtered headlines", className: "tall" })
        : note("No headline matches these filters. Clear a filter or change the search."),
    );
  };
  root.append(
    h("h2", { class: "view-title" }, "Headlines"),
    h(
      "div",
      { class: "controls filters" },
      chips("Region", reg.regions.map((r) => ({ value: r.key, label: r.name })), state.regions, update),
      chips("Sentiment", LABELS.map((l) => ({ value: l, label: l })), state.labels, update),
      h("label", { class: "field search" }, "Search titles",
        h("input", {
          type: "search", value: state.query, placeholder: "Filter headlines",
          oninput: (event) => { state.query = event.target.value; update(); },
        })),
    ),
    slot,
  );
  update();
}
