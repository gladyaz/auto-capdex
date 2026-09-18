from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(Enum):
    PENDING = "pending"
    AUDIO_EXTRACTED = "audio_extracted"
    TRANSCRIBED = "transcribed"
    TRANSLATED = "translated"
    SRT_GENERATED = "srt_generated"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class VideoJob:
    job_id: str
    video_path: Path
    video_name: Optional[str] = None
    # Relative output name, identical to video_name unless the drama folder
    # title was translated for the output tree. Source files are never renamed.
    output_name: Optional[str] = None
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    error_message: Optional[str] = None
    audio_path: Optional[Path] = None
    transcript_path: Optional[Path] = None
    translation_path: Optional[Path] = None
    srt_path: Optional[Path] = None
    output_video_path: Optional[Path] = None

    def __post_init__(self) -> None:
        video_path = Path(self.video_path)
        object.__setattr__(self, "video_path", video_path)

        if self.video_name is None:
            object.__setattr__(self, "video_name", video_path.stem)

        if self.output_name is None:
            object.__setattr__(self, "output_name", self.video_name)

        for field_name in (
            "audio_path",
            "transcript_path",
            "translation_path",
            "srt_path",
            "output_video_path",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, Path(value))

    def with_status(self, status: JobStatus, **changes: object) -> VideoJob:
        return replace(
            self,
            status=status,
            error_message=changes.pop("error_message", self.error_message),
            updated_at=utc_now(),
            **changes,
        )

    def with_failure(self, error_message: str) -> VideoJob:
        return replace(
            self,
            status=JobStatus.FAILED,
            error_message=error_message,
            updated_at=utc_now(),
        )


@dataclass(frozen=True)
class TextSegment:
    start_time: float
    end_time: float
    text: str

    def __post_init__(self) -> None:
        if self.start_time < 0:
            raise ValueError("start_time must be greater than or equal to 0")
        if self.end_time < self.start_time:
            raise ValueError("end_time must be greater than or equal to start_time")


@dataclass(frozen=True)
class Transcript:
    segments: tuple[TextSegment, ...] | list[TextSegment]
    language: str
    source_audio: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "segments", tuple(self.segments))
        object.__setattr__(self, "source_audio", Path(self.source_audio))


@dataclass(frozen=True)
class Translation:
    segments: tuple[TextSegment, ...] | list[TextSegment]
    source_language: str
    target_language: str
    source_transcript: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "segments", tuple(self.segments))
        object.__setattr__(self, "source_transcript", Path(self.source_transcript))


@dataclass(frozen=True)
class FFmpegAudioConfig:
    format: str = "wav"
    codec: str = "pcm_s16le"
    sample_rate: int = 16000
    channels: int = 1

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be greater than 0")
        if self.channels <= 0:
            raise ValueError("channels must be greater than 0")


@dataclass(frozen=True)
class FFmpegSubtitleConfig:
    output_suffix: str = "_subtitled"
    font: str = "Arial"
    font_size: int = 18
    alignment: str = "bottom_center"
    margin_v: int = 8
    video_codec: str = "libx264"
    audio_codec: str = "copy"
    subtitle_time_offset_seconds: float = 1.0
    max_display_seconds: float = 7.0
    cover_source_subtitles: bool = False
    cover_source_subtitles_mode: str = "blur"
    cover_band_height_ratio: float = 0.22
    cover_band_opacity: float = 0.72
    cover_blur_radius: int = 18

    def __post_init__(self) -> None:
        if self.font_size <= 0:
            raise ValueError("font_size must be greater than 0")
        if self.margin_v < 0:
            raise ValueError("margin_v must be greater than or equal to 0")
        if self.subtitle_time_offset_seconds < 0:
            raise ValueError("subtitle_time_offset_seconds must be greater than or equal to 0")
        if self.max_display_seconds <= 0:
            raise ValueError("max_display_seconds must be greater than 0")
        if self.cover_source_subtitles_mode not in {"blur", "cover"}:
            raise ValueError("cover_source_subtitles_mode must be 'blur' or 'cover'")
        if not 0 < self.cover_band_height_ratio < 1:
            raise ValueError("cover_band_height_ratio must be between 0 and 1")
        if not 0 <= self.cover_band_opacity <= 1:
            raise ValueError("cover_band_opacity must be between 0 and 1")
        if self.cover_blur_radius <= 0:
            raise ValueError("cover_blur_radius must be greater than 0")


@dataclass(frozen=True)
class Config:
    input_folder: Path = Path("input")
    output_folder: Path = Path("output")
    temp_folder: Path = Path("temp")
    transcription_provider: str = "faster-whisper"
    transcription_model_size: str = "base"
    transcription_device: str = "auto"
    transcription_compute_type: str = "auto"
    transcription_vad_filter: bool = True
    transcription_no_speech_threshold: float = 0.75
    transcription_condition_on_previous_text: bool = False
    transcription_cpu_threads: int = 0
    transcription_beam_size: int = 5
    transcription_compression_ratio_threshold: float = 2.4
    transcription_skip_intro_seconds: float = 0.0
    transcription_min_word_probability: float = 0.5
    translation_provider: str = "googletrans"
    translation_max_retries: int = 3
    translation_retry_backoff_seconds: float = 2.0
    translation_api_key_env: str = "GOOGLE_TRANSLATE_API_KEY"
    translation_api_key: Optional[str] = None
    source_language: str = "zh"
    translation_source_language: str = "zh-cn"
    target_language: str = "id"
    concurrency_level: int = 1
    cleanup_temp_on_success: bool = True
    cleanup_temp_on_failure: bool = False
    ffmpeg_audio: FFmpegAudioConfig = field(default_factory=FFmpegAudioConfig)
    ffmpeg_subtitles: FFmpegSubtitleConfig = field(default_factory=FFmpegSubtitleConfig)

    def __post_init__(self) -> None:
        if self.concurrency_level <= 0:
            raise ValueError("concurrency_level must be greater than 0")
        if self.transcription_cpu_threads < 0:
            raise ValueError("transcription_cpu_threads must be greater than or equal to 0")
        if self.transcription_beam_size <= 0:
            raise ValueError("transcription_beam_size must be greater than 0")
        if self.transcription_compression_ratio_threshold <= 0:
            raise ValueError("transcription_compression_ratio_threshold must be greater than 0")
        if self.transcription_skip_intro_seconds < 0:
            raise ValueError("transcription_skip_intro_seconds must be greater than or equal to 0")
        if not 0 <= self.transcription_min_word_probability <= 1:
            raise ValueError("transcription_min_word_probability must be between 0 and 1")
        if self.translation_max_retries < 0:
            raise ValueError("translation_max_retries must be greater than or equal to 0")
        if self.translation_retry_backoff_seconds < 0:
            raise ValueError("translation_retry_backoff_seconds must be greater than or equal to 0")

        object.__setattr__(self, "input_folder", Path(self.input_folder))
        object.__setattr__(self, "output_folder", Path(self.output_folder))
        object.__setattr__(self, "temp_folder", Path(self.temp_folder))


__all__ = [
    "Config",
    "FFmpegAudioConfig",
    "FFmpegSubtitleConfig",
    "JobStatus",
    "TextSegment",
    "Transcript",
    "Translation",
    "VideoJob",
    "utc_now",
]
