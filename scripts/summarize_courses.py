#!/usr/bin/env python3

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    print("Course summarization is not implemented yet.")
    print("TODO: Send local course data to Ollama and generate actionable summaries.")


if __name__ == "__main__":
    main()
