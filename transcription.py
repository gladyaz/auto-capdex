from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from models import Config, JobStatus, TextSegment, Transcript, VideoJob


class TranscriptionError(RuntimeError):
    pass


class TranscriptionProvider(ABC):
    @abstractmethod
    def transcribe(self, audio_file: Path, language: str) -> Transcript:
        raise NotImplementedError


class FasterWhisperProvider(TranscriptionProvider):
    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        compute_type: str = "auto",
        vad_filter: bool = True,
        no_speech_threshold: float = 0.75,
        condition_on_previous_text: bool = False,
        cpu_threads: int = 0,
        beam_size: int = 5,
        compression_ratio_threshold: float = 2.4,
        skip_intro_seconds: float = 0.0,
        min_word_probability: float = 0.5,
        model_factory: Callable[..., Any] | None = None,
    ):
        if model_factory is None:
            from faster_whisper import WhisperModel

            model_factory = WhisperModel

        self.model = model_factory(
            model_size,
            device=device,
            compute_type=compute_type,
            cpu_threads=cpu_threads,
        )
        self.vad_filter = vad_filter
        self.no_speech_threshold = no_speech_threshold
        self.condition_on_previous_text = condition_on_previous_text
        self.beam_size = beam_size
        self.compression_ratio_threshold = compression_ratio_threshold
        self.skip_intro_seconds = skip_intro_seconds
        self.min_word_probability = min_word_probability

    def transcribe(self, audio_file: Path, language: str) -> Transcript:
        try:
            segments, info = self.model.transcribe(
                str(audio_file),
                language=language,
                vad_filter=self.vad_filter,
                no_speech_threshold=self.no_speech_threshold,
                condition_on_previous_text=self.condition_on_previous_text,
                beam_size=self.beam_size,
                compression_ratio_threshold=self.compression_ratio_threshold,
                word_timestamps=True,
            )
            text_segments = tuple(
                built_segment
                for segment in segments
                if segment.no_speech_prob < self.no_speech_threshold
                and segment.compression_ratio <= self.compression_ratio_threshold
                and segment.start >= self.skip_intro_seconds
                for built_segment in (
                    _build_confident_segment(segment, self.min_word_probability),
                )
                if built_segment is not None
            )
        except Exception as error:
            raise TranscriptionError(f"Transcription failed: {error}") from error

        detected_language = getattr(info, "language", language) or language
        return Transcript(
            segments=text_segments,
            language=str(detected_language),
            source_audio=audio_file,
        )


def _build_confident_segment(segment: Any, min_word_probability: float) -> TextSegment | None:
    words = getattr(segment, "words", None) or []
    confident_words = [word for word in words if word.probability >= min_word_probability]
    if not confident_words:
        return None

    text = "".join(word.word for word in confident_words).strip()
    if not text:
        return None

    return TextSegment(
        start_time=float(min(word.start for word in confident_words)),
        end_time=float(max(word.end for word in confident_words)),
        text=text,
    )


@dataclass(frozen=True)
class TranscriptionResult:
    job: VideoJob
    transcript: Transcript


class TranscriptionService:
    def __init__(
        self,
        provider: TranscriptionProvider,
        config: Config,
        logger: logging.Logger | None = None,
    ):
        self.provider = provider
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

    def transcribe(self, job: VideoJob) -> TranscriptionResult:
        if job.audio_path is None:
            raise TranscriptionError("job.audio_path is required before transcription")

        transcript = self.provider.transcribe(job.audio_path, self.config.source_language)
        transcript_path = self._transcript_output_path(job)
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.write_text(
            json.dumps(_transcript_to_dict(transcript), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        updated_job = job.with_status(
            JobStatus.TRANSCRIBED,
            transcript_path=transcript_path,
        )
        self.logger.info("Transcribed %s to %s", job.audio_path, transcript_path)
        return TranscriptionResult(job=updated_job, transcript=transcript)

    def _transcript_output_path(self, job: VideoJob) -> Path:
        return self.config.temp_folder / f"{job.video_name}_transcript.json"


def _transcript_to_dict(transcript: Transcript) -> dict[str, Any]:
    return {
        "language": transcript.language,
        "source_audio": str(transcript.source_audio),
        "segments": [
            {
                "start_time": segment.start_time,
                "end_time": segment.end_time,
                "text": segment.text,
            }
            for segment in transcript.segments
        ],
    }


__all__ = [
    "FasterWhisperProvider",
    "TranscriptionError",
    "TranscriptionProvider",
    "TranscriptionResult",
    "TranscriptionService",
]
