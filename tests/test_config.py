import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_reads_required_and_default_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TFL_APP_KEY", "test-key")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://tfl:tfl@localhost:5432/tfl_disruption_history"
    )

    settings = Settings()

    assert settings.tfl_app_key == "test-key"
    assert settings.environment == "local"
    assert settings.log_level == "INFO"


def test_settings_requires_tfl_app_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TFL_APP_KEY", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://tfl:tfl@localhost:5432/tfl_disruption_history"
    )

    with pytest.raises(ValidationError):
        Settings()
