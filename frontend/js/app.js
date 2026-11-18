import { clearCache, describeError, getJson } from "./api.js";
import { h, percent, plural, signed, utcTime } from "./dom.js";
import { indexRegistry, indexSnapshot } from "./model.js";
import * as country from "./views/country.js";
import * as regions from "./views/regions.js";
import * as sources from "./views/sources.js";

const VIEWS = {
  regions: regions.render,
  country: country.render,
  sources: sources.render,
};
const DEFAULT_VIEW = Object.keys(VIEWS)[0];

const state = { reg: null, snap: null, error: null, reloadError: null, reloading: false, ui: {} };
const $ = (id) => document.getElementById(id);
let renderToken = 0;

function parseRoute() {
  const [view, arg] = location.hash.replace(/^#\/?/, "").split("/");
  if (view === "country" && arg && VIEWS.country) return { view, nav: "regions", iso3: arg.toUpperCase() };
  return VIEWS[view] ? { view, nav: view } : { view: DEFAULT_VIEW, nav: DEFAULT_VIEW };
}

function renderCaption() {
  const { reg, snap } = state;
  if (!reg) return;
  let text = `${reg.outletCount} outlets in ${reg.regions.length} regions, scored with ${reg.model.name}.`;
  if (snap) text += ` Snapshot taken ${utcTime(snap.taken_at)}; ${plural(snap.newly_scored, "headline")} newly scored.`;
  $("caption").textContent = text;
}

function figure(label, value, help) {
  return h("div", { class: "figure" }, h("dt", {}, label), h("dd", {}, value), help && h("p", { class: "figure-help" }, help));
}

function renderFigures() {
  const { snap } = state;
  const root = $("figures");
  if (!snap) return root.replaceChildren();
  const count = (label) => snap.headlines.filter((item) => item.label === label).length / (snap.headlines.length || 1);
  const online = snap.sources.filter((s) => s.error == null).length;
  root.replaceChildren(
    h(
      "dl",
      {},
      h(
        "div",
        { class: "figure figure-lead" },
        h("dt", {}, "Global sentiment index"),
        h("dd", {}, snap.globalIndex == null ? "\u2013" : signed(snap.globalIndex)),
        h("p", { class: "figure-help" }, "Mean of P(positive) \u2212 P(negative) per headline, scaled to \u2212100\u2026+100."),
      ),
      figure("Headlines", snap.headlines.length.toLocaleString("en")),
      figure("Positive", percent(count("positive"))),
      figure("Negative", percent(count("negative"))),
      figure("Sources online", `${online}/${snap.sources.length}`),
    ),
  );
}

function renderAlerts() {
  const { reg, snap } = state;
  const root = $("alerts");
  const alerts = snap?.alerts ?? [];
  root.hidden = alerts.length === 0;
  root.replaceChildren(
    ...alerts.map((alert) => {
      const rising = alert.z > 0;
      return h(
        "p",
        { class: "alert", "data-direction": rising ? "up" : "down" },
        h("span", { class: "alert-tag" }, h("span", { "aria-hidden": "true" }, rising ? "\u25B2 " : "\u25BC "), rising ? "Rising" : "Falling"),
        h(
          "span",
          {},
          h("strong", {}, reg.regionByKey.get(alert.region)?.name ?? alert.region),
          ` sentiment is ${signed(alert.today)} today, ${rising ? "above" : "below"} its ${reg.baseline_days}-day mean of ${signed(alert.mean)} (${signed(alert.z)} standard deviations).`,
        ),
      );
    }),
  );
}

function renderNav(route) {
  for (const anchor of document.querySelectorAll(".views a")) {
    if (anchor.dataset.view === route.nav) anchor.setAttribute("aria-current", "page");
    else anchor.removeAttribute("aria-current");
  }
}

function loadingPanel() {
  const outlets = state.reg ? plural(state.reg.outletCount, "outlet") : "every outlet";
  return h(
    "div",
    { class: "panel loading", role: "status" },
    h("span", { class: "loading-bar", "aria-hidden": "true" }),
    h("p", { class: "panel-title" }, `Fetching and scoring headlines from ${outlets}.`),
    h("p", { class: "caption" }, "The first run after the server starts downloads the sentiment model and can take a minute."),
  );
}

function errorPanel(error) {
  const feeds = Array.isArray(error.body?.sources) ? error.body.sources : null;
  return h(
    "div",
    { class: "panel panel-error", role: "alert" },
    h("p", { class: "panel-title" }, "Could not build a snapshot."),
    h("p", {}, describeError(error)),
    feeds && state.reg && [
      h("p", {}, "Every feed below failed. The app needs outbound HTTPS access to them."),
      sources.sourcesTable(feeds, state.reg),
    ],
    h("button", { class: "button", type: "button", onclick: () => (state.reg ? loadSnapshot() : boot()) }, "Try again"),
  );
}

function renderView() {
  const route = parseRoute();
  const token = ++renderToken;
  const main = $("view");
  renderNav(route);
  main.replaceChildren();
  if (state.reloadError) {
    main.append(h("p", { class: "note note-error", role: "alert" },
      `Reload failed: ${describeError(state.reloadError)} Showing the snapshot from ${utcTime(state.snap.taken_at)}.`));
  }
  if (!state.snap) {
    main.append(state.error ? errorPanel(state.error) : loadingPanel());
    return;
  }
  VIEWS[route.view](main, {
    ...state,
    route,
    alive: () => token === renderToken,
    go: (hash) => { location.hash = hash; },
  });
}

function render() {
  renderCaption();
  renderFigures();
  renderAlerts();
  renderView();
  const button = $("reload");
  button.disabled = state.reloading || !state.reg;
  button.textContent = state.reloading ? (state.snap ? "Reloading\u2026" : "Loading\u2026") : "Reload snapshot";
}

async function loadSnapshot() {
  state.reloading = true;
  state.error = null;
  state.reloadError = null;
  render();
  try {
    const snapshot = await getJson("api/snapshot");
    clearCache();
    state.snap = indexSnapshot(snapshot);
  } catch (error) {
    if (state.snap) state.reloadError = error;
    else state.error = error;
  }
  state.reloading = false;
  render();
}

async function boot() {
  try {
    state.reg = indexRegistry(await getJson("api/registry"));
  } catch (error) {
    state.error = error;
    render();
    return;
  }
  await loadSnapshot();
}

window.addEventListener("hashchange", () => {
  renderView();
  $("view").focus({ preventScroll: true });
  if (parseRoute().view === "country") window.scrollTo({ top: 0 });
});
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", renderView);
$("reload").addEventListener("click", loadSnapshot);
boot();
