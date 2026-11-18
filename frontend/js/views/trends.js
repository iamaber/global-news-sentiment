import { describeError, getCached } from "../api.js";
import { lineChart, toDate } from "../chart.js";
import { regionStyle } from "../colors.js";
import { h, link, note, plural, segmented, signed } from "../dom.js";
import { buildUp } from "./country.js";

const WEEK_MS = 7 * 24 * 3600 * 1000;

function rolling(points) {
  return points.map((point, i) => {
    const window = points.slice(0, i + 1).filter((p) => p.date - point.date > -WEEK_MS);
    return { ...point, value: window.reduce((sum, p) => sum + p.value, 0) / window.length };
  });
}

function seriesByRegion(reg, points, smooth, count) {
  return reg.regions
    .map((region) => {
      const own = points
        .filter((p) => p.region === region.key)
        .map((p) => ({ date: toDate(p.day), value: p.value, note: plural(p[count], count.slice(0, -1)) }))
        .sort((a, b) => a.date - b.date);
      return { name: region.name, ...regionStyle(reg, region.key), points: smooth ? rolling(own) : own };
    })
    .filter((s) => s.points.length);
}

function gdelt(slot, data, ctx) {
  if (!data.points.length) {
    return slot.replaceChildren(note("No GDELT tone to show for this window."), h("p", { class: "caption" }, `Source: ${data.origin}.`));
  }
  const series = seriesByRegion(ctx.reg, data.points, ctx.ui.smooth, "articles");
  slot.replaceChildren(
    lineChart({ series, format: (v) => signed(v, 2), label: `GDELT event tone by region over ${ctx.ui.trendDays} days.` }),
    h(
      "p",
      { class: "caption" },
      "Daily average tone of the news coverage of events whose main actor is from each region's countries, weighted by article count, from the ",
      link("GDELT Project", "https://www.gdeltproject.org/"),
      "'s daily event files. It covers news about the region's actors from outlets worldwide, so it differs from our model's index below, which scores the outlets based in each region. Lexicon-based and typically negative; compare regions and direction rather than absolute level. ",
      `Updated daily; ${data.origin}.`,
    ),
  );
}

function model(slot, data, ctx) {
  const days = new Set(data.points.map((p) => p.day)).size;
  if (days < 2) return slot.replaceChildren(...buildUp(days, data.origin));
  const series = seriesByRegion(ctx.reg, data.points, ctx.ui.smooth, "headlines");
  const headlines = data.points.reduce((sum, p) => sum + p.headlines, 0);
  slot.replaceChildren(
    lineChart({ series, label: `Model sentiment index by region over ${days} days.` }),
    h("p", { class: "caption" }, `${days} days, ${plural(headlines, "unique headline")}, ${data.origin}.`),
  );
}

function load(slot, source, draw, ctx) {
  const days = ctx.ui.trendDays;
  slot.replaceChildren(h("p", { class: "caption" }, "Loading."));
  getCached(`api/trends?days=${days}&source=${source}`).then(
    (data) => ctx.alive() && ctx.ui.trendDays === days && draw(slot, data, ctx),
    (error) => ctx.alive() && slot.replaceChildren(note(describeError(error), "error")),
  );
}

export function render(root, ctx) {
  const { reg, ui } = ctx;
  ui.trendDays ??= 30;
  ui.smooth ??= true;
  const gdeltSlot = h("div", { class: "trend" });
  const modelSlot = h("div", { class: "trend" });
  const update = () => {
    load(gdeltSlot, "gdelt", gdelt, ctx);
    load(modelSlot, "model", model, ctx);
  };
  root.append(
    h("h2", { class: "view-title" }, "Trends"),
    h(
      "div",
      { class: "controls" },
      segmented("trend-window", reg.windows.map((d) => ({ value: d, label: `${d} days` })), ui.trendDays,
        (days) => { ui.trendDays = days; update(); }, "Window"),
      h("label", { class: "toggle" },
        h("input", { type: "checkbox", checked: ui.smooth, onchange: (event) => { ui.smooth = event.target.checked; update(); } }),
        h("span", {}, "7-day smoothing")),
    ),
    h("h3", {}, "GDELT event tone by region"),
    gdeltSlot,
    h("h3", {}, "Model sentiment index by region"),
    modelSlot,
  );
  update();
}
