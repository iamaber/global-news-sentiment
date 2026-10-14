"""Real-time News Sentiment Analysis dashboard (single-entry Streamlit app)."""

import os
import tempfile

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from news_sources import FEED_URLS, MAX_HEADLINES, fetch_headlines
from sentiment_utils import aggregate_sentiment, normalize_sentiment

# Keep every model artefact inside a temp directory instead of the repo or home
# directory. Combined with st.cache_resource this bounds the app to one model
# download per running process.
HF_HOME = os.path.join(tempfile.gettempdir(), "realtime-news-sentiment-hf")
os.environ.setdefault("HF_HOME", HF_HOME)
os.environ.setdefault("TRANSFORMERS_CACHE", HF_HOME)

MODEL_NAME = "distilbert-base-uncased-finetuned-sst-2-english"
BATCH_SIZE = 10
SENTIMENT_COLORS = {
    "POSITIVE": "#2E8B57",
    "NEGATIVE": "#DC143C",
    "NEUTRAL": "#708090",
}

st.set_page_config(
    page_title="Real-time News Sentiment Analysis", page_icon="📊", layout="wide"
)


@st.cache_resource(show_spinner=False)
def load_sentiment_model():
    """Load the sentiment pipeline once per process."""
    from transformers import pipeline

    return pipeline("sentiment-analysis", model=MODEL_NAME)


@st.cache_data(ttl=300, max_entries=1, show_spinner=False)
def cached_fetch_headlines():
    """Cache the headline snapshot for five minutes, keeping one entry."""
    return fetch_headlines()


def analyze_sentiment(texts, model):
    """Run sentiment analysis in batches to keep memory use predictable."""
    results = []
    for start in range(0, len(texts), BATCH_SIZE):
        results.extend(model(texts[start : start + BATCH_SIZE]))
    return results


def main():
    st.title("📊 Real-time News Sentiment Analysis Dashboard")
    st.markdown("*Analyzing sentiment from live news headlines using AI*")

    st.sidebar.header("📰 News Sources")
    st.sidebar.markdown("\n".join(f"- {url}" for url in FEED_URLS))
    st.sidebar.caption(
        "No API key required — this dashboard reads public RSS feeds."
    )

    if st.button("🔄 Fetch Latest Headlines", type="primary"):
        cached_fetch_headlines.clear()

    with st.spinner("Fetching latest headlines..."):
        headlines, sources, errors = cached_fetch_headlines()

    if errors:
        with st.expander(f"⚠️ {len(errors)} news source(s) could not be read"):
            for error in errors:
                st.write(f"- {error}")

    if not headlines:
        st.error(
            "Could not fetch headlines from any news source. This app needs "
            "outbound network access to the RSS feeds listed in the sidebar. "
            "Check the connection and try again."
        )
        st.stop()

    st.subheader(f"📰 Latest Headlines ({len(headlines)} found)")
    headlines_df = pd.DataFrame({"headline": headlines, "source": sources})
    st.dataframe(headlines_df, use_container_width=True, height=300)

    if st.button("🤖 Run Sentiment Analysis", type="secondary"):
        try:
            with st.spinner("Loading sentiment model..."):
                model = load_sentiment_model()
        except Exception as exc:
            st.error(
                "Could not load the sentiment model. The first run downloads "
                f"~260 MB from Hugging Face; check network access and retry.\n\n{exc}"
            )
            st.stop()

        try:
            with st.spinner("Analyzing sentiment..."):
                sentiments = analyze_sentiment(headlines, model)
        except Exception as exc:
            st.error(f"Sentiment analysis failed: {exc}")
            st.stop()

        if not sentiments:
            st.error("Could not analyze sentiment. Please try again.")
            st.stop()

        results = []
        for headline, source, sentiment in zip(headlines, sources, sentiments):
            normalized = normalize_sentiment(sentiment)
            results.append(
                {
                    "headline": headline,
                    "source": source,
                    "sentiment": normalized["label"],
                    "score": round(normalized["score"], 3),
                }
            )

        results_df = pd.DataFrame(results)
        summary = aggregate_sentiment(sentiments)
        sentiment_counts = summary["counts"]

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("📊 Sentiment Distribution")
            labels = list(sentiment_counts.keys())
            values = list(sentiment_counts.values())
            fig = go.Figure(
                data=[
                    go.Pie(
                        labels=labels,
                        values=values,
                        marker=dict(
                            colors=[SENTIMENT_COLORS.get(label, "#4682B4") for label in labels]
                        ),
                        textinfo="label+percent",
                        textfont_size=12,
                    )
                ]
            )
            fig.update_layout(title="Sentiment Distribution", height=400)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.subheader("📈 Sentiment Summary")
            st.metric("Total Headlines", summary["total"])
            for label, count in sorted(sentiment_counts.items()):
                percentage = summary["percentages"][label]
                st.metric(label.title(), f"{count} ({percentage:.1f}%)")
            st.metric(
                "Average Confidence", f"{summary['average_confidence']:.2f}"
            )

        st.subheader("📋 Detailed Analysis")

        def color_sentiment(value):
            if value == "POSITIVE":
                return "background-color: #90EE90"
            if value == "NEGATIVE":
                return "background-color: #FFB6C1"
            return "background-color: #D3D3D3"

        styled_df = results_df.style.applymap(color_sentiment, subset=["sentiment"])
        st.dataframe(styled_df, use_container_width=True, height=400)

        st.download_button(
            label="📥 Download Results as CSV",
            data=results_df.to_csv(index=False),
            file_name=(
                "news_sentiment_analysis_"
                f"{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv"
            ),
            mime="text/csv",
        )

    st.markdown("---")
    st.markdown(
        "*Built with Hugging Face Transformers, Streamlit, and public RSS feeds. "
        f"Analyzes at most {MAX_HEADLINES} headlines per snapshot.*"
    )


if __name__ == "__main__":
    main()
