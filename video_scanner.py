from __future__ import annotations

import json
import logging
import subprocess
import uuid
from pathlib import Path
from typing import Any, Mapping

from models import VideoJob


class VideoScanner:
    def __init__(self, ffprobe_path: str = "ffprobe", logger: logging.Logger | None = None):
        self.ffprobe_path = ffprobe_path
        self.logger = logger or logging.getLogger(__name__)
        self.skipped_files: list[dict[str, str]] = []

    def scan(self, input_folder: str | Path) -> list[VideoJob]:
        folder = Path(input_folder)
        if not folder.exists():
            raise FileNotFoundError(f"Input folder does not exist: {folder}")
        if not folder.is_dir():
            raise NotADirectoryError(f"Input path is not a directory: {folder}")

        video_paths = sorted(
            path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() == ".mp4"
        )
        jobs: list[VideoJob] = []
        self.skipped_files = []

        for video_path in video_paths:
            validation = self._validate_video(video_path)
            if not validation.is_valid:
                self.skipped_files.append(
                    {
                        "video_path": str(video_path),
                        "reason": validation.reason or "invalid video",
                    }
                )
                self.logger.warning(
                    "Skipping invalid video %s: %s",
                    video_path,
                    validation.reason,
                )
                continue

            jobs.append(
                VideoJob(
                    job_id=str(uuid.uuid4()),
                    video_path=video_path,
                    video_name=video_path.relative_to(folder).with_suffix("").as_posix(),
                )
            )

        self.logger.info("Scanned %s valid video job(s) from %s", len(jobs), folder)
        return jobs

    def _validate_video(self, video_path: Path) -> "_ValidationResult":
        try:
            probe = subprocess.run(
                [
                    self.ffprobe_path,
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_type",
                    "-of",
                    "json",
                    str(video_path),
                ],
                capture_output=True,
                check=True,
                text=True,
            )
        except FileNotFoundError:
            raise
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or "ffprobe failed").strip()
            return _ValidationResult(False, detail)

        try:
            payload = json.loads(probe.stdout)
        except json.JSONDecodeError as error:
            return _ValidationResult(False, f"invalid ffprobe JSON: {error}")

        if not _has_audio_stream(payload):
            return _ValidationResult(False, "video does not contain an audio stream")

        return _ValidationResult(True, None)


class _ValidationResult:
    def __init__(self, is_valid: bool, reason: str | None):
        self.is_valid = is_valid
        self.reason = reason


def _has_audio_stream(payload: Mapping[str, Any]) -> bool:
    streams = payload.get("streams", [])
    if not isinstance(streams, list):
        return False

    return any(
        isinstance(stream, Mapping) and stream.get("codec_type") == "audio"
        for stream in streams
    )


__all__ = ["VideoScanner"]
