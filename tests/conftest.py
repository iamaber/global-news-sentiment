import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    path = tmp_path / "news.db"
    monkeypatch.setenv("NEWS_SENTIMENT_DB", str(path))
    return path


@pytest.fixture(autouse=True)
def no_collected_history(monkeypatch):
    from newsent import history

    monkeypatch.setattr(history, "HISTORY_SOURCE", "")
