import tempfile
import unittest
from pathlib import Path

from cleanup import CleanupManager
from models import Config, JobStatus, VideoJob


class CleanupManagerTests(unittest.TestCase):
    def test_cleanup_job_temp_files_deletes_temp_artifacts_after_success_when_enabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio = root / "temp" / "drama_audio.wav"
            transcript = root / "temp" / "drama_transcript.json"
            translation = root / "temp" / "drama_translation.json"
            srt = root / "output" / "drama.srt"
            output_video = root / "output" / "drama_subtitled.mp4"
            for path in (audio, transcript, translation, srt, output_video):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("data", encoding="utf-8")
            job = VideoJob(
                job_id="job-1",
                video_path=root / "input" / "drama.mp4",
                status=JobStatus.COMPLETED,
                audio_path=audio,
                transcript_path=transcript,
                translation_path=translation,
                srt_path=srt,
                output_video_path=output_video,
            )
            manager = CleanupManager(config=Config(cleanup_temp_on_success=True))

            removed = manager.cleanup_job_temp_files(job)

            self.assertEqual(removed, [audio, transcript, translation])
            self.assertFalse(audio.exists())
            self.assertFalse(transcript.exists())
            self.assertFalse(translation.exists())
            self.assertTrue(srt.exists())
            self.assertTrue(output_video.exists())

    def test_cleanup_job_temp_files_preserves_failed_job_artifacts_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio = root / "temp" / "broken_audio.wav"
            audio.parent.mkdir()
            audio.write_text("data", encoding="utf-8")
            job = VideoJob(
                job_id="job-1",
                video_path=root / "input" / "broken.mp4",
                status=JobStatus.FAILED,
                audio_path=audio,
            )
            manager = CleanupManager(config=Config(cleanup_temp_on_failure=False))

            removed = manager.cleanup_job_temp_files(job)

            self.assertEqual(removed, [])
            self.assertTrue(audio.exists())

    def test_cleanup_job_temp_files_deletes_failed_job_artifacts_when_enabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio = root / "temp" / "broken_audio.wav"
            audio.parent.mkdir()
            audio.write_text("data", encoding="utf-8")
            job = VideoJob(
                job_id="job-1",
                video_path=root / "input" / "broken.mp4",
                status=JobStatus.FAILED,
                audio_path=audio,
            )
            manager = CleanupManager(config=Config(cleanup_temp_on_failure=True))

            removed = manager.cleanup_job_temp_files(job)

            self.assertEqual(removed, [audio])
            self.assertFalse(audio.exists())

    def test_cleanup_all_temp_files_deletes_temp_directory_contents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            temp_folder = root / "temp"
            nested = temp_folder / "nested"
            audio = nested / "audio.wav"
            audio.parent.mkdir(parents=True)
            audio.write_text("data", encoding="utf-8")
            manager = CleanupManager(config=Config(temp_folder=temp_folder))

            manager.cleanup_all_temp_files()

            self.assertFalse(temp_folder.exists())

    def test_cleanup_missing_files_is_noop(self):
        job = VideoJob(
            job_id="job-1",
            video_path=Path("input/drama.mp4"),
            status=JobStatus.COMPLETED,
            audio_path=Path("temp/missing.wav"),
        )
        manager = CleanupManager(config=Config(cleanup_temp_on_success=True))

        removed = manager.cleanup_job_temp_files(job)

        self.assertEqual(removed, [])


if __name__ == "__main__":
    unittest.main()
