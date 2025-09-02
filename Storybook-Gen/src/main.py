from __future__ import annotations

import argparse
from pathlib import Path

from .models import StoryRequest
from .orchestrator import run_pipeline
from .utils import load_environment


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AG2 Storybook Demo")
    p.add_argument("--name", required=True, help="Child's name")
    p.add_argument("--age", required=True, type=int, help="Child's age")
    p.add_argument("--interests", default=None, help="Comma-separated interests")
    p.add_argument("--pages", type=int, default=None, help="Page count override")
    return p.parse_args()


def main() -> None:
    load_environment()
    args = parse_args()

    req = StoryRequest(
        child_name=args.name,
        child_age=args.age,
        interests=args.interests,
        page_count=args.pages or 10,
    )

    result = run_pipeline(req)
    print("Output directory:", result.output_dir)
    print("Cover image:", result.cover_image_path)
    print("PDF:", result.pdf_path)


if __name__ == "__main__":
    main() 