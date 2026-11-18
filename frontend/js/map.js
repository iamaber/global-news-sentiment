import { h } from "./dom.js";

const WIDTH = 960;
const FOCUS_HEIGHT = 560;
let world;

export function loadWorld() {
  world ??= fetch("data/world-110m.json")
    .then((response) => {
      if (!response.ok) throw new Error(`The map outline failed to load (status ${response.status}).`);
      return response.json();
    })
    .then((topo) => {
      const geometries = topo.objects.countries.geometries.filter((g) => g.id !== "ATA");
      const features = geometries.map((g) => topojson.feature(topo, g));
      return { topo, geometries, features, all: { type: "FeatureCollection", features } };
    });
  world.catch(() => { world = undefined; });
  return world;
}

export function regionShape(map, region) {
  const isos = new Set(region.countries.map((c) => c.iso3));
  return topojson.merge(map.topo, map.geometries.filter((g) => isos.has(g.id)));
}

export function worldMap(map, { fillFor, describe, onSelect, selected, focus, labels = [], label, animate }) {
  const target = focus ? regionShape(map, focus) : map.all;
  const projection = d3.geoEqualEarth();
  let height = FOCUS_HEIGHT;
  if (focus) {
    projection.rotate([-d3.geoCentroid(target)[0], 0]);
    projection.fitExtent([[24, 24], [WIDTH - 24, height - 24]], target);
  } else {
    projection.fitWidth(WIDTH, target);
    const [[, top], [, bottom]] = d3.geoPath(projection).bounds(target);
    height = Math.ceil(bottom - top);
    projection.fitSize([WIDTH, height], target);
  }
  const path = d3.geoPath(projection);

  const tooltip = h("div", { class: "map-tip", role: "presentation", hidden: true });
  const svg = d3
    .create("svg")
    .attr("viewBox", `0 0 ${WIDTH} ${height}`)
    .attr("role", "img")
    .attr("aria-label", label);
  svg.append("path").attr("class", "graticule").attr("d", path(d3.geoGraticule10())).attr("aria-hidden", "true");

  const container = h("div", { class: `map${focus ? " map-focus" : ""}` }, svg.node(), tooltip);
  const showTip = (event, iso3) => {
    const lines = describe(iso3);
    if (!lines) return hideTip();
    tooltip.replaceChildren(...lines.map((line, i) => h(i ? "span" : "strong", {}, line)));
    tooltip.hidden = false;
    const box = container.getBoundingClientRect();
    const x = event.clientX - box.left;
    const flip = x > box.width - 200;
    tooltip.style.left = `${flip ? x - 12 : x + 12}px`;
    tooltip.style.top = `${event.clientY - box.top + 12}px`;
    tooltip.classList.toggle("flip", flip);
  };
  const hideTip = () => { tooltip.hidden = true; };

  const countries = svg
    .append("g")
    .attr("aria-hidden", "true")
    .selectAll("path")
    .data(map.features)
    .join("path")
    .attr("d", path)
    .attr("class", (f) => (describe(f.id) ? "country" : "country inert"))
    .classed("is-selected", (f) => selected != null && f.id === selected)
    .on("pointermove", (event, f) => showTip(event, f.id))
    .on("pointerleave", hideTip)
    .on("click", (_, f) => describe(f.id) && onSelect(f.id));

  const paint = (selection) => selection.style("fill", (f) => fillFor(f.id));
  if (animate && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    countries.classed("filling", true);
    requestAnimationFrame(() => requestAnimationFrame(() => paint(countries)));
  } else {
    paint(countries);
  }
  countries.filter(".is-selected").raise();

  container.append(
    ...labels.map(({ point, name, value }) => {
      const [x, y] = path.centroid(point);
      return h(
        "div",
        { class: "map-label", "aria-hidden": "true", style: `left:${(x / WIDTH) * 100}%;top:${(y / height) * 100}%` },
        h("span", {}, name),
        h("strong", {}, value),
      );
    }),
  );
  return container;
}
