import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from newsent import gdelt, history, model
from newsent.pipeline import RegionSummary, summarize, take_snapshot
from newsent.regions import ALL_FEEDS, REGIONS
from newsent.scores import LABELS
from newsent.store import Store

SNAPSHOT_TTL_SECONDS = 300
LABEL_COLORS = {"negative": "#E5484D", "neutral": "#8B8D98", "positive": "#30A46C"}
REGION_COLORS = {
    "americas": "#3E63DD",
    "europe": "#8E4EC6",
    "asia_pacific": "#F76B15",
    "mea": "#12A594",
}
REGION_NAMES = {region.key: region.name for region in REGIONS}
WINDOWS = {"7 days": 7, "30 days": 30, "90 days": 90}
BASELINE_DAYS = 7
MARKDOWN_SPECIALS = re.compile(r"[\\`*_{}\[\]()#+\-.!|$~<>:]")

st.set_page_config(page_title="Global News Sentiment", page_icon="🌐", layout="wide")


@st.cache_resource(show_spinner=False)
def get_store() -> Store:
    return Store()


@dataclass(frozen=True)
class View:
    headlines: pd.DataFrame
    statuses: pd.DataFrame
    regions: dict[str, RegionSummary]
    taken_at: datetime
    newly_scored: int


@st.cache_data(ttl=SNAPSHOT_TTL_SECONDS, max_entries=1, show_spinner=False)
def load_snapshot() -> View:
    snapshot = take_snapshot(get_store(), score=model.score)
    headlines = pd.DataFrame(
        [
            {
                "title": item.headline.title,
                "source": item.headline.source,
                "region": REGION_NAMES[item.headline.region],
                "region_key": item.headline.region,
                "published": item.headline.published,
                "link": item.headline.link,
                "sentiment": item.scores.label,
                "index": round(item.scores.net * 100, 1),
                "positive": item.scores.positive,
                "neutral": item.scores.neutral,
                "negative": item.scores.negative,
            }
            for item in snapshot.items
        ]
    )
    statuses = pd.DataFrame(
        [
            {
                "region": REGION_NAMES[s.region],
                "source": s.source,
                "headlines": s.headlines,
                "latency (s)": s.seconds,
                "status": "OK" if s.error is None else s.error,
            }
            for s in snapshot.statuses
        ]
    )
    return View(
        headlines=headlines,
        statuses=statuses,
        regions={s.region: s for s in summarize(snapshot.items)},
        taken_at=snapshot.taken_at,
        newly_scored=snapshot.newly_scored,
    )


def trend_frame(points) -> pd.DataFrame:
    frame = pd.DataFrame(
        [
            {
                "day": p.day,
                "region_key": p.region,
                "value": p.value,
                "headlines": p.headlines,
            }
            for p in points
        ]
    )
    if not frame.empty:
        frame["day"] = pd.to_datetime(frame["day"])
    return frame


def baseline_index(store: Store) -> dict[str, float]:
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    by_region: dict[str, list[float]] = {}
    points, _ = history.model_trend(store, BASELINE_DAYS, yesterday)
    for point in points:
        by_region.setdefault(point.region, []).append(point.value * 100)
    return {region: sum(v) / len(v) for region, v in by_region.items()}


def style_figure(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
    )
    return fig


def line_chart(frame: pd.DataFrame, y_title: str, smooth: bool) -> go.Figure:
    fig = go.Figure()
    wide = frame.pivot(index="day", columns="region_key", values="value").sort_index()
    if smooth:
        wide = wide.rolling("7D", min_periods=1).mean()
    for region in REGIONS:
        if region.key not in wide:
            continue
        series = wide[region.key].dropna()
        fig.add_scatter(
            x=series.index,
            y=series.values,
            name=region.name,
            mode="lines",
            line=dict(color=REGION_COLORS[region.key], width=2),
        )
    fig.add_hline(y=0, line=dict(color="#8B8D98", width=1, dash="dot"))
    fig.update_yaxes(title=y_title, zeroline=False)
    fig.update_layout(hovermode="x unified")
    return style_figure(fig, 380)


def render_header(view: View):
    headlines, statuses = view.headlines, view.statuses
    left, right = st.columns([5, 1], vertical_alignment="bottom")
    with left:
        st.title("Global News Sentiment")
        st.caption(
            f"{len(ALL_FEEDS)} outlets across {len(REGIONS)} regions · scored with "
            f"`{model.MODEL_NAME}` · snapshot {view.taken_at:%H:%M UTC} · "
            f"{view.newly_scored} new headlines scored"
        )
    with right:
        if st.button("Refresh", icon=":material/refresh:", use_container_width=True):
            load_snapshot.clear()
            st.rerun()

    shares = headlines["sentiment"].value_counts(normalize=True)
    online = int((statuses["status"] == "OK").sum())
    cols = st.columns(5)
    cols[0].metric(
        "Global sentiment index",
        f"{headlines['index'].mean():+.1f}",
        help="Mean of P(positive) − P(negative) per headline, scaled to −100…+100.",
    )
    cols[1].metric("Headlines", len(headlines))
    cols[2].metric("Positive", f"{shares.get('positive', 0):.0%}")
    cols[3].metric("Negative", f"{shares.get('negative', 0):.0%}")
    cols[4].metric("Sources online", f"{online}/{len(statuses)}")


def render_regions(summaries: dict[str, RegionSummary], store: Store):
    baseline = baseline_index(store)

    cards = st.columns(len(REGIONS))
    for card, region in zip(cards, REGIONS):
        summary = summaries[region.key]
        index = summary.net * 100
        with card.container(border=True):
            delta = None
            if region.key in baseline and summary.headlines:
                delta = (
                    f"{index - baseline[region.key]:+.1f} vs {BASELINE_DAYS}-day avg"
                )
            st.metric(region.name, f"{index:+.1f}", delta=delta)
            st.caption(f"{summary.headlines} headlines · {len(region.feeds)} outlets")

    map_col, bar_col = st.columns([3, 2])
    with map_col:
        st.subheader("Sentiment by region")
        countries = pd.DataFrame(
            [
                {
                    "iso3": c.iso3,
                    "country": c.name,
                    "region": region.name,
                    "index": summaries[region.key].net * 100,
                }
                for region in REGIONS
                for c in region.source_countries
                if summaries[region.key].headlines
            ]
        )
        bound = (
            max(20.0, countries["index"].abs().max()) if not countries.empty else 20.0
        )
        fig = px.choropleth(
            countries,
            locations="iso3",
            color="index",
            hover_name="country",
            hover_data={"region": True, "index": ":+.1f", "iso3": False},
            color_continuous_scale=[
                LABEL_COLORS["negative"],
                "#F1F1F1",
                LABEL_COLORS["positive"],
            ],
            range_color=(-bound, bound),
            projection="natural earth",
        )
        fig.update_geos(
            showframe=False,
            showcoastlines=False,
            showcountries=True,
            countrycolor="rgba(128,128,128,0.3)",
            bgcolor="rgba(0,0,0,0)",
            landcolor="rgba(128,128,128,0.12)",
            showland=True,
        )
        fig.update_coloraxes(colorbar=dict(title="Index", thickness=10))
        st.plotly_chart(style_figure(fig, 380), use_container_width=True)

    with bar_col:
        st.subheader("Tone mix")
        mix = pd.DataFrame(
            [
                {"region": region.name, "sentiment": label, "share": share}
                for region in REGIONS
                for label, share in summaries[region.key].shares.items()
            ]
        )
        fig = px.bar(
            mix,
            x="share",
            y="region",
            color="sentiment",
            orientation="h",
            color_discrete_map=LABEL_COLORS,
            category_orders={"sentiment": list(LABELS)},
        )
        fig.update_xaxes(tickformat=".0%", title=None, range=[0, 1])
        fig.update_yaxes(title=None, autorange="reversed")
        st.plotly_chart(style_figure(fig, 380), use_container_width=True)


def render_trends(store: Store):
    controls = st.columns([3, 2, 5], vertical_alignment="center")
    window = (
        controls[0].segmented_control(
            "Window", list(WINDOWS), default="30 days", label_visibility="collapsed"
        )
        or "30 days"
    )
    smooth = controls[1].toggle("7-day smoothing", value=True)
    days = WINDOWS[window]

    st.subheader("News tone by region")
    stale = gdelt.stale_regions(store, REGIONS, datetime.now(UTC))
    if stale:
        with st.spinner("Fetching regional history from GDELT…"):
            errors = gdelt.refresh(store, stale)
        if errors:
            names = ", ".join(REGION_NAMES[key] for key in errors)
            reasons = "; ".join(sorted(set(errors.values())))
            st.caption(f":orange[GDELT history pending for {names}: {reasons}.]")

    tone = trend_frame(store.gdelt_trend(days))
    if tone.empty:
        st.info(
            "No GDELT history yet. It is fetched on demand and cached for six hours."
        )
    else:
        st.plotly_chart(
            line_chart(tone, "GDELT tone", smooth), use_container_width=True
        )
        st.caption(
            "Daily average tone of all online news published in each region's countries, "
            "from the [GDELT Project](https://www.gdeltproject.org/). Lexicon-based and "
            "typically negative; compare regions and direction rather than absolute level."
        )

    st.subheader("Model sentiment index by region")
    points, origin = history.model_trend(store, days)
    recorded = trend_frame(points)
    recorded_days = recorded["day"].nunique() if not recorded.empty else 0
    if recorded_days < 2:
        st.info(
            "This chart builds up one day at a time. "
            f"{recorded_days} day(s) recorded so far; come back tomorrow."
        )
        st.caption(f"Source: {origin}.")
    else:
        recorded["value"] *= 100
        st.plotly_chart(
            line_chart(recorded, "Sentiment index", smooth), use_container_width=True
        )
        st.caption(
            f"{recorded_days} days · {int(recorded['headlines'].sum())} unique "
            f"headlines · {origin}."
        )


def escape_markdown(text: str) -> str:
    return MARKDOWN_SPECIALS.sub(r"\\\g<0>", text)


def render_headlines(headlines: pd.DataFrame, taken_at: datetime):
    filters = st.columns([3, 3, 4], vertical_alignment="bottom")
    regions = filters[0].multiselect(
        "Region", [r.name for r in REGIONS], placeholder="All regions"
    )
    sentiment = filters[1].segmented_control(
        "Sentiment",
        ["positive", "neutral", "negative"],
        selection_mode="multi",
        format_func=str.title,
    )
    query = filters[2].text_input("Search", placeholder="Filter headlines…")

    view = headlines
    if regions:
        view = view[view["region"].isin(regions)]
    if sentiment:
        view = view[view["sentiment"].isin(sentiment)]
    if query:
        view = view[view["title"].str.contains(query, case=False, regex=False)]

    top, bottom = st.columns(2)
    for col, title, frame in (
        (top, "Most positive", view.nlargest(5, "index")),
        (bottom, "Most negative", view.nsmallest(5, "index")),
    ):
        with col.container(border=True):
            st.markdown(f"**{title}**")
            for row in frame.to_dict("records"):
                index = row["index"]
                color = "green" if index > 0 else "red" if index < 0 else "gray"
                st.markdown(
                    f":{color}-badge[{index:+.0f}] {escape_markdown(row['title'])}  \n"
                    f":gray[{row['source']} · {row['region']}]"
                )

    st.dataframe(
        view[["title", "source", "region", "published", "sentiment", "index", "link"]],
        hide_index=True,
        use_container_width=True,
        height=480,
        column_config={
            "title": st.column_config.TextColumn("Headline", width="large"),
            "source": st.column_config.TextColumn("Source"),
            "region": st.column_config.TextColumn("Region"),
            "published": st.column_config.DatetimeColumn(
                "Published", format="MMM D, HH:mm"
            ),
            "sentiment": st.column_config.TextColumn("Sentiment"),
            "index": st.column_config.ProgressColumn(
                "Index", min_value=-100, max_value=100, format="%+.0f"
            ),
            "link": st.column_config.LinkColumn("Link", display_text="Open"),
        },
    )
    st.download_button(
        "Download CSV",
        view.drop(columns="region_key").to_csv(index=False),
        file_name=f"news_sentiment_{taken_at:%Y%m%d_%H%M}.csv",
        mime="text/csv",
        icon=":material/download:",
    )


def render_sources(statuses: pd.DataFrame):
    st.dataframe(statuses, hide_index=True, use_container_width=True)
    st.caption(
        "Regions are assigned by where each outlet is based. Feeds are fetched over "
        "HTTPS from an allowlist with a 15 s overall deadline."
    )


def main():
    store = get_store()
    try:
        with st.spinner(
            "Fetching and scoring headlines… first run downloads the model (~500 MB)"
        ):
            view = load_snapshot()
    except Exception as exc:
        st.error(f"Could not build a snapshot: {exc}")
        st.stop()

    if view.headlines.empty:
        st.error(
            "No news source responded. The app needs outbound HTTPS access to the "
            "feeds listed under Sources."
        )
        st.dataframe(view.statuses, hide_index=True)
        st.stop()

    render_header(view)
    regions_tab, trends_tab, headlines_tab, sources_tab = st.tabs(
        ["Regions", "Trends", "Headlines", "Sources"]
    )
    with regions_tab:
        render_regions(view.regions, store)
    with headlines_tab:
        render_headlines(view.headlines, view.taken_at)
    with sources_tab:
        render_sources(view.statuses)
    with trends_tab:
        render_trends(store)


main()
