from dataclasses import replace
from datetime import UTC, datetime, timedelta

import streamlit as st

from dashboard.data import BASELINE_DAYS, REGION_NAMES, View
from newsent import history
from newsent.alerts import detect
from newsent.store import Store


def render_banner(view: View, store: Store) -> None:
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    points, _ = history.model_trend(store, BASELINE_DAYS, until=yesterday)
    today = {key: s.net * 100 for key, s in view.regions.items() if s.headlines}
    baseline = [replace(p, value=p.value * 100) for p in points]
    for alert in detect(today, baseline):
        rising = alert.z > 0
        st.warning(
            f"**{REGION_NAMES[alert.region]}** sentiment is {alert.today:+.1f} today, "
            f"{'above' if rising else 'below'} its {BASELINE_DAYS}-day mean of "
            f"{alert.mean:+.1f} ({alert.z:+.1f} standard deviations).",
            icon=f":material/trending_{'up' if rising else 'down'}:",
        )
