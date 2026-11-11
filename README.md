---
title: Real-time News Sentiment Analysis
emoji: 📊
colorFrom: blue
colorTo: green
sdk: streamlit
sdk_version: 1.48.0
app_file: app.py
python_version: "3.12"
pinned: false
license: mit
---

# Real-time News Sentiment Analysis Dashboard

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Streamlit dashboard that pulls headlines from public RSS feeds, runs sentiment
analysis with a Hugging Face Transformers model, and visualises the results.

- Live demo: <https://huggingface.co/spaces/iamaber/Real-time-News-Sentiment-Analysis>
- GitHub: <https://github.com/iamaber/realtime-news-sentiment>

## Features

- Fetches headlines from seven public RSS feeds (no API key required)
- Sentiment analysis with `distilbert-base-uncased-finetuned-sst-2-english`
- Positive/negative distribution chart and summary metrics
- Bounded, cached fetching (five-minute TTL, 50 headlines, one cache entry)
- Clear in-app messages when a feed is unreachable or no feed responds
- Optional FastAPI service exposing the same sentiment logic over HTTP

## Model and limitations

- Model:
  [`distilbert-base-uncased-finetuned-sst-2-english`](https://huggingface.co/distilbert/distilbert-base-uncased-finetuned-sst-2-english),
  pinned to revision `714eb0fa89d2f80546fda750413ed43d93601a13` so a Hub
  update cannot silently change predictions.
- License: Apache-2.0, as stated on the model card.
- The model was fine-tuned on SST-2, a dataset of movie-review sentences. It is
  a two-class (`POSITIVE` / `NEGATIVE`) classifier and has no neutral class.
- Applying it to news headlines is a domain shift. Treat the labels as rough
  signals, not ground truth.
- "Mean Model Score" is the average softmax score of the predicted label, not
  accuracy. This repository does not claim a measured accuracy for news
  headlines.

## Project structure

```
.
├── app.py                     # Single Streamlit entry point (local + Space)
├── model_config.py            # Pinned model id and Hub revision
├── news_sources.py            # Bounded RSS fetching
├── sentiment_utils.py         # Pure dedupe / normalization / aggregation logic
├── tests/                     # pytest tests for fetching, API and pure logic
├── backend/                   # Optional FastAPI service
│   ├── api.py
│   └── services/
├── main.py                    # Convenience runner for the dashboard + API
├── requirements.txt           # Hash-pinned runtime dependencies
├── requirements-api.txt       # Hash-pinned runtime + optional FastAPI deps
├── pyproject.toml             # uv project metadata
├── .github/workflows/ci.yml   # Test workflow
└── uv.lock
```

`app.py` is the only Streamlit entry point. It fetches RSS directly and runs the
model in-process, so it works on a Hugging Face Space without a separate
backend. The FastAPI service in `backend/` is optional.

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

Open <http://localhost:8501>.

The dashboard loads the sentiment model on first analysis. The model is roughly
260 MB and is cached for the life of the process.

### Optional FastAPI service

```bash
uv sync --extra api
uv run python main.py --mode backend
```

- API: <http://localhost:8000>
- Interactive docs: <http://localhost:8000/docs>
- Readiness: <http://localhost:8000/ready> (503 until the model is loaded)
- Liveness: <http://localhost:8000/health>

`uv run python main.py --mode all` starts the API and the dashboard together.

Both processes bind to `127.0.0.1` by default. The API is unauthenticated and
runs expensive inference, so it also limits clients to 10 requests per minute
and two concurrent inference requests. Pass `--host 0.0.0.0` only when you
intend to expose it, and put an authenticating proxy in front.

## Configuration

No secrets or API keys are required. The dashboard reads public RSS feeds.

| Variable | Purpose | Default |
| --- | --- | --- |
| `HF_HOME` | Directory for the Hugging Face model cache | a temp directory under `/tmp` |

## Tests

```bash
uv sync --extra dev --extra api
uv run pytest -q
```

The tests cover headline extraction, order-preserving deduplication, feed
fetching with mocked feeds, the FastAPI routes, sentiment normalization and
aggregation. None of them download the model. CI runs the same commands on
every push and pull request.

API tests need the `api` extra (FastAPI) and `httpx`; they are skipped when
those packages are not installed.

## Deploying to Hugging Face Spaces

The Space runs as a Streamlit SDK app (`sdk: streamlit`, `app_file: app.py`,
Python 3.12), as declared in this README's frontmatter.

- Dependencies are installed from the hash-pinned `requirements.txt`
- Only `app.py`, `model_config.py`, `news_sources.py`, `sentiment_utils.py`,
  `requirements.txt` and this README are needed at runtime

`requirements.txt` is generated from `uv.lock`:

```bash
uv export --format requirements-txt --no-dev --no-emit-project --offline \
  --emit-index-url -o requirements.txt
```

Add `--require-hashes` below the index lines after regenerating. uv emits the
PyTorch CPU index globally because a requirements file cannot scope an index to
a single package. The hashes still make the install integrity-safe: every
package must match the locked hash, so nothing from either index can shadow a
pinned dependency. pip also enables hash checking automatically whenever hashes
are present. `requirements-api.txt` is the equivalent export with the `api`
extra.

The CPU index is needed only for the Linux `torch==2.7.1+cpu` wheel. Pulling the
default PyPI `torch` wheel on Linux also pulls CUDA libraries and driver
packages (`nvidia-*`, `triton`, about 3 GB of wheels). This dashboard runs on CPU
only, so the CPU index keeps the install small and avoids filling the Space's
ephemeral disk.

## Troubleshooting

**No headlines are shown.** The Space needs outbound network access to the RSS
feeds listed in the sidebar. If every feed fails, the app shows an error instead
of crashing.

**The model takes a while on first run.** It is downloaded once per process and
cached. `st.cache_resource` prevents reloading it on every Streamlit rerun.

**Storage errors on a Space.** Make sure `requirements.txt` still points at the
CPU PyTorch wheel, and do not commit virtual environments, caches or model
weights. `.gitignore` covers these.

## License

MIT — see [LICENSE](LICENSE).
