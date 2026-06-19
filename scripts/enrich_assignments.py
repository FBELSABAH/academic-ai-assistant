#!/usr/bin/env python3

import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.moodle_scraper import MoodleScraper


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main() -> None:
    scraper = MoodleScraper()
    results = scraper.enrich_assignment_details()

    for result in results:
        print(f"Assignment: {result.assignment_title}")
        print(f"Due at: {'found' if result.due_at_found else 'missing'}")
        print(f"Status: {'found' if result.status_found else 'missing'}")
        print(f"Updated: {result.updated_count}")
        if result.error:
            print(f"Error: {result.error}")
        if result.debug_html_path:
            print(f"Debug HTML: {result.debug_html_path}")
        print()


if __name__ == "__main__":
    main()
