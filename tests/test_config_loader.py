import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config_loader import ConfigError, load_config
from models import Config


class ConfigLoaderTests(unittest.TestCase):
    def test_load_config_reads_nested_yaml(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(
                """
paths:
  input_folder: videos/in
  output_folder: videos/out
  temp_folder: work/tmp
processing:
  concurrency_level: 2
  cleanup_temp_on_success: false
  cleanup_temp_on_failure: true
transcription:
  provider: faster-whisper
  model_size: small
  source_language: zh
  device: cpu
  compute_type: int8
  vad_filter: true
  no_speech_threshold: 0.75
  condition_on_previous_text: false
  cpu_threads: 4
  beam_size: 3
  compression_ratio_threshold: 2.2
  skip_intro_seconds: 35.0
  min_word_probability: 0.6
translation:
  provider: googletrans
  source_language: zh-cn
  target_language: id
  api_key_env: TEST_TRANSLATE_KEY
  max_retries: 5
  retry_backoff_seconds: 1.5
ffmpeg:
  audio:
    format: wav
    codec: pcm_s16le
    sample_rate: 22050
    channels: 2
  subtitles:
    output_suffix: _id
    font: Noto Sans
    font_size: 28
    alignment: bottom_center
    margin_v: 8
    video_codec: libx264
    audio_codec: aac
    subtitle_time_offset_seconds: 1.0
    max_display_seconds: 6.0
    cover_source_subtitles: false
    cover_source_subtitles_mode: blur
    cover_band_height_ratio: 0.24
    cover_band_opacity: 0.8
    cover_blur_radius: 20
""",
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertIsInstance(config, Config)
        self.assertEqual(config.input_folder, Path("videos/in"))
        self.assertEqual(config.output_folder, Path("videos/out"))
        self.assertEqual(config.temp_folder, Path("work/tmp"))
        self.assertEqual(config.concurrency_level, 2)
        self.assertFalse(config.cleanup_temp_on_success)
        self.assertTrue(config.cleanup_temp_on_failure)
        self.assertEqual(config.transcription_provider, "faster-whisper")
        self.assertEqual(config.transcription_model_size, "small")
        self.assertEqual(config.transcription_device, "cpu")
        self.assertEqual(config.transcription_compute_type, "int8")
        self.assertTrue(config.transcription_vad_filter)
        self.assertEqual(config.transcription_no_speech_threshold, 0.75)
        self.assertFalse(config.transcription_condition_on_previous_text)
        self.assertEqual(config.transcription_cpu_threads, 4)
        self.assertEqual(config.transcription_beam_size, 3)
        self.assertEqual(config.transcription_compression_ratio_threshold, 2.2)
        self.assertEqual(config.transcription_skip_intro_seconds, 35.0)
        self.assertEqual(config.transcription_min_word_probability, 0.6)
        self.assertEqual(config.translation_provider, "googletrans")
        self.assertEqual(config.source_language, "zh")
        self.assertEqual(config.translation_source_language, "zh-cn")
        self.assertEqual(config.target_language, "id")
        self.assertEqual(config.translation_api_key_env, "TEST_TRANSLATE_KEY")
        self.assertEqual(config.translation_max_retries, 5)
        self.assertEqual(config.translation_retry_backoff_seconds, 1.5)
        self.assertEqual(config.ffmpeg_audio.sample_rate, 22050)
        self.assertEqual(config.ffmpeg_audio.channels, 2)
        self.assertEqual(config.ffmpeg_subtitles.output_suffix, "_id")
        self.assertEqual(config.ffmpeg_subtitles.font, "Noto Sans")
        self.assertEqual(config.ffmpeg_subtitles.font_size, 28)
        self.assertEqual(config.ffmpeg_subtitles.margin_v, 8)
        self.assertEqual(config.ffmpeg_subtitles.audio_codec, "aac")
        self.assertEqual(config.ffmpeg_subtitles.subtitle_time_offset_seconds, 1.0)
        self.assertEqual(config.ffmpeg_subtitles.max_display_seconds, 6.0)
        self.assertFalse(config.ffmpeg_subtitles.cover_source_subtitles)
        self.assertEqual(config.ffmpeg_subtitles.cover_source_subtitles_mode, "blur")
        self.assertEqual(config.ffmpeg_subtitles.cover_band_height_ratio, 0.24)
        self.assertEqual(config.ffmpeg_subtitles.cover_band_opacity, 0.8)
        self.assertEqual(config.ffmpeg_subtitles.cover_blur_radius, 20)

    def test_load_config_reads_translation_api_key_from_configured_env_var(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(
                """
translation:
  api_key_env: TEST_TRANSLATE_KEY
""",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"TEST_TRANSLATE_KEY": "secret-value"}, clear=False):
                config = load_config(config_path)

        self.assertEqual(config.translation_api_key_env, "TEST_TRANSLATE_KEY")
        self.assertEqual(config.translation_api_key, "secret-value")

    def test_load_config_with_none_returns_defaults(self):
        config = load_config(None)

        self.assertEqual(config, Config())

    def test_load_config_rejects_missing_file(self):
        with self.assertRaises(ConfigError):
            load_config(Path("does-not-exist.yaml"))

    def test_load_config_rejects_invalid_yaml_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")

            with self.assertRaises(ConfigError):
                load_config(config_path)

    def test_load_config_rejects_invalid_config_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(
                """
processing:
  concurrency_level: 0
""",
                encoding="utf-8",
            )

            with self.assertRaises(ConfigError):
                load_config(config_path)

    def test_load_config_rejects_invalid_beam_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(
                """
transcription:
  beam_size: 0
""",
                encoding="utf-8",
            )

            with self.assertRaises(ConfigError):
                load_config(config_path)


if __name__ == "__main__":
    unittest.main()
