import streamlit as st

from dashboard.data import View, escape_markdown
from newsent.regions import REGIONS
from newsent.stories import group_stories
from newsent.store import Store


def render(view: View, store: Store) -> None:
    frame = view.headlines
    stories = group_stories(list(zip(frame["title"], frame["region_key"])))
    if not stories:
        st.info(
            "No story is covered by more than one region in this snapshot. "
            "Refresh later to check again."
        )
        return

    st.caption(
        f"{len(stories)} stories covered by two or more regions. Headlines are "
        "grouped when their titles share most of their words, so a story told in "
        "very different words can show up split or not at all."
    )
    for story in stories:
        rows = frame.iloc[list(story.members)]
        by_region = [
            (region.name, rows[rows["region_key"] == region.key])
            for region in REGIONS
            if region.key in story.regions
        ]
        with st.container(border=True):
            st.markdown(f"**{escape_markdown(frame['title'].iloc[story.lead])}**")
            st.markdown(
                " ".join(
                    _badge(group["index"].mean(), f"{name} ")
                    for name, group in by_region
                )
            )
            with st.expander(f"{len(rows)} headlines from {len(by_region)} regions"):
                for name, group in by_region:
                    st.markdown(f"**{name}**")
                    for row in group.to_dict("records"):
                        st.markdown(
                            f"{_badge(row['index'])} "
                            f"{_title_link(row['title'], row['link'])}  \n"
                            f":gray[{row['source']}]"
                        )


def _badge(index: float, prefix: str = "") -> str:
    color = "green" if index > 0 else "red" if index < 0 else "gray"
    return f":{color}-badge[{prefix}{index:+.0f}]"


def _title_link(title: str, link: str | None) -> str:
    if not link:
        return escape_markdown(title)
    target = link.replace("(", "%28").replace(")", "%29")
    return f"[{escape_markdown(title)}]({target})"
