from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

import yaml

from models import Config, FFmpegAudioConfig, FFmpegSubtitleConfig


class ConfigError(ValueError):
    pass


def load_config(config_path: str | Path | None = Path("config.yaml")) -> Config:
    if config_path is None:
        return Config()

    path = Path(config_path)
    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    try:
        raw_config = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ConfigError(f"Invalid YAML in configuration file: {path}") from error
    except OSError as error:
        raise ConfigError(f"Unable to read configuration file: {path}") from error

    if raw_config is None:
        raw_config = {}

    if not isinstance(raw_config, Mapping):
        raise ConfigError("Configuration file must contain a YAML mapping")

    return _build_config(raw_config)


def _build_config(raw_config: Mapping[str, Any]) -> Config:
    paths = _mapping(raw_config, "paths")
    processing = _mapping(raw_config, "processing")
    transcription = _mapping(raw_config, "transcription")
    translation = _mapping(raw_config, "translation")
    ffmpeg = _mapping(raw_config, "ffmpeg")
    ffmpeg_audio = _mapping(ffmpeg, "audio")
    ffmpeg_subtitles = _mapping(ffmpeg, "subtitles")

    translation_api_key_env = str(
        translation.get("api_key_env", Config.translation_api_key_env)
    )

    try:
        return Config(
            input_folder=Path(paths.get("input_folder", Config.input_folder)),
            output_folder=Path(paths.get("output_folder", Config.output_folder)),
            temp_folder=Path(paths.get("temp_folder", Config.temp_folder)),
            transcription_provider=str(
                transcription.get("provider", Config.transcription_provider)
            ),
            transcription_model_size=str(
                transcription.get("model_size", Config.transcription_model_size)
            ),
            transcription_device=str(
                transcription.get("device", Config.transcription_device)
            ),
            transcription_compute_type=str(
                transcription.get("compute_type", Config.transcription_compute_type)
            ),
            transcription_vad_filter=bool(
                transcription.get("vad_filter", Config.transcription_vad_filter)
            ),
            transcription_no_speech_threshold=float(
                transcription.get(
                    "no_speech_threshold",
                    Config.transcription_no_speech_threshold,
                )
            ),
            transcription_condition_on_previous_text=bool(
                transcription.get(
                    "condition_on_previous_text",
                    Config.transcription_condition_on_previous_text,
                )
            ),
            transcription_cpu_threads=int(
                transcription.get("cpu_threads", Config.transcription_cpu_threads)
            ),
            transcription_beam_size=int(
                transcription.get("beam_size", Config.transcription_beam_size)
            ),
            transcription_compression_ratio_threshold=float(
                transcription.get(
                    "compression_ratio_threshold",
                    Config.transcription_compression_ratio_threshold,
                )
            ),
            transcription_skip_intro_seconds=float(
                transcription.get(
                    "skip_intro_seconds",
                    Config.transcription_skip_intro_seconds,
                )
            ),
            transcription_min_word_probability=float(
                transcription.get(
                    "min_word_probability",
                    Config.transcription_min_word_probability,
                )
            ),
            translation_provider=str(
                translation.get("provider", Config.translation_provider)
            ),
            translation_max_retries=int(
                translation.get("max_retries", Config.translation_max_retries)
            ),
            translation_retry_backoff_seconds=float(
                translation.get(
                    "retry_backoff_seconds",
                    Config.translation_retry_backoff_seconds,
                )
            ),
            translation_api_key_env=translation_api_key_env,
            translation_api_key=os.environ.get(translation_api_key_env),
            source_language=str(
                transcription.get("source_language", Config.source_language)
            ),
            translation_source_language=str(
                translation.get(
                    "source_language",
                    Config.translation_source_language,
                )
            ),
            target_language=str(translation.get("target_language", Config.target_language)),
            concurrency_level=int(
                processing.get("concurrency_level", Config.concurrency_level)
            ),
            cleanup_temp_on_success=bool(
                processing.get(
                    "cleanup_temp_on_success",
                    Config.cleanup_temp_on_success,
                )
            ),
            cleanup_temp_on_failure=bool(
                processing.get(
                    "cleanup_temp_on_failure",
                    Config.cleanup_temp_on_failure,
                )
            ),
            ffmpeg_audio=FFmpegAudioConfig(
                format=str(ffmpeg_audio.get("format", FFmpegAudioConfig.format)),
                codec=str(ffmpeg_audio.get("codec", FFmpegAudioConfig.codec)),
                sample_rate=int(
                    ffmpeg_audio.get("sample_rate", FFmpegAudioConfig.sample_rate)
                ),
                channels=int(ffmpeg_audio.get("channels", FFmpegAudioConfig.channels)),
            ),
            ffmpeg_subtitles=FFmpegSubtitleConfig(
                output_suffix=str(
                    ffmpeg_subtitles.get(
                        "output_suffix",
                        FFmpegSubtitleConfig.output_suffix,
                    )
                ),
                font=str(ffmpeg_subtitles.get("font", FFmpegSubtitleConfig.font)),
                font_size=int(
                    ffmpeg_subtitles.get("font_size", FFmpegSubtitleConfig.font_size)
                ),
                alignment=str(
                    ffmpeg_subtitles.get("alignment", FFmpegSubtitleConfig.alignment)
                ),
                margin_v=int(ffmpeg_subtitles.get("margin_v", FFmpegSubtitleConfig.margin_v)),
                video_codec=str(
                    ffmpeg_subtitles.get("video_codec", FFmpegSubtitleConfig.video_codec)
                ),
                audio_codec=str(
                    ffmpeg_subtitles.get("audio_codec", FFmpegSubtitleConfig.audio_codec)
                ),
                subtitle_time_offset_seconds=float(
                    ffmpeg_subtitles.get(
                        "subtitle_time_offset_seconds",
                        FFmpegSubtitleConfig.subtitle_time_offset_seconds,
                    )
                ),
                max_display_seconds=float(
                    ffmpeg_subtitles.get(
                        "max_display_seconds",
                        FFmpegSubtitleConfig.max_display_seconds,
                    )
                ),
                cover_source_subtitles=bool(
                    ffmpeg_subtitles.get(
                        "cover_source_subtitles",
                        FFmpegSubtitleConfig.cover_source_subtitles,
                    )
                ),
                cover_source_subtitles_mode=str(
                    ffmpeg_subtitles.get(
                        "cover_source_subtitles_mode",
                        FFmpegSubtitleConfig.cover_source_subtitles_mode,
                    )
                ),
                cover_band_height_ratio=float(
                    ffmpeg_subtitles.get(
                        "cover_band_height_ratio",
                        FFmpegSubtitleConfig.cover_band_height_ratio,
                    )
                ),
                cover_band_opacity=float(
                    ffmpeg_subtitles.get(
                        "cover_band_opacity",
                        FFmpegSubtitleConfig.cover_band_opacity,
                    )
                ),
                cover_blur_radius=int(
                    ffmpeg_subtitles.get(
                        "cover_blur_radius",
                        FFmpegSubtitleConfig.cover_blur_radius,
                    )
                ),
            ),
        )
    except (TypeError, ValueError) as error:
        raise ConfigError(f"Invalid configuration value: {error}") from error


def _mapping(parent: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = parent.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigError(f"Configuration section '{key}' must be a mapping")
    return value


__all__ = ["ConfigError", "load_config"]
