# Real-time News Sentiment Analysis Dashboard

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Streamlit dashboard that pulls headlines from public RSS feeds, runs sentiment
analysis with a Hugging Face Transformers model, and visualises the results.

- Live demo: <https://huggingface.co/spaces/iamaber/Real-time-News-Sentiment-Analysis>
- GitHub: <https://github.com/iamaber/realtime-news-sentiment>

## Features

- Fetches headlines from eight public RSS feeds (no API key required)
- Sentiment analysis with `distilbert-base-uncased-finetuned-sst-2-english`
- Positive/negative distribution chart and summary metrics
- Bounded, cached fetching (five-minute TTL, 50 headlines, one cache entry)
- Clear in-app messages when a feed is unreachable or no feed responds
- Optional FastAPI service exposing the same sentiment logic over HTTP

## Project structure

```
.
├── app.py                     # Single Streamlit entry point (local + Space)
├── news_sources.py            # Bounded RSS fetching
├── sentiment_utils.py         # Pure dedupe / normalization / aggregation logic
├── tests/                     # pytest tests for the pure logic
├── backend/                   # Optional FastAPI service
│   ├── api.py
│   └── services/
├── main.py                    # Convenience runner for the dashboard + API
├── requirements.txt           # Pinned runtime dependencies
├── requirements-api.txt       # Runtime + optional FastAPI dependencies
├── pyproject.toml             # uv project metadata
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

`uv run python main.py --mode all` starts the API and the dashboard together.

## Configuration

No secrets or API keys are required. The dashboard reads public RSS feeds.

| Variable | Purpose | Default |
| --- | --- | --- |
| `HF_HOME` | Directory for the Hugging Face model cache | a temp directory under `/tmp` |

## Tests

```bash
uv run --extra dev pytest -q
```

The tests cover headline extraction, order-preserving deduplication, sentiment
normalization and aggregation, and require no model download.

## Deploying to Hugging Face Spaces

The Space runs as a Streamlit SDK app:

- `app_file: app.py`
- Dependencies are installed from the pinned `requirements.txt`
- Only `app.py`, `news_sources.py`, `sentiment_utils.py`, `requirements.txt` and
  this README are needed at runtime

`requirements.txt` installs the CPU build of PyTorch on Linux:

```
--extra-index-url https://download.pytorch.org/whl/cpu
torch==2.7.1+cpu; sys_platform == "linux"
```

Pulling the default PyPI `torch` wheel on Linux also pulls CUDA libraries and
driver packages (`nvidia-*`, `triton`, about 3 GB of wheels). This dashboard runs
on CPU only, so the CPU index keeps the install small and avoids filling the
Space's ephemeral disk.

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
