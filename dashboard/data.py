import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from newsent import history, model
from newsent.pipeline import RegionSummary, summarize, take_snapshot
from newsent.regions import REGIONS
from newsent.store import Store

SNAPSHOT_TTL_SECONDS = 300
LABEL_COLORS = {"negative": "#E5484D", "neutral": "#8B8D98", "positive": "#30A46C"}
REGION_COLORS = {
    "americas": "#3E63DD",
    "europe": "#8E4EC6",
    "asia_pacific": "#F76B15",
    "mea": "#12A594",
}
REGION_NAMES = {region.key: region.name for region in REGIONS}
WINDOWS = {"7 days": 7, "30 days": 30, "90 days": 90}
BASELINE_DAYS = 7
MARKDOWN_SPECIALS = re.compile(r"[\\`*_{}\[\]()#+\-.!|$~<>:]")


@st.cache_resource(show_spinner=False)
def get_store() -> Store:
    return Store()


@dataclass(frozen=True)
class View:
    headlines: pd.DataFrame
    statuses: pd.DataFrame
    regions: dict[str, RegionSummary]
    taken_at: datetime
    newly_scored: int


@st.cache_data(ttl=SNAPSHOT_TTL_SECONDS, max_entries=1, show_spinner=False)
def load_snapshot() -> View:
    snapshot = take_snapshot(get_store(), score=model.score)
    headlines = pd.DataFrame(
        [
            {
                "title": item.headline.title,
                "source": item.headline.source,
                "region": REGION_NAMES[item.headline.region],
                "region_key": item.headline.region,
                "published": item.headline.published,
                "link": item.headline.link,
                "sentiment": item.scores.label,
                "index": round(item.scores.net * 100, 1),
                "positive": item.scores.positive,
                "neutral": item.scores.neutral,
                "negative": item.scores.negative,
            }
            for item in snapshot.items
        ]
    )
    statuses = pd.DataFrame(
        [
            {
                "region": REGION_NAMES[s.region],
                "source": s.source,
                "headlines": s.headlines,
                "latency (s)": s.seconds,
                "status": "OK" if s.error is None else s.error,
            }
            for s in snapshot.statuses
        ]
    )
    return View(
        headlines=headlines,
        statuses=statuses,
        regions={s.region: s for s in summarize(snapshot.items)},
        taken_at=snapshot.taken_at,
        newly_scored=snapshot.newly_scored,
    )


def trend_frame(points) -> pd.DataFrame:
    frame = pd.DataFrame(
        [
            {
                "day": p.day,
                "region_key": p.region,
                "value": p.value,
                "headlines": p.headlines,
            }
            for p in points
        ]
    )
    if not frame.empty:
        frame["day"] = pd.to_datetime(frame["day"])
    return frame


def baseline_index(store: Store) -> dict[str, float]:
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    by_region: dict[str, list[float]] = {}
    points, _ = history.model_trend(store, BASELINE_DAYS, yesterday)
    for point in points:
        by_region.setdefault(point.region, []).append(point.value * 100)
    return {region: sum(v) / len(v) for region, v in by_region.items()}


def style_figure(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
    )
    return fig


def line_chart(frame: pd.DataFrame, y_title: str, smooth: bool) -> go.Figure:
    fig = go.Figure()
    wide = frame.pivot(index="day", columns="region_key", values="value").sort_index()
    if smooth:
        wide = wide.rolling("7D", min_periods=1).mean()
    for region in REGIONS:
        if region.key not in wide:
            continue
        series = wide[region.key].dropna()
        fig.add_scatter(
            x=series.index,
            y=series.values,
            name=region.name,
            mode="lines",
            line=dict(color=REGION_COLORS[region.key], width=2),
        )
    fig.add_hline(y=0, line=dict(color="#8B8D98", width=1, dash="dot"))
    fig.update_yaxes(title=y_title, zeroline=False)
    fig.update_layout(hovermode="x unified")
    return style_figure(fig, 380)


def escape_markdown(text: str) -> str:
    return MARKDOWN_SPECIALS.sub(r"\\\g<0>", text)
