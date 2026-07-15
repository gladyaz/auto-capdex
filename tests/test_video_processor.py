import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from models import Config, FFmpegSubtitleConfig, JobStatus, VideoJob
from video_processor import VideoProcessingError, VideoProcessor


class VideoProcessorTests(unittest.TestCase):
    def test_burn_subtitles_blurs_source_subtitles_and_burns_new_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_video = root / "input" / "drama.mp4"
            srt_path = root / "output" / "drama.srt"
            output_folder = root / "output"
            input_video.parent.mkdir()
            srt_path.parent.mkdir()
            input_video.write_bytes(b"video")
            srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nHalo\n\n", encoding="utf-8")
            job = VideoJob(
                job_id="job-1",
                video_path=input_video,
                srt_path=srt_path,
                status=JobStatus.SRT_GENERATED,
            )
            config = Config(
                output_folder=output_folder,
                ffmpeg_subtitles=FFmpegSubtitleConfig(
                    output_suffix="_id",
                    font="Arial",
                    font_size=18,
                    alignment="bottom_center",
                    video_codec="libx264",
                    audio_codec="copy",
                    cover_source_subtitles=True,
                    cover_source_subtitles_mode="blur",
                    cover_band_height_ratio=0.30,
                    cover_blur_radius=18,
                ),
            )

            def fake_run(command, **kwargs):
                if command[0] == "ffmpeg":
                    Path(command[-1]).write_bytes(b"mp4")
                    return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
                if command[0] == "ffprobe":
                    return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
                raise AssertionError(f"Unexpected command: {command}")

            processor = VideoProcessor(config=config)
            with patch("video_processor.subprocess.run", side_effect=fake_run) as run:
                updated = processor.burn_subtitles(job)

            self.assertIsNot(updated, job)
            self.assertEqual(job.status, JobStatus.SRT_GENERATED)
            self.assertIsNone(job.output_video_path)
            self.assertEqual(updated.status, JobStatus.COMPLETED)
            self.assertEqual(updated.output_video_path, output_folder / "drama_id.mp4")
            self.assertTrue(updated.output_video_path.exists())

            ffmpeg_command = run.call_args_list[0].args[0]
            ffprobe_command = run.call_args_list[1].args[0]

        self.assertEqual(ffmpeg_command[0], "ffmpeg")
        self.assertIn("-i", ffmpeg_command)
        self.assertIn(str(input_video), ffmpeg_command)
        self.assertIn("-filter_complex", ffmpeg_command)
        filter_complex = ffmpeg_command[ffmpeg_command.index("-filter_complex") + 1]
        self.assertIn("crop=iw:ih*0.3:0:ih*(1-0.3)", filter_complex)
        self.assertIn("boxblur=luma_radius=18:luma_power=1", filter_complex)
        self.assertIn("subtitles=", filter_complex)
        self.assertIn("FontName=Arial", filter_complex)
        self.assertIn("FontSize=18", filter_complex)
        self.assertIn("[v]", ffmpeg_command)
        self.assertIn("0:a?", ffmpeg_command)
        self.assertIn("-c:v", ffmpeg_command)
        self.assertIn("libx264", ffmpeg_command)
        self.assertIn("-c:a", ffmpeg_command)
        self.assertIn("copy", ffmpeg_command)
        self.assertEqual(ffmpeg_command[-1], str(output_folder / "drama_id.mp4"))
        self.assertEqual(ffprobe_command[0], "ffprobe")
        self.assertEqual(ffprobe_command[-1], str(output_folder / "drama_id.mp4"))

    def test_burn_subtitles_can_cover_hardcoded_source_subtitles_before_burning_new_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_video = root / "input" / "drama.mp4"
            srt_path = root / "output" / "drama.srt"
            output_folder = root / "output"
            input_video.parent.mkdir()
            srt_path.parent.mkdir()
            input_video.write_bytes(b"video")
            srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nHalo\n\n", encoding="utf-8")
            job = VideoJob(
                job_id="job-1",
                video_path=input_video,
                srt_path=srt_path,
                status=JobStatus.SRT_GENERATED,
            )
            config = Config(
                output_folder=output_folder,
                ffmpeg_subtitles=FFmpegSubtitleConfig(
                    cover_source_subtitles=True,
                    cover_source_subtitles_mode="cover",
                    cover_band_height_ratio=0.24,
                    cover_band_opacity=0.8,
                ),
            )

            def fake_run(command, **kwargs):
                if command[0] == "ffmpeg":
                    Path(command[-1]).write_bytes(b"mp4")
                    return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
                if command[0] == "ffprobe":
                    return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
                raise AssertionError(f"Unexpected command: {command}")

            processor = VideoProcessor(config=config)
            with patch("video_processor.subprocess.run", side_effect=fake_run) as run:
                updated = processor.burn_subtitles(job)

            ffmpeg_command = run.call_args_list[0].args[0]
            vf_filter = ffmpeg_command[ffmpeg_command.index("-vf") + 1]

        self.assertEqual(updated.status, JobStatus.COMPLETED)
        self.assertIn("drawbox=", vf_filter)
        self.assertIn("color=black@0.8", vf_filter)
        self.assertIn("subtitles=", vf_filter)

    def test_burn_subtitles_raises_on_ffmpeg_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_video = root / "input" / "broken.mp4"
            srt_path = root / "output" / "broken.srt"
            input_video.parent.mkdir()
            srt_path.parent.mkdir()
            input_video.write_bytes(b"video")
            srt_path.write_text("", encoding="utf-8")
            job = VideoJob(
                job_id="job-1",
                video_path=input_video,
                srt_path=srt_path,
                status=JobStatus.SRT_GENERATED,
            )
            processor = VideoProcessor(config=Config(output_folder=root / "output"))

            with patch(
                "video_processor.subprocess.run",
                side_effect=subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["ffmpeg"],
                    stderr="subtitle burn failed",
                ),
            ):
                with self.assertRaises(VideoProcessingError) as error:
                    processor.burn_subtitles(job)

        self.assertIn("subtitle burn failed", str(error.exception))
        self.assertEqual(job.status, JobStatus.SRT_GENERATED)
        self.assertIsNone(job.output_video_path)

    def test_burn_subtitles_with_empty_srt_copies_video_without_subtitle_filter(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_video = root / "input" / "silent.mp4"
            srt_path = root / "output" / "silent.srt"
            output_folder = root / "output"
            input_video.parent.mkdir()
            srt_path.parent.mkdir()
            input_video.write_bytes(b"video")
            srt_path.write_text("", encoding="utf-8")
            job = VideoJob(
                job_id="job-1",
                video_path=input_video,
                srt_path=srt_path,
                status=JobStatus.SRT_GENERATED,
            )

            def fake_run(command, **kwargs):
                if command[0] == "ffmpeg":
                    Path(command[-1]).write_bytes(b"mp4")
                    return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
                if command[0] == "ffprobe":
                    return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
                raise AssertionError(f"Unexpected command: {command}")

            processor = VideoProcessor(config=Config(output_folder=output_folder))
            with patch("video_processor.subprocess.run", side_effect=fake_run) as run:
                updated = processor.burn_subtitles(job)

            command = run.call_args_list[0].args[0]

        self.assertEqual(updated.status, JobStatus.COMPLETED)
        self.assertNotIn("-vf", command)
        self.assertIn("-c:v", command)
        self.assertIn("copy", command)
        self.assertEqual(command[-1], str(output_folder / "silent_subtitled.mp4"))

    def test_burn_subtitles_raises_when_output_missing_or_empty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_video = root / "input" / "empty.mp4"
            srt_path = root / "output" / "empty.srt"
            input_video.parent.mkdir()
            srt_path.parent.mkdir()
            input_video.write_bytes(b"video")
            srt_path.write_text("", encoding="utf-8")
            job = VideoJob(
                job_id="job-1",
                video_path=input_video,
                srt_path=srt_path,
                status=JobStatus.SRT_GENERATED,
            )
            processor = VideoProcessor(config=Config(output_folder=root / "output"))

            with patch(
                "video_processor.subprocess.run",
                return_value=subprocess.CompletedProcess(["ffmpeg"], 0, stdout="", stderr=""),
            ):
                with self.assertRaises(VideoProcessingError) as error:
                    processor.burn_subtitles(job)

        self.assertIn("not created or is empty", str(error.exception))

    def test_burn_subtitles_requires_srt_path(self):
        processor = VideoProcessor(config=Config())
        job = VideoJob(job_id="job-1", video_path=Path("input/drama.mp4"))

        with self.assertRaises(VideoProcessingError) as error:
            processor.burn_subtitles(job)

        self.assertIn("srt_path is required", str(error.exception))


if __name__ == "__main__":
    unittest.main()
