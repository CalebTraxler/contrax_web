from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    anthropic_api_key: str = ""
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    base_url: str = "http://localhost:8080"
    report_price_cents: int = 1900
    skip_payments: bool = True
    mock_analysis: bool = True
    extraction_model: str = "claude-opus-4-8"
    research_model: str = "claude-opus-4-8"
    db_path: Path = DATA_DIR / "contrax.db"


settings = Settings()
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
