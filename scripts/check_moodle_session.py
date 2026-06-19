#!/usr/bin/env python3

import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.moodle_browser import open_moodle_with_saved_session


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main() -> None:
    result = open_moodle_with_saved_session()

    print(f"Checked URL: {result['current_url'] or '(no page loaded)'}")
    print(f"Page title: {result['title'] or '(unknown)'}")

    if result["valid"]:
        print("Result: session valid.")
        print(result["reason"])
        return

    print("Result: session missing/expired and login_moodle.py should be rerun.")
    print(result["reason"])


if __name__ == "__main__":
    main()
