#!/usr/bin/env python3
"""Convert a PDF file to text using the same base filename."""

from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a PDF to a .txt file with the same base name."
    )
    parser.add_argument("pdf", help="Path to the input PDF file.")
    parser.add_argument(
        "--out-dir",
        help="Optional output directory for the .txt file (default: PDF directory).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the output .txt file if it already exists.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError("Input file must be a .pdf")

    out_dir = (
        Path(args.out_dir).expanduser().resolve() if args.out_dir else pdf_path.parent
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    txt_path = out_dir / f"{pdf_path.stem}.txt"

    if txt_path.exists() and not args.overwrite:
        raise FileExistsError(
            f"Output already exists: {txt_path}. Use --overwrite to replace it."
        )

    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency: pypdf. Install with `python3 -m pip install pypdf`."
        ) from exc

    reader = PdfReader(str(pdf_path))
    pages = []
    for page in reader.pages:
        pages.append((page.extract_text() or "").strip())

    text = "\n\n".join(p for p in pages if p)
    txt_path.write_text(text, encoding="utf-8")
    print(f"PDF: {pdf_path}")
    print(f"TXT: {txt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
