#!/usr/bin/env python3

import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.moodle_scraper import MoodleScraper


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main() -> None:
    scraper = MoodleScraper()
    result = scraper.fetch_courses()

    print(f"Courses found: {result.found_count}")
    if result.courses:
        print("Course list:")
        for course in result.courses:
            print(f"- {course.name}")
            print(f"  {course.url}")

    print(f"Inserted: {result.inserted_count}")
    print(f"Updated: {result.updated_count}")

    if result.debug_html_path is not None:
        print(f"Debug HTML saved to: {result.debug_html_path}")


if __name__ == "__main__":
    main()
