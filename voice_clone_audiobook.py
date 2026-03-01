#!/usr/bin/env python3
"""Create an audiobook with a cloned voice (authorized use only)."""

from __future__ import annotations

import argparse
import importlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable, List, Tuple

SAFE_CHUNK_CHARS = 900
XTTS_SAFE_CHARS_EN = 450
XTTS_SAFE_TOKENS_EN = 320


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate audiobook audio from text using a cloned reference voice."
    )
    parser.add_argument("--input-text", required=True, help="Path to source text file.")
    parser.add_argument(
        "--reference-audio",
        required=True,
        help="Path to reference speaker audio (.wav recommended).",
    )
    parser.add_argument(
        "--consent-file",
        required=True,
        help="JSON file asserting rights/consent for the reference voice.",
    )
    parser.add_argument("--speaker-name", required=True, help="Speaker name in consent file.")
    parser.add_argument("--output", required=True, help="Final audiobook path (.wav or .mp3).")
    parser.add_argument(
        "--language",
        default="en",
        help="Target language code for synthesis (default: en).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=SAFE_CHUNK_CHARS,
        help="Chunk size for synthesis text. Keep moderate for stable quality.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=XTTS_SAFE_TOKENS_EN,
        help="Approximate token cap per chunk in API mode to avoid XTTS token-limit errors.",
    )
    parser.add_argument(
        "--backend",
        choices=["api", "cli"],
        default="api",
        help="`api` is faster (loads XTTS once). `cli` loads per chunk and is slower.",
    )
    parser.add_argument(
        "--work-dir",
        default="output/clone",
        help="Directory for intermediate audio chunks.",
    )
    parser.add_argument(
        "--keep-chunks",
        action="store_true",
        help="Keep intermediate chunk files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands only.",
    )
    return parser.parse_args()


def read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Input text not found: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("Input text file is empty.")
    return re.sub(r"\s+", " ", text)


def sentence_split(text: str) -> Iterable[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    if len(parts) == 1:
        parts = re.split(r"\n{2,}", text)
    return (p.strip() for p in parts if p.strip())


def estimate_tokens(text: str) -> int:
    # Conservative approximation for GPT-style tokenization.
    tokens = 0
    for item in re.findall(r"[A-Za-z0-9]+|[^A-Za-z0-9\s]", text):
        if re.match(r"[A-Za-z0-9]+$", item):
            tokens += max(1, (len(item) + 3) // 4)
        else:
            tokens += 1
    return tokens


def split_to_limits(text: str, max_chars: int, max_tokens: int) -> List[str]:
    words = text.split()
    out: List[str] = []
    piece = ""
    for word in words:
        candidate = f"{piece} {word}".strip() if piece else word
        if len(candidate) <= max_chars and estimate_tokens(candidate) <= max_tokens:
            piece = candidate
        else:
            if piece:
                out.append(piece)
            # Hard-wrap pathological words that exceed limits by themselves.
            if len(word) > max_chars:
                for i in range(0, len(word), max_chars):
                    wrapped = word[i : i + max_chars]
                    if estimate_tokens(wrapped) > max_tokens:
                        # Final guard for extremely dense strings.
                        step = max(8, max_chars // 2)
                        for j in range(0, len(wrapped), step):
                            out.append(wrapped[j : j + step])
                    else:
                        out.append(wrapped)
                piece = ""
            else:
                piece = word
    if piece:
        out.append(piece)
    return out


def chunk_text(text: str, chunk_size: int, max_tokens: int) -> List[str]:
    if chunk_size < 120:
        raise ValueError("--chunk-size too small; use >= 120.")
    if max_tokens < 80:
        raise ValueError("--max-tokens too small; use >= 80.")
    chunks: List[str] = []
    current = ""
    for sentence in sentence_split(text):
        if len(sentence) > chunk_size or estimate_tokens(sentence) > max_tokens:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(split_to_limits(sentence, chunk_size, max_tokens))
            continue

        trial = f"{current} {sentence}".strip() if current else sentence
        if len(trial) <= chunk_size and estimate_tokens(trial) <= max_tokens:
            current = trial
        else:
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def verify_consent(consent_path: Path, speaker_name: str) -> None:
    if not consent_path.exists():
        raise FileNotFoundError(f"Consent file not found: {consent_path}")
    data = json.loads(consent_path.read_text(encoding="utf-8"))
    required = ["speaker_name", "consent_granted", "rights_confirmed", "usage_scope"]
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"Consent file missing fields: {', '.join(missing)}")

    if data["speaker_name"] != speaker_name:
        raise ValueError("speaker_name does not match consent file.")
    if not data["consent_granted"] or not data["rights_confirmed"]:
        raise PermissionError(
            "Voice cloning blocked: consent_granted and rights_confirmed must both be true."
        )


def run(cmd: List[str], dry_run: bool) -> None:
    print("$ " + " ".join(cmd))
    if dry_run:
        return
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout, file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        raise RuntimeError(f"Command failed with exit code {proc.returncode}")


def format_seconds(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    mins, secs = divmod(total, 60)
    hrs, mins = divmod(mins, 60)
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def require_cmd(name: str, install_hint: str) -> str:
    path = shutil.which(name)
    if not path:
        raise FileNotFoundError(f"`{name}` not found. Install hint: {install_hint}")
    return path


def check_tts_runtime_compat() -> None:
    """Validate Coqui XTTS runtime deps before running synthesis."""
    try:
        torch = importlib.import_module("torch")
    except ImportError as exc:
        raise RuntimeError(
            "Missing `torch`. Install compatible deps with:\n"
            "python3 -m pip install 'torch==2.5.1' 'torchaudio==2.5.1'"
        ) from exc

    torch_version = getattr(torch, "__version__", "0")
    version_match = re.match(r"^(\d+)\.(\d+)", torch_version)
    if version_match:
        major = int(version_match.group(1))
        minor = int(version_match.group(2))
        if major > 2 or (major == 2 and minor >= 6):
            raise RuntimeError(
                "Incompatible torch version for XTTS checkpoint loading.\n"
                f"Installed: {torch_version}\n"
                "Fix with:\n"
                "python3 -m pip install --upgrade 'torch==2.5.1' 'torchaudio==2.5.1'"
            )

    try:
        transformers = importlib.import_module("transformers")
    except ImportError as exc:
        raise RuntimeError(
            "Missing `transformers`. Install compatible deps with:\n"
            "python3 -m pip install 'transformers<5' 'tokenizers<0.20'"
        ) from exc

    if not hasattr(transformers, "BeamSearchScorer"):
        version = getattr(transformers, "__version__", "unknown")
        raise RuntimeError(
            "Incompatible transformers version for XTTS.\n"
            f"Installed: {version}\n"
            "Fix with:\n"
            "python3 -m pip install --upgrade 'transformers<5' 'tokenizers<0.20'"
        )

    try:
        importlib.import_module("TTS")
    except ImportError as exc:
        raise RuntimeError(
            "Missing `TTS` package. Install with:\n"
            "python3 -m pip install TTS"
        ) from exc


def merge_with_ffmpeg(chunk_paths: List[Path], output: Path, dry_run: bool) -> None:
    ffmpeg = require_cmd("ffmpeg", "brew install ffmpeg")
    if len(chunk_paths) == 1:
        run([ffmpeg, "-y", "-i", str(chunk_paths[0]), str(output)], dry_run=dry_run)
        return
    concat_file = output.with_suffix(output.suffix + ".concat.txt")
    concat_file.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in chunk_paths) + "\n",
        encoding="utf-8",
    )
    run(
        [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(output),
        ],
        dry_run=dry_run,
    )
    if not dry_run and concat_file.exists():
        concat_file.unlink()


def is_xtts_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return ("maximum of 400 tokens" in text) or ("character limit of 250" in text)


def is_mps_unsupported_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return ("mps device" in text and "not supported" in text) or (
        "pytorch_enable_mps_fallback" in text
    )


def split_chunk_for_retry(chunk: str) -> Tuple[str, str]:
    words = chunk.split()
    if len(words) < 2:
        mid = max(1, len(chunk) // 2)
        return chunk[:mid].strip(), chunk[mid:].strip()
    mid = len(words) // 2
    left = " ".join(words[:mid]).strip()
    right = " ".join(words[mid:]).strip()
    if not left or not right:
        mid = max(1, len(chunk) // 2)
        return chunk[:mid].strip(), chunk[mid:].strip()
    return left, right


def main() -> int:
    args = parse_args()
    input_text = Path(args.input_text).expanduser().resolve()
    reference_audio = Path(args.reference_audio).expanduser().resolve()
    consent_file = Path(args.consent_file).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    work_dir = Path(args.work_dir).expanduser().resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    if not reference_audio.exists():
        raise FileNotFoundError(f"Reference audio not found: {reference_audio}")

    verify_consent(consent_file, args.speaker_name)
    text = read_text(input_text)
    effective_chunk_size = args.chunk_size
    effective_max_tokens = args.max_tokens
    if args.backend == "api" and args.language.lower().startswith("en"):
        if args.chunk_size > XTTS_SAFE_CHARS_EN:
            print(
                "Note: XTTS English API mode is sensitive to long input. "
                f"Auto-capping chunk size to {XTTS_SAFE_CHARS_EN} characters."
            )
        effective_chunk_size = min(args.chunk_size, XTTS_SAFE_CHARS_EN)
        if args.max_tokens > XTTS_SAFE_TOKENS_EN:
            print(
                "Note: Auto-capping max tokens for XTTS English API mode to "
                f"{XTTS_SAFE_TOKENS_EN}."
            )
        effective_max_tokens = min(args.max_tokens, XTTS_SAFE_TOKENS_EN)
    chunks = chunk_text(text, effective_chunk_size, effective_max_tokens)

    check_tts_runtime_compat()
    tts_cmd: str | None = None
    if args.backend == "cli":
        tts_cmd = require_cmd(
            "tts",
            "python3 -m pip install TTS",
        )
    print(
        "Disclosure: This output is AI-generated from a cloned voice and should be used only with authorization."
    )
    print(f"Chunks: {len(chunks)}")
    print(f"Backend: {args.backend}")
    print(f"Chunk size: {effective_chunk_size}")
    print(f"Max tokens/chunk: {effective_max_tokens}")

    tts_model = None
    device = "cpu"
    if args.backend == "api" and not args.dry_run:
        torch = importlib.import_module("torch")
        tts_api_mod = importlib.import_module("TTS.api")
        tts_cls = getattr(tts_api_mod, "TTS")
        if torch.cuda.is_available():
            device = "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"
        print(f"Loading XTTS model once on device: {device}")
        tts_model = tts_cls(model_name="tts_models/multilingual/multi-dataset/xtts_v2").to(
            device
        )
    started_at = time.perf_counter()

    chunk_files: List[Path] = []
    pending_chunks: List[Tuple[str, int]] = [(c, 0) for c in chunks]
    i = 0
    while pending_chunks:
        chunk, split_depth = pending_chunks.pop(0)
        i += 1
        out_chunk = work_dir / f"{output_path.stem}.part{i:04d}.wav"
        before = time.perf_counter()
        done = i - 1
        total = done + len(pending_chunks) + 1
        if done > 0:
            elapsed = before - started_at
            avg_per_chunk = elapsed / done
            eta = avg_per_chunk * (total - done)
            print(
                f"[{i}/{total}] Starting chunk ({len(chunk)} chars, "
                f"~{estimate_tokens(chunk)} tokens) | "
                f"Elapsed: {format_seconds(elapsed)} | "
                f"ETA: {format_seconds(eta)}"
            )
        else:
            print(
                f"[{i}/{total}] Starting chunk ({len(chunk)} chars, "
                f"~{estimate_tokens(chunk)} tokens)"
            )
        try:
            if args.backend == "cli":
                if not tts_cmd:
                    raise RuntimeError("`tts` CLI command not resolved.")
                cmd = [
                    tts_cmd,
                    "--text",
                    chunk,
                    "--model_name",
                    "tts_models/multilingual/multi-dataset/xtts_v2",
                    "--speaker_wav",
                    str(reference_audio),
                    "--language_idx",
                    args.language,
                    "--out_path",
                    str(out_chunk),
                ]
                run(cmd, dry_run=args.dry_run)
            else:
                if args.dry_run:
                    print(
                        "$ XTTS_API tts_to_file "
                        f"--text '{chunk[:50]}...' "
                        f"--speaker_wav {reference_audio} "
                        f"--language {args.language} "
                        f"--file_path {out_chunk}"
                    )
                else:
                    if tts_model is None:
                        raise RuntimeError("XTTS API model failed to initialize.")
                    try:
                        tts_model.tts_to_file(
                            text=chunk,
                            speaker_wav=str(reference_audio),
                            language=args.language,
                            file_path=str(out_chunk),
                        )
                    except Exception as inner_exc:
                        if device == "mps" and is_mps_unsupported_error(inner_exc):
                            print(
                                "MPS op unsupported for this chunk. "
                                "Switching XTTS runtime to CPU and retrying."
                            )
                            tts_model = tts_model.to("cpu")
                            device = "cpu"
                            tts_model.tts_to_file(
                                text=chunk,
                                speaker_wav=str(reference_audio),
                                language=args.language,
                                file_path=str(out_chunk),
                            )
                        else:
                            raise
        except Exception as exc:
            if args.backend == "api" and is_xtts_limit_error(exc) and split_depth < 6:
                left, right = split_chunk_for_retry(chunk)
                print(
                    f"Retry split: chunk exceeded XTTS limit; splitting into "
                    f"{len(left)} and {len(right)} chars."
                )
                if out_chunk.exists():
                    out_chunk.unlink()
                i -= 1
                pending_chunks.insert(0, (right, split_depth + 1))
                pending_chunks.insert(0, (left, split_depth + 1))
                continue
            raise
        chunk_files.append(out_chunk)
        after = time.perf_counter()
        chunk_elapsed = after - before
        total_elapsed = after - started_at
        avg_per_chunk = total_elapsed / i
        remaining = len(pending_chunks)
        eta = avg_per_chunk * remaining
        print(
            f"[{i}/{i + remaining}] Done in {format_seconds(chunk_elapsed)} | "
            f"Total: {format_seconds(total_elapsed)} | "
            f"Remaining ETA: {format_seconds(eta)}"
        )

    merge_with_ffmpeg(chunk_files, output_path, dry_run=args.dry_run)

    if not args.keep_chunks and not args.dry_run:
        for file in chunk_files:
            if file.exists():
                file.unlink()

    print(f"Created audiobook: {output_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
