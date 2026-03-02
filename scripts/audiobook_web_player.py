#!/usr/bin/env python3
"""
Local audiobook web player server.

Features:
- Streams audio files from output/finished
- Lists available books via API
- Supports browser range requests for smooth seeking
- Serves a small web app from web-player/
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac"}


class AudiobookHandler(BaseHTTPRequestHandler):
    server_version = "AudiobookWebPlayer/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return

        if path == "/api/books":
            self._send_books()
            return

        if path.startswith("/api/stream/"):
            file_name = unquote(path.removeprefix("/api/stream/"))
            self._stream_file(file_name)
            return

        if path == "/" or path == "":
            self._serve_static("index.html")
            return

        if path.startswith("/"):
            self._serve_static(path[1:])
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, fmt: str, *args) -> None:
        # Keep logs concise in terminal.
        print(f"[web-player] {self.address_string()} - {fmt % args}")

    @property
    def books_dir(self) -> Path:
        return self.server.books_dir  # type: ignore[attr-defined]

    @property
    def static_dir(self) -> Path:
        return self.server.static_dir  # type: ignore[attr-defined]

    def _send_json(self, payload: object, status: int = HTTPStatus.OK) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self._safe_write(data)

    def _safe_write(self, data: bytes) -> bool:
        try:
            self.wfile.write(data)
            return True
        except (BrokenPipeError, ConnectionResetError):
            # Browsers may cancel range requests while preloading/seeking.
            return False

    def _send_books(self) -> None:
        books = []
        for file_path in sorted(self.books_dir.iterdir()):
            if not file_path.is_file() or file_path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            books.append(
                {
                    "name": file_path.name,
                    "size": file_path.stat().st_size,
                    "url": f"/api/stream/{file_path.name}",
                }
            )
        self._send_json({"books": books})

    def _serve_static(self, rel_path: str) -> None:
        rel_path = rel_path.split("?", 1)[0]
        requested = (self.static_dir / rel_path).resolve()

        if self.static_dir not in requested.parents and requested != self.static_dir:
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return

        if requested.is_dir():
            requested = requested / "index.html"

        if not requested.exists() or not requested.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        content_type = mimetypes.guess_type(str(requested))[0] or "application/octet-stream"
        data = requested.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self._safe_write(data)

    def _stream_file(self, file_name: str) -> None:
        safe_name = os.path.basename(file_name)
        if safe_name != file_name:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid file name")
            return

        file_path = (self.books_dir / safe_name).resolve()
        if not file_path.exists() or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return

        if self.books_dir not in file_path.parents:
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return

        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        file_size = file_path.stat().st_size
        range_header = self.headers.get("Range")

        if not range_header:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(file_size))
            self.end_headers()
            with file_path.open("rb") as f:
                self._safe_write(f.read())
            return

        match = re.match(r"bytes=(\d*)-(\d*)", range_header)
        if not match:
            self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, "Invalid range")
            return

        start_str, end_str = match.groups()
        if start_str == "" and end_str == "":
            self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, "Invalid range")
            return

        if start_str == "":
            length = int(end_str)
            start = max(file_size - length, 0)
            end = file_size - 1
        else:
            start = int(start_str)
            end = int(end_str) if end_str else file_size - 1

        if start >= file_size or start < 0 or end < start:
            self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, "Range out of bounds")
            return

        end = min(end, file_size - 1)
        chunk_size = end - start + 1

        self.send_response(HTTPStatus.PARTIAL_CONTENT)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Content-Length", str(chunk_size))
        self.end_headers()

        with file_path.open("rb") as f:
            f.seek(start)
            remaining = chunk_size
            while remaining > 0:
                chunk = f.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                if not self._safe_write(chunk):
                    break
                remaining -= len(chunk)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve local audiobook web player.")
    parser.add_argument(
        "--books-dir",
        default="output/finished",
        help="Directory containing finished audiobook files (default: output/finished)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for the local web server (default: 8000)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parent.parent
    books_dir = (root / args.books_dir).resolve()
    static_dir = (root / "web-player").resolve()

    if not books_dir.exists():
        raise SystemExit(f"Books directory does not exist: {books_dir}")
    if not static_dir.exists():
        raise SystemExit(f"Static web directory does not exist: {static_dir}")

    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), AudiobookHandler)
    httpd.books_dir = books_dir  # type: ignore[attr-defined]
    httpd.static_dir = static_dir  # type: ignore[attr-defined]

    print(f"Serving audiobook player at http://127.0.0.1:{args.port}")
    print(f"Streaming files from: {books_dir}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
