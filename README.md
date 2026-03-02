# Audiobook Maker

Create an audiobook from a `.txt` file with chunked synthesis and female-style voice presets.

## Project Layout

- `scripts/` CLI tools
- `samples/` test text samples
- `books/` source PDFs/TXTs
- `output/` generated audio
- `docs/` setup guides
- `templates/` config templates

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
python3 scripts/audiobook_maker.py \
  --input book.txt \
  --output output/speech/my_audiobook.mp3 \
  --engine edge \
  --preset warm
```

## Voice Test Command

Use the included sample paragraph to quickly test a voice preset:

```bash
python3 scripts/audiobook_maker.py \
  --input samples/voice_test_paragraph.txt \
  --output output/speech/voice_test.mp3 \
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
python3 scripts/audiobook_maker.py --engine edge --list-voices
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
python3 scripts/pdf_to_txt.py \
  "books/Forgotten Gods Blue Futanari Series Book 2 Gabi Prevot.pdf"
```

This creates:
- `books/Forgotten Gods Blue Futanari Series Book 2 Gabi Prevot.txt`

If needed, overwrite existing output:

```bash
python3 scripts/pdf_to_txt.py \
  "books/Forgotten Gods Blue Futanari Series Book 2 Gabi Prevot.pdf" \
  --overwrite
```

## Voice Cloning Setup

If you need custom voice cloning (with explicit rights/consent), use:

- [voice_clone_audiobook.py](/Users/jordansyring/Documents/Audiobook/scripts/voice_clone_audiobook.py)
- [voice-clone-setup.md](/Users/jordansyring/Documents/Audiobook/docs/voice-clone-setup.md)
- [voice_consent.example.json](/Users/jordansyring/Documents/Audiobook/templates/voice_consent.example.json)

## Local Audiobook Website Player

Stream finished audiobooks in your browser with:
- instant resume from last stop time
- saved timestamp bookmarks (tag + jump back)

Run:

```bash
python3 scripts/audiobook_web_player.py --books-dir output/finished --port 8000
```

Then open:

```text
http://127.0.0.1:8000
```

## Publish Website So Anyone Can Stream

GitHub Pages is static-only, so use this split:
- `web-player/` on GitHub Pages
- large `.wav` files on public object storage (recommended: Cloudflare R2)

### 1) Upload `.wav` files to public storage

Upload files from `output/finished` to your public bucket/domain.
Example public base URL:

```text
https://pub-xxxxxxxxxxxxxxxx.r2.dev
```

### 2) Generate static manifest for the website

```bash
python3 scripts/generate_books_manifest.py \
  --books-dir output/finished \
  --base-url https://pub-xxxxxxxxxxxxxxxx.r2.dev \
  --out web-player/books.json
```

### 3) Commit and push website files to GitHub

```bash
git add web-player scripts/generate_books_manifest.py README.md
git commit -m "Add public web player manifest flow"
git push origin main
```

### 4) Enable GitHub Pages

- GitHub repo -> `Settings` -> `Pages`
- `Source`: `Deploy from a branch`
- Branch: `main`
- Folder: `/web-player`

Your public site will be available at:

```text
https://<your-github-username>.github.io/<repo-name>/
```

### Notes

- Player keeps resume time + bookmarks in each listener's browser localStorage.
- `web-player/app.js` supports both local mode (`/api/books`) and public mode (`/books.json`).
