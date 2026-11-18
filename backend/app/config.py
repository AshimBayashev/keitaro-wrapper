import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class Settings:
    base_url = os.getenv("KEITARO_BASE_URL", "https://tlgk.host").rstrip("/")
    api_key = os.getenv("KEITARO_API_KEY", "")
    database_url = os.getenv("DATABASE_URL", "sqlite:///./keitaro.db")
    name_prefix = os.getenv("CAMPAIGN_NAME_PREFIX", "test_bayashev_")
    frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:4200")


settings = Settings()
