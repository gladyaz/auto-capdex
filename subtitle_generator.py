from __future__ import annotations

import logging
from pathlib import Path

from models import Config, JobStatus, Translation, VideoJob


class SubtitleError(RuntimeError):
    pass


class SubtitleGenerator:
    def __init__(self, config: Config, logger: logging.Logger | None = None):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

    def generate(self, job: VideoJob, translation: Translation) -> VideoJob:
        if job.translation_path is None:
            raise SubtitleError("job.translation_path is required before SRT generation")

        srt_path = self._srt_output_path(job)
        srt_path.parent.mkdir(parents=True, exist_ok=True)
        content = build_srt_content(
            translation,
            time_offset_seconds=self.config.ffmpeg_subtitles.subtitle_time_offset_seconds,
            max_display_seconds=self.config.ffmpeg_subtitles.max_display_seconds,
        )
        _validate_srt_content(content, expected_entries=len(translation.segments))

        try:
            srt_path.write_text(content, encoding="utf-8")
        except OSError as error:
            raise SubtitleError(f"Unable to write SRT file: {srt_path}") from error

        self.logger.info("Generated subtitles for %s at %s", job.video_path, srt_path)
        return job.with_status(JobStatus.SRT_GENERATED, srt_path=srt_path)

    def _srt_output_path(self, job: VideoJob) -> Path:
        return self.config.output_folder / f"{job.video_name}.srt"


def build_srt_content(
    translation: Translation,
    time_offset_seconds: float = 0.0,
    max_display_seconds: float | None = None,
) -> str:
    entries: list[str] = []
    for index, segment in enumerate(translation.segments, start=1):
        start_time = max(0.0, segment.start_time - time_offset_seconds)
        end_time = max(start_time, segment.end_time - time_offset_seconds)
        if max_display_seconds is not None:
            end_time = min(end_time, start_time + max_display_seconds)
        entries.append(
            "\n".join(
                [
                    str(index),
                    f"{format_srt_timestamp(start_time)} --> {format_srt_timestamp(end_time)}",
                    segment.text,
                    "",
                ]
            )
        )

    if not entries:
        return ""

    return "\n".join(entries) + "\n"


def format_srt_timestamp(seconds: float) -> str:
    total_milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def _validate_srt_content(content: str, expected_entries: int) -> None:
    if expected_entries == 0:
        if content != "":
            raise SubtitleError("Empty translation must produce an empty SRT file")
        return

    blocks = [block for block in content.strip().split("\n\n") if block]
    if len(blocks) != expected_entries:
        raise SubtitleError("Generated SRT entry count does not match translation segments")

    for expected_index, block in enumerate(blocks, start=1):
        lines = block.splitlines()
        if len(lines) < 3:
            raise SubtitleError("Generated SRT entry is missing required fields")
        if lines[0] != str(expected_index):
            raise SubtitleError("Generated SRT sequence numbers are invalid")
        if " --> " not in lines[1]:
            raise SubtitleError("Generated SRT timestamp range is invalid")


__all__ = [
    "SubtitleError",
    "SubtitleGenerator",
    "build_srt_content",
    "format_srt_timestamp",
]
