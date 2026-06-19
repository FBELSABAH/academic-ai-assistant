#!/usr/bin/env python3

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.calendar_exporter import CalendarExporter


def main() -> None:
    exporter = CalendarExporter()
    result = exporter.export()
    print(f"Events exported: {result.events_exported}")
    print(f"Output path: {result.output_path}")
    print(f"Skipped events: {result.skipped_events}")


if __name__ == "__main__":
    main()
