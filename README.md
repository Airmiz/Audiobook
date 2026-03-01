# Audiobook Maker

Create an audiobook from a `.txt` file with chunked synthesis and female-style voice presets.

## Requirements

- Python 3.10+
- `ffmpeg`
- `edge-tts` for best free quality:
  - `python3 -m pip install edge-tts`

Free default engine:
- `edge` (neural voice, no API key, no paid service)
- `macos` (built-in `say`, fully local, lower quality)

Optional engine:
- `openai` (requires `OPENAI_API_KEY` and the speech skill CLI)

## Quick Start

```bash
python audiobook_maker.py \
  --input book.txt \
  --output output/speech/my_audiobook.mp3 \
  --engine edge \
  --preset warm
```

## Voice Test Command

Use the included sample paragraph to quickly test a voice preset:

```bash
python audiobook_maker.py \
  --input /Users/jordansyring/Documents/Audiobook/voice_test_paragraph.txt \
  --output /Users/jordansyring/Documents/Audiobook/output/speech/voice_test.mp3 \
  --engine edge \
  --preset warm
```

## Female Voice Presets

- `warm` (default)
- `clear`
- `soft`
- `confident`

Override the exact voice:

List available voices:

```bash
python audiobook_maker.py --engine edge --list-voices
```

## Useful Options

- `--instructions "Tone: ..."` append custom style instructions
- `--speed 0.95` adjust pace
- `--chunk-size 3400` chunk target size (must be <= 4096)
- `--keep-chunks` keep part files
- `--dry-run` run without live API calls
- `--engine openai` switch to OpenAI voices if desired

## Notes

- The program prints an AI voice disclosure by design.
- Without `ffmpeg`, it still generates chunk files in `output/speech/`.
- For best free quality, use `--engine edge`.

## PDF To TXT Command

Convert a PDF to a text file with the same name:

```bash
python3 /Users/jordansyring/Documents/Audiobook/pdf_to_txt.py \
  "/Users/jordansyring/Documents/Audiobook/Forgotten Gods Blue Futanari Series Book 2 Gabi Prevot.pdf"
```

This creates:
- `/Users/jordansyring/Documents/Audiobook/Forgotten Gods Blue Futanari Series Book 2 Gabi Prevot.txt`

If needed, overwrite existing output:

```bash
python3 /Users/jordansyring/Documents/Audiobook/pdf_to_txt.py \
  "/Users/jordansyring/Documents/Audiobook/Forgotten Gods Blue Futanari Series Book 2 Gabi Prevot.pdf" \
  --overwrite
```

## Voice Cloning Setup

If you need custom voice cloning (with explicit rights/consent), use:

- [voice_clone_audiobook.py](/Users/jordansyring/Documents/Audiobook/voice_clone_audiobook.py)
- [voice-clone-setup.md](/Users/jordansyring/Documents/Audiobook/docs/voice-clone-setup.md)
- [voice_consent.example.json](/Users/jordansyring/Documents/Audiobook/templates/voice_consent.example.json)
