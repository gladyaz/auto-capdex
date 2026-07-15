import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from job_logger import JobLogger
from models import JobStatus, VideoJob


class FixedClock:
    def __init__(self, *values):
        self.values = list(values)

    def __call__(self):
        if not self.values:
            raise AssertionError("Clock exhausted")
        return self.values.pop(0)


class JobLoggerTests(unittest.TestCase):
    def test_processing_log_entries_are_timestamped(self):
        start_time = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        complete_time = datetime(2026, 1, 1, 10, 1, tzinfo=timezone.utc)
        logger = JobLogger(
            batch_start_time=datetime(2026, 1, 1, 9, 59, tzinfo=timezone.utc),
            clock=FixedClock(start_time, complete_time),
        )
        job = VideoJob(job_id="job-1", video_path=Path("input/drama.mp4"))
        completed = job.with_status(
            JobStatus.COMPLETED,
            output_video_path=Path("output/drama_subtitled.mp4"),
        )

        logger.log_job_start(job)
        logger.log_job_complete(completed)

        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "processing.log"
            logger.write_processing_log(log_file)
            lines = log_file.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(lines), 2)
        first = json.loads(lines[0])
        second = json.loads(lines[1])
        self.assertEqual(first["timestamp"], "2026-01-01T10:00:00+00:00")
        self.assertEqual(first["event"], "job_started")
        self.assertEqual(first["video_filename"], "drama.mp4")
        self.assertEqual(second["timestamp"], "2026-01-01T10:01:00+00:00")
        self.assertEqual(second["event"], "job_completed")
        self.assertEqual(second["output_video_path"], "output/drama_subtitled.mp4")
        self.assertEqual(second["status"], "completed")

    def test_failed_jobs_file_captures_error_and_stack_trace_is_logged(self):
        failure_time = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)
        logger = JobLogger(
            batch_start_time=datetime(2026, 1, 1, 10, 59, tzinfo=timezone.utc),
            clock=FixedClock(failure_time),
        )
        job = VideoJob(job_id="job-1", video_path=Path("input/broken.mp4"))

        try:
            raise ValueError("bad input")
        except ValueError as error:
            failed = job.with_failure(str(error))
            logger.log_job_failure(failed, error)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            failed_file = root / "failed_jobs.txt"
            log_file = root / "processing.log"
            logger.write_failed_jobs(failed_file)
            logger.write_processing_log(log_file)
            failed_content = failed_file.read_text(encoding="utf-8")
            log_entry = json.loads(log_file.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(failed_content, "broken.mp4: ValueError: bad input\n")
        self.assertEqual(log_entry["event"], "job_failed")
        self.assertEqual(log_entry["error"], "ValueError: bad input")
        self.assertIn("Traceback", log_entry["stack_trace"])
        self.assertIn("bad input", log_entry["stack_trace"])

    def test_batch_report_contains_summary_counts_and_timing(self):
        batch_start = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        batch_end = datetime(2026, 1, 1, 12, 2, tzinfo=timezone.utc)
        logger = JobLogger(
            batch_id="batch-1",
            batch_start_time=batch_start,
            clock=FixedClock(batch_end),
            input_folder=Path("input"),
            output_folder=Path("output"),
        )
        completed = VideoJob(
            job_id="job-1",
            video_path=Path("input/ok.mp4"),
        ).with_status(JobStatus.COMPLETED, output_video_path=Path("output/ok_subtitled.mp4"))
        failed = VideoJob(job_id="job-2", video_path=Path("input/bad.mp4")).with_failure(
            "ffmpeg failed"
        )
        pending = VideoJob(job_id="job-3", video_path=Path("input/pending.mp4"))

        with tempfile.TemporaryDirectory() as temp_dir:
            report_file = Path(temp_dir) / "batch_report.json"
            report = logger.generate_batch_report(report_file, [completed, failed, pending])
            payload = json.loads(report_file.read_text(encoding="utf-8"))

        self.assertEqual(report, payload)
        self.assertEqual(payload["batch_id"], "batch-1")
        self.assertEqual(payload["input_folder"], "input")
        self.assertEqual(payload["output_folder"], "output")
        self.assertEqual(payload["job_count"], 3)
        self.assertEqual(payload["success_count"], 1)
        self.assertEqual(payload["failure_count"], 1)
        self.assertEqual(payload["pending_count"], 1)
        self.assertEqual(payload["total_processing_seconds"], 120.0)
        self.assertEqual(payload["jobs"][0]["status"], "completed")
        self.assertEqual(payload["jobs"][1]["error_message"], "ffmpeg failed")

    def test_video_skip_is_written_to_failed_jobs_and_processing_log(self):
        skip_time = datetime(2026, 1, 1, 13, 0, tzinfo=timezone.utc)
        logger = JobLogger(
            batch_start_time=datetime(2026, 1, 1, 12, 59, tzinfo=timezone.utc),
            clock=FixedClock(skip_time),
        )

        logger.log_video_skip(Path("input/corrupt.mp4"), "moov atom not found")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            failed_file = root / "failed_jobs.txt"
            log_file = root / "processing.log"
            logger.write_failed_jobs(failed_file)
            logger.write_processing_log(log_file)
            failed_content = failed_file.read_text(encoding="utf-8")
            log_entry = json.loads(log_file.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(failed_content, "corrupt.mp4: Skipped: moov atom not found\n")
        self.assertEqual(log_entry["event"], "video_skipped")
        self.assertEqual(log_entry["status"], "skipped")
        self.assertEqual(log_entry["error"], "Skipped: moov atom not found")

    def test_failed_jobs_file_is_empty_when_no_failures(self):
        logger = JobLogger()

        with tempfile.TemporaryDirectory() as temp_dir:
            failed_file = Path(temp_dir) / "failed_jobs.txt"
            logger.write_failed_jobs(failed_file)
            content = failed_file.read_text(encoding="utf-8")

        self.assertEqual(content, "")


if __name__ == "__main__":
    unittest.main()
