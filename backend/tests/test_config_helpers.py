from app.utils.config import _csv_env, _database_url


def test_database_url_normalizes_render_postgres_url():
    assert _database_url("postgres://u:p@host/db") == "postgresql+asyncpg://u:p@host/db"


def test_database_url_preserves_asyncpg_url():
    url = "postgresql+asyncpg://u:p@host/db"
    assert _database_url(url) == url


def test_csv_env_uses_defaults_when_missing(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS_TEST", raising=False)
    assert _csv_env("ALLOWED_ORIGINS_TEST", ["http://localhost"]) == ["http://localhost"]


def test_csv_env_parses_comma_separated_values(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS_TEST", "https://a.com, https://b.com")
    assert _csv_env("ALLOWED_ORIGINS_TEST", []) == ["https://a.com", "https://b.com"]
