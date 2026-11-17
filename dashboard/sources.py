import streamlit as st

from dashboard.data import View
from newsent.store import Store


def render(view: View, store: Store) -> None:
    st.dataframe(view.statuses, hide_index=True, use_container_width=True)
    st.caption(
        "Regions are assigned by where each outlet is based. Feeds are fetched over "
        "HTTPS from an allowlist with a 15 s overall deadline."
    )
