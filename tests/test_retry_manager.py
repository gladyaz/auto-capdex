import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from models import JobStatus, VideoJob
from retry_manager import RetryManager


class RetryManagerTests(unittest.TestCase):
    def test_job_state_round_trips_through_json(self):
        created_at = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
        updated_at = datetime(2026, 1, 1, 9, 5, tzinfo=timezone.utc)
        jobs = [
            VideoJob(
                job_id="job-1",
                video_path=Path("input/drama.mp4"),
                video_name="custom-name",
                status=JobStatus.TRANSLATED,
                created_at=created_at,
                updated_at=updated_at,
                error_message=None,
                audio_path=Path("temp/drama_audio.wav"),
                transcript_path=Path("temp/drama_transcript.json"),
                translation_path=Path("temp/drama_translation.json"),
                srt_path=None,
                output_video_path=None,
            )
        ]
        manager = RetryManager()

        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "job_state.json"
            manager.save_job_state(state_file, jobs)
            loaded = manager.load_job_state(state_file)
            payload = json.loads(state_file.read_text(encoding="utf-8"))

        self.assertEqual(loaded, jobs)
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["jobs"][0]["status"], "translated")
        self.assertEqual(payload["jobs"][0]["audio_path"], "temp/drama_audio.wav")

    def test_filter_resumable_excludes_completed_jobs(self):
        completed = VideoJob(
            job_id="job-1",
            video_path=Path("input/done.mp4"),
            status=JobStatus.COMPLETED,
        )
        failed = VideoJob(job_id="job-2", video_path=Path("input/failed.mp4")).with_failure(
            "translation failed"
        )
        pending = VideoJob(job_id="job-3", video_path=Path("input/pending.mp4"))
        transcribed = VideoJob(
            job_id="job-4",
            video_path=Path("input/transcribed.mp4"),
            status=JobStatus.TRANSCRIBED,
        )

        resumable = RetryManager().filter_resumable([completed, failed, pending, transcribed])

        self.assertEqual(resumable, [failed, pending, transcribed])

    def test_load_job_state_returns_empty_list_when_file_missing(self):
        jobs = RetryManager().load_job_state(Path("missing-job-state.json"))

        self.assertEqual(jobs, [])

    def test_load_job_state_rejects_invalid_state_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "job_state.json"
            state_file.write_text('{"jobs": "not-a-list"}', encoding="utf-8")

            with self.assertRaises(ValueError):
                RetryManager().load_job_state(state_file)


if __name__ == "__main__":
    unittest.main()
