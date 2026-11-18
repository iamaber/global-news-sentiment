import { h, link, mean, note, plural, signOf, signed } from "../dom.js";

const badge = (value, text) => h("span", { class: "badge", "data-sign": signOf(value, 0) }, text);

function story(entry, reg, snap) {
  const items = entry.headlines.map((id) => snap.headlineById.get(id)).filter(Boolean);
  const lead = snap.headlineById.get(entry.lead) ?? items[0];
  const groups = reg.regions
    .filter((region) => entry.regions.includes(region.key))
    .map((region) => ({ region, items: items.filter((item) => item.region === region.key) }))
    .filter((group) => group.items.length);
  return h(
    "article",
    { class: "story" },
    h("h3", {}, link(lead.title, lead.link)),
    h("p", { class: "story-badges" }, groups.map(({ region, items: own }) => {
      const value = mean(own.map((item) => item.index));
      return badge(value, `${region.name} ${signed(value, 0)}`);
    })),
    h(
      "details",
      {},
      h("summary", {}, `${plural(items.length, "headline")} from ${plural(groups.length, "region")}`),
      groups.map(({ region, items: own }) =>
        h("section", { class: "story-region" },
          h("h4", {}, region.name),
          h("ul", {}, own.map((item) =>
            h("li", {}, badge(item.index, signed(item.index, 0)),
              h("div", {}, link(item.title, item.link), h("p", { class: "caption" }, item.source))))))),
    ),
  );
}

export function render(root, { reg, snap }) {
  root.append(h("h2", { class: "view-title" }, "Stories"));
  if (!snap.stories.length) {
    root.append(note("No story is covered by more than one region in this snapshot. Refresh later to check again."));
    return;
  }
  root.append(
    h("p", { class: "caption" },
      `${plural(snap.stories.length, "story", "stories")} covered by two or more regions. Headlines are grouped when their titles share most of their words, so a story told in very different words can show up split or not at all.`),
    h("div", { class: "stories" }, snap.stories.map((entry) => story(entry, reg, snap))),
  );
}
