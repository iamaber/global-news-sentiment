from datetime import UTC, datetime

import streamlit as st

from dashboard.data import REGION_NAMES, WINDOWS, View, line_chart, trend_frame
from newsent import gdelt, history
from newsent.regions import REGIONS
from newsent.store import Store


def render(view: View, store: Store) -> None:
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
