# Implementation Plan: Batch Mandarin to Indonesian Subtitle Pipeline

## Overview

This implementation plan breaks down the batch subtitle pipeline into discrete coding tasks for the POC (10 videos). The pipeline will process Mandarin videos sequentially, extracting audio, transcribing speech, translating to Indonesian, generating SRT files, and burning subtitles into output videos.

**Implementation Language:** Python

**Core Libraries:**
- FFmpeg (audio extraction, subtitle burning)
- faster-whisper (Mandarin transcription)
- googletrans or Google Cloud Translation API (translation)
- Standard library (pathlib, logging, argparse, json, dataclasses)

## Tasks

- [x] 1. Set up project structure and dependencies
  - Create project directory structure (input/, output/, temp/)
  - Create requirements.txt with dependencies (faster-whisper, googletrans, ffmpeg-python)
  - Create config.yaml with default configuration
  - Set up virtual environment and install dependencies
  - _Requirements: 9.1, 9.2, 9.5_

- [x] 2. Implement core data models
  - [x] 2.1 Create data models module (models.py)
    - Implement JobStatus enum (PENDING, AUDIO_EXTRACTED, TRANSCRIBED, TRANSLATED, SRT_GENERATED, COMPLETED, FAILED)
    - Implement VideoJob dataclass with job_id, video_path, status, timestamps, artifact paths
    - Implement TextSegment dataclass with start_time, end_time, text
    - Implement Transcript dataclass with segments, language, source_audio
    - Implement Translation dataclass with segments, source/target languages
    - Implement Config dataclass with provider settings, processing options, FFmpeg parameters
    - _Requirements: 1.4, 7.2, 9.1, 9.2_

- [x] 3. Implement configuration loader
  - [x] 3.1 Create config module (config_loader.py)
    - Implement load_config() function that reads config.yaml
    - Support environment variable overrides for sensitive values (API keys)
    - Validate required configuration fields
    - Return Config dataclass instance
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 4. Implement video scanner
  - [x] 4.1 Create video scanner module (video_scanner.py)
    - Implement VideoScanner class with scan() method
    - Use pathlib to recursively find all .mp4 files in input folder
    - Use FFprobe to validate each video (readable, has audio track)
    - Create VideoJob instance for each valid video with status PENDING
    - Log skipped files (invalid, no audio, unreadable)
    - Return list of VideoJob instances
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 4.2 Write unit tests for video scanner
  - Test valid .mp4 files are discovered
  - Test invalid files are skipped
  - Test files without audio are skipped
  - Test empty folder returns empty job list
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 5. Implement audio extractor
  - [x] 5.1 Create audio extractor module (audio_extractor.py)
    - Implement AudioExtractor class with extract() method
    - Use FFmpeg to extract audio track from video: `ffmpeg -i input.mp4 -vn -acodec pcm_s16le output.wav`
    - Save audio to temp/{video_name}_audio.wav
    - Verify extracted audio file is non-empty and readable
    - Update job status to AUDIO_EXTRACTED and set audio_path
    - Raise ExtractionError on FFmpeg failure
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 5.2 Write unit tests for audio extractor
  - Test successful extraction produces valid WAV file
  - Test FFmpeg errors are caught and raised as ExtractionError
  - Test output path follows naming convention
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 6. Implement transcription provider interface
  - [x] 6.1 Create transcription module (transcription.py)
    - Create TranscriptionProvider abstract base class with transcribe() abstract method
    - Implement FasterWhisperProvider class that uses faster-whisper library
    - Load faster-whisper model in __init__ (configurable model size: base, small, medium)
    - Implement transcribe() that returns Transcript with timestamped segments
    - Detect language as Mandarin/Chinese (configurable or auto-detect)
    - Save transcript JSON to temp/{video_name}_transcript.json
    - Raise TranscriptionError on failure
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.6, 9.3_

- [x] 6.2 Create TranscriptionService wrapper
  - Implement TranscriptionService class that wraps configured provider
  - Implement transcribe() method that delegates to provider
  - Update job status to TRANSCRIBED and set transcript_path
  - _Requirements: 3.1, 3.3, 3.4, 9.6_

- [x] 6.3 Write unit tests for transcription service
  - Test FasterWhisperProvider returns valid Transcript structure
  - Test transcribe() saves transcript JSON correctly
  - Test transcription errors are caught and raised
  - _Requirements: 3.1, 3.3, 3.4_

- [x] 7. Implement translation provider interface
  - [x] 7.1 Create translation module (translation.py)
    - Create TranslationProvider abstract base class with translate() abstract method
    - Implement GoogleTranslateProvider using googletrans library or Google Cloud Translation API
    - Implement translate() that preserves timestamps and translates text segments
    - Translate Mandarin to Indonesian (configurable source/target languages)
    - Save translation JSON to temp/{video_name}_translation.json
    - Raise TranslationError on failure
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 9.4_

- [x] 7.2 Create TranslationService wrapper
  - Implement TranslationService class that wraps configured provider
  - Implement translate() method that delegates to provider
    - Update job status to TRANSLATED and set translation_path
  - _Requirements: 4.1, 4.2, 4.3, 9.6_

- [x] 7.3 Write unit tests for translation service
  - Test GoogleTranslateProvider preserves timestamps
  - Test translate() saves translation JSON correctly
  - Test translation errors are caught and raised
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 8. Implement subtitle generator
  - [x] 8.1 Create subtitle generator module (subtitle_generator.py)
    - Implement SubtitleGenerator class with generate() method
    - Format each translated segment as SRT entry: sequence number, timestamp (HH:MM:SS,mmm --> HH:MM:SS,mmm), text, blank line
    - Save SRT file to output/{video_name}.srt
    - Validate SRT format correctness
    - Update job status to SRT_GENERATED and set srt_path
    - Raise SubtitleError on failure
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 8.2 Write unit tests for subtitle generator
  - Test valid segments produce correctly formatted SRT
  - Test timestamp format is HH:MM:SS,mmm
  - Test sequence numbers are sequential starting from 1
  - Test empty segment list produces empty SRT
  - _Requirements: 5.1, 5.2, 5.4_

- [x] 9. Implement video processor (subtitle burner)
  - [x] 9.1 Create video processor module (video_processor.py)
    - Implement VideoProcessor class with burn_subtitles() method
    - Use FFmpeg to burn subtitles into video: `ffmpeg -i input.mp4 -vf "subtitles=subtitle.srt" output.mp4`
    - Preserve original video quality, resolution, codec, audio track
    - Configure subtitle placement (bottom center), font, size from config
    - Save output video to output/{video_name}_subtitled.mp4
    - Verify output video is playable (non-zero size, valid container)
    - Update job status to COMPLETED and set output_video_path
    - Raise VideoProcessingError on failure
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 9.5_

- [x] 9.2 Write unit tests for video processor
  - Test successful subtitle burning produces valid output video
  - Test FFmpeg errors are caught and raised as VideoProcessingError
  - Test output path follows naming convention
  - _Requirements: 6.1, 6.2, 6.4, 6.5_

- [x] 10. Implement job logger
  - [x] 10.1 Create logging module (job_logger.py)
    - Implement JobLogger class with in-memory log buffer
    - Implement log_job_start() to record job start timestamp and filename
    - Implement log_job_complete() to record completion time, output filename, success status
    - Implement log_job_failure() to record error message, stack trace, timestamp
    - Implement write_processing_log() to save all logs to output/processing.log
    - Implement write_failed_jobs() to create output/failed_jobs.txt with failed job names and errors
    - Implement generate_batch_report() to create output/batch_report.json with summary statistics
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [x] 10.2 Write unit tests for job logger
  - Test log entries are timestamped correctly
  - Test failed jobs are captured in failed_jobs.txt
  - Test batch report contains correct counts
  - _Requirements: 7.2, 7.3, 7.4, 7.6_

- [x] 11. Implement retry and resume manager
  - [x] 11.1 Create retry manager module (retry_manager.py)
    - Implement RetryManager class
    - Implement save_job_state() to save job list to output/job_state.json after each job
    - Implement load_job_state() to restore job list from JSON
    - Implement filter_resumable() to return jobs that are not COMPLETED
    - Handle JSON serialization of VideoJob dataclasses (custom encoder/decoder)
    - _Requirements: 7.6, 8.5_

- [x] 11.2 Write unit tests for retry manager
  - Test completed jobs are filtered out on resume
  - Test failed jobs are included in resumable list
  - Test job state round-trips through JSON serialization
  - _Requirements: 8.5_

- [x] 12. Implement temporary file cleanup
  - [x] 12.1 Create cleanup module (cleanup.py)
    - Implement CleanupManager class
    - Implement cleanup_job_temp_files() to delete audio, transcript, translation files for a completed job
    - Implement cleanup_all_temp_files() to delete entire temp/ directory
    - Respect config.cleanup_temp_on_success and config.cleanup_temp_on_failure settings
    - Preserve temp files on job failure for debugging
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

- [x] 12.2 Write unit tests for cleanup manager
  - Test temp files are deleted after successful job when configured
  - Test temp files are preserved after failed job when configured
  - Test cleanup respects configuration settings
  - _Requirements: 11.2, 11.3, 11.4_

- [x] 13. Implement CLI runner and pipeline orchestration
  - [x] 13.1 Create main pipeline runner (pipeline.py)
    - Implement PipelineRunner class with run() method
    - Parse command-line arguments: --input, --output, --config, --resume (use argparse)
    - Load configuration from file or defaults
    - Validate input and output folders exist (create output/ and temp/ if missing)
    - If --resume flag: load job state from job_state.json
    - Else: scan input folder with VideoScanner to create job list
    - Loop through jobs sequentially (POC: no concurrency)
    - For each job: execute pipeline stages (extract audio → transcribe → translate → generate SRT → burn subtitles)
    - Handle exceptions per job: log failure, mark job as FAILED, continue to next job
    - After each job: save job state for resume capability
    - Display progress updates: "Processing 3/10: video3.mp4 (30%)"
    - After all jobs: write processing log, failed jobs list, batch report
    - Display final summary: success count, failure count, total time
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 13.2 Write integration tests for full pipeline
  - Test happy path: process 3 sample videos, verify all outputs exist
  - Test error handling: process corrupt video, verify it's marked as failed
  - Test resume capability: interrupt batch, resume, verify only remaining videos processed
  - _Requirements: 8.1, 8.2, 8.4, 8.5_

- [x] 14. Create sample configuration file
  - [x] 14.1 Create config.yaml template
    - Define default transcription provider (faster-whisper)
    - Define default translation provider (google)
    - Define default source language (zh) and target language (id)
    - Define FFmpeg audio and subtitle parameters
    - Define cleanup options
    - Add comments explaining each configuration option
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 15. Test with single video
  - [x] 15.1 Run pipeline with one test video
    - Create test input folder with 1 short Mandarin video (10-30 seconds)
    - Run pipeline: `python pipeline.py --input ./test_input --output ./test_output`
    - Verify output video exists with burned-in Indonesian subtitles
    - Verify SRT file exists and is correctly formatted
    - Verify processing.log contains all stages
    - Verify batch_report.json shows 1/1 success
    - Manually inspect output video for subtitle quality and synchronization
    - _Requirements: 1.5, 6.6, 7.5, 8.5, 10.5_

- [x] 16. Checkpoint - Ensure single video processing works correctly
  - Ensure all tests pass, ask the user if questions arise.

- [x] 17. Test with 10 videos (POC validation)
  - [x] 17.1 Run pipeline with 10 test videos
    - Create test input folder with 10 Mandarin videos (mix of short and medium length)
    - Run pipeline: `python pipeline.py --input ./input --output ./output`
    - Verify all 10 videos are processed (success or logged failure)
    - Verify processing.log contains entries for all 10 jobs
    - Verify batch_report.json shows accurate counts
    - Measure total processing time (baseline for scalability)
    - _Requirements: 8.1, 8.4, 8.5_

- [x] 17.2 Test resume capability with 10 videos
  - Start processing 10 videos
  - Interrupt after 5 videos complete (Ctrl+C)
  - Resume with --resume flag: `python pipeline.py --input ./input --output ./output --resume`
  - Verify only remaining 5 videos are processed
  - Verify final batch_report.json includes all 10 videos
  - _Requirements: 8.5_

- [x] 17.3 Test error handling with problematic videos
  - Add 1 corrupt video file to input folder
  - Add 1 video without audio track to input folder
  - Run pipeline with these 12 videos (10 valid + 2 invalid)
  - Verify corrupt video is processed and fails gracefully (logged in failed_jobs.txt)
  - Verify video without audio is skipped during scanning
  - Verify remaining 10 valid videos are processed successfully
  - _Requirements: 1.2, 1.3, 7.4, 7.6, 8.4_

- [x] 18. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 19. Create README and usage documentation
  - [x] 19.1 Write README.md
    - Add project overview and purpose
    - Add prerequisites (Python 3.8+, FFmpeg, virtual environment)
    - Add installation instructions (clone, create venv, pip install -r requirements.txt)
    - Add usage instructions with examples
    - Add configuration guide (explain config.yaml options)
    - Add troubleshooting section (common errors, solutions)
    - Add example output structure
    - Add notes on scalability and future enhancements
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation through manual testing
- No property-based tests included because the system is infrastructure-focused (FFmpeg, external APIs, file I/O) without algorithmic transformations
- Unit tests validate component isolation with mocked dependencies
- Integration tests validate end-to-end pipeline correctness with real sample videos
- Testing strategy focuses on error handling, resume capability, and output quality
- POC processes videos sequentially; concurrency will be added in future scaling phase

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "3.1"] },
    { "id": 2, "tasks": ["4.1", "14.1"] },
    { "id": 3, "tasks": ["4.2", "5.1"] },
    { "id": 4, "tasks": ["5.2", "6.1"] },
    { "id": 5, "tasks": ["6.2"] },
    { "id": 6, "tasks": ["6.3", "7.1"] },
    { "id": 7, "tasks": ["7.2"] },
    { "id": 8, "tasks": ["7.3", "8.1"] },
    { "id": 9, "tasks": ["8.2", "9.1"] },
    { "id": 10, "tasks": ["9.2", "10.1"] },
    { "id": 11, "tasks": ["10.2", "11.1"] },
    { "id": 12, "tasks": ["11.2", "12.1"] },
    { "id": 13, "tasks": ["12.2", "13.1"] },
    { "id": 14, "tasks": ["13.2", "15.1"] },
    { "id": 15, "tasks": ["17.1"] },
    { "id": 16, "tasks": ["17.2", "17.3"] },
    { "id": 17, "tasks": ["19.1"] }
  ]
}
```
