import streamlit as st

from dashboard.data import View, escape_markdown
from newsent.regions import REGIONS
from newsent.store import Store


def render(view: View, store: Store) -> None:
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

    shown = view.headlines
    if regions:
        shown = shown[shown["region"].isin(regions)]
    if sentiment:
        shown = shown[shown["sentiment"].isin(sentiment)]
    if query:
        shown = shown[shown["title"].str.contains(query, case=False, regex=False)]

    top, bottom = st.columns(2)
    for col, title, frame in (
        (top, "Most positive", shown.nlargest(5, "index")),
        (bottom, "Most negative", shown.nsmallest(5, "index")),
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
        shown[["title", "source", "region", "published", "sentiment", "index", "link"]],
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
        shown.drop(columns="region_key").to_csv(index=False),
        file_name=f"news_sentiment_{view.taken_at:%Y%m%d_%H%M}.csv",
        mime="text/csv",
        icon=":material/download:",
    )
