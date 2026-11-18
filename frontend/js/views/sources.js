import { h, plural, table } from "../dom.js";

export function sourcesTable(sources, reg) {
  return table(
    [
      { label: "Region", cell: (s) => reg.regionByKey.get(s.region)?.name ?? s.region },
      { label: "Source", cell: (s) => s.source },
      { label: "Headlines", className: "num", cell: (s) => String(s.headlines) },
      { label: "Latency (s)", className: "num", cell: (s) => s.seconds.toFixed(2) },
      {
        label: "Status",
        cell: (s) => h("span", { class: "status", "data-ok": s.error == null }, s.error == null ? "OK" : s.error),
      },
    ],
    sources,
    { label: "Feed status" },
  );
}

export function render(root, { reg, snap }) {
  const online = snap.sources.filter((s) => s.error == null).length;
  root.append(
    h("h2", { class: "view-title" }, "Sources"),
    h("p", { class: "caption" }, `${online} of ${plural(snap.sources.length, "feed")} answered in this snapshot.`),
    sourcesTable(snap.sources, reg),
    h(
      "p",
      { class: "caption" },
      "Regions are assigned by where each outlet is based. Feeds are fetched over HTTPS from an allowlist with a 15 s overall deadline.",
    ),
  );
}
