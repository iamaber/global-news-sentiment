import streamlit as st

from dashboard.data import WINDOWS, View, line_chart, trend_frame
from newsent import history
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

    st.subheader("GDELT event tone by region")
    points, origin = history.gdelt_trend(days)
    tone = trend_frame(points)
    if tone.empty:
        st.info("No GDELT tone to show for this window.")
        st.caption(f"Source: {origin}.")
    else:
        st.plotly_chart(
            line_chart(tone, "GDELT tone", smooth), use_container_width=True
        )
        st.caption(
            "Daily average tone of the news coverage of events whose main actor is "
            "from each region's countries, weighted by article count, from the "
            "[GDELT Project](https://www.gdeltproject.org/)'s daily event files. "
            "It covers news about the region's actors from outlets worldwide, so it "
            "differs from our model's index below, which scores the outlets based "
            "in each region. Lexicon-based and typically negative; compare regions "
            f"and direction rather than absolute level. Updated daily · {origin}."
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
