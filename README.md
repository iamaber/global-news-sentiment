# Global News Sentiment

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Streamlit dashboard that reads 20 news outlets across four regions, scores
every headline with a three-class sentiment model, and charts how each region's
news tone moves over 7, 30, and 90 days. A FastAPI service exposes the same data
as JSON.

- Live demo: <https://huggingface.co/spaces/iamaber/Real-time-News-Sentiment-Analysis>
- GitHub: <https://github.com/iamaber/realtime-news-sentiment>

## What the dashboard shows

- **Alerts.** A warning above the tabs for each region whose index today sits
  more than two standard deviations from its mean over the previous seven
  days. A region needs at least five of those days, with some variation, before
  it can be judged.
- **Regions.** A sentiment index per region with its change against the
  previous seven days, a world map coloured by region, and the share of
  negative, neutral, and positive headlines.
- **Countries.** Click a country on the Regions map, or pick one from the list
  under it, to open its page. It lists the outlets based there with their
  current headline count and mean index, the country's daily index, and its
  current headlines. A country with no outlet of its own shows its region's
  figures.
- **Topics.** Each headline is tagged economy, conflict, politics, climate,
  or tech by keywords in its title, and can carry several. A heatmap shows the
  sentiment index per region and topic, and a picker lists the matching
  headlines for any topic and region.
- **Trends.** Two daily series per region, both read from the hourly collector
  described under [Collected history](#collected-history). GDELT event tone is
  the tone of the news coverage of events whose main actor is from the
  region's countries, from GDELT's daily event files. The model's own index
  scores the outlets based in the region, and falls back to the snapshots this
  instance has recorded when the collected history is unavailable. Each chart
  caption says where its data came from.
- **Headlines.** Every scored headline, filterable by region, sentiment, and
  text, with the five most positive and most negative, a link to each story,
  and CSV export.
- **Stories.** Headlines about the same event, grouped across regions by
  shared title words, with each region's mean index for the story and its
  headlines, sources, and links.
- **Sources.** Per-feed status, headline count, and fetch latency.

## Regions and outlets

A headline belongs to the region where its outlet is based, not where the
story happens. GDELT event tone uses a different rule. It counts an event for
a region when the event's main actor is from one of the region's countries,
whichever outlet in the world reported it. The two trend series measure
different things, so compare their direction, not their level.

| Region | Outlets |
| --- | --- |
| Americas | NPR, New York Times, CNBC, CBC News, Buenos Aires Times |
| Europe | BBC News, The Guardian, Deutsche Welle, France 24, RTÉ News |
| Asia-Pacific | South China Morning Post, Times of India, CNA, The Japan Times, ABC News Australia |
| Middle East & Africa | Al Jazeera, The Times of Israel, AllAfrica, Daily Maverick, Nation |

`newsent/regions.py` is the single registry for regions, feeds, and the
countries used by the map and the GDELT event tone. To add an outlet, add a `Feed`
to its region. The feed allowlist is derived from that registry.

## How sentiment is measured

The model is
[`cardiffnlp/twitter-roberta-base-sentiment-latest`](https://huggingface.co/cardiffnlp/twitter-roberta-base-sentiment-latest),
pinned to revision `3216a57f2a0d9c45a2e6c20157c20c49fb4bf9c7`. It returns a
probability for `negative`, `neutral`, and `positive`. Each headline gets:

- a **label**, the most probable class, and
- a **sentiment index**, `P(positive) − P(negative)` scaled to −100…+100.

A region's index is the mean over its headlines. The model was trained on
tweets, not news, so treat the index as a relative signal between regions and
over time. This repository does not claim a measured accuracy on headlines.

GDELT event tone is a separate, lexicon-based score from the
[GDELT Project](https://www.gdeltproject.org/) and sits on its own axis. Each
event in GDELT's daily event file carries the mean tone of the articles that
reported it. A region's daily tone is the mean over events whose first actor
(`Actor1CountryCode`) is one of the region's countries, weighted by each
event's article count. It runs negative for most news, so compare its
direction and the gaps between regions, not its absolute level.

## Performance

- All 20 feeds are fetched concurrently under one 15 s deadline.
- Scores are cached in SQLite by headline. A refresh scores only headlines it
  has not seen, so a typical refresh after the first one runs the model on a
  handful of headlines.
- Headlines are truncated to 64 tokens and scored in batches of 32.
- The dashboard and the API reuse one snapshot for five minutes.

## Quick start

With [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/iamaber/realtime-news-sentiment.git
cd realtime-news-sentiment
uv sync
uv run streamlit run app.py
```

Or with pip:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Open <http://localhost:8501>. The first load downloads the model, about 500 MB,
and keeps it for the life of the process.

## API

```bash
uv sync --extra api
uv run python main.py --mode backend
```

| Endpoint | Returns |
| --- | --- |
| `GET /headlines` | Scored headlines with label, class probabilities, index, and per-feed status |
| `GET /regions` | Per-region headline count, index, and label shares |
| `GET /trends?days=30&source=model` | Daily per-region index (`days` 1–90), plus `origin`, where the series came from |
| `GET /trends?days=30&source=gdelt` | Daily per-region GDELT event tone and article count from the collected `gdelt.csv`, plus `origin`, where the series came from or why it is empty |
| `GET /ready` | 503 until the model is loaded |
| `GET /health` | Liveness |

Interactive docs are at <http://localhost:8000/docs>. `main.py --mode all`
starts the API and the dashboard together.

Both processes bind to `127.0.0.1` by default. The API has no authentication,
so it limits each client to 10 requests per minute and allows two concurrent
scoring requests. Pass `--host 0.0.0.0` only behind an authenticating proxy.

## Project structure

```
.
├── app.py                 # Streamlit entry point: header and tab registry
├── dashboard/
│   ├── data.py            # Snapshot view, cached store, chart helpers
│   ├── regions.py         # Regions tab
│   ├── trends.py          # Trends tab
│   ├── headlines.py       # Headlines tab
│   └── sources.py         # Sources tab
├── newsent/
│   ├── regions.py         # Regions, outlets, and countries (single registry)
│   ├── feeds.py           # Bounded, concurrent RSS fetching
│   ├── scores.py          # Class probabilities, label, and sentiment index
│   ├── model.py           # Pinned RoBERTa model and batched scoring
│   ├── store.py           # SQLite score cache and model trend
│   ├── gdelt.py           # Daily GDELT event file download and per-region tone
│   ├── pipeline.py        # Fetch, score unseen headlines, persist, summarise
│   ├── collect.py         # Hourly collector that writes the history branch
│   └── history.py         # Reads collected history, falls back to the store
├── .github/workflows/     # CI and the hourly collector
├── backend/api.py         # FastAPI service
├── main.py                # Runs the API, the dashboard, or both
└── tests/
```

## Configuration

No API keys are needed.

| Variable | Purpose | Default |
| --- | --- | --- |
| `NEWS_SENTIMENT_DB` | SQLite file for scores and trend history | `data/news_sentiment.db` |
| `HF_HOME` | Hugging Face model cache | a directory under the system temp dir |
| `NEWS_HISTORY` | Collected `trend.csv`, as an https URL or a local path. `sources.csv` and `gdelt.csv` are read from the same directory. Empty uses only this instance's recordings and shows no GDELT tone | the `history` branch on GitHub |

The database keeps 120 days of headlines. Delete the file to start over.

## Collected history

A Space's disk is wiped on restart, so the dashboard cannot build a long trend
on its own. `.github/workflows/collect.yml` runs `python -m newsent.collect` at
17 minutes past every hour. Each run fetches every feed, scores only headlines
it has not seen before, and commits four things to the `history` branch:

- `days/YYYY-MM-DD.jsonl`, one scored headline per line, appended to the UTC
  day it was first seen. Files older than 120 days are deleted.
- `trend.csv`, the daily mean index per region over the last 90 days.
- `sources.csv`, the daily mean index per outlet over the last 90 days. Country
  pages read it from the same directory as `trend.csv`.
- `gdelt.csv`, the daily GDELT event tone and article count per region over
  the 90 days before today (UTC), with the columns `day,region,tone,articles`.

Each run downloads GDELT's event file
(`https://data.gdeltproject.org/events/YYYYMMDD.export.CSV.zip`, about 7 MB)
for every day missing from `gdelt.csv`, newest first, up to 15 files per run.
A new history branch fills its 90 days in six runs. After that, a run
downloads at most one file, yesterday's. GDELT publishes that file early in
the UTC day, so a run that gets a 404 skips the day and the next run tries
again. Any other GDELT error is logged and does not stop the headline
collection. The dashboard and the API never call GDELT themselves.

The dashboard and the API read the CSV files from `raw.githubusercontent.com`
and keep the result, or the error, for 15 minutes. A fork that enables the
workflow publishes its own history. Point `NEWS_HISTORY` at the fork's raw
URL. To collect without GitHub, run the collector from cron and set
`NEWS_HISTORY` to `<dir>/trend.csv`:

```bash
uv run python -m newsent.collect /var/lib/newsent-history
```

## Tests

```bash
uv sync --extra dev --extra api
uv run pytest -q
```

The tests cover feed parsing and deduplication, URL and redirect validation,
the score cache, trend aggregation, the collector and its fallback, GDELT event
file parsing and day selection, and every API route. None of them download the
model or touch the network. CI runs the same commands on every push to `main`
and on every pull request.

## Deploying to Hugging Face Spaces

The Space is a Docker Space built from `Dockerfile`, which runs `app.py` with
Streamlit on Python 3.12 and port 8501. It is not a Streamlit SDK Space because
that SDK installs `requirements.txt` together with unhashed packages of its own
in one `pip` command, and `--require-hashes` then rejects the whole install.

Every push to `main` deploys itself. After the tests pass, the `deploy-space`
job in `.github/workflows/ci.yml` uploads the app to the Space with the
`HF_TOKEN` repository secret. The Space's README is this README with
`.github/space/header.md` on top, which holds the Space settings
(`sdk: docker`, `app_port: 8501`). Edit that header to change the Space's
title or settings. The upload adds and updates files but never deletes them, so
remove a file from the Space by hand when you delete it here.

A Space's disk is wiped on restart. The model trend comes from the collected
history, so it survives restarts. To keep the instance's own fallback
recordings too, enable persistent storage and point `NEWS_SENTIMENT_DB` at
`/data/news_sentiment.db`.

`requirements.txt` is generated from `uv.lock`:

```bash
uv export --format requirements-txt --no-dev --no-emit-project --offline \
  --emit-index-url -o requirements.txt
```

Add `--require-hashes` below the index lines after regenerating. uv emits the
PyTorch CPU index globally because a requirements file cannot scope an index to
one package. The hashes still make the install integrity-safe, because every
package must match its locked hash. `requirements-api.txt` is the same export
with the `api` extra.

The CPU index exists only for the Linux `torch==2.7.1+cpu` wheel. The default
PyPI wheel on Linux pulls about 3 GB of CUDA packages that a CPU-only Space
cannot use.

## Troubleshooting

**No headlines are shown.** The app needs outbound HTTPS access to the feeds
listed on the **Sources** tab. If every feed fails, the app shows an error and
the feed statuses.

**The GDELT chart is empty.** The caption under the message names the reason.
The app reads GDELT tone only from the collected `gdelt.csv` and never calls
GDELT. If the caption says the collected GDELT history is unavailable, check
the latest run of the "Collect history" workflow. Its log names any day it
could not download.

**The model trend says "come back tomorrow".** The model trend needs at least
two days of data. The caption under the message names the source. If it says
collected history is unavailable, check the latest run of the "Collect
history" workflow.

## License

MIT. See [LICENSE](LICENSE).
