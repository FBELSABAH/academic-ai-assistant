#!/usr/bin/env python3

import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings
from src.db import init_db


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Initializing database at %s", settings.database_url)
    init_db()
    print("Database initialized successfully.")
    print("Expected SQLite location: data/academic.db")


if __name__ == "__main__":
    main()
