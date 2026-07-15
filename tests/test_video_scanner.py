import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from models import JobStatus, VideoJob
from video_scanner import VideoScanner


def ffprobe_result(streams):
    return subprocess.CompletedProcess(
        args=["ffprobe"],
        returncode=0,
        stdout=json.dumps({"streams": streams}),
        stderr="",
    )


class VideoScannerTests(unittest.TestCase):
    def test_scan_discovers_valid_mp4_files_recursively(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_folder = Path(temp_dir)
            nested = input_folder / "nested"
            nested.mkdir()
            first = input_folder / "episode1.mp4"
            second = nested / "episode2.mp4"
            ignored = input_folder / "notes.txt"
            first.write_bytes(b"video")
            second.write_bytes(b"video")
            ignored.write_text("ignore me", encoding="utf-8")

            logger = Mock()
            scanner = VideoScanner(logger=logger)
            with patch(
                "video_scanner.subprocess.run",
                return_value=ffprobe_result([{"codec_type": "audio"}]),
            ) as run:
                jobs = scanner.scan(input_folder)

        self.assertEqual([job.video_path for job in jobs], [first, second])
        self.assertTrue(all(isinstance(job, VideoJob) for job in jobs))
        self.assertTrue(all(job.status == JobStatus.PENDING for job in jobs))
        self.assertEqual([job.video_name for job in jobs], ["episode1", "nested/episode2"])
        self.assertTrue(all(job.job_id for job in jobs))
        self.assertEqual(run.call_count, 2)
        logger.warning.assert_not_called()

    def test_scan_gives_unique_video_names_for_same_filename_across_series(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_folder = Path(temp_dir)
            series_a = input_folder / "DramaA"
            series_b = input_folder / "DramaB"
            series_a.mkdir()
            series_b.mkdir()
            (series_a / "episode1.mp4").write_bytes(b"video")
            (series_b / "episode1.mp4").write_bytes(b"video")

            scanner = VideoScanner(logger=Mock())
            with patch(
                "video_scanner.subprocess.run",
                return_value=ffprobe_result([{"codec_type": "audio"}]),
            ):
                jobs = scanner.scan(input_folder)

        video_names = [job.video_name for job in jobs]
        self.assertEqual(len(video_names), len(set(video_names)))
        self.assertEqual(sorted(video_names), ["DramaA/episode1", "DramaB/episode1"])

    def test_scan_skips_unreadable_or_corrupt_video(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_folder = Path(temp_dir)
            corrupt = input_folder / "corrupt.mp4"
            corrupt.write_bytes(b"not a real video")

            logger = Mock()
            scanner = VideoScanner(logger=logger)
            with patch(
                "video_scanner.subprocess.run",
                side_effect=subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["ffprobe"],
                    stderr="invalid data",
                ),
            ):
                jobs = scanner.scan(input_folder)

        self.assertEqual(jobs, [])
        self.assertEqual(
            scanner.skipped_files,
            [{"video_path": str(corrupt), "reason": "invalid data"}],
        )
        logger.warning.assert_called_once()
        self.assertIn("Skipping invalid video", logger.warning.call_args.args[0])
        self.assertEqual(logger.warning.call_args.args[2], "invalid data")

    def test_scan_skips_video_without_audio_stream(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_folder = Path(temp_dir)
            no_audio = input_folder / "silent.mp4"
            no_audio.write_bytes(b"video")

            logger = Mock()
            scanner = VideoScanner(logger=logger)
            with patch(
                "video_scanner.subprocess.run",
                return_value=ffprobe_result([{"codec_type": "video"}]),
            ):
                jobs = scanner.scan(input_folder)

        self.assertEqual(jobs, [])
        self.assertEqual(
            scanner.skipped_files,
            [
                {
                    "video_path": str(no_audio),
                    "reason": "video does not contain an audio stream",
                }
            ],
        )
        logger.warning.assert_called_once()
        self.assertEqual(
            logger.warning.call_args.args[2],
            "video does not contain an audio stream",
        )

    def test_scan_empty_folder_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = Mock()
            scanner = VideoScanner(logger=logger)
            jobs = scanner.scan(Path(temp_dir))

        self.assertEqual(jobs, [])
        logger.info.assert_called_once()

    def test_scan_rejects_missing_input_folder(self):
        scanner = VideoScanner(logger=Mock())

        with self.assertRaises(FileNotFoundError):
            scanner.scan(Path("missing-input-folder"))


if __name__ == "__main__":
    unittest.main()
