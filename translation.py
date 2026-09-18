from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from models import Config, JobStatus, TextSegment, Transcript, Translation, VideoJob


class TranslationError(RuntimeError):
    pass


class TranslationProvider(ABC):
    @abstractmethod
    def translate(
        self,
        transcript: Transcript,
        source_language: str,
        target_language: str,
    ) -> Translation:
        raise NotImplementedError


class GoogleTranslateProvider(TranslationProvider):
    def __init__(
        self,
        translator_client: Any | None = None,
        max_retries: int = 3,
        retry_backoff_seconds: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if translator_client is None:
            from googletrans import Translator

            translator_client = Translator(http2=False, raise_exception=True)

        self.translator_client = translator_client
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.sleep = sleep

    def translate(
        self,
        transcript: Transcript,
        source_language: str,
        target_language: str,
    ) -> Translation:
        translated_segments: list[TextSegment] = []

        try:
            for segment in transcript.segments:
                translated_text = ""
                if segment.text:
                    response = self._translate_with_retry(
                        segment.text,
                        source_language,
                        target_language,
                    )
                    translated_text = str(response.text).strip()

                translated_segments.append(
                    TextSegment(
                        start_time=segment.start_time,
                        end_time=segment.end_time,
                        text=translated_text,
                    )
                )
        except Exception as error:
            raise TranslationError(f"Translation failed: {error}") from error

        return Translation(
            segments=translated_segments,
            source_language=source_language,
            target_language=target_language,
            source_transcript=transcript.source_audio,
        )

    def translate_text(self, text: str, source_language: str, target_language: str) -> str:
        """Translate a single standalone string, e.g. a drama folder title.

        Shares the retry/backoff behaviour used for subtitle segments so a
        transient googletrans failure does not immediately fall back.
        """
        if not text.strip():
            return ""

        try:
            response = self._translate_with_retry(text, source_language, target_language)
        except Exception as error:
            raise TranslationError(f"Text translation failed: {error}") from error

        return str(response.text).strip()

    def _translate_with_retry(self, text: str, source_language: str, target_language: str) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return self.translator_client.translate(
                    text,
                    src=source_language,
                    dest=target_language,
                )
            except Exception as error:
                last_error = error
                if attempt < self.max_retries:
                    self.sleep(self.retry_backoff_seconds * (2**attempt))
        raise last_error


@dataclass(frozen=True)
class TranslationResult:
    job: VideoJob
    translation: Translation


class TranslationService:
    def __init__(
        self,
        provider: TranslationProvider,
        config: Config,
        logger: logging.Logger | None = None,
    ):
        self.provider = provider
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

    def translate(self, job: VideoJob, transcript: Transcript) -> TranslationResult:
        if job.transcript_path is None:
            raise TranslationError("job.transcript_path is required before translation")

        translation = self.provider.translate(
            transcript,
            self.config.translation_source_language,
            self.config.target_language,
        )
        translation = Translation(
            segments=translation.segments,
            source_language=translation.source_language,
            target_language=translation.target_language,
            source_transcript=job.transcript_path,
        )

        translation_path = self._translation_output_path(job)
        translation_path.parent.mkdir(parents=True, exist_ok=True)
        translation_path.write_text(
            json.dumps(_translation_to_dict(translation), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        updated_job = job.with_status(
            JobStatus.TRANSLATED,
            translation_path=translation_path,
        )
        self.logger.info("Translated %s to %s", job.transcript_path, translation_path)
        return TranslationResult(job=updated_job, translation=translation)

    def _translation_output_path(self, job: VideoJob) -> Path:
        return self.config.temp_folder / f"{job.video_name}_translation.json"


def _translation_to_dict(translation: Translation) -> dict[str, Any]:
    return {
        "source_language": translation.source_language,
        "target_language": translation.target_language,
        "source_transcript": str(translation.source_transcript),
        "segments": [
            {
                "start_time": segment.start_time,
                "end_time": segment.end_time,
                "text": segment.text,
            }
            for segment in translation.segments
        ],
    }


__all__ = [
    "GoogleTranslateProvider",
    "TranslationError",
    "TranslationProvider",
    "TranslationResult",
    "TranslationService",
]
