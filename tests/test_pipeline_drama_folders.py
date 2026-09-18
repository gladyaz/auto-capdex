import json
import logging
import tempfile
import unittest
import uuid
from pathlib import Path

from cleanup import CleanupManager
from folder_titles import FolderTitleTranslator
from job_logger import JobLogger
from models import Config, JobStatus, TextSegment, Transcript, Translation, VideoJob
from pipeline import PipelineRunner
from retry_manager import RetryManager
from transcription import TranscriptionResult
from translation import TranslationResult


JPEG_BYTES = b"\xff\xd8\xff\xe0" + bytes(range(256)) * 4 + b"\xff\xd9"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + bytes(range(255, -1, -1)) * 4
WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBPVP8 " + bytes(range(128))


def _silent_logger():
    logger = logging.getLogger("pipeline_drama_folder_tests")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


class FakeScanner:
    def __init__(self, jobs):
        self.jobs = jobs
        self.skipped_files = []

    def scan(self, input_folder):
        return list(self.jobs)


class FakeAudioExtractor:
    def __init__(self, config):
        self.config = config

    def extract(self, job):
        path = self.config.temp_folder / f"{job.video_name}_audio.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("audio", encoding="utf-8")
        return job.with_status(JobStatus.AUDIO_EXTRACTED, audio_path=path)


class FakeTranscriptionService:
    def __init__(self, config):
        self.config = config

    def transcribe(self, job):
        path = self.config.temp_folder / f"{job.video_name}_transcript.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        return TranscriptionResult(
            job=job.with_status(JobStatus.TRANSCRIBED, transcript_path=path),
            transcript=Transcript(
                segments=[TextSegment(start_time=0.0, end_time=1.0, text="你好")],
                language="zh",
                source_audio=job.audio_path,
            ),
        )


class FakeTranslationService:
    """Mirrors TranslationService, including the `provider` attribute."""

    def __init__(self, config, provider=None):
        self.config = config
        self.provider = provider

    def translate(self, job, transcript):
        path = self.config.temp_folder / f"{job.video_name}_translation.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        return TranslationResult(
            job=job.with_status(JobStatus.TRANSLATED, translation_path=path),
            translation=Translation(
                segments=[TextSegment(start_time=0.0, end_time=1.0, text="Halo")],
                source_language="zh-cn",
                target_language="id",
                source_transcript=job.transcript_path,
            ),
        )


class FakeSubtitleGenerator:
    """Writes to output_name, exactly like the real SubtitleGenerator."""

    def __init__(self, config):
        self.config = config

    def generate(self, job, translation):
        path = self.config.output_folder / f"{job.output_name}.srt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("1\n00:00:00,000 --> 00:00:01,000\nHalo\n\n", encoding="utf-8")
        return job.with_status(JobStatus.SRT_GENERATED, srt_path=path)


class FakeVideoProcessor:
    """Writes to output_name, exactly like the real VideoProcessor."""

    def __init__(self, config):
        self.config = config

    def burn_subtitles(self, job):
        path = self.config.output_folder / f"{job.output_name}_subtitled.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"video")
        return job.with_status(JobStatus.COMPLETED, output_video_path=path)


class CountingTextTranslator:
    def __init__(self, mapping=None, error=None):
        self.mapping = mapping or {}
        self.error = error
        self.calls = []

    def translate_text(self, text, source_language, target_language):
        self.calls.append(text)
        if self.error is not None:
            raise self.error
        return self.mapping.get(text, f"terjemahan {text}")


def _snapshot(folder):
    """Relative path -> bytes for every file under `folder`."""
    root = Path(folder)
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class DramaFolderPipelineTests(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.root = Path(self._temp_dir.name)
        self.config = Config(
            input_folder=self.root / "input",
            output_folder=self.root / "output",
            temp_folder=self.root / "temp",
        )
        self.config.input_folder.mkdir(parents=True)

    def _add_drama_folder(self, folder_name, videos=("001.mp4",), images=()):
        folder = self.config.input_folder / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        jobs = []
        for video in videos:
            (folder / video).write_bytes(b"video")
            jobs.append(
                VideoJob(
                    job_id=str(uuid.uuid4()),
                    video_path=folder / video,
                    video_name=f"{folder_name}/{Path(video).stem}",
                )
            )
        for image_name, payload in images:
            (folder / image_name).write_bytes(payload)
        return jobs

    def _run(self, jobs, translator, resume=False):
        runner = PipelineRunner(
            config=self.config,
            scanner=FakeScanner(jobs),
            audio_extractor=FakeAudioExtractor(self.config),
            transcription_service=FakeTranscriptionService(self.config),
            translation_service=FakeTranslationService(self.config),
            subtitle_generator=FakeSubtitleGenerator(self.config),
            video_processor=FakeVideoProcessor(self.config),
            job_logger=JobLogger(
                input_folder=self.config.input_folder,
                output_folder=self.config.output_folder,
            ),
            retry_manager=RetryManager(),
            cleanup_manager=CleanupManager(self.config),
            title_translator=FolderTitleTranslator(translator, logger=_silent_logger()),
            progress_writer=None,
        )
        return runner.run(resume=resume)

    def test_output_folder_uses_the_indonesian_title(self):
        jobs = self._add_drama_folder("143-老公突然有了读心术")
        translator = CountingTextTranslator(
            {"老公突然有了读心术": "suamiku tiba-tiba bisa membaca pikiran"}
        )

        summary = self._run(jobs, translator)

        expected = self.config.output_folder / "143-Suamiku Tiba-Tiba Bisa Membaca Pikiran"
        self.assertEqual(summary.success_count, 1)
        self.assertTrue(expected.is_dir())
        self.assertTrue((expected / "001_subtitled.mp4").is_file())
        self.assertTrue((expected / "001.srt").is_file())

    def test_numeric_prefix_and_episode_count_survive_translation(self):
        jobs = self._add_drama_folder("4-网恋掉马那天全寝室沉默了（35集）")
        translator = CountingTextTranslator(
            {"网恋掉马那天全寝室沉默了": "seisi asrama terdiam"}
        )

        self._run(jobs, translator)

        self.assertTrue(
            (self.config.output_folder / "4-Seisi Asrama Terdiam (35 Episode)").is_dir()
        )

    def test_windows_invalid_characters_never_reach_the_output_folder(self):
        jobs = self._add_drama_folder("12-某剧")
        translator = CountingTextTranslator({"某剧": 'cinta: rahasia/terlarang?'})

        self._run(jobs, translator)

        created = [
            path.name for path in self.config.output_folder.iterdir() if path.is_dir()
        ]
        self.assertEqual(created, ["12-Cinta - Rahasia-Terlarang"])
        for character in '<>:"/\\|?*':
            self.assertNotIn(character, created[0])

    def test_poster_jpg_is_copied_into_the_translated_folder(self):
        jobs = self._add_drama_folder(
            "143-老公突然有了读心术",
            images=(("poster.jpg", JPEG_BYTES),),
        )
        translator = CountingTextTranslator(
            {"老公突然有了读心术": "suamiku tiba-tiba bisa membaca pikiran"}
        )

        self._run(jobs, translator)

        copied = (
            self.config.output_folder
            / "143-Suamiku Tiba-Tiba Bisa Membaca Pikiran"
            / "poster.jpg"
        )
        self.assertTrue(copied.is_file())
        self.assertEqual(copied.read_bytes(), JPEG_BYTES)

    def test_cover_png_is_copied_into_the_translated_folder(self):
        jobs = self._add_drama_folder("7-某剧", images=(("cover.png", PNG_BYTES),))
        translator = CountingTextTranslator({"某剧": "drama rahasia"})

        self._run(jobs, translator)

        copied = self.config.output_folder / "7-Drama Rahasia" / "cover.png"
        self.assertTrue(copied.is_file())
        self.assertEqual(copied.read_bytes(), PNG_BYTES)

    def test_every_image_in_a_folder_is_copied(self):
        jobs = self._add_drama_folder(
            "143-老公突然有了读心术",
            videos=("001.mp4", "002.mp4"),
            images=(
                ("poster.jpg", JPEG_BYTES),
                ("thumbnail.png", PNG_BYTES),
                ("banner.webp", WEBP_BYTES),
            ),
        )
        translator = CountingTextTranslator(
            {"老公突然有了读心术": "suamiku tiba-tiba bisa membaca pikiran"}
        )

        self._run(jobs, translator)

        output = self.config.output_folder / "143-Suamiku Tiba-Tiba Bisa Membaca Pikiran"
        self.assertEqual((output / "poster.jpg").read_bytes(), JPEG_BYTES)
        self.assertEqual((output / "thumbnail.png").read_bytes(), PNG_BYTES)
        self.assertEqual((output / "banner.webp").read_bytes(), WEBP_BYTES)

    def test_images_are_not_processed_as_videos(self):
        jobs = self._add_drama_folder(
            "143-老公突然有了读心术",
            images=(("poster.jpg", JPEG_BYTES),),
        )
        translator = CountingTextTranslator(
            {"老公突然有了读心术": "suamiku tiba-tiba bisa membaca pikiran"}
        )

        summary = self._run(jobs, translator)
        output = self.config.output_folder / "143-Suamiku Tiba-Tiba Bisa Membaca Pikiran"

        self.assertEqual(summary.total_count, 1)
        self.assertFalse((output / "poster_subtitled.mp4").exists())
        self.assertFalse((output / "poster.srt").exists())

    def test_source_folder_is_never_renamed_or_modified(self):
        jobs = self._add_drama_folder(
            "143-老公突然有了读心术",
            videos=("001.mp4", "002.mp4"),
            images=(("poster.jpg", JPEG_BYTES), ("cover.png", PNG_BYTES)),
        )
        translator = CountingTextTranslator(
            {"老公突然有了读心术": "suamiku tiba-tiba bisa membaca pikiran"}
        )
        before = _snapshot(self.config.input_folder)

        self._run(jobs, translator)

        self.assertTrue((self.config.input_folder / "143-老公突然有了读心术").is_dir())
        self.assertEqual(_snapshot(self.config.input_folder), before)

    def test_translation_runs_once_per_folder_not_once_per_video(self):
        jobs = self._add_drama_folder(
            "143-老公突然有了读心术",
            videos=("001.mp4", "002.mp4", "003.mp4", "004.mp4", "005.mp4"),
        )
        translator = CountingTextTranslator(
            {"老公突然有了读心术": "suamiku tiba-tiba bisa membaca pikiran"}
        )

        summary = self._run(jobs, translator)

        self.assertEqual(summary.success_count, 5)
        self.assertEqual(translator.calls, ["老公突然有了读心术"])

    def test_each_folder_is_translated_once_across_several_folders(self):
        jobs = self._add_drama_folder("4-剧甲", videos=("001.mp4", "002.mp4"))
        jobs += self._add_drama_folder("143-剧乙", videos=("001.mp4", "002.mp4"))
        translator = CountingTextTranslator({"剧甲": "drama satu", "剧乙": "drama dua"})

        self._run(jobs, translator)

        self.assertEqual(sorted(translator.calls), ["剧乙", "剧甲"])

    def test_duplicate_translated_titles_do_not_overwrite_each_other(self):
        jobs = self._add_drama_folder("禁忌之恋", images=(("poster.jpg", JPEG_BYTES),))
        jobs += self._add_drama_folder("不可以的爱", images=(("poster.jpg", PNG_BYTES),))
        translator = CountingTextTranslator(
            {"禁忌之恋": "cinta terlarang", "不可以的爱": "cinta terlarang"}
        )

        summary = self._run(jobs, translator)

        first = self.config.output_folder / "Cinta Terlarang"
        second = self.config.output_folder / "Cinta Terlarang-2"
        self.assertEqual(summary.success_count, 2)
        self.assertTrue((first / "001_subtitled.mp4").is_file())
        self.assertTrue((second / "001_subtitled.mp4").is_file())
        # Each folder keeps its own poster instead of one clobbering the other.
        self.assertEqual((first / "poster.jpg").read_bytes(), JPEG_BYTES)
        self.assertEqual((second / "poster.jpg").read_bytes(), PNG_BYTES)

    def test_translation_failure_falls_back_to_the_source_folder_name(self):
        jobs = self._add_drama_folder(
            "143-老公突然有了读心术",
            images=(("poster.jpg", JPEG_BYTES),),
        )
        translator = CountingTextTranslator(error=RuntimeError("googletrans timed out"))

        summary = self._run(jobs, translator)

        fallback = self.config.output_folder / "143-老公突然有了读心术"
        self.assertEqual(summary.success_count, 1)
        self.assertEqual(summary.failure_count, 0)
        self.assertTrue((fallback / "001_subtitled.mp4").is_file())
        self.assertEqual((fallback / "poster.jpg").read_bytes(), JPEG_BYTES)

    def test_translation_failure_is_recorded_in_the_batch_report(self):
        jobs = self._add_drama_folder("143-老公突然有了读心术")
        translator = CountingTextTranslator(error=RuntimeError("googletrans timed out"))

        self._run(jobs, translator)
        report = json.loads(
            (self.config.output_folder / "batch_report.json").read_text(encoding="utf-8")
        )

        folder = report["drama_folders"][0]
        self.assertEqual(folder["source_folder_name"], "143-老公突然有了读心术")
        self.assertEqual(folder["translated_folder_name"], "143-老公突然有了读心术")
        self.assertFalse(folder["title_translated"])
        self.assertIn("googletrans timed out", folder["title_translation_error"])

    def test_batch_report_records_the_folder_name_mapping(self):
        jobs = self._add_drama_folder("143-老公突然有了读心术")
        translator = CountingTextTranslator(
            {"老公突然有了读心术": "suamiku tiba-tiba bisa membaca pikiran"}
        )

        self._run(jobs, translator)
        report = json.loads(
            (self.config.output_folder / "batch_report.json").read_text(encoding="utf-8")
        )

        self.assertEqual(
            report["drama_folders"],
            [
                {
                    "source_folder_name": "143-老公突然有了读心术",
                    "translated_folder_name": "143-Suamiku Tiba-Tiba Bisa Membaca Pikiran",
                    "title_translated": True,
                }
            ],
        )

    def test_image_copy_failure_is_logged_and_other_videos_still_process(self):
        blocked_jobs = self._add_drama_folder("4-剧甲", images=(("poster.jpg", JPEG_BYTES),))
        healthy_jobs = self._add_drama_folder("143-剧乙")
        translator = CountingTextTranslator({"剧甲": "drama satu", "剧乙": "drama dua"})
        # A plain file where "4-Drama Satu" should go makes that folder's image
        # copy fail; the other drama must still be processed end to end.
        self.config.output_folder.mkdir(parents=True, exist_ok=True)
        (self.config.output_folder / "4-Drama Satu").write_bytes(b"not a folder")

        with self.assertLogs("image_assets", level="ERROR") as captured:
            summary = self._run(blocked_jobs + healthy_jobs, translator)

        failed = (self.config.output_folder / "failed_jobs.txt").read_text(encoding="utf-8")
        log_lines = (self.config.output_folder / "processing.log").read_text(encoding="utf-8")

        self.assertTrue(
            any("poster.jpg" in message for message in captured.output),
            captured.output,
        )
        self.assertIn("poster.jpg: Image copy failed", failed)
        self.assertIn("image_copy_failed", log_lines)
        # The unaffected drama completed despite the other folder's failure.
        self.assertEqual(summary.success_count, 1)
        self.assertTrue(
            (self.config.output_folder / "143-Drama Dua" / "001_subtitled.mp4").is_file()
        )

    def test_resume_reuses_the_stored_output_name_without_retranslating(self):
        jobs = self._add_drama_folder(
            "143-老公突然有了读心术",
            videos=("001.mp4", "002.mp4"),
            images=(("poster.jpg", JPEG_BYTES),),
        )
        translator = CountingTextTranslator(
            {"老公突然有了读心术": "suamiku tiba-tiba bisa membaca pikiran"}
        )
        self._run(jobs, translator)

        resume_translator = CountingTextTranslator(error=RuntimeError("must not be called"))
        summary = self._run([], resume_translator, resume=True)

        output = self.config.output_folder / "143-Suamiku Tiba-Tiba Bisa Membaca Pikiran"
        self.assertEqual(resume_translator.calls, [])
        self.assertEqual(summary.success_count, 2)
        self.assertTrue(output.is_dir())
        self.assertEqual((output / "poster.jpg").read_bytes(), JPEG_BYTES)

    def test_videos_without_a_drama_folder_keep_their_original_output_name(self):
        (self.config.input_folder / "loose.mp4").write_bytes(b"video")
        jobs = [
            VideoJob(
                job_id="job-loose",
                video_path=self.config.input_folder / "loose.mp4",
                video_name="loose",
            )
        ]
        translator = CountingTextTranslator()

        self._run(jobs, translator)

        self.assertEqual(translator.calls, [])
        self.assertTrue((self.config.output_folder / "loose_subtitled.mp4").is_file())


if __name__ == "__main__":
    unittest.main()
