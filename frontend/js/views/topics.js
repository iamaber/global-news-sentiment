import { sentimentScale, textOn } from "../colors.js";
import { h, mean, note, plural, signed, table } from "../dom.js";
import { byIndexDesc } from "../model.js";
import { headlineColumns } from "./country.js";

function heatmap(reg, tagged) {
  const cells = new Map();
  for (const item of tagged) {
    for (const topic of item.topics) {
      const key = `${item.region}|${topic}`;
      if (!cells.has(key)) cells.set(key, []);
      cells.get(key).push(item.index);
    }
  }
  const means = new Map([...cells].map(([key, values]) => [key, { mean: mean(values), count: values.length }]));
  const bound = Math.max(20, ...[...means.values()].map((c) => Math.abs(c.mean)));
  const scale = sentimentScale(bound);
  return h(
    "div",
    { class: "table-wrap", role: "region", "aria-label": "Sentiment by region and topic", tabindex: 0 },
    h(
      "table",
      { class: "heatmap" },
      h("thead", {}, h("tr", {}, h("td", {}), reg.topics.map((t) => h("th", { scope: "col" }, t.name)))),
      h("tbody", {}, reg.regions.map((region) =>
        h("tr", {}, h("th", { scope: "row" }, region.name), reg.topics.map((topic) => {
          const cell = means.get(`${region.key}|${topic.key}`);
          if (!cell) return h("td", { class: "empty" }, h("span", { class: "visually-hidden" }, "No headlines"));
          const fill = scale(cell.mean);
          return h("td", { style: `background:${fill};color:${textOn(fill)}` },
            h("strong", {}, signed(cell.mean, 0)), h("span", {}, plural(cell.count, "headline")));
        })))),
    ),
  );
}

function results(slot, reg, tagged, ui) {
  const topic = reg.topicByKey.get(ui.topic);
  const region = reg.regionByKey.get(ui.topicRegion);
  const shown = tagged
    .filter((item) => item.topics.includes(topic.key) && (!region || item.region === region.key))
    .sort(byIndexDesc);
  const where = region ? ` from ${region.name}` : "";
  slot.replaceChildren(
    ...(shown.length
      ? [
          h("p", { class: "caption" }, `${plural(shown.length, `${topic.name.toLowerCase()} headline`)}${where}, most positive first.`),
          table(headlineColumns({ region: true, sentiment: false }, reg), shown, { label: `${topic.name} headlines${where}` }),
        ]
      : [note(`No ${topic.name.toLowerCase()} headlines${where} right now.`)]),
  );
}

function select(label, options, current, onChange) {
  const control = h("select", { onchange: (event) => onChange(event.target.value) },
    options.map((o) => h("option", { value: o.value }, o.label)));
  control.value = current;
  return h("label", { class: "field" }, label, control);
}

export function render(root, { reg, snap, ui }) {
  const tagged = snap.headlines.filter((item) => item.topics.length > 0);
  root.append(
    h("h2", { class: "view-title" }, "Topics"),
    h("p", { class: "caption" },
      `${tagged.length} of ${plural(snap.headlines.length, "headline")} mention at least one topic. A headline can carry several topics.`),
  );
  if (!tagged.length) return;

  ui.topic ??= reg.topics[0].key;
  ui.topicRegion ??= "";
  const slot = h("div", { class: "topic-results" });
  const update = () => results(slot, reg, tagged, ui);
  root.append(
    h("h3", {}, "Sentiment by region and topic"),
    h("p", { class: "caption" }, "Each cell is the mean index of the region's headlines on that topic. Blank cells have no headlines."),
    heatmap(reg, tagged),
    h(
      "details",
      { class: "explainer" },
      h("summary", {}, "How topics are assigned"),
      h("dl", {}, reg.topics.map((t) => h("div", {}, h("dt", {}, t.name), h("dd", {}, t.keywords.join(", "))))),
      h("p", { class: "caption" },
        "A headline gets a topic when its title contains one of the topic's words. \u2026 stands for any ending. Acronyms and names match only in their exact case."),
    ),
    h("h3", {}, "Headlines by topic"),
    h(
      "div",
      { class: "controls" },
      select("Topic", reg.topics.map((t) => ({ value: t.key, label: t.name })), ui.topic, (v) => { ui.topic = v; update(); }),
      select("Region", [{ value: "", label: "All regions" }, ...reg.regions.map((r) => ({ value: r.key, label: r.name }))],
        ui.topicRegion, (v) => { ui.topicRegion = v; update(); }),
    ),
    slot,
  );
  update();
}
