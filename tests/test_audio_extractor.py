import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from audio_extractor import AudioExtractor, ExtractionError
from models import Config, FFmpegAudioConfig, JobStatus, VideoJob


class AudioExtractorTests(unittest.TestCase):
    def test_extract_creates_audio_file_and_returns_updated_job(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video_path = root / "drama.mp4"
            temp_folder = root / "temp"
            video_path.write_bytes(b"video")
            config = Config(
                temp_folder=temp_folder,
                ffmpeg_audio=FFmpegAudioConfig(
                    format="wav",
                    codec="pcm_s16le",
                    sample_rate=16000,
                    channels=1,
                ),
            )
            job = VideoJob(job_id="job-1", video_path=video_path)

            def fake_ffmpeg(command, **kwargs):
                Path(command[-1]).write_bytes(b"RIFFfake-audio")
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            extractor = AudioExtractor(config=config)
            with patch("audio_extractor.subprocess.run", side_effect=fake_ffmpeg) as run:
                updated = extractor.extract(job)

            self.assertIsNot(updated, job)
            self.assertEqual(job.status, JobStatus.PENDING)
            self.assertIsNone(job.audio_path)
            self.assertEqual(updated.status, JobStatus.AUDIO_EXTRACTED)
            self.assertEqual(updated.audio_path, temp_folder / "drama_audio.wav")
            self.assertTrue(updated.audio_path.exists())
            self.assertGreater(updated.audio_path.stat().st_size, 0)

            command = run.call_args.args[0]
            self.assertEqual(command[0], "ffmpeg")
            self.assertIn("-i", command)
            self.assertIn(str(video_path), command)
            self.assertIn("-vn", command)
            self.assertIn("-acodec", command)
            self.assertIn("pcm_s16le", command)
            self.assertIn("-ar", command)
            self.assertIn("16000", command)
            self.assertIn("-ac", command)
            self.assertIn("1", command)
            self.assertEqual(command[-1], str(temp_folder / "drama_audio.wav"))

    def test_extract_uses_configured_output_extension(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video_path = root / "episode.mp4"
            temp_folder = root / "temp"
            video_path.write_bytes(b"video")
            config = Config(
                temp_folder=temp_folder,
                ffmpeg_audio=FFmpegAudioConfig(format="mp3", codec="libmp3lame"),
            )
            job = VideoJob(job_id="job-1", video_path=video_path)

            def fake_ffmpeg(command, **kwargs):
                Path(command[-1]).write_bytes(b"audio")
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            extractor = AudioExtractor(config=config)
            with patch("audio_extractor.subprocess.run", side_effect=fake_ffmpeg):
                updated = extractor.extract(job)

        self.assertEqual(updated.audio_path, temp_folder / "episode_audio.mp3")

    def test_extract_raises_extraction_error_on_ffmpeg_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video_path = root / "broken.mp4"
            video_path.write_bytes(b"video")
            job = VideoJob(job_id="job-1", video_path=video_path)
            extractor = AudioExtractor(config=Config(temp_folder=root / "temp"))

            with patch(
                "audio_extractor.subprocess.run",
                side_effect=subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["ffmpeg"],
                    stderr="audio extraction failed",
                ),
            ):
                with self.assertRaises(ExtractionError) as error:
                    extractor.extract(job)

        self.assertIn("audio extraction failed", str(error.exception))
        self.assertEqual(job.status, JobStatus.PENDING)

    def test_extract_raises_extraction_error_when_output_is_missing_or_empty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video_path = root / "empty.mp4"
            video_path.write_bytes(b"video")
            job = VideoJob(job_id="job-1", video_path=video_path)
            extractor = AudioExtractor(config=Config(temp_folder=root / "temp"))

            with patch(
                "audio_extractor.subprocess.run",
                return_value=subprocess.CompletedProcess(["ffmpeg"], 0, stdout="", stderr=""),
            ):
                with self.assertRaises(ExtractionError) as error:
                    extractor.extract(job)

        self.assertIn("not created or is empty", str(error.exception))


if __name__ == "__main__":
    unittest.main()
