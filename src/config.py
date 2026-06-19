from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    moodle_home_url: str = os.getenv("MOODLE_HOME_URL", "https://moodle31.upei.ca/")
    moodle_dashboard_url: str = os.getenv("MOODLE_DASHBOARD_URL", "https://moodle31.upei.ca/my/")
    moodle_courses_url: str = os.getenv("MOODLE_COURSES_URL", "https://moodle31.upei.ca/my/courses.php")
    moodle_calendar_export_url: str = os.getenv(
        "MOODLE_CALENDAR_EXPORT_URL",
        "https://moodle31.upei.ca/calendar/export.php",
    )
    moodle_calendar_ics_url: str = os.getenv("MOODLE_CALENDAR_ICS_URL", "")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3:8b")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///data/academic.db")
    playwright_storage_state: str = os.getenv("PLAYWRIGHT_STORAGE_STATE", "storage_state.json")
    local_timezone: str = os.getenv("LOCAL_TIMEZONE", "America/Halifax")


settings = Settings()
