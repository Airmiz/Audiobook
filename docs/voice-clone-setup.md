# Voice Clone Setup (Authorized Use Only)

This setup can clone a reference voice and generate audiobook narration from new text.
Use only when you have explicit legal rights and speaker permission.

## 1) Install dependencies

```bash
python3 -m pip install TTS
brew install ffmpeg
```

Notes:
- `TTS` provides runtime used by `scripts/voice_clone_audiobook.py`.
- First run may download model files for `xtts_v2`.

## 2) Prepare files

- Source text file (example): `book.txt`
- Reference speaker audio (recommended): clean 30-90 seconds WAV with minimal background noise.
- Consent file: copy template and fill it in.

```bash
cp templates/voice_consent.example.json voice_consent.json
```

## 3) Run generation

```bash
python3 scripts/voice_clone_audiobook.py \
  --input-text samples/voice_test_paragraph.txt \
  --reference-audio /absolute/path/to/reference.wav \
  --consent-file voice_consent.json \
  --speaker-name "Jane Example" \
  --output output/clone/clone_audiobook.wav \
  --language en
```

## 4) Optional controls

- `--chunk-size 280` for shorter chunks (can improve stability)
- `--keep-chunks` to inspect each part
- `--dry-run` to print commands without synthesis

## Important safeguards

- The script blocks generation unless `consent_granted` and `rights_confirmed` are both `true`.
- Keep your consent file in project records.
- Do not use this workflow to impersonate people without explicit permission.
