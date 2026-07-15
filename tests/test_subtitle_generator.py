import tempfile
import unittest
from pathlib import Path

from models import Config, FFmpegSubtitleConfig, JobStatus, TextSegment, Translation, VideoJob
from subtitle_generator import SubtitleError, SubtitleGenerator, format_srt_timestamp


class SubtitleTimestampTests(unittest.TestCase):
    def test_format_srt_timestamp_uses_hours_minutes_seconds_milliseconds(self):
        self.assertEqual(format_srt_timestamp(0), "00:00:00,000")
        self.assertEqual(format_srt_timestamp(1.234), "00:00:01,234")
        self.assertEqual(format_srt_timestamp(61.2), "00:01:01,200")
        self.assertEqual(format_srt_timestamp(3723.9876), "01:02:03,988")


class SubtitleGeneratorTests(unittest.TestCase):
    def test_generate_writes_correctly_formatted_srt_and_updates_job(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_folder = root / "output"
            translation_path = root / "temp" / "drama_translation.json"
            translation_path.parent.mkdir()
            translation_path.write_text("{}", encoding="utf-8")
            job = VideoJob(
                job_id="job-1",
                video_path=root / "input" / "drama.mp4",
                translation_path=translation_path,
                status=JobStatus.TRANSLATED,
            )
            translation = Translation(
                segments=[
                    TextSegment(start_time=1.0, end_time=3.5, text="Halo, selamat datang."),
                    TextSegment(start_time=61.234, end_time=3723.9876, text="Ini baris kedua."),
                ],
                source_language="zh-cn",
                target_language="id",
                source_transcript=root / "temp" / "drama_transcript.json",
            )
            generator = SubtitleGenerator(
                config=Config(
                    output_folder=output_folder,
                    ffmpeg_subtitles=FFmpegSubtitleConfig(subtitle_time_offset_seconds=1.0),
                )
            )

            updated = generator.generate(job, translation)

            self.assertIsNot(updated, job)
            self.assertEqual(job.status, JobStatus.TRANSLATED)
            self.assertIsNone(job.srt_path)
            self.assertEqual(updated.status, JobStatus.SRT_GENERATED)
            self.assertEqual(updated.srt_path, output_folder / "drama.srt")

            content = updated.srt_path.read_text(encoding="utf-8")

        self.assertEqual(
            content,
            "1\n"
            "00:00:00,000 --> 00:00:02,500\n"
            "Halo, selamat datang.\n\n"
            "2\n"
            "00:01:00,234 --> 00:01:07,234\n"
            "Ini baris kedua.\n\n",
        )

    def test_generate_caps_duration_of_abnormally_long_whisper_segment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_folder = root / "output"
            translation_path = root / "temp" / "drama_translation.json"
            translation_path.parent.mkdir()
            translation_path.write_text("{}", encoding="utf-8")
            job = VideoJob(
                job_id="job-1",
                video_path=root / "input" / "drama.mp4",
                translation_path=translation_path,
                status=JobStatus.TRANSLATED,
            )
            translation = Translation(
                segments=[
                    TextSegment(start_time=8.57, end_time=29.19, text="Halo"),
                    TextSegment(start_time=29.19, end_time=30.83, text="Xiao Cheng adalah penyelamat ibu"),
                ],
                source_language="zh-cn",
                target_language="id",
                source_transcript=root / "temp" / "drama_transcript.json",
            )
            generator = SubtitleGenerator(
                config=Config(
                    output_folder=output_folder,
                    ffmpeg_subtitles=FFmpegSubtitleConfig(
                        subtitle_time_offset_seconds=0.0,
                        max_display_seconds=7.0,
                    ),
                )
            )

            updated = generator.generate(job, translation)

            content = updated.srt_path.read_text(encoding="utf-8")

        self.assertEqual(
            content,
            "1\n"
            "00:00:08,570 --> 00:00:15,570\n"
            "Halo\n\n"
            "2\n"
            "00:00:29,190 --> 00:00:30,830\n"
            "Xiao Cheng adalah penyelamat ibu\n\n",
        )

    def test_generate_empty_translation_writes_empty_srt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_folder = root / "output"
            translation_path = root / "temp" / "drama_translation.json"
            translation_path.parent.mkdir()
            translation_path.write_text("{}", encoding="utf-8")
            job = VideoJob(
                job_id="job-1",
                video_path=root / "input" / "drama.mp4",
                translation_path=translation_path,
                status=JobStatus.TRANSLATED,
            )
            translation = Translation(
                segments=[],
                source_language="zh-cn",
                target_language="id",
                source_transcript=root / "temp" / "drama_transcript.json",
            )
            generator = SubtitleGenerator(config=Config(output_folder=output_folder))

            updated = generator.generate(job, translation)

            content = updated.srt_path.read_text(encoding="utf-8")

        self.assertEqual(content, "")
        self.assertEqual(updated.status, JobStatus.SRT_GENERATED)

    def test_generate_requires_translation_path(self):
        job = VideoJob(job_id="job-1", video_path=Path("input/drama.mp4"))
        translation = Translation(
            segments=[],
            source_language="zh-cn",
            target_language="id",
            source_transcript=Path("temp/drama_transcript.json"),
        )
        generator = SubtitleGenerator(config=Config())

        with self.assertRaises(SubtitleError) as error:
            generator.generate(job, translation)

        self.assertIn("translation_path is required", str(error.exception))


if __name__ == "__main__":
    unittest.main()
