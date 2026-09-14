from app.config import Settings


def test_settings_ignores_undeclared_env_keys(tmp_path, monkeypatch):
    monkeypatch.delenv("CLICKHOUSE_HOST", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "CLICKHOUSE_HOST=localhost\n"
        "OZON_CABINET_1_NAME=Кабинет 1\n"
        "OZON_CABINET_1_CLIENT_ID=123\n"
        "OZON_CABINET_1_API_KEY=abc\n"
        "WB_CABINET_1_NAME=Кабинет 1\n"
        "WB_CABINET_1_TOKEN=tok\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    settings = Settings()

    assert settings.clickhouse_host == "localhost"
