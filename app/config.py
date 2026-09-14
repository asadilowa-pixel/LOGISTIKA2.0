from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "default"

    dashboard_user: str = "admin"
    dashboard_password: str = "admin"

    telegram_bot_token: str = ""
    telegram_chat_id: int = 0
    alert_hours_before_deadline: float = 4.0
    fbs_poll_interval_minutes: int = 15
    wb_assembly_hours: float = 48.0
    wb_coefficient_alert_cooldown_minutes: int = 60
    ozon_watch_poll_interval_seconds: int = 90
    wb_coefficient_poll_interval_minutes: int = 10


settings = Settings()
