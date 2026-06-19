#!/usr/bin/env python3

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    print("ICS export is not implemented yet.")
    print("TODO: Export selected local deadlines and events as a clean calendar feed.")


if __name__ == "__main__":
    main()
