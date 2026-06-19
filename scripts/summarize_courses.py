#!/usr/bin/env python3

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.summarizer import CourseSummarizer


def main() -> None:
    summarizer = CourseSummarizer()
    print(summarizer.summarize(), end="")


if __name__ == "__main__":
    main()
