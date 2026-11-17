import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.data import LABEL_COLORS, View, style_figure
from newsent.regions import REGIONS
from newsent.store import Store
from newsent.topics import TOPICS, topics_of

TOPIC_NAMES = {topic.key: topic.name for topic in TOPICS}
ALL_REGIONS = "All regions"


def render(view: View, store: Store) -> None:
    headlines = view.headlines
    tagged = headlines.assign(topic=headlines["title"].map(topics_of)).explode("topic")
    tagged = tagged.dropna(subset=["topic"])
    covered = tagged.index.nunique()
    st.caption(
        f"{covered} of {len(headlines)} headlines mention at least one topic. "
        "A headline can carry several topics."
    )
    if tagged.empty:
        return

    st.subheader("Sentiment by region and topic")
    cells = tagged.groupby(["region_key", "topic"])["index"].agg(["mean", "size"])
    st.plotly_chart(heatmap(cells), use_container_width=True)

    with st.expander("How topics are assigned"):
        for topic in TOPICS:
            words = (*topic.keywords, *topic.exact)
            keywords = ", ".join(k.replace("*", "…") for k in words)
            st.markdown(f"**{topic.name}** · {keywords}")
        st.caption(
            "A headline gets a topic when its title contains one of the topic's "
            "words. … stands for any ending. Acronyms and names match only in "
            "their exact case."
        )

    picker = st.columns(2)
    topic = picker[0].selectbox(
        "Topic",
        list(TOPIC_NAMES),
        format_func=TOPIC_NAMES.__getitem__,
        key="topics_topic",
    )
    region = picker[1].selectbox(
        "Region", [ALL_REGIONS, *(r.name for r in REGIONS)], key="topics_region"
    )
    shown = tagged[tagged["topic"] == topic]
    where = ""
    if region != ALL_REGIONS:
        shown = shown[shown["region"] == region]
        where = f" from {region}"
    if shown.empty:
        st.info(f"No {TOPIC_NAMES[topic].lower()} headlines{where} right now.")
        return
    st.dataframe(
        shown.sort_values("index", ascending=False)[
            ["title", "source", "region", "published", "index", "link"]
        ],
        hide_index=True,
        use_container_width=True,
        column_config={
            "title": st.column_config.TextColumn("Headline", width="large"),
            "source": st.column_config.TextColumn("Source"),
            "region": st.column_config.TextColumn("Region"),
            "published": st.column_config.DatetimeColumn(
                "Published", format="MMM D, HH:mm"
            ),
            "index": st.column_config.ProgressColumn(
                "Index", min_value=-100, max_value=100, format="%+.0f"
            ),
            "link": st.column_config.LinkColumn("Link", display_text="Open"),
        },
    )


def heatmap(cells: pd.DataFrame) -> go.Figure:
    def grid(values: pd.Series) -> pd.DataFrame:
        regions = [r.key for r in REGIONS]
        return values.unstack().reindex(index=regions, columns=list(TOPIC_NAMES))

    size = cells["size"].map(lambda n: f"{n} headline{'' if n == 1 else 's'}")
    text = cells["mean"].map("{:+.0f}".format) + "<br>" + size
    hover = cells["mean"].map("Index {:+.1f}".format) + "<br>" + size
    bound = max(20.0, cells["mean"].abs().max())
    fig = go.Figure(
        go.Heatmap(
            z=grid(cells["mean"]).values,
            x=list(TOPIC_NAMES.values()),
            y=[r.name for r in REGIONS],
            text=grid(text).fillna("").values,
            texttemplate="%{text}",
            customdata=grid(hover).fillna("").values,
            hovertemplate="%{y} · %{x}<br>%{customdata}<extra></extra>",
            hoverongaps=False,
            colorscale=[
                [0.0, LABEL_COLORS["negative"]],
                [0.5, "#F1F1F1"],
                [1.0, LABEL_COLORS["positive"]],
            ],
            zmin=-bound,
            zmax=bound,
            colorbar=dict(title="Index", thickness=10),
            xgap=2,
            ygap=2,
        )
    )
    fig.update_yaxes(autorange="reversed")
    return style_figure(fig, 360)
