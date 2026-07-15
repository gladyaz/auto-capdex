import json
import tempfile
import unittest
from pathlib import Path

from models import Config, JobStatus, TextSegment, Transcript, VideoJob
from transcription import (
    FasterWhisperProvider,
    TranscriptionError,
    TranscriptionProvider,
    TranscriptionService,
)


class FakeInfo:
    language = "zh"


class FakeWhisperWord:
    def __init__(self, start, end, word, probability):
        self.start = start
        self.end = end
        self.word = word
        self.probability = probability


class FakeWhisperSegment:
    def __init__(self, start, end, text, no_speech_prob=0.0, compression_ratio=1.0, words=None):
        self.start = start
        self.end = end
        self.text = text
        self.no_speech_prob = no_speech_prob
        self.compression_ratio = compression_ratio
        self.words = (
            words if words is not None else [FakeWhisperWord(start, end, text, probability=1.0)]
        )


class FakeWhisperModel:
    def __init__(self, segments=None, error=None):
        self.segments = segments or []
        self.error = error
        self.calls = []

    def transcribe(self, audio_file, language, **kwargs):
        self.calls.append((audio_file, language, kwargs))
        if self.error is not None:
            raise self.error
        return iter(self.segments), FakeInfo()


class FakeProvider(TranscriptionProvider):
    def __init__(self, transcript=None, error=None):
        self.transcript = transcript
        self.error = error
        self.calls = []

    def transcribe(self, audio_file: Path, language: str) -> Transcript:
        self.calls.append((audio_file, language))
        if self.error is not None:
            raise self.error
        return self.transcript


class FasterWhisperProviderTests(unittest.TestCase):
    def test_transcribe_returns_timestamped_transcript(self):
        fake_model = FakeWhisperModel(
            segments=[
                FakeWhisperSegment(0.0, 1.25, " 你好 "),
                FakeWhisperSegment(1.25, 2.0, "世界"),
            ]
        )
        captured_model_kwargs = {}

        def capturing_model_factory(*args, **kwargs):
            captured_model_kwargs.update(kwargs)
            return fake_model

        provider = FasterWhisperProvider(
            model_size="base",
            device="cpu",
            compute_type="int8",
            vad_filter=True,
            no_speech_threshold=0.75,
            condition_on_previous_text=False,
            cpu_threads=4,
            beam_size=5,
            model_factory=capturing_model_factory,
        )

        transcript = provider.transcribe(Path("temp/drama_audio.wav"), language="zh")

        self.assertEqual(captured_model_kwargs.get("cpu_threads"), 4)
        self.assertEqual(
            fake_model.calls,
            [
                (
                    "temp/drama_audio.wav",
                    "zh",
                    {
                        "vad_filter": True,
                        "no_speech_threshold": 0.75,
                        "condition_on_previous_text": False,
                        "beam_size": 5,
                        "compression_ratio_threshold": 2.4,
                        "word_timestamps": True,
                    },
                )
            ],
        )
        self.assertEqual(transcript.language, "zh")
        self.assertEqual(transcript.source_audio, Path("temp/drama_audio.wav"))
        self.assertEqual(
            transcript.segments,
            (
                TextSegment(start_time=0.0, end_time=1.25, text="你好"),
                TextSegment(start_time=1.25, end_time=2.0, text="世界"),
            ),
        )

    def test_transcribe_drops_segments_whisper_flags_as_non_speech(self):
        fake_model = FakeWhisperModel(
            segments=[
                FakeWhisperSegment(0.0, 7.0, "kamu melihat kamu melihat", no_speech_prob=0.92),
                FakeWhisperSegment(8.69, 9.19, "Hai", no_speech_prob=0.05),
            ]
        )
        provider = FasterWhisperProvider(
            no_speech_threshold=0.75,
            model_factory=lambda *args, **kwargs: fake_model,
        )

        transcript = provider.transcribe(Path("temp/drama_audio.wav"), language="zh")

        self.assertEqual(
            transcript.segments,
            (TextSegment(start_time=8.69, end_time=9.19, text="Hai"),),
        )

    def test_transcribe_drops_segments_with_high_compression_ratio(self):
        fake_model = FakeWhisperModel(
            segments=[
                FakeWhisperSegment(
                    0.0,
                    7.0,
                    "kamu melihat kamu melihat kamu melihat kamu melihat",
                    no_speech_prob=0.1,
                    compression_ratio=3.1,
                ),
                FakeWhisperSegment(8.69, 9.19, "Hai", no_speech_prob=0.05, compression_ratio=0.9),
            ]
        )
        provider = FasterWhisperProvider(
            compression_ratio_threshold=2.4,
            model_factory=lambda *args, **kwargs: fake_model,
        )

        transcript = provider.transcribe(Path("temp/drama_audio.wav"), language="zh")

        self.assertEqual(
            transcript.segments,
            (TextSegment(start_time=8.69, end_time=9.19, text="Hai"),),
        )

    def test_transcribe_skips_segments_before_intro_cutoff(self):
        fake_model = FakeWhisperModel(
            segments=[
                FakeWhisperSegment(0.0, 9.69, "真没眼睛"),
                FakeWhisperSegment(10.99, 31.15, "小城市"),
                FakeWhisperSegment(35.0, 36.5, "Xiao Cheng"),
            ]
        )
        provider = FasterWhisperProvider(
            skip_intro_seconds=32.0,
            model_factory=lambda *args, **kwargs: fake_model,
        )

        transcript = provider.transcribe(Path("temp/drama_audio.wav"), language="zh")

        self.assertEqual(
            transcript.segments,
            (TextSegment(start_time=35.0, end_time=36.5, text="Xiao Cheng"),),
        )

    def test_transcribe_drops_segment_with_no_confident_words(self):
        fake_model = FakeWhisperModel(
            segments=[
                FakeWhisperSegment(
                    0.0,
                    9.69,
                    "真没眼睛",
                    words=[
                        FakeWhisperWord(0.0, 3.0, "真没", probability=0.22),
                        FakeWhisperWord(3.0, 9.69, "眼睛", probability=0.18),
                    ],
                ),
                FakeWhisperSegment(
                    9.69,
                    10.9,
                    "Hai",
                    words=[FakeWhisperWord(9.69, 10.9, "Hai", probability=0.93)],
                ),
            ]
        )
        provider = FasterWhisperProvider(
            model_factory=lambda *args, **kwargs: fake_model,
        )

        transcript = provider.transcribe(Path("temp/drama_audio.wav"), language="zh")

        self.assertEqual(
            transcript.segments,
            (TextSegment(start_time=9.69, end_time=10.9, text="Hai"),),
        )

    def test_transcribe_tightens_segment_to_confident_word_span(self):
        fake_model = FakeWhisperModel(
            segments=[
                FakeWhisperSegment(
                    0.0,
                    30.0,
                    "noise noise 小城市 noise",
                    words=[
                        FakeWhisperWord(0.0, 5.0, "noise", probability=0.15),
                        FakeWhisperWord(5.0, 10.0, "noise", probability=0.20),
                        FakeWhisperWord(10.0, 12.0, "小城市", probability=0.91),
                        FakeWhisperWord(12.0, 30.0, "noise", probability=0.10),
                    ],
                ),
            ]
        )
        provider = FasterWhisperProvider(
            model_factory=lambda *args, **kwargs: fake_model,
        )

        transcript = provider.transcribe(Path("temp/drama_audio.wav"), language="zh")

        self.assertEqual(
            transcript.segments,
            (TextSegment(start_time=10.0, end_time=12.0, text="小城市"),),
        )

    def test_transcribe_wraps_model_errors(self):
        provider = FasterWhisperProvider(
            model_factory=lambda *args, **kwargs: FakeWhisperModel(error=RuntimeError("boom"))
        )

        with self.assertRaises(TranscriptionError) as error:
            provider.transcribe(Path("temp/drama_audio.wav"), language="zh")

        self.assertIn("boom", str(error.exception))


class TranscriptionServiceTests(unittest.TestCase):
    def test_transcribe_saves_transcript_json_and_updates_job(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio_path = root / "temp" / "drama_audio.wav"
            audio_path.parent.mkdir()
            audio_path.write_bytes(b"audio")
            job = VideoJob(
                job_id="job-1",
                video_path=root / "input" / "drama.mp4",
                audio_path=audio_path,
                status=JobStatus.AUDIO_EXTRACTED,
            )
            transcript = Transcript(
                segments=[TextSegment(start_time=0.0, end_time=1.0, text="你好")],
                language="zh",
                source_audio=audio_path,
            )
            provider = FakeProvider(transcript=transcript)
            service = TranscriptionService(
                provider=provider,
                config=Config(temp_folder=root / "temp", source_language="zh"),
            )

            result = service.transcribe(job)

            self.assertIsNot(result.job, job)
            self.assertEqual(job.status, JobStatus.AUDIO_EXTRACTED)
            self.assertIsNone(job.transcript_path)
            self.assertEqual(result.job.status, JobStatus.TRANSCRIBED)
            self.assertEqual(result.job.transcript_path, root / "temp" / "drama_transcript.json")
            self.assertEqual(result.transcript, transcript)
            self.assertEqual(provider.calls, [(audio_path, "zh")])

            payload = json.loads(result.job.transcript_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["language"], "zh")
        self.assertEqual(payload["source_audio"], str(audio_path))
        self.assertEqual(payload["segments"][0]["start_time"], 0.0)
        self.assertEqual(payload["segments"][0]["end_time"], 1.0)
        self.assertEqual(payload["segments"][0]["text"], "你好")

    def test_transcribe_requires_audio_path(self):
        service = TranscriptionService(provider=FakeProvider(), config=Config())
        job = VideoJob(job_id="job-1", video_path=Path("input/drama.mp4"))

        with self.assertRaises(TranscriptionError) as error:
            service.transcribe(job)

        self.assertIn("audio_path is required", str(error.exception))

    def test_transcribe_preserves_job_when_provider_fails(self):
        job = VideoJob(
            job_id="job-1",
            video_path=Path("input/drama.mp4"),
            audio_path=Path("temp/drama_audio.wav"),
            status=JobStatus.AUDIO_EXTRACTED,
        )
        service = TranscriptionService(
            provider=FakeProvider(error=TranscriptionError("provider failed")),
            config=Config(),
        )

        with self.assertRaises(TranscriptionError):
            service.transcribe(job)

        self.assertEqual(job.status, JobStatus.AUDIO_EXTRACTED)
        self.assertIsNone(job.transcript_path)


if __name__ == "__main__":
    unittest.main()
