import unittest
from datetime import datetime, timezone
from pathlib import Path

from models import (
    Config,
    FFmpegAudioConfig,
    FFmpegSubtitleConfig,
    JobStatus,
    TextSegment,
    Transcript,
    Translation,
    VideoJob,
)


class JobStatusTests(unittest.TestCase):
    def test_job_status_values_match_pipeline_contract(self):
        self.assertEqual(JobStatus.PENDING.value, "pending")
        self.assertEqual(JobStatus.AUDIO_EXTRACTED.value, "audio_extracted")
        self.assertEqual(JobStatus.TRANSCRIBED.value, "transcribed")
        self.assertEqual(JobStatus.TRANSLATED.value, "translated")
        self.assertEqual(JobStatus.SRT_GENERATED.value, "srt_generated")
        self.assertEqual(JobStatus.COMPLETED.value, "completed")
        self.assertEqual(JobStatus.FAILED.value, "failed")


class VideoJobTests(unittest.TestCase):
    def test_video_job_derives_name_and_defaults_to_pending(self):
        job = VideoJob(job_id="job-1", video_path=Path("input/drama.mp4"))

        self.assertEqual(job.video_name, "drama")
        self.assertEqual(job.status, JobStatus.PENDING)
        self.assertIsInstance(job.created_at, datetime)
        self.assertIsInstance(job.updated_at, datetime)
        self.assertIsNone(job.error_message)
        self.assertIsNone(job.audio_path)
        self.assertIsNone(job.transcript_path)
        self.assertIsNone(job.translation_path)
        self.assertIsNone(job.srt_path)
        self.assertIsNone(job.output_video_path)

    def test_video_job_status_update_returns_new_instance(self):
        job = VideoJob(job_id="job-1", video_path=Path("input/drama.mp4"))
        updated = job.with_status(JobStatus.AUDIO_EXTRACTED, audio_path=Path("temp/drama_audio.wav"))

        self.assertIsNot(updated, job)
        self.assertEqual(job.status, JobStatus.PENDING)
        self.assertIsNone(job.audio_path)
        self.assertEqual(updated.status, JobStatus.AUDIO_EXTRACTED)
        self.assertEqual(updated.audio_path, Path("temp/drama_audio.wav"))
        self.assertGreaterEqual(updated.updated_at, job.updated_at)

    def test_video_job_failure_update_keeps_original_immutable(self):
        job = VideoJob(job_id="job-1", video_path=Path("input/drama.mp4"))
        failed = job.with_failure("ffprobe failed")

        self.assertIsNot(failed, job)
        self.assertEqual(failed.status, JobStatus.FAILED)
        self.assertEqual(failed.error_message, "ffprobe failed")
        self.assertEqual(job.status, JobStatus.PENDING)
        self.assertIsNone(job.error_message)


class SegmentArtifactTests(unittest.TestCase):
    def test_text_segment_requires_valid_timing(self):
        with self.assertRaises(ValueError):
            TextSegment(start_time=2.0, end_time=1.0, text="invalid")

        with self.assertRaises(ValueError):
            TextSegment(start_time=-0.1, end_time=1.0, text="invalid")

    def test_transcript_and_translation_hold_segments_and_paths(self):
        source_segment = TextSegment(start_time=0.0, end_time=1.5, text="你好")
        translated_segment = TextSegment(start_time=0.0, end_time=1.5, text="Halo")

        transcript = Transcript(
            segments=[source_segment],
            language="zh",
            source_audio=Path("temp/drama_audio.wav"),
        )
        translation = Translation(
            segments=[translated_segment],
            source_language="zh",
            target_language="id",
            source_transcript=Path("temp/drama_transcript.json"),
        )

        self.assertEqual(transcript.segments[0].text, "你好")
        self.assertIsInstance(transcript.segments, tuple)
        self.assertEqual(transcript.language, "zh")
        self.assertEqual(translation.segments[0].text, "Halo")
        self.assertIsInstance(translation.segments, tuple)
        self.assertEqual(translation.target_language, "id")


class ConfigTests(unittest.TestCase):
    def test_config_defaults_match_poc_pipeline(self):
        config = Config()

        self.assertEqual(config.input_folder, Path("input"))
        self.assertEqual(config.output_folder, Path("output"))
        self.assertEqual(config.temp_folder, Path("temp"))
        self.assertEqual(config.transcription_provider, "faster-whisper")
        self.assertEqual(config.translation_provider, "googletrans")
        self.assertEqual(config.source_language, "zh")
        self.assertEqual(config.target_language, "id")
        self.assertEqual(config.concurrency_level, 1)
        self.assertTrue(config.transcription_vad_filter)
        self.assertEqual(config.transcription_no_speech_threshold, 0.75)
        self.assertFalse(config.transcription_condition_on_previous_text)
        self.assertEqual(config.transcription_cpu_threads, 0)
        self.assertEqual(config.transcription_beam_size, 5)
        self.assertTrue(config.cleanup_temp_on_success)
        self.assertFalse(config.cleanup_temp_on_failure)
        self.assertIsInstance(config.ffmpeg_audio, FFmpegAudioConfig)
        self.assertIsInstance(config.ffmpeg_subtitles, FFmpegSubtitleConfig)

    def test_config_rejects_invalid_concurrency(self):
        with self.assertRaises(ValueError):
            Config(concurrency_level=0)

    def test_config_rejects_negative_cpu_threads(self):
        with self.assertRaises(ValueError):
            Config(transcription_cpu_threads=-1)

    def test_config_rejects_invalid_beam_size(self):
        with self.assertRaises(ValueError):
            Config(transcription_beam_size=0)

    def test_config_rejects_invalid_compression_ratio_threshold(self):
        with self.assertRaises(ValueError):
            Config(transcription_compression_ratio_threshold=0)

    def test_config_rejects_negative_skip_intro_seconds(self):
        with self.assertRaises(ValueError):
            Config(transcription_skip_intro_seconds=-1.0)

    def test_config_rejects_invalid_min_word_probability(self):
        with self.assertRaises(ValueError):
            Config(transcription_min_word_probability=-0.1)

        with self.assertRaises(ValueError):
            Config(transcription_min_word_probability=1.1)

    def test_config_rejects_negative_translation_retry_settings(self):
        with self.assertRaises(ValueError):
            Config(translation_max_retries=-1)

        with self.assertRaises(ValueError):
            Config(translation_retry_backoff_seconds=-1.0)

    def test_ffmpeg_subtitle_config_rejects_invalid_cover_band_values(self):
        with self.assertRaises(ValueError):
            FFmpegSubtitleConfig(cover_band_height_ratio=0.0)

        with self.assertRaises(ValueError):
            FFmpegSubtitleConfig(cover_band_height_ratio=1.0)

        with self.assertRaises(ValueError):
            FFmpegSubtitleConfig(cover_band_opacity=-0.1)

        with self.assertRaises(ValueError):
            FFmpegSubtitleConfig(cover_band_opacity=1.1)

    def test_ffmpeg_subtitle_config_rejects_invalid_cover_mode_and_blur_radius(self):
        with self.assertRaises(ValueError):
            FFmpegSubtitleConfig(cover_source_subtitles_mode="invalid")

        with self.assertRaises(ValueError):
            FFmpegSubtitleConfig(cover_blur_radius=0)

    def test_ffmpeg_subtitle_config_rejects_invalid_margin_and_offset(self):
        with self.assertRaises(ValueError):
            FFmpegSubtitleConfig(margin_v=-1)

        with self.assertRaises(ValueError):
            FFmpegSubtitleConfig(subtitle_time_offset_seconds=-0.1)

    def test_ffmpeg_subtitle_config_rejects_invalid_max_display_seconds(self):
        with self.assertRaises(ValueError):
            FFmpegSubtitleConfig(max_display_seconds=0)

        with self.assertRaises(ValueError):
            FFmpegSubtitleConfig(max_display_seconds=-1.0)


if __name__ == "__main__":
    unittest.main()
