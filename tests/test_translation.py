import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from models import Config, JobStatus, TextSegment, Transcript, Translation, VideoJob
from translation import (
    GoogleTranslateProvider,
    TranslationError,
    TranslationProvider,
    TranslationService,
)


class FakeTranslationResponse:
    def __init__(self, text):
        self.text = text


class FakeTranslatorClient:
    def __init__(self, translations=None, error=None, fail_times=None):
        self.translations = translations or {}
        self.error = error
        self.fail_times = fail_times
        self.calls = []

    def translate(self, text, src, dest):
        self.calls.append((text, src, dest))
        should_fail = self.error is not None and (
            self.fail_times is None or len(self.calls) <= self.fail_times
        )
        if should_fail:
            raise self.error
        return FakeTranslationResponse(self.translations[text])


class FakeSleep:
    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)


class FakeProvider(TranslationProvider):
    def __init__(self, translation=None, error=None):
        self.translation = translation
        self.error = error
        self.calls = []

    def translate(
        self,
        transcript: Transcript,
        source_language: str,
        target_language: str,
    ) -> Translation:
        self.calls.append((transcript, source_language, target_language))
        if self.error is not None:
            raise self.error
        return self.translation


class GoogleTranslateProviderTests(unittest.TestCase):
    def test_default_translator_disables_http2(self):
        with patch("googletrans.Translator") as translator_cls:
            GoogleTranslateProvider()

        translator_cls.assert_called_once_with(http2=False, raise_exception=True)

    def test_translate_preserves_segment_timing_and_boundaries(self):
        transcript = Transcript(
            segments=[
                TextSegment(start_time=0.0, end_time=1.5, text="你好"),
                TextSegment(start_time=1.5, end_time=3.0, text="世界"),
            ],
            language="zh",
            source_audio=Path("temp/drama_audio.wav"),
        )
        client = FakeTranslatorClient(
            translations={
                "你好": "Halo",
                "世界": "Dunia",
            }
        )
        provider = GoogleTranslateProvider(translator_client=client)

        translation = provider.translate(transcript, source_language="zh-cn", target_language="id")

        self.assertEqual(
            client.calls,
            [
                ("你好", "zh-cn", "id"),
                ("世界", "zh-cn", "id"),
            ],
        )
        self.assertEqual(translation.source_language, "zh-cn")
        self.assertEqual(translation.target_language, "id")
        self.assertEqual(translation.source_transcript, Path("temp/drama_audio.wav"))
        self.assertEqual(
            translation.segments,
            (
                TextSegment(start_time=0.0, end_time=1.5, text="Halo"),
                TextSegment(start_time=1.5, end_time=3.0, text="Dunia"),
            ),
        )

    def test_translate_retries_transient_failures_then_succeeds(self):
        transcript = Transcript(
            segments=[TextSegment(start_time=0.0, end_time=1.0, text="你好")],
            language="zh",
            source_audio=Path("temp/drama_audio.wav"),
        )
        client = FakeTranslatorClient(
            translations={"你好": "Halo"},
            error=TimeoutError("read timed out"),
            fail_times=2,
        )
        sleep = FakeSleep()
        provider = GoogleTranslateProvider(
            translator_client=client,
            max_retries=3,
            retry_backoff_seconds=2.0,
            sleep=sleep,
        )

        translation = provider.translate(transcript, source_language="zh-cn", target_language="id")

        self.assertEqual(len(client.calls), 3)
        self.assertEqual(translation.segments[0].text, "Halo")
        self.assertEqual(sleep.calls, [2.0, 4.0])

    def test_translate_gives_up_after_max_retries_exhausted(self):
        transcript = Transcript(
            segments=[TextSegment(start_time=0.0, end_time=1.0, text="你好")],
            language="zh",
            source_audio=Path("temp/drama_audio.wav"),
        )
        client = FakeTranslatorClient(error=TimeoutError("read timed out"))
        sleep = FakeSleep()
        provider = GoogleTranslateProvider(
            translator_client=client,
            max_retries=2,
            retry_backoff_seconds=1.0,
            sleep=sleep,
        )

        with self.assertRaises(TranslationError) as error:
            provider.translate(transcript, source_language="zh-cn", target_language="id")

        self.assertIn("read timed out", str(error.exception))
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(sleep.calls, [1.0, 2.0])

    def test_translate_wraps_client_errors(self):
        transcript = Transcript(
            segments=[TextSegment(start_time=0.0, end_time=1.0, text="你好")],
            language="zh",
            source_audio=Path("temp/drama_audio.wav"),
        )
        provider = GoogleTranslateProvider(
            translator_client=FakeTranslatorClient(error=RuntimeError("network failed")),
            sleep=FakeSleep(),
        )

        with self.assertRaises(TranslationError) as error:
            provider.translate(transcript, source_language="zh-cn", target_language="id")

        self.assertIn("network failed", str(error.exception))


class TranslationServiceTests(unittest.TestCase):
    def test_translate_saves_translation_json_and_updates_job(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            transcript_path = root / "temp" / "drama_transcript.json"
            transcript_path.parent.mkdir()
            transcript_path.write_text("{}", encoding="utf-8")
            job = VideoJob(
                job_id="job-1",
                video_path=root / "input" / "drama.mp4",
                transcript_path=transcript_path,
                status=JobStatus.TRANSCRIBED,
            )
            transcript = Transcript(
                segments=[TextSegment(start_time=0.0, end_time=1.0, text="你好")],
                language="zh",
                source_audio=root / "temp" / "drama_audio.wav",
            )
            translation = Translation(
                segments=[TextSegment(start_time=0.0, end_time=1.0, text="Halo")],
                source_language="zh-cn",
                target_language="id",
                source_transcript=transcript_path,
            )
            provider = FakeProvider(translation=translation)
            service = TranslationService(
                provider=provider,
                config=Config(
                    temp_folder=root / "temp",
                    translation_source_language="zh-cn",
                    target_language="id",
                ),
            )

            result = service.translate(job, transcript)

            self.assertIsNot(result.job, job)
            self.assertEqual(job.status, JobStatus.TRANSCRIBED)
            self.assertIsNone(job.translation_path)
            self.assertEqual(result.job.status, JobStatus.TRANSLATED)
            self.assertEqual(result.job.translation_path, root / "temp" / "drama_translation.json")
            self.assertEqual(result.translation, translation)
            self.assertEqual(provider.calls, [(transcript, "zh-cn", "id")])

            payload = json.loads(result.job.translation_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["source_language"], "zh-cn")
        self.assertEqual(payload["target_language"], "id")
        self.assertEqual(payload["source_transcript"], str(transcript_path))
        self.assertEqual(payload["segments"][0]["start_time"], 0.0)
        self.assertEqual(payload["segments"][0]["end_time"], 1.0)
        self.assertEqual(payload["segments"][0]["text"], "Halo")

    def test_translate_requires_transcript_path(self):
        transcript = Transcript(
            segments=[],
            language="zh",
            source_audio=Path("temp/drama_audio.wav"),
        )
        service = TranslationService(provider=FakeProvider(), config=Config())
        job = VideoJob(job_id="job-1", video_path=Path("input/drama.mp4"))

        with self.assertRaises(TranslationError) as error:
            service.translate(job, transcript)

        self.assertIn("transcript_path is required", str(error.exception))

    def test_translate_preserves_job_when_provider_fails(self):
        transcript = Transcript(
            segments=[TextSegment(start_time=0.0, end_time=1.0, text="你好")],
            language="zh",
            source_audio=Path("temp/drama_audio.wav"),
        )
        job = VideoJob(
            job_id="job-1",
            video_path=Path("input/drama.mp4"),
            transcript_path=Path("temp/drama_transcript.json"),
            status=JobStatus.TRANSCRIBED,
        )
        service = TranslationService(
            provider=FakeProvider(error=TranslationError("provider failed")),
            config=Config(),
        )

        with self.assertRaises(TranslationError):
            service.translate(job, transcript)

        self.assertEqual(job.status, JobStatus.TRANSCRIBED)
        self.assertIsNone(job.translation_path)


if __name__ == "__main__":
    unittest.main()
