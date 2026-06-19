#!/usr/bin/env python3

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.summarizer import CourseSummarizer


def main() -> None:
    summarizer = CourseSummarizer()
    result = summarizer.build_summary(include_llm=True)
    print(result.rule_summary, end="")
    if result.llm_summary:
        print("\nOptional Ollama Summary")
        print(result.llm_summary)
    if result.llm_warning:
        print("\nWarning")
        print(result.llm_warning)


if __name__ == "__main__":
    main()
