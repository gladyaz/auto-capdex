from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from models import Config, JobStatus, VideoJob


class ExtractionError(RuntimeError):
    pass


class AudioExtractor:
    def __init__(
        self,
        config: Config,
        ffmpeg_path: str = "ffmpeg",
        logger: logging.Logger | None = None,
    ):
        self.config = config
        self.ffmpeg_path = ffmpeg_path
        self.logger = logger or logging.getLogger(__name__)

    def extract(self, job: VideoJob) -> VideoJob:
        output_path = self._audio_output_path(job)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        command = self._build_command(job.video_path, output_path)
        try:
            subprocess.run(
                command,
                capture_output=True,
                check=True,
                text=True,
            )
        except FileNotFoundError as error:
            raise ExtractionError(f"FFmpeg executable not found: {self.ffmpeg_path}") from error
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or error.stdout or "ffmpeg failed").strip()
            raise ExtractionError(detail) from error

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise ExtractionError(f"Audio output was not created or is empty: {output_path}")

        self.logger.info("Extracted audio for %s to %s", job.video_path, output_path)
        return job.with_status(JobStatus.AUDIO_EXTRACTED, audio_path=output_path)

    def _audio_output_path(self, job: VideoJob) -> Path:
        audio_config = self.config.ffmpeg_audio
        return self.config.temp_folder / f"{job.video_name}_audio.{audio_config.format}"

    def _build_command(self, input_path: Path, output_path: Path) -> list[str]:
        audio_config = self.config.ffmpeg_audio
        return [
            self.ffmpeg_path,
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-acodec",
            audio_config.codec,
            "-ar",
            str(audio_config.sample_rate),
            "-ac",
            str(audio_config.channels),
            str(output_path),
        ]


__all__ = ["AudioExtractor", "ExtractionError"]
