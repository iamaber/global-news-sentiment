import plotly.graph_objects as go
import streamlit as st

from dashboard.data import REGION_COLORS, WINDOWS, View, style_figure
from newsent import history
from newsent.countries import COUNTRIES, daily_index
from newsent.store import Store

COUNTRY_KEY = "country"
MAP_KEY = "country_map"
BY_NAME = sorted(COUNTRIES, key=lambda iso3: COUNTRIES[iso3].country.name)


def select_from_map() -> None:
    points = st.session_state[MAP_KEY].selection.points
    st.session_state[COUNTRY_KEY] = points[0]["location"] if points else None


def selected_point_indices(iso3s: list[str]) -> list[int] | None:
    chosen = st.session_state.get(COUNTRY_KEY)
    return [iso3s.index(chosen)] if chosen in iso3s else None


def render(view: View, store: Store) -> None:
    iso3 = st.selectbox(
        "Country",
        BY_NAME,
        format_func=lambda iso3: COUNTRIES[iso3].country.name,
        index=None,
        key=COUNTRY_KEY,
        placeholder="Click a country on the map, or pick one here",
    )
    if iso3:
        render_country(iso3, view, store)


def render_country(iso3: str, view: View, store: Store) -> None:
    entry = COUNTRIES[iso3]
    name, region = entry.country.name, entry.region
    feeds = entry.feeds or region.feeds
    sources = {feed.name for feed in feeds}
    shown = view.headlines[view.headlines["source"].isin(sources)]

    st.subheader(name)
    st.caption(f"{region.name} · {len(entry.feeds)} outlet(s) based here")
    if not entry.feeds:
        st.info(
            f"No outlet in this dashboard is based in {name}. "
            f"Showing the {region.name} figures instead."
        )

    cols = st.columns(3)
    cols[0].metric(
        "Sentiment index", f"{shown['index'].mean():+.1f}" if len(shown) else "–"
    )
    cols[1].metric("Headlines", len(shown))
    cols[2].metric("Outlets", len(feeds))

    stats = shown.groupby("source")["index"].agg(["count", "mean"])
    st.dataframe(
        [
            {
                "outlet": feed.name,
                "based in": feed.country,
                "headlines": int(stats["count"].get(feed.name, 0)),
                "index": stats["mean"].get(feed.name),
            }
            for feed in feeds
        ],
        hide_index=True,
        use_container_width=True,
        column_config={
            "outlet": st.column_config.TextColumn("Outlet"),
            "based in": st.column_config.TextColumn("Based in"),
            "headlines": st.column_config.NumberColumn("Headlines now"),
            "index": st.column_config.ProgressColumn(
                "Mean index", min_value=-100, max_value=100, format="%+.0f"
            ),
        },
    )

    window = (
        st.segmented_control(
            "Window", list(WINDOWS), default="30 days", key="country_window"
        )
        or "30 days"
    )
    points, origin = history.source_trend(store, WINDOWS[window])
    series = daily_index(points, sources)
    if len(series) < 2:
        st.info(
            "This chart builds up one day at a time. "
            f"{len(series)} day(s) recorded so far; come back tomorrow."
        )
        st.caption(f"Source: {origin}.")
    else:
        fig = go.Figure()
        fig.add_scatter(
            x=[point.day for point in series],
            y=[point.value * 100 for point in series],
            name=name,
            mode="lines+markers",
            line=dict(color=REGION_COLORS[region.key], width=2),
        )
        fig.add_hline(y=0, line=dict(color="#8B8D98", width=1, dash="dot"))
        fig.update_yaxes(title="Sentiment index", zeroline=False)
        st.plotly_chart(style_figure(fig, 300), use_container_width=True)
        st.caption(
            f"{len(series)} days · {sum(p.headlines for p in series)} unique "
            f"headlines · {origin}."
        )

    st.dataframe(
        shown[["title", "source", "published", "sentiment", "index", "link"]],
        hide_index=True,
        use_container_width=True,
        column_config={
            "title": st.column_config.TextColumn("Headline", width="large"),
            "source": st.column_config.TextColumn("Source"),
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
