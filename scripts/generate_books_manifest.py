#!/usr/bin/env python3
"""
Generate a static web-player books.json manifest from local audiobook files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import quote


AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate web-player/books.json manifest.")
    parser.add_argument(
        "--books-dir",
        default="output/finished",
        help="Directory with audio files (default: output/finished)",
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help="Public base URL for audiobook files, e.g. https://pub-xxx.r2.dev",
    )
    parser.add_argument(
        "--out",
        default="web-player/books.json",
        help="Output manifest path (default: web-player/books.json)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parent.parent
    books_dir = (root / args.books_dir).resolve()
    out_path = (root / args.out).resolve()

    base_url = args.base_url.rstrip("/")
    books = []
    for file_path in sorted(books_dir.iterdir()):
        if not file_path.is_file() or file_path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        books.append(
            {
                "name": file_path.name,
                "size": file_path.stat().st_size,
                "url": f"{base_url}/{quote(file_path.name)}",
            }
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"books": books}, indent=2), encoding="utf-8")
    print(f"Wrote {out_path} with {len(books)} books")


if __name__ == "__main__":
    main()
