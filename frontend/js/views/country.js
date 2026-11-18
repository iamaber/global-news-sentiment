import { describeError, getCached } from "../api.js";
import { lineChart, toDate } from "../chart.js";
import { regionStyle } from "../colors.js";
import { h, indexValue, link, mean, note, plural, segmented, sentimentLabel, signed, table, utcDateTime } from "../dom.js";
import { loadWorld, worldMap } from "../map.js";
import { countryPicker, describeCountry, regionFills } from "./regions.js";

export function headlineColumns({ region = false, sentiment = true } = {}, reg) {
  return [
    { label: "Headline", className: "title", cell: (item) => link(item.title, item.link) },
    { label: "Source", className: "nowrap", cell: (item) => item.source },
    region && { label: "Region", className: "nowrap", cell: (item) => reg.regionByKey.get(item.region)?.name ?? item.region },
    { label: "Published (UTC)", className: "nowrap tabular", cell: (item) => utcDateTime(item.published) },
    sentiment && { label: "Sentiment", cell: (item) => sentimentLabel(item.label) },
    { label: "Index", cell: (item) => indexValue(item.index) },
  ].filter(Boolean);
}

export function buildUp(count, origin) {
  return [
    note(`This chart builds up one day at a time. ${count} day(s) recorded so far; come back tomorrow.`),
    h("p", { class: "caption" }, `Source: ${origin}.`),
  ];
}

function history(slot, ctx, country, outlets) {
  const { reg, ui, alive } = ctx;
  const days = ui.countryDays;
  slot.replaceChildren(h("p", { class: "caption" }, "Loading the daily index."));
  getCached(`api/countries/${country.iso3}?days=${days}`).then(
    (data) => {
      if (!alive() || ui.countryDays !== days) return;
      if (data.points.length < 2) return slot.replaceChildren(...buildUp(data.points.length, data.origin));
      const style = regionStyle(reg, country.region.key);
      slot.replaceChildren(
        lineChart({
          series: [{
            name: country.name,
            color: style.color,
            points: data.points.map((p) => ({ date: toDate(p.day), value: p.value, note: plural(p.headlines, "headline") })),
          }],
          markers: true,
          label: `Daily sentiment index for ${outlets} over ${data.points.length} days, from ${signed(data.points[0].value)} to ${signed(data.points.at(-1).value)}.`,
        }),
        h("p", { class: "caption" },
          `${data.points.length} days, ${plural(data.points.reduce((sum, p) => sum + p.headlines, 0), "unique headline")}, ${data.origin}.`),
      );
    },
    (error) => alive() && slot.replaceChildren(note(describeError(error), "error")),
  );
}

export function render(root, ctx) {
  const { reg, ui, route, go, alive } = ctx;
  const country = reg.countryByIso.get(route.iso3);
  const back = h("p", {}, h("a", { href: "#/regions" }, "Back to the world map"));
  if (!country) {
    root.append(back, h("h2", { class: "view-title" }, "Country not found"),
      note(`No country with the code "${route.iso3}" is in this dashboard.`), countryPicker(reg, null, go));
    return;
  }
  ui.selectedCountry = country.iso3;
  ui.countryDays ??= 30;
  root.append(back, h("h2", { class: "country-name" }, country.name), h("p", { class: "caption" }, "Loading the outlets."));

  getCached(`api/countries/${country.iso3}?days=${ui.countryDays}`).then(
    (data) => alive() && renderCountry(root, ctx, country, data, back),
    (error) => alive() && root.replaceChildren(back, h("h2", { class: "country-name" }, country.name), note(describeError(error), "error")),
  );
}

function renderCountry(root, ctx, country, data, back) {
  const { reg, snap, ui, go, alive } = ctx;
  const region = country.region;
  const outlets = new Set(data.outlets);
  const shown = snap.headlines.filter((item) => outlets.has(item.source));
  const based = data.fallback ? 0 : data.outlets.length;
  const meanIndex = mean(shown.map((item) => item.index));
  const bySource = d3.group(shown, (item) => item.source);
  const locator = h("div", { class: "country-locator" });
  const historySlot = h("div", { class: "country-history" });
  const outletWord = data.fallback ? `the ${region.name} outlets` : data.outlets.join(", ");

  root.replaceChildren(
    back,
    h(
      "section",
      { class: "country-head" },
      h(
        "div",
        { class: "country-facts" },
        h("h2", { class: "country-name" }, country.name),
        h("p", { class: "country-meta" }, `${region.name}. ${plural(based, "outlet")} based here.`),
        data.fallback && note(`No outlet in this dashboard is based in ${country.name}. Showing the ${region.name} figures instead.`),
        h(
          "dl",
          { class: "figures-small tabular" },
          h("div", { class: "figure" }, h("dt", {}, "Sentiment index"), h("dd", {}, meanIndex == null ? "\u2013" : signed(meanIndex))),
          h("div", { class: "figure" }, h("dt", {}, "Headlines"), h("dd", {}, String(shown.length))),
          h("div", { class: "figure" }, h("dt", {}, "Outlets"), h("dd", {}, String(data.outlets.length))),
        ),
        countryPicker(reg, null, go),
      ),
      locator,
    ),
    h("h3", {}, "Outlets"),
    table(
      [
        { label: "Outlet", cell: (name) => name },
        { label: "Based in", cell: (name) => reg.feedCountry.get(name) ?? "" },
        { label: "Headlines now", className: "num", cell: (name) => String(bySource.get(name)?.length ?? 0) },
        {
          label: "Mean index",
          cell: (name) => {
            const items = bySource.get(name);
            return items ? indexValue(mean(items.map((item) => item.index))) : "\u2013";
          },
        },
      ],
      data.outlets,
      { label: "Outlets" },
    ),
    h("h3", {}, "Daily index"),
    segmented("country-window", reg.windows.map((d) => ({ value: d, label: `${d} days` })), ui.countryDays, (days) => {
      ui.countryDays = days;
      history(historySlot, ctx, country, outletWord);
    }, "Window"),
    historySlot,
    h("h3", {}, "Headlines now"),
    shown.length
      ? table(headlineColumns({}, reg), shown, { label: `Headlines from ${outletWord}` })
      : note(`None of ${outletWord} has a headline in this snapshot.`),
  );
  history(historySlot, ctx, country, outletWord);

  loadWorld().then((map) => {
    if (!alive()) return;
    locator.replaceChildren(worldMap(map, {
      focus: region,
      selected: country.iso3,
      fillFor: regionFills(reg, snap),
      describe: describeCountry(reg, snap),
      onSelect: (iso3) => go(`#/country/${iso3}`),
      label: `Map of ${region.name} with ${country.name} outlined.`,
    }));
  }, () => {});
}
