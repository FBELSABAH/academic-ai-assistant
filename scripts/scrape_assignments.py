#!/usr/bin/env python3

import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.moodle_scraper import MoodleScraper


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main() -> None:
    scraper = MoodleScraper()
    result = scraper.fetch_assignments_and_resources()

    for course_result in result.course_results:
        print(f"Course: {course_result.course_name}")
        print(f"Assignments found: {course_result.assignments_found}")
        print(f"Resources found: {course_result.resources_found}")
        print(f"Inserted: {course_result.inserted_count}")
        print(f"Updated: {course_result.updated_count}")
        if course_result.error:
            print(f"Error: {course_result.error}")
        if course_result.debug_html_path:
            print(f"Debug HTML: {course_result.debug_html_path}")
        print()


if __name__ == "__main__":
    main()
