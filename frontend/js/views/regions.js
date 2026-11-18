import { sentimentScale } from "../colors.js";
import { h, note, percent, plural, signed } from "../dom.js";
import { loadWorld, regionShape, worldMap } from "../map.js";

const TONES = ["negative", "neutral", "positive"];

export function countryPicker(reg, selected, go) {
  const input = h("input", {
    id: "country-picker",
    type: "search",
    list: "country-names",
    autocomplete: "off",
    placeholder: `Type one of ${reg.countriesByName.length} country names`,
    value: selected?.name ?? "",
  });
  const message = h("p", { class: "caption", "aria-live": "polite" });
  const pick = () => {
    const wanted = input.value.trim().toLocaleLowerCase("en");
    if (!wanted) return;
    const match = reg.countriesByName.find((c) => c.name.toLocaleLowerCase("en") === wanted);
    if (match) go(`#/country/${match.iso3}`);
    else message.textContent = `No country called "${input.value.trim()}" is in this dashboard. Pick a name from the list.`;
  };
  input.addEventListener("input", (event) => {
    message.textContent = "";
    if (event.inputType === "insertReplacementText" || event.inputType === undefined) pick();
  });
  return h(
    "form",
    { class: "picker", onsubmit: (event) => { event.preventDefault(); pick(); } },
    h("label", { class: "field" }, "Find a country, or click one on the map", input),
    h("datalist", { id: "country-names" }, reg.countriesByName.map((c) => h("option", { value: c.name }))),
    message,
  );
}

export function regionFills(reg, snap) {
  const scale = sentimentScale(snap.mapBound);
  return (iso3) => {
    const region = reg.countryByIso.get(iso3)?.region;
    const summary = region && snap.regionByKey.get(region.key);
    return summary?.headlines ? scale(summary.index) : null;
  };
}

export function describeCountry(reg, snap) {
  return (iso3) => {
    const country = reg.countryByIso.get(iso3);
    if (!country) return null;
    const summary = snap.regionByKey.get(country.region.key);
    const reading = summary?.headlines ? `Region index ${signed(summary.index)}` : "No headlines from this region now";
    return [country.name, country.region.name, reading];
  };
}

function legend(snap, reg, scale) {
  const bound = snap.mapBound;
  const stops = d3.range(0, 1.0001, 0.1).map((t) => `${scale(-bound + t * 2 * bound)} ${t * 100}%`);
  const markers = [
    ...snap.regions.filter((r) => r.headlines).map((r) => ({ name: r.name, value: r.index })),
    ...(snap.globalIndex == null ? [] : [{ name: "All headlines", value: snap.globalIndex, global: true }]),
  ];
  const position = (value) => ((Math.max(-bound, Math.min(bound, value)) + bound) / (2 * bound)) * 100;
  const marks = markers.map((m) =>
    h(
      "div",
      { class: `legend-mark${m.global ? " is-global" : ""}`, style: `--x:${position(m.value)}%` },
      h("span", { class: "legend-text" }, `${m.name} ${signed(m.value)}`),
    ),
  );
  const track = h("div", { class: "legend-marks" }, marks);
  const root = h(
    "figure",
    { class: "legend" },
    track,
    h("div", { class: "legend-bar", style: `background:linear-gradient(90deg, ${stops.join(", ")})` }),
    h(
      "div",
      { class: "legend-ticks tabular" },
      h("span", {}, `${signed(-bound, 0)} negative`),
      h("span", {}, "0"),
      h("span", {}, `${signed(bound, 0)} positive`),
    ),
    h("figcaption", { class: "caption" }, `Colour scale runs from ${signed(-bound, 0)} to ${signed(bound, 0)}, the widest regional index or ±20, whichever is larger. Countries are filled with their region's index; grey means no headlines from that region.`),
  );
  new ResizeObserver(() => stackLabels(track, marks)).observe(track);
  return root;
}

function stackLabels(track, marks) {
  const width = track.clientWidth;
  if (!width) return;
  const rowEnds = [];
  const placed = marks
    .map((mark) => ({ mark, text: mark.firstChild, x: (parseFloat(mark.style.getPropertyValue("--x")) / 100) * width }))
    .sort((a, b) => a.x - b.x);
  for (const item of placed) {
    const w = item.text.offsetWidth;
    const left = Math.max(0, Math.min(width - w, item.x - w / 2));
    let row = rowEnds.findIndex((end) => end + 12 <= left);
    if (row === -1) row = rowEnds.push(0) - 1;
    rowEnds[row] = left + w;
    item.text.style.left = `${left - item.x}px`;
    item.mark.style.setProperty("--row", row);
  }
  track.style.setProperty("--rows", rowEnds.length);
}

function readout(region, summary, scale, baselineDays) {
  const scored = summary.headlines > 0;
  const delta = scored && summary.baseline != null ? summary.index - summary.baseline : null;
  return h(
    "article",
    { class: "readout" },
    h("h3", {}, h("span", { class: "swatch", style: scored ? `background:${scale(summary.index)}` : null, "aria-hidden": "true" }), region.name),
    h("p", { class: "readout-value tabular" }, scored ? signed(summary.index) : "\u2013"),
    delta != null &&
      h("p", { class: "readout-delta" },
        `${delta > 0 ? "Up" : delta < 0 ? "Down" : "Level"}${delta ? ` ${Math.abs(delta).toFixed(1)}` : ""} on its ${baselineDays}-day mean of ${signed(summary.baseline)}`),
    h("p", { class: "caption" }, `${plural(summary.headlines, "headline")} from ${plural(region.feeds.length, "outlet")}`),
    scored && [
      h("div", { class: "tone", "aria-hidden": "true" },
        TONES.map((tone) => h("span", { "data-label": tone, style: `width:${summary.shares[tone] * 100}%` }))),
      h("p", { class: "tone-text" }, TONES.map((tone) => h("span", { class: "label", "data-label": tone }, `${percent(summary.shares[tone])} ${tone}`))),
    ],
  );
}

export function render(root, ctx) {
  const { reg, snap, ui, go, alive } = ctx;
  const scale = sentimentScale(snap.mapBound);
  const selected = reg.countryByIso.get(ui.selectedCountry);
  const mapSlot = h("div", { class: "map-slot" });
  root.append(
    h("h2", { class: "visually-hidden" }, "Sentiment by region"),
    mapSlot,
    h("div", { class: "map-foot" }, legend(snap, reg, scale), countryPicker(reg, selected, go)),
    h("section", { class: "readouts", "aria-label": "Regions" },
      reg.regions.map((region) => readout(region, snap.regionByKey.get(region.key), scale, reg.baseline_days))),
    h("p", { class: "caption" }, "Tone mix is the share of each region's headlines the model labels negative, neutral or positive."),
  );

  loadWorld().then(
    (map) => {
      if (!alive()) return;
      const scored = reg.regions.filter((region) => snap.regionByKey.get(region.key)?.headlines);
      const firstPaint = !ui.mapPainted;
      ui.mapPainted = true;
      mapSlot.replaceChildren(
        worldMap(map, {
          fillFor: regionFills(reg, snap),
          describe: describeCountry(reg, snap),
          onSelect: (iso3) => go(`#/country/${iso3}`),
          selected: selected?.iso3,
          animate: firstPaint,
          labels: scored.map((region) => ({
            point: regionShape(map, region),
            name: region.name,
            value: signed(snap.regionByKey.get(region.key).index),
          })),
          label: `World map. ${reg.regions
            .map((r) => `${r.name} ${snap.regionByKey.get(r.key)?.headlines ? signed(snap.regionByKey.get(r.key).index) : "no headlines"}`)
            .join(", ")}.`,
        }),
      );
    },
    (error) => alive() && mapSlot.replaceChildren(note(error.message, "error")),
  );
}
