#!/usr/bin/env python3

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    print("Course scraping is not implemented yet.")
    print("TODO: Reuse the saved Moodle session and collect course metadata.")


if __name__ == "__main__":
    main()
