#!/usr/bin/env python3
"""Create an audiobook from a plain text file using free or OpenAI TTS."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List

MAX_INPUT_CHARS = 4096
SAFE_CHUNK_CHARS = 3600

ALL_VOICES = [
    "alloy",
    "ash",
    "ballad",
    "cedar",
    "coral",
    "echo",
    "fable",
    "marin",
    "nova",
    "onyx",
    "sage",
    "shimmer",
    "verse",
]

FEMALE_PRESETS_OPENAI = {
    "warm": {
        "voice": "marin",
        "instructions": (
            "Voice Affect: Warm and human.\n"
            "Tone: Friendly and natural.\n"
            "Pacing: Steady and moderate.\n"
            "Emotion: Gentle and engaging.\n"
            "Delivery: Smooth narration for long-form listening."
        ),
    },
    "clear": {
        "voice": "nova",
        "instructions": (
            "Voice Affect: Clear and polished.\n"
            "Tone: Professional and approachable.\n"
            "Pacing: Moderate and consistent.\n"
            "Pronunciation: Crisp with careful enunciation.\n"
            "Delivery: Clean audiobook narration."
        ),
    },
    "soft": {
        "voice": "shimmer",
        "instructions": (
            "Voice Affect: Soft and soothing.\n"
            "Tone: Calm and reassuring.\n"
            "Pacing: Slightly slow and unhurried.\n"
            "Emotion: Subtle warmth.\n"
            "Delivery: Relaxed cadence with gentle pauses."
        ),
    },
    "confident": {
        "voice": "sage",
        "instructions": (
            "Voice Affect: Confident and composed.\n"
            "Tone: Conversational and assured.\n"
            "Pacing: Steady with clear phrasing.\n"
            "Emphasis: Highlight key ideas naturally.\n"
            "Delivery: Balanced, human, and expressive."
        ),
    },
}

FEMALE_PRESETS_MACOS = {
    "warm": {"voice": "Samantha"},
    "clear": {"voice": "Allison"},
    "soft": {"voice": "Ava"},
    "confident": {"voice": "Karen"},
}

FEMALE_PRESETS_EDGE = {
    "warm": {"voice": "en-US-JennyNeural"},
    "clear": {"voice": "en-US-AriaNeural"},
    "soft": {"voice": "en-US-AvaMultilingualNeural"},
    "confident": {"voice": "en-US-EmmaNeural"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an audiobook from a text file."
    )
    parser.add_argument(
        "--engine",
        choices=["edge", "macos", "openai"],
        default="edge",
        help="TTS engine. `edge` is free neural quality (no API key).",
    )
    parser.add_argument("--input", help="Path to source text file.")
    parser.add_argument(
        "--output",
        help="Final output audio file path (.mp3/.wav/etc).",
    )
    parser.add_argument(
        "--preset",
        choices=["warm", "clear", "soft", "confident"],
        default="warm",
        help="Female-style voice preset.",
    )
    parser.add_argument(
        "--voice",
        help="Override preset voice. For `openai`, use built-in voice names.",
    )
    parser.add_argument(
        "--instructions",
        help="Extra style instructions appended to the preset instructions.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=SAFE_CHUNK_CHARS,
        help=f"Chunk size target; must be <= {MAX_INPUT_CHARS}.",
    )
    parser.add_argument(
        "--format",
        default="mp3",
        choices=["mp3", "wav", "flac", "aac", "opus", "pcm"],
        help="Intermediate/output audio format for synthesis requests.",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini-tts-2025-12-15",
        help="OpenAI speech model.",
    )
    parser.add_argument(
        "--speed", type=float, default=1.0, help="Speech speed (0.25 to 4.0)."
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="List available voices for the selected engine and exit.",
    )
    parser.add_argument(
        "--work-dir",
        default="output/speech",
        help="Directory for intermediate chunk files.",
    )
    parser.add_argument(
        "--keep-chunks",
        action="store_true",
        help="Keep generated chunk files and concat list.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would run without making API calls.",
    )
    parser.add_argument(
        "--tts-cli",
        help=(
            "Path to text_to_speech.py. Defaults to "
            "$CODEX_HOME/skills/speech/scripts/text_to_speech.py."
        ),
    )
    return parser.parse_args()


def resolve_tts_cli(explicit_path: str | None) -> Path:
    if explicit_path:
        candidate = Path(explicit_path).expanduser().resolve()
    else:
        codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        candidate = codex_home / "skills" / "speech" / "scripts" / "text_to_speech.py"
    if not candidate.exists():
        raise FileNotFoundError(
            "Unable to find speech CLI at "
            f"'{candidate}'. Pass --tts-cli with the correct path."
        )
    return candidate


def list_macos_voices() -> List[str]:
    say_cmd = shutil.which("say")
    if not say_cmd:
        raise FileNotFoundError("macOS `say` command not found.")
    result = subprocess.run([say_cmd, "-v", "?"], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("Failed to list macOS voices with `say -v ?`.")

    voices: List[str] = []
    for line in result.stdout.splitlines():
        if "#" not in line:
            continue
        voice = line.split("#", 1)[0].strip()
        match = re.match(r"^(.*?)\s+[a-z]{2}_[A-Z]{2}$", voice)
        if match:
            voices.append(match.group(1).strip())
    return voices


def resolve_edge_tts() -> str:
    edge_cmd = shutil.which("edge-tts")
    if not edge_cmd:
        raise FileNotFoundError(
            "`edge-tts` is not installed. Install it with: python3 -m pip install edge-tts"
        )
    return edge_cmd


def list_edge_voices() -> List[str]:
    edge_cmd = resolve_edge_tts()
    result = subprocess.run([edge_cmd, "--list-voices"], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("Failed to list edge voices with `edge-tts --list-voices`.")

    voices: List[str] = []
    for line in result.stdout.splitlines():
        match = re.search(r"Name:\s*([A-Za-z0-9\-]+)", line)
        if match:
            voices.append(match.group(1))
    return voices


def load_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"\r\n?", "\n", text).strip()
    if not text:
        raise ValueError("Input file is empty.")
    return text


def sentence_split(text: str) -> Iterable[str]:
    # Split on sentence boundaries while preserving punctuation.
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", text)
    if len(parts) == 1:
        # Fallback split for texts lacking sentence punctuation/case patterns.
        parts = re.split(r"\n{2,}", text)
    return (p.strip() for p in parts if p.strip())


def chunk_text(text: str, chunk_size: int) -> List[str]:
    if chunk_size > MAX_INPUT_CHARS:
        raise ValueError(f"--chunk-size must be <= {MAX_INPUT_CHARS}.")
    if chunk_size < 500:
        raise ValueError("--chunk-size is too small; use at least 500.")

    chunks: List[str] = []
    current = ""
    for sentence in sentence_split(text):
        if len(sentence) > MAX_INPUT_CHARS:
            # Hard-wrap very long lines when natural boundaries are missing.
            for i in range(0, len(sentence), chunk_size):
                piece = sentence[i : i + chunk_size].strip()
                if piece:
                    chunks.append(piece)
            continue
        trial = f"{current} {sentence}".strip() if current else sentence
        if len(trial) <= chunk_size:
            current = trial
        else:
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def run_cmd(cmd: List[str], dry_run: bool) -> None:
    print("$ " + " ".join(cmd))
    if dry_run:
        return
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"Command failed with exit code {result.returncode}")


def concat_audio_with_ffmpeg(
    chunk_files: List[Path], output_file: Path, dry_run: bool, copy_codec: bool
) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FileNotFoundError("ffmpeg not found.")

    if len(chunk_files) == 1:
        cmd = [ffmpeg, "-y", "-i", str(chunk_files[0])]
        if copy_codec:
            cmd.extend(["-c", "copy"])
        cmd.append(str(output_file))
        run_cmd(cmd, dry_run=dry_run)
        return

    list_file = output_file.with_suffix(output_file.suffix + ".concat.txt")
    list_lines = [f"file '{p.resolve()}'" for p in chunk_files]
    list_file.write_text("\n".join(list_lines) + "\n", encoding="utf-8")

    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        str(output_file),
    ]
    if copy_codec:
        cmd[8:8] = ["-c", "copy"]
    run_cmd(cmd, dry_run=dry_run)


def main() -> int:
    args = parse_args()
    if args.list_voices:
        if args.engine == "macos":
            print("macOS voices:")
            for v in list_macos_voices():
                print(f"- {v}")
        elif args.engine == "edge":
            print("Edge neural voices:")
            for v in list_edge_voices():
                print(f"- {v}")
        else:
            print("OpenAI built-in voices:")
            for v in ALL_VOICES:
                print(f"- {v}")
        return 0

    if not args.input or not args.output:
        raise ValueError("--input and --output are required unless --list-voices is used.")

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    work_dir = Path(args.work_dir).expanduser().resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    tts_cli: Path | None = None
    edge_tts_cmd: str | None = None
    if args.engine == "openai":
        if args.voice and args.voice not in ALL_VOICES:
            raise ValueError(f"Unknown OpenAI voice '{args.voice}'.")
        tts_cli = resolve_tts_cli(args.tts_cli)
    elif args.engine == "macos":
        if not shutil.which("say"):
            raise FileNotFoundError("`say` not found. macOS engine requires macOS.")
    else:
        edge_tts_cmd = resolve_edge_tts()

    source_text = load_text(input_path)
    chunks = chunk_text(source_text, args.chunk_size)

    preset = (
        FEMALE_PRESETS_MACOS[args.preset]
        if args.engine == "macos"
        else FEMALE_PRESETS_EDGE[args.preset]
        if args.engine == "edge"
        else FEMALE_PRESETS_OPENAI[args.preset]
    )
    voice = args.voice or preset["voice"]
    instructions = preset.get("instructions", "")
    if args.instructions:
        instructions = (
            f"{instructions}\n{args.instructions.strip()}".strip()
            if instructions
            else args.instructions.strip()
        )

    print("AI voice disclosure: This audiobook is generated with an AI voice model.")
    print(f"Chunks: {len(chunks)}")
    print(f"Engine: {args.engine}")
    print(f"Voice preset: {args.preset} | Voice: {voice}")

    ext = "aiff" if args.engine == "macos" else "mp3" if args.engine == "edge" else args.format
    chunk_files: List[Path] = []
    for i, chunk in enumerate(chunks, start=1):
        chunk_file = work_dir / f"{output_path.stem}.part{i:04d}.{ext}"
        chunk_files.append(chunk_file)
        if args.engine == "macos":
            words_per_minute = max(90, min(360, int(round(175 * args.speed))))
            cmd = ["say", "-v", voice, "-r", str(words_per_minute), "-o", str(chunk_file)]
            cmd.extend(["--", chunk])
            run_cmd(cmd, dry_run=args.dry_run)
        elif args.engine == "edge":
            if not edge_tts_cmd:
                raise RuntimeError("edge-tts command path was not resolved.")
            rate_percent = max(-50, min(100, int(round((args.speed - 1.0) * 100))))
            cmd = [
                edge_tts_cmd,
                "--voice",
                voice,
                "--rate",
                f"{rate_percent:+d}%",
                "--text",
                chunk,
                "--write-media",
                str(chunk_file),
            ]
            run_cmd(cmd, dry_run=args.dry_run)
        else:
            if not tts_cli:
                raise RuntimeError("OpenAI TTS CLI path was not resolved.")
            cmd = [
                sys.executable,
                str(tts_cli),
                "speak",
                "--input",
                chunk,
                "--model",
                args.model,
                "--voice",
                voice,
                "--response-format",
                args.format,
                "--speed",
                str(args.speed),
                "--out",
                str(chunk_file),
            ]
            if instructions:
                cmd.extend(["--instructions", instructions])
            if args.dry_run:
                cmd.append("--dry-run")
            run_cmd(cmd, dry_run=False)

    try:
        copy_codec = (
            args.engine == "openai" and output_path.suffix.lstrip(".") == args.format
        ) or (args.engine == "edge" and output_path.suffix.lower() == ".mp3")
        concat_audio_with_ffmpeg(
            chunk_files, output_path, dry_run=args.dry_run, copy_codec=copy_codec
        )
        if args.dry_run:
            print(f"Dry run complete. Merge command prepared for: {output_path}")
        else:
            print(f"Created audiobook: {output_path}")
    except FileNotFoundError:
        print(
            "ffmpeg not available; generated chunk files only. "
            "Install ffmpeg to merge automatically."
        )
        print(f"Chunk directory: {work_dir}")
    finally:
        if not args.keep_chunks:
            concat_file = output_path.with_suffix(output_path.suffix + ".concat.txt")
            if concat_file.exists():
                concat_file.unlink()

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
