"""Central configuration. All values come from environment variables with
sensible zero-config defaults for local development."""
from __future__ import annotations
import os
from functools import lru_cache


def _default_db_url() -> str:
    # Local dev: a SQLite file next to the backend package.
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend/app
    root = os.path.dirname(here)  # backend/
    return "sqlite:///" + os.path.join(root, "crowdlens.db")


class Settings:
    # --- database --------------------------------------------------------
    # PostgreSQL example:  postgresql+psycopg://user:pass@localhost:5432/crowdlens
    DATABASE_URL: str = os.environ.get("DATABASE_URL") or os.environ.get("CROWDLENS_DB_URL") or _default_db_url()

    # Back-compat: the old CROWDLENS_DB pointed at a bare sqlite file path.
    _legacy = os.environ.get("CROWDLENS_DB")
    if _legacy and "://" not in _legacy and not os.environ.get("DATABASE_URL"):
        DATABASE_URL = "sqlite:///" + _legacy

    # --- ML service -----------------------------------------------------
    ML_SERVICE_URL: str = os.environ.get("ML_SERVICE_URL", "http://localhost:8001")
    ML_SERVICE_TIMEOUT: float = float(os.environ.get("ML_SERVICE_TIMEOUT", "5.0"))

    # --- app ----------------------------------------------------------
    APP_NAME: str = "CROWDLENS API"
    APP_VERSION: str = "1.0.0"
    CORS_ORIGINS: list[str] = (os.environ.get("CORS_ORIGINS", "*").split(","))

    # Directory for uploaded video files (never contains identity data).
    UPLOAD_DIR: str = os.environ.get(
        "CROWDLENS_UPLOAD_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads"),
    )

    # Default prediction horizon (seconds) used by the forecasting logic.
    PREDICTION_HORIZON_SEC: int = int(os.environ.get("PREDICTION_HORIZON_SEC", "20"))

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    os.makedirs(s.UPLOAD_DIR, exist_ok=True)
    return s


settings = get_settings()
