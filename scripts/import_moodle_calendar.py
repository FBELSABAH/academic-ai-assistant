#!/usr/bin/env python3

import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.calendar_importer import MissingCalendarUrlError, MoodleCalendarImporter


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main() -> None:
    importer = MoodleCalendarImporter()

    try:
        result = importer.import_from_ics()
    except MissingCalendarUrlError as exc:
        print(str(exc))
        return

    print(f"Events found: {result.events_found}")
    print(f"Inserted: {result.inserted}")
    print(f"Updated: {result.updated}")
    print(f"Skipped: {result.skipped}")
    print(f"Errors: {result.errors}")


if __name__ == "__main__":
    main()
