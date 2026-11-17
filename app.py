from collections.abc import Callable
from dataclasses import dataclass

import streamlit as st

from dashboard import alerts, headlines, regions, sources, stories, trends
from dashboard.data import View, get_store, load_snapshot
from newsent import model
from newsent.regions import ALL_FEEDS, REGIONS
from newsent.store import Store

st.set_page_config(page_title="Global News Sentiment", page_icon="🌐", layout="wide")


@dataclass(frozen=True)
class Tab:
    label: str
    render: Callable[[View, Store], None]
    # Deferred tabs render after the others so slow work (GDELT fetches) does
    # not hold back the rest of the page.
    deferred: bool = False


TABS: tuple[Tab, ...] = (
    Tab("Regions", regions.render),
    Tab("Trends", trends.render, deferred=True),
    Tab("Headlines", headlines.render),
    Tab("Stories", stories.render),
    Tab("Sources", sources.render),
)


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
    alerts.render_banner(view, store)
    containers = st.tabs([tab.label for tab in TABS])
    placed = list(zip(TABS, containers))
    for tab, container in sorted(placed, key=lambda pair: pair[0].deferred):
        with container:
            tab.render(view, store)


main()
