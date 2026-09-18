# Batch Mandarin to Indonesian Subtitle Pipeline

Batch command-line pipeline for processing Mandarin/Chinese `.mp4` videos into subtitled Indonesian outputs.

## Prerequisites

- Python 3.8+
- FFmpeg and FFprobe available on `PATH`
- Virtual environment support
- Network access for `faster-whisper` model download and `googletrans` translation calls

## Installation

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

If you use the already-created environment in this repo, you can run the pipeline with `.venv/bin/python`.

## Usage

Run a batch from the command line:

```bash
.venv/bin/python pipeline.py --input ./input --output ./output --config ./config.yaml
```

Resume from `output/job_state.json`:

```bash
.venv/bin/python pipeline.py --input ./input --output ./output --config ./config.yaml --resume
```

Required arguments:

- `--input`: folder containing source `.mp4` files
- `--output`: folder for subtitles, subtitled videos, logs, and reports

Optional arguments:

- `--config`: YAML config file, defaults to `config.yaml`
- `--resume`: reuse `output/job_state.json` and continue incomplete jobs

## Processing Flow

1. Scan `input/` for `.mp4` files.
2. Validate each video with FFprobe.
3. Extract audio with FFmpeg.
4. Transcribe Mandarin speech with `faster-whisper`.
5. Translate segments to Indonesian with `googletrans`.
6. Generate `.srt` subtitles.
7. Burn subtitles into the output video.

If the source video already has Mandarin subtitles burned into the frame, enable
`ffmpeg.subtitles.cover_source_subtitles` in `config.yaml`. The pipeline will
blur the lower subtitle band first, then render the Indonesian subtitle over it.
8. Write logs, failed-job entries, batch report, and job state.

## Configuration

Default settings live in [config.yaml](./config.yaml).

Important sections:

- `paths`: input, output, and temp directories
- `processing`: sequential batch size and temp cleanup behavior
- `transcription`: provider, model size, language, and device settings
- `translation`: provider and source/target language settings
- `ffmpeg`: audio extraction and subtitle burn parameters

Notes:

- `translation.api_key_env` is reserved for future API-backed translation providers.
- `googletrans` currently does not use a key in this implementation.
- `cleanup_temp_on_success` removes intermediate audio/transcript/translation files after success.
- `cleanup_temp_on_failure` defaults to `false` so failed jobs keep artifacts for debugging.

## Drama Folders, Titles, and Artwork

When the input folder holds one subfolder per drama, the pipeline mirrors that
structure into the output folder with an Indonesian folder title:

```text
input/                                  output/
  143-老公突然有了读心术/          ->     143-Suamiku Tiba-Tiba Bisa Membaca Pikiran/
    001.mp4                               001.srt
    002.mp4                               001_subtitled.mp4
    poster.jpg                            002.srt
    thumbnail.png                         002_subtitled.mp4
                                          poster.jpg
                                          thumbnail.png
```

Behaviour:

- **Source folders are never renamed or modified.** Only the newly created
  output folder uses the Indonesian title.
- The numeric catalogue prefix (`4-`, `12-`, `143-`, `114-`) is carried across
  untranslated, and an episode count such as `（85集）` becomes `(85 Episode)`.
- The title is translated **once per drama folder** by the same `googletrans`
  provider already used for subtitles, then cached for every episode in that
  folder. No extra provider and no API key are involved.
- Output folder names are sanitized for Windows: the reserved characters
  `< > : " / \ | ? *` are replaced, reserved device names (`CON`, `PRN`, `AUX`,
  `NUL`, `COM1`-`COM9`, `LPT1`-`LPT9`) are escaped, trailing dots and spaces are
  removed, and `/` or `\` can never create an accidental subdirectory.
- If two dramas translate to the same Indonesian title, the numeric prefix keeps
  them apart; without prefixes a `-2`, `-3` suffix is appended so neither folder
  overwrites the other.
- If title translation fails, the batch continues and that folder falls back to
  its original name. The failure is logged and recorded in `batch_report.json`.
- `.jpg`, `.jpeg`, `.png`, and `.webp` files are copied byte-for-byte into the
  translated output folder, keeping their original filenames. They are never
  re-encoded, resized, OCR'd, or treated as video inputs. A failed image copy is
  logged and does not stop video processing.
- `batch_report.json` records the mapping under `drama_folders` as
  `source_folder_name` / `translated_folder_name`.

On `--resume`, the output folder name stored in `job_state.json` is reused, so a
resumed batch never re-translates a title or splits one drama across two folders.

## Output Structure

Typical output after a batch run:

```text
output/
  poc_01.srt
  poc_01_subtitled.mp4
  processing.log
  failed_jobs.txt
  job_state.json
  batch_report.json
```

Temporary artifacts are written to `temp/`:

```text
temp/
  poc_01_audio.wav
  poc_01_transcript.json
  poc_01_translation.json
```

## Logs and Reports

- `processing.log`: structured JSON lines for job start, completion, failure, and skipped input files
- `failed_jobs.txt`: one-line summary per failed or skipped video
- `job_state.json`: resume state for incomplete batches
- `batch_report.json`: counts, timing, and per-job summary

## Troubleshooting

- `FFmpeg executable not found`: install FFmpeg and ensure `ffmpeg` and `ffprobe` are on `PATH`.
- `Translation failed: [Errno 8] nodename nor servname provided`: the machine cannot reach Google Translate; rerun with network access.
- `No module named faster_whisper`: install dependencies inside the virtual environment.
- `Input folder does not exist`: create the folder or point `--input` at the correct path.
- `Resume does not continue expected jobs`: check `output/job_state.json` and make sure completed jobs are marked `completed`.

## Scalability Notes

- Current POC execution is sequential for reliability.
- `RetryManager` keeps resume state after every job.
- The architecture is split into isolated stages so later concurrency work can be added without rewriting the full pipeline.

## Development

Run the test suite:

```bash
.venv/bin/python -m unittest discover -s tests
```

Current implementation status is tracked in [tasks.md](./tasks.md).
