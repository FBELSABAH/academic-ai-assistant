#!/usr/bin/env python3

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    print("Moodle calendar import is not implemented yet.")
    print("TODO: Import Moodle calendar events from ICS or export endpoints into SQLite.")


if __name__ == "__main__":
    main()
