#!/usr/bin/env python3

import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.moodle_browser import open_moodle_for_manual_login


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main() -> None:
    print("A browser window will open.")
    print("Log into Moodle manually.")
    print("Do not type your password into the code or terminal.")
    print("After the Moodle dashboard loads, return to the terminal and press Enter.")

    storage_path = open_moodle_for_manual_login()
    print(f"Saved Playwright session to: {storage_path}")


if __name__ == "__main__":
    main()
