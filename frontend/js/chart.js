import { h, signed } from "./dom.js";

const HEIGHT = 300;
const LABEL_ROOM = 180;
const WIDE = 560;
const dayLabel = d3.utcFormat("%b %-d");

export const toDate = (day) => new Date(`${day}T00:00:00Z`);

export function lineChart({ series, label, format = (v) => signed(v), markers = false }) {
  const days = [...new Set(series.flatMap((s) => s.points.map((p) => +p.date)))].sort((a, b) => a - b).map((t) => new Date(t));
  const values = series.flatMap((s) => s.points.map((p) => p.value));
  const plot = h("div", { class: "chart-plot", tabindex: 0, role: "img", "aria-label": label });
  const tip = h("div", { class: "map-tip chart-tip", hidden: true });
  const key = series.length > 1 &&
    h("ul", { class: "chart-key" }, series.map((s) =>
      h("li", {}, keySwatch(s), s.name)));
  const root = h("figure", { class: "chart" }, h("div", { class: "chart-frame" }, plot, tip), key);
  let active = null;
  let geometry;

  const draw = () => {
    const width = plot.clientWidth;
    if (!width) return;
    const wide = width >= WIDE && series.length > 1;
    if (key) key.hidden = wide;
    const margin = { top: 14, right: wide ? LABEL_ROOM : 14, bottom: 28, left: 44 };
    const x = d3.scaleUtc(d3.extent(days), [margin.left, width - margin.right]);
    const y = d3.scaleLinear([Math.min(0, d3.min(values)), Math.max(0, d3.max(values))], [HEIGHT - margin.bottom, margin.top]).nice();
    const [low, high] = y.domain();
    const tickDigits = high - low < 10 ? 1 : 0;
    const stride = Math.ceil(days.length / Math.max(2, Math.floor((width - margin.left - margin.right) / 90)));
    geometry = { x, y, margin, width };

    const svg = d3.create("svg").attr("viewBox", `0 0 ${width} ${HEIGHT}`).attr("width", width).attr("height", HEIGHT).attr("aria-hidden", "true");
    svg.append("g").attr("class", "axis").attr("transform", `translate(0,${HEIGHT - margin.bottom})`)
      .call(d3.axisBottom(x).tickValues(days.filter((_, i) => i % stride === 0)).tickFormat(dayLabel).tickSizeOuter(0));
    svg.append("g").attr("class", "axis axis-y").attr("transform", `translate(${margin.left},0)`)
      .call(d3.axisLeft(y).ticks(5).tickFormat((v) => signed(v, tickDigits)).tickSize(-(width - margin.left - margin.right)))
      .call((g) => g.select(".domain").remove());
    svg.append("line").attr("class", "zero").attr("x1", margin.left).attr("x2", width - margin.right).attr("y1", y(0)).attr("y2", y(0));

    const line = d3.line().x((p) => x(p.date)).y((p) => y(p.value)).curve(d3.curveMonotoneX);
    for (const s of series) {
      svg.append("path").attr("class", "series").attr("d", line(s.points))
        .style("stroke", s.color).attr("stroke-dasharray", s.dash || null);
      if (markers) {
        svg.append("g").selectAll("circle").data(s.points).join("circle")
          .attr("class", "marker").attr("r", 3).attr("cx", (p) => x(p.date)).attr("cy", (p) => y(p.value)).style("fill", s.color);
      }
    }
    if (wide) {
      const ends = series.filter((s) => s.points.length).map((s) => {
        const last = s.points.at(-1);
        return { s, x: x(last.date), y: y(last.value), lineY: y(last.value) };
      }).sort((a, b) => a.y - b.y);
      for (let i = 1; i < ends.length; i++) ends[i].y = Math.max(ends[i].y, ends[i - 1].y + 17);
      const labels = svg.append("g").selectAll("g").data(ends).join("g").attr("class", "end-label");
      labels.append("path").attr("d", (d) => `M${d.x + 3},${d.lineY}L${d.x + 10},${d.y}h18`)
        .style("stroke", (d) => d.s.color).attr("stroke-dasharray", (d) => d.s.dash || null);
      labels.append("text").attr("x", (d) => d.x + 32).attr("y", (d) => d.y).attr("dy", "0.35em").text((d) => d.s.name);
    }
    svg.append("g").attr("class", "focus");
    plot.replaceChildren(svg.node());
    show(active);
  };

  const show = (index) => {
    active = index;
    const focus = d3.select(plot).select(".focus");
    focus.selectAll("*").remove();
    if (index == null || !geometry) { tip.hidden = true; return; }
    const { x, y, margin } = geometry;
    const day = days[index];
    const at = x(day);
    focus.append("line").attr("class", "rule").attr("x1", at).attr("x2", at).attr("y1", margin.top).attr("y2", HEIGHT - margin.bottom);
    const rows = series.map((s) => ({ s, p: s.points.find((p) => +p.date === +day) })).filter((r) => r.p);
    focus.selectAll("circle").data(rows).join("circle").attr("r", 4.5).attr("cx", at).attr("cy", (r) => y(r.p.value)).style("fill", (r) => r.s.color);
    tip.replaceChildren(
      h("strong", {}, dayLabel(day)),
      ...rows.map((r) => h("span", {}, `${series.length > 1 ? `${r.s.name} ` : ""}${format(r.p.value)}${r.p.note ? `, ${r.p.note}` : ""}`)),
    );
    tip.hidden = false;
    const flip = at > geometry.width / 2;
    tip.classList.toggle("flip", flip);
    tip.style.left = `${flip ? at - 12 : at + 12}px`;
    tip.style.top = `${margin.top}px`;
  };

  const nearest = (event) => {
    const [px] = d3.pointer(event, plot);
    const t = geometry.x.invert(px);
    return d3.leastIndex(days, (d) => Math.abs(d - t));
  };
  plot.addEventListener("pointermove", (event) => geometry && show(nearest(event)));
  plot.addEventListener("pointerleave", () => show(null));
  plot.addEventListener("blur", () => show(null));
  plot.addEventListener("keydown", (event) => {
    const step = { ArrowLeft: -1, ArrowRight: 1 }[event.key];
    if (event.key === "Escape") return show(null);
    if (!step) return;
    event.preventDefault();
    show(active == null ? (step > 0 ? 0 : days.length - 1) : Math.max(0, Math.min(days.length - 1, active + step)));
  });
  new ResizeObserver(draw).observe(plot);
  return root;
}

function keySwatch(s) {
  const svg = d3.create("svg").attr("width", 28).attr("height", 10).attr("aria-hidden", "true");
  svg.append("line").attr("x1", 0).attr("x2", 28).attr("y1", 5).attr("y2", 5)
    .attr("stroke-dasharray", s.dash || null).style("stroke", s.color).attr("stroke-width", 2.5);
  return svg.node();
}
