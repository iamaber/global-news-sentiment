import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard import countries as country_page
from dashboard.data import (
    BASELINE_DAYS,
    LABEL_COLORS,
    View,
    baseline_index,
    style_figure,
)
from newsent.regions import REGIONS
from newsent.scores import LABELS
from newsent.store import Store


def render(view: View, store: Store) -> None:
    summaries = view.regions
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
        fig.update_traces(
            selectedpoints=country_page.selected_point_indices(list(countries["iso3"]))
        )
        st.plotly_chart(
            style_figure(fig, 380),
            use_container_width=True,
            on_select=country_page.select_from_map,
            selection_mode="points",
            key=country_page.MAP_KEY,
        )

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

    country_page.render(view, store)
