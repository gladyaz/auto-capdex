from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from models import Config, JobStatus, VideoJob


class VideoProcessingError(RuntimeError):
    pass


class VideoProcessor:
    def __init__(
        self,
        config: Config,
        ffmpeg_path: str = "ffmpeg",
        ffprobe_path: str = "ffprobe",
        logger: logging.Logger | None = None,
    ):
        self.config = config
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.logger = logger or logging.getLogger(__name__)

    def burn_subtitles(self, job: VideoJob) -> VideoJob:
        if job.srt_path is None:
            raise VideoProcessingError("job.srt_path is required before subtitle burning")

        output_path = self._output_video_path(job)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        command = self._build_ffmpeg_command(job.video_path, job.srt_path, output_path)
        try:
            subprocess.run(
                command,
                capture_output=True,
                check=True,
                text=True,
            )
        except FileNotFoundError as error:
            raise VideoProcessingError(f"FFmpeg executable not found: {self.ffmpeg_path}") from error
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or error.stdout or "ffmpeg failed").strip()
            raise VideoProcessingError(detail) from error

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise VideoProcessingError(f"Output video was not created or is empty: {output_path}")

        self._validate_output_video(output_path)
        self.logger.info("Burned subtitles for %s to %s", job.video_path, output_path)
        return job.with_status(JobStatus.COMPLETED, output_video_path=output_path)

    def _output_video_path(self, job: VideoJob) -> Path:
        suffix = self.config.ffmpeg_subtitles.output_suffix
        # output_name mirrors video_name unless the drama folder title was
        # translated, in which case only the output tree uses the new name.
        return self.config.output_folder / f"{job.output_name}{suffix}.mp4"

    def _build_ffmpeg_command(
        self,
        input_video: Path,
        srt_path: Path,
        output_path: Path,
    ) -> list[str]:
        if srt_path.stat().st_size == 0:
            return [
                self.ffmpeg_path,
                "-y",
                "-i",
                str(input_video),
                "-c:v",
                "copy",
                "-c:a",
                "copy",
                str(output_path),
            ]

        subtitle_config = self.config.ffmpeg_subtitles
        subtitle_filter = _subtitle_filter(
            srt_path,
            subtitle_config.font,
            subtitle_config.font_size,
            subtitle_config.margin_v,
        )
        if subtitle_config.cover_source_subtitles:
            if subtitle_config.cover_source_subtitles_mode == "cover":
                vf_filters = [
                    _cover_source_subtitles_filter(
                        subtitle_config.cover_band_height_ratio,
                        subtitle_config.cover_band_opacity,
                    ),
                    subtitle_filter,
                ]
                return [
                    self.ffmpeg_path,
                    "-y",
                    "-i",
                    str(input_video),
                    "-vf",
                    ",".join(vf_filters),
                    "-c:v",
                    subtitle_config.video_codec,
                    "-c:a",
                    subtitle_config.audio_codec,
                    str(output_path),
                ]

            filter_complex = _blur_source_subtitles_and_burn_filter(
                subtitle_filter=subtitle_filter,
                height_ratio=subtitle_config.cover_band_height_ratio,
                blur_radius=subtitle_config.cover_blur_radius,
            )
            return [
                self.ffmpeg_path,
                "-y",
                "-i",
                str(input_video),
                "-filter_complex",
                filter_complex,
                "-map",
                "[v]",
                "-map",
                "0:a?",
                "-c:v",
                subtitle_config.video_codec,
                "-c:a",
                subtitle_config.audio_codec,
                str(output_path),
            ]

        return [
            self.ffmpeg_path,
            "-y",
            "-i",
            str(input_video),
            "-vf",
            subtitle_filter,
            "-c:v",
            subtitle_config.video_codec,
            "-c:a",
            subtitle_config.audio_codec,
            str(output_path),
        ]

    def _validate_output_video(self, output_path: Path) -> None:
        try:
            subprocess.run(
                [
                    self.ffprobe_path,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(output_path),
                ],
                capture_output=True,
                check=True,
                text=True,
            )
        except FileNotFoundError as error:
            raise VideoProcessingError(f"FFprobe executable not found: {self.ffprobe_path}") from error
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or error.stdout or "ffprobe failed").strip()
            raise VideoProcessingError(f"Output video validation failed: {detail}") from error


def _subtitle_filter(srt_path: Path, font: str, font_size: int, margin_v: int) -> str:
    escaped_path = _escape_subtitle_path(srt_path)
    return (
        f"subtitles='{escaped_path}':"
        f"force_style='FontName={font},FontSize={font_size},Alignment=2,MarginV={margin_v}'"
    )


def _cover_source_subtitles_filter(height_ratio: float, opacity: float) -> str:
    return (
        "drawbox="
        "x=0:"
        f"y=ih*(1-{height_ratio}):"
        "w=iw:"
        f"h=ih*{height_ratio}:"
        f"color=black@{opacity}:"
        "t=fill"
    )


def _blur_source_subtitles_and_burn_filter(
    subtitle_filter: str,
    height_ratio: float,
    blur_radius: int,
) -> str:
    blur_height = f"ih*{height_ratio}"
    crop_start = f"ih*(1-{height_ratio})"
    blur_strength = f"luma_radius={blur_radius}:luma_power=1"
    return (
        f"[0:v]split=2[base][tmp];"
        f"[tmp]crop=iw:{blur_height}:0:{crop_start},boxblur={blur_strength}[blur];"
        f"[base][blur]overlay=0:H-h[covered];"
        f"[covered]{subtitle_filter}[v]"
    )


def _escape_subtitle_path(path: Path) -> str:
    text = str(path)
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


__all__ = ["VideoProcessingError", "VideoProcessor"]
