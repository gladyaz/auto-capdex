import json
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

from cleanup import CleanupManager
from job_logger import JobLogger
from models import Config, JobStatus, TextSegment, Transcript, Translation, VideoJob
from pipeline import PipelineRunner, PipelineSummary, parse_args
from retry_manager import RetryManager
from transcription import TranscriptionResult
from translation import TranslationResult


class FakeScanner:
    def __init__(self, jobs):
        self.jobs = jobs
        self.calls = []

    def scan(self, input_folder):
        self.calls.append(Path(input_folder))
        return self.jobs


class FakeAudioExtractor:
    def __init__(self, config, fail_names=None, processed=None):
        self.config = config
        self.fail_names = set(fail_names or [])
        self.processed = processed if processed is not None else []

    def extract(self, job):
        self.processed.append(("audio", job.video_name))
        if job.video_name in self.fail_names:
            raise RuntimeError("audio failed")
        path = self.config.temp_folder / f"{job.video_name}_audio.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("audio", encoding="utf-8")
        return job.with_status(JobStatus.AUDIO_EXTRACTED, audio_path=path)


class FakeTranscriptionService:
    def __init__(self, config, processed=None):
        self.config = config
        self.processed = processed if processed is not None else []

    def transcribe(self, job):
        self.processed.append(("transcription", job.video_name))
        transcript = Transcript(
            segments=[TextSegment(start_time=0.0, end_time=1.0, text="你好")],
            language="zh",
            source_audio=job.audio_path,
        )
        path = self.config.temp_folder / f"{job.video_name}_transcript.json"
        path.write_text("{}", encoding="utf-8")
        return TranscriptionResult(
            job=job.with_status(JobStatus.TRANSCRIBED, transcript_path=path),
            transcript=transcript,
        )


class FakeTranslationService:
    def __init__(self, config, processed=None):
        self.config = config
        self.processed = processed if processed is not None else []

    def translate(self, job, transcript):
        self.processed.append(("translation", job.video_name))
        translation = Translation(
            segments=[TextSegment(start_time=0.0, end_time=1.0, text="Halo")],
            source_language="zh-cn",
            target_language="id",
            source_transcript=job.transcript_path,
        )
        path = self.config.temp_folder / f"{job.video_name}_translation.json"
        path.write_text("{}", encoding="utf-8")
        return TranslationResult(
            job=job.with_status(JobStatus.TRANSLATED, translation_path=path),
            translation=translation,
        )


class FakeSubtitleGenerator:
    def __init__(self, config, processed=None):
        self.config = config
        self.processed = processed if processed is not None else []

    def generate(self, job, translation):
        self.processed.append(("subtitle", job.video_name))
        path = self.config.output_folder / f"{job.video_name}.srt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("1\n00:00:00,000 --> 00:00:01,000\nHalo\n\n", encoding="utf-8")
        return job.with_status(JobStatus.SRT_GENERATED, srt_path=path)


class FakeVideoProcessor:
    def __init__(self, config, processed=None):
        self.config = config
        self.processed = processed if processed is not None else []

    def burn_subtitles(self, job):
        self.processed.append(("video", job.video_name))
        path = self.config.output_folder / f"{job.video_name}_subtitled.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"video")
        return job.with_status(JobStatus.COMPLETED, output_video_path=path)


class ConcurrencyTrackingTranscriptionService:
    """Records the peak number of simultaneous transcribe() calls."""

    def __init__(self, config, processed=None):
        self.config = config
        self.processed = processed if processed is not None else []
        self._lock = threading.Lock()
        self._active = 0
        self.peak_concurrent = 0

    def transcribe(self, job):
        with self._lock:
            self._active += 1
            self.peak_concurrent = max(self.peak_concurrent, self._active)
        try:
            self.processed.append(("transcription", job.video_name))
            transcript = Transcript(
                segments=[TextSegment(start_time=0.0, end_time=1.0, text="你好")],
                language="zh",
                source_audio=job.audio_path,
            )
            path = self.config.temp_folder / f"{job.video_name}_transcript.json"
            path.write_text("{}", encoding="utf-8")
            return TranscriptionResult(
                job=job.with_status(JobStatus.TRANSCRIBED, transcript_path=path),
                transcript=transcript,
            )
        finally:
            with self._lock:
                self._active -= 1


class BarrierAudioExtractor:
    """Fails (via timeout) unless `participant_count` jobs extract audio concurrently."""

    def __init__(self, config, participant_count, processed=None):
        self.config = config
        self.processed = processed if processed is not None else []
        self.barrier = threading.Barrier(participant_count, timeout=2)

    def extract(self, job):
        self.processed.append(("audio", job.video_name))
        self.barrier.wait()
        path = self.config.temp_folder / f"{job.video_name}_audio.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("audio", encoding="utf-8")
        return job.with_status(JobStatus.AUDIO_EXTRACTED, audio_path=path)


class PipelineRunnerTests(unittest.TestCase):
    def test_run_processes_jobs_sequentially_and_writes_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = Config(
                input_folder=root / "input",
                output_folder=root / "output",
                temp_folder=root / "temp",
            )
            config.input_folder.mkdir()
            jobs = [
                VideoJob(job_id="job-1", video_path=config.input_folder / "one.mp4"),
                VideoJob(job_id="job-2", video_path=config.input_folder / "two.mp4"),
            ]
            processed = []
            runner = PipelineRunner(
                config=config,
                scanner=FakeScanner(jobs),
                audio_extractor=FakeAudioExtractor(config, processed=processed),
                transcription_service=FakeTranscriptionService(config, processed=processed),
                translation_service=FakeTranslationService(config, processed=processed),
                subtitle_generator=FakeSubtitleGenerator(config, processed=processed),
                video_processor=FakeVideoProcessor(config, processed=processed),
                job_logger=JobLogger(input_folder=config.input_folder, output_folder=config.output_folder),
                retry_manager=RetryManager(),
                cleanup_manager=CleanupManager(config),
                progress_writer=None,
            )

            summary = runner.run()
            report = json.loads((config.output_folder / "batch_report.json").read_text(encoding="utf-8"))
            state = json.loads((config.output_folder / "job_state.json").read_text(encoding="utf-8"))

        self.assertIsInstance(summary, PipelineSummary)
        self.assertEqual(summary.success_count, 2)
        self.assertEqual(summary.failure_count, 0)
        self.assertEqual(report["success_count"], 2)
        self.assertEqual(report["failure_count"], 0)
        self.assertEqual([job["status"] for job in state["jobs"]], ["completed", "completed"])
        self.assertEqual(
            processed,
            [
                ("audio", "one"),
                ("transcription", "one"),
                ("translation", "one"),
                ("subtitle", "one"),
                ("video", "one"),
                ("audio", "two"),
                ("transcription", "two"),
                ("translation", "two"),
                ("subtitle", "two"),
                ("video", "two"),
            ],
        )

    def test_run_marks_failed_job_and_continues_remaining_jobs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = Config(
                input_folder=root / "input",
                output_folder=root / "output",
                temp_folder=root / "temp",
            )
            config.input_folder.mkdir()
            jobs = [
                VideoJob(job_id="job-1", video_path=config.input_folder / "bad.mp4"),
                VideoJob(job_id="job-2", video_path=config.input_folder / "good.mp4"),
            ]
            processed = []
            runner = PipelineRunner(
                config=config,
                scanner=FakeScanner(jobs),
                audio_extractor=FakeAudioExtractor(config, fail_names={"bad"}, processed=processed),
                transcription_service=FakeTranscriptionService(config, processed=processed),
                translation_service=FakeTranslationService(config, processed=processed),
                subtitle_generator=FakeSubtitleGenerator(config, processed=processed),
                video_processor=FakeVideoProcessor(config, processed=processed),
                job_logger=JobLogger(input_folder=config.input_folder, output_folder=config.output_folder),
                retry_manager=RetryManager(),
                cleanup_manager=CleanupManager(config),
                progress_writer=None,
            )

            summary = runner.run()
            failed_jobs = (config.output_folder / "failed_jobs.txt").read_text(encoding="utf-8")
            state = json.loads((config.output_folder / "job_state.json").read_text(encoding="utf-8"))

        self.assertEqual(summary.success_count, 1)
        self.assertEqual(summary.failure_count, 1)
        self.assertIn("bad.mp4: RuntimeError: audio failed", failed_jobs)
        self.assertEqual([job["status"] for job in state["jobs"]], ["failed", "completed"])
        self.assertIn(("video", "good"), processed)

    def test_run_resume_skips_completed_jobs_from_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = Config(
                input_folder=root / "input",
                output_folder=root / "output",
                temp_folder=root / "temp",
            )
            config.input_folder.mkdir()
            config.output_folder.mkdir()
            completed = VideoJob(
                job_id="job-1",
                video_path=config.input_folder / "done.mp4",
                status=JobStatus.COMPLETED,
                output_video_path=config.output_folder / "done_subtitled.mp4",
            )
            pending = VideoJob(job_id="job-2", video_path=config.input_folder / "todo.mp4")
            RetryManager().save_job_state(config.output_folder / "job_state.json", [completed, pending])
            scanner = FakeScanner([])
            processed = []
            runner = PipelineRunner(
                config=config,
                scanner=scanner,
                audio_extractor=FakeAudioExtractor(config, processed=processed),
                transcription_service=FakeTranscriptionService(config, processed=processed),
                translation_service=FakeTranslationService(config, processed=processed),
                subtitle_generator=FakeSubtitleGenerator(config, processed=processed),
                video_processor=FakeVideoProcessor(config, processed=processed),
                job_logger=JobLogger(input_folder=config.input_folder, output_folder=config.output_folder),
                retry_manager=RetryManager(),
                cleanup_manager=CleanupManager(config),
                progress_writer=None,
            )

            summary = runner.run(resume=True)
            state = json.loads((config.output_folder / "job_state.json").read_text(encoding="utf-8"))

        self.assertEqual(scanner.calls, [])
        self.assertEqual(summary.success_count, 2)
        self.assertEqual(summary.failure_count, 0)
        self.assertEqual(processed, [
            ("audio", "todo"),
            ("transcription", "todo"),
            ("translation", "todo"),
            ("subtitle", "todo"),
            ("video", "todo"),
        ])
        self.assertEqual([job["status"] for job in state["jobs"]], ["completed", "completed"])

    def test_run_with_concurrency_processes_all_jobs_successfully(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = Config(
                input_folder=root / "input",
                output_folder=root / "output",
                temp_folder=root / "temp",
                concurrency_level=3,
            )
            config.input_folder.mkdir()
            jobs = [
                VideoJob(job_id=f"job-{i}", video_path=config.input_folder / f"v{i}.mp4")
                for i in range(5)
            ]
            processed = []
            runner = PipelineRunner(
                config=config,
                scanner=FakeScanner(jobs),
                audio_extractor=FakeAudioExtractor(config, processed=processed),
                transcription_service=FakeTranscriptionService(config, processed=processed),
                translation_service=FakeTranslationService(config, processed=processed),
                subtitle_generator=FakeSubtitleGenerator(config, processed=processed),
                video_processor=FakeVideoProcessor(config, processed=processed),
                job_logger=JobLogger(input_folder=config.input_folder, output_folder=config.output_folder),
                retry_manager=RetryManager(),
                cleanup_manager=CleanupManager(config),
                progress_writer=None,
            )

            summary = runner.run()
            state = json.loads((config.output_folder / "job_state.json").read_text(encoding="utf-8"))

        self.assertEqual(summary.success_count, 5)
        self.assertEqual(summary.failure_count, 0)
        self.assertEqual(len(state["jobs"]), 5)
        self.assertTrue(all(job["status"] == "completed" for job in state["jobs"]))

    def test_run_serializes_transcription_across_concurrent_jobs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = Config(
                input_folder=root / "input",
                output_folder=root / "output",
                temp_folder=root / "temp",
                concurrency_level=4,
            )
            config.input_folder.mkdir()
            jobs = [
                VideoJob(job_id=f"job-{i}", video_path=config.input_folder / f"v{i}.mp4")
                for i in range(4)
            ]
            processed = []
            transcription_service = ConcurrencyTrackingTranscriptionService(config, processed=processed)
            runner = PipelineRunner(
                config=config,
                scanner=FakeScanner(jobs),
                audio_extractor=FakeAudioExtractor(config, processed=processed),
                transcription_service=transcription_service,
                translation_service=FakeTranslationService(config, processed=processed),
                subtitle_generator=FakeSubtitleGenerator(config, processed=processed),
                video_processor=FakeVideoProcessor(config, processed=processed),
                job_logger=JobLogger(input_folder=config.input_folder, output_folder=config.output_folder),
                retry_manager=RetryManager(),
                cleanup_manager=CleanupManager(config),
                progress_writer=None,
            )

            summary = runner.run()

        self.assertEqual(summary.success_count, 4)
        self.assertEqual(transcription_service.peak_concurrent, 1)

    def test_run_overlaps_non_transcription_stages_across_jobs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = Config(
                input_folder=root / "input",
                output_folder=root / "output",
                temp_folder=root / "temp",
                concurrency_level=3,
            )
            config.input_folder.mkdir()
            jobs = [
                VideoJob(job_id=f"job-{i}", video_path=config.input_folder / f"v{i}.mp4")
                for i in range(3)
            ]
            processed = []
            runner = PipelineRunner(
                config=config,
                scanner=FakeScanner(jobs),
                audio_extractor=BarrierAudioExtractor(config, participant_count=3, processed=processed),
                transcription_service=FakeTranscriptionService(config, processed=processed),
                translation_service=FakeTranslationService(config, processed=processed),
                subtitle_generator=FakeSubtitleGenerator(config, processed=processed),
                video_processor=FakeVideoProcessor(config, processed=processed),
                job_logger=JobLogger(input_folder=config.input_folder, output_folder=config.output_folder),
                retry_manager=RetryManager(),
                cleanup_manager=CleanupManager(config),
                progress_writer=None,
            )

            summary = runner.run()

        self.assertEqual(summary.success_count, 3)
        self.assertEqual(summary.failure_count, 0)

    def test_run_isolates_failures_under_concurrency(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = Config(
                input_folder=root / "input",
                output_folder=root / "output",
                temp_folder=root / "temp",
                concurrency_level=3,
            )
            config.input_folder.mkdir()
            jobs = [
                VideoJob(job_id=f"job-{i}", video_path=config.input_folder / name)
                for i, name in enumerate(["bad.mp4", "good1.mp4", "good2.mp4"])
            ]
            processed = []
            runner = PipelineRunner(
                config=config,
                scanner=FakeScanner(jobs),
                audio_extractor=FakeAudioExtractor(config, fail_names={"bad"}, processed=processed),
                transcription_service=FakeTranscriptionService(config, processed=processed),
                translation_service=FakeTranslationService(config, processed=processed),
                subtitle_generator=FakeSubtitleGenerator(config, processed=processed),
                video_processor=FakeVideoProcessor(config, processed=processed),
                job_logger=JobLogger(input_folder=config.input_folder, output_folder=config.output_folder),
                retry_manager=RetryManager(),
                cleanup_manager=CleanupManager(config),
                progress_writer=None,
            )

            summary = runner.run()
            state = json.loads((config.output_folder / "job_state.json").read_text(encoding="utf-8"))

        self.assertEqual(summary.success_count, 2)
        self.assertEqual(summary.failure_count, 1)
        statuses = {job["video_path"].split("/")[-1]: job["status"] for job in state["jobs"]}
        self.assertEqual(statuses["bad.mp4"], "failed")
        self.assertEqual(statuses["good1.mp4"], "completed")
        self.assertEqual(statuses["good2.mp4"], "completed")


class PipelineCliTests(unittest.TestCase):
    def test_parse_args_accepts_required_paths_and_resume(self):
        args = parse_args(
            [
                "--input",
                "input",
                "--output",
                "output",
                "--config",
                "config.yaml",
                "--resume",
            ]
        )

        self.assertEqual(args.input, Path("input"))
        self.assertEqual(args.output, Path("output"))
        self.assertEqual(args.config, Path("config.yaml"))
        self.assertTrue(args.resume)

    def test_parse_args_requires_input_and_output(self):
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                parse_args([])


if __name__ == "__main__":
    unittest.main()
