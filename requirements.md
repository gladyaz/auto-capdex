# Requirements Document

## Introduction

This document specifies the requirements for a batch subtitle pipeline that processes Mandarin/Chinese short drama videos and adds Indonesian subtitles. The system is designed to handle proof-of-concept processing of 10 videos with scalability to 1,000–10,000 videos. The pipeline extracts audio, transcribes Mandarin speech, translates to Indonesian, and burns subtitles into the final video output.

## Glossary

- **Pipeline**: The automated batch processing system that handles video subtitle generation
- **Input_Folder**: Directory containing source .mp4 video files
- **Output_Folder**: Directory where processed videos with burned-in subtitles are saved
- **Audio_Extractor**: Component that extracts audio tracks from video files using FFmpeg
- **Transcriber**: Component that converts Mandarin audio to text using Whisper or faster-whisper
- **Translator**: Component that converts Mandarin text to Indonesian text
- **Subtitle_Generator**: Component that creates .srt subtitle files from translated text
- **Video_Processor**: Component that burns subtitles into video using FFmpeg
- **Job**: A single video processing operation from input to final output
- **Processing_Log**: Record of all processing activities, timestamps, and outcomes
- **Failed_Jobs_List**: List of jobs that encountered errors during processing
- **SRT**: SubRip Subtitle file format containing timed text segments

## Requirements

### Requirement 1: Video Input Processing

**User Story:** As a video processor, I want to scan and validate input videos, so that I can process all valid video files in a batch.

#### Acceptance Criteria

1. WHEN the Pipeline starts, THE Pipeline SHALL scan the Input_Folder for all .mp4 files
2. WHEN a file is found, THE Pipeline SHALL validate that it is a readable video file with audio
3. IF a file cannot be read or lacks audio, THEN THE Pipeline SHALL skip it and log the error
4. THE Pipeline SHALL create a job entry for each valid video file
5. WHEN all files are scanned, THE Pipeline SHALL report the total count of valid jobs

### Requirement 2: Audio Extraction

**User Story:** As a transcription system, I want to extract audio from video files, so that I can transcribe the spoken content.

#### Acceptance Criteria

1. WHEN processing a job, THE Audio_Extractor SHALL extract the audio track using FFmpeg
2. THE Audio_Extractor SHALL save the extracted audio as a temporary file in a supported format (WAV or MP3)
3. IF audio extraction fails, THEN THE Audio_Extractor SHALL mark the job as failed and log the error
4. WHEN audio extraction succeeds, THE Audio_Extractor SHALL verify the audio file is readable
5. THE Audio_Extractor SHALL preserve the original video file unchanged

### Requirement 3: Mandarin Speech Transcription

**User Story:** As a subtitle generator, I want to transcribe Mandarin audio to text, so that I can create accurate subtitle content.

#### Acceptance Criteria

1. WHEN audio is extracted, THE Transcriber SHALL transcribe the audio using Whisper or faster-whisper
2. THE Transcriber SHALL detect Mandarin/Chinese as the source language
3. THE Transcriber SHALL generate timestamped text segments with start time, end time, and text content
4. IF transcription fails, THEN THE Transcriber SHALL mark the job as failed and log the error
5. THE Transcriber SHALL preserve timing accuracy within 500ms of actual speech
6. WHERE the Transcriber implementation is configurable, THE Pipeline SHALL allow switching between Whisper and faster-whisper

### Requirement 4: Indonesian Translation

**User Story:** As a subtitle generator, I want to translate Mandarin text to Indonesian, so that I can provide localized subtitles.

#### Acceptance Criteria

1. WHEN transcription is complete, THE Translator SHALL translate each text segment from Mandarin to Indonesian
2. THE Translator SHALL preserve the timing information (start time, end time) for each segment
3. THE Translator SHALL maintain the original segment boundaries without merging or splitting
4. IF translation fails for a segment, THEN THE Translator SHALL mark the job as failed and log the error
5. WHERE the Translator implementation is configurable, THE Pipeline SHALL allow switching between different translation providers

### Requirement 5: Subtitle File Generation

**User Story:** As a video processor, I want to generate SRT subtitle files, so that I can burn subtitles into videos.

#### Acceptance Criteria

1. WHEN translation is complete, THE Subtitle_Generator SHALL create an SRT file with Indonesian text
2. THE Subtitle_Generator SHALL format each subtitle entry with sequence number, timestamp range, and text
3. THE Subtitle_Generator SHALL save the SRT file with a name matching the original video filename
4. THE Subtitle_Generator SHALL ensure timestamp format is HH:MM:SS,mmm --> HH:MM:SS,mmm
5. IF SRT generation fails, THEN THE Subtitle_Generator SHALL mark the job as failed and log the error

### Requirement 6: Subtitle Burning

**User Story:** As a content producer, I want subtitles burned into the video, so that viewers see Indonesian subtitles during playback.

#### Acceptance Criteria

1. WHEN an SRT file is generated, THE Video_Processor SHALL burn the subtitles into the video using FFmpeg
2. THE Video_Processor SHALL preserve the original video quality, resolution, and audio track
3. THE Video_Processor SHALL place subtitles in a readable position (bottom center or configurable)
4. THE Video_Processor SHALL save the output video to the Output_Folder with a distinguishable filename
5. IF subtitle burning fails, THEN THE Video_Processor SHALL mark the job as failed and log the error
6. THE Video_Processor SHALL verify the output video file is playable and non-corrupted

### Requirement 7: Processing Logs and Error Handling

**User Story:** As a system operator, I want comprehensive processing logs, so that I can track progress and troubleshoot failures.

#### Acceptance Criteria

1. THE Pipeline SHALL create a Processing_Log for each batch run with timestamp, input folder, and job count
2. WHEN a job starts, THE Pipeline SHALL log the job start time and video filename
3. WHEN a job completes, THE Pipeline SHALL log the completion time, output filename, and success status
4. WHEN a job fails, THE Pipeline SHALL log the failure reason, stack trace, and timestamp
5. THE Pipeline SHALL save all logs to a persistent log file in the Output_Folder
6. THE Pipeline SHALL create a Failed_Jobs_List file containing all failed job names and error reasons

### Requirement 8: Batch Processing and Scalability

**User Story:** As a batch processor, I want to process multiple videos efficiently, so that I can handle 1,000–10,000 videos.

#### Acceptance Criteria

1. THE Pipeline SHALL process videos sequentially for the POC (10 videos)
2. WHERE parallel processing is implemented, THE Pipeline SHALL process multiple videos concurrently
3. THE Pipeline SHALL allow configuration of concurrency level (number of parallel jobs)
4. THE Pipeline SHALL continue processing remaining jobs even when individual jobs fail
5. WHEN all jobs are complete, THE Pipeline SHALL generate a summary report with success count, failure count, and total processing time

### Requirement 9: Configuration and Extensibility

**User Story:** As a system maintainer, I want configurable components, so that I can replace transcription models or translation providers easily.

#### Acceptance Criteria

1. THE Pipeline SHALL read configuration from a configuration file or environment variables
2. THE Pipeline SHALL allow configuration of Input_Folder and Output_Folder paths
3. THE Pipeline SHALL allow configuration of transcription provider (Whisper, faster-whisper)
4. THE Pipeline SHALL allow configuration of translation provider (plugin-based or API-based)
5. THE Pipeline SHALL allow configuration of FFmpeg parameters for audio extraction and subtitle burning
6. WHERE a component is replaced, THE Pipeline SHALL continue functioning without code changes to other components

### Requirement 10: Command-Line Interface

**User Story:** As a system operator, I want a CLI to run the pipeline, so that I can process videos from the command line.

#### Acceptance Criteria

1. THE Pipeline SHALL provide a command-line interface for execution
2. WHEN invoked, THE Pipeline SHALL accept input folder path and output folder path as arguments
3. THE Pipeline SHALL accept optional configuration file path as an argument
4. THE Pipeline SHALL display progress updates during processing (current job, percentage complete)
5. WHEN processing completes, THE Pipeline SHALL display a summary with success count, failure count, and total time
6. IF required arguments are missing, THEN THE Pipeline SHALL display usage instructions and exit

### Requirement 11: Temporary File Management

**User Story:** As a system operator, I want automatic cleanup of temporary files, so that I don't waste disk space.

#### Acceptance Criteria

1. THE Pipeline SHALL create a temporary directory for intermediate files (extracted audio, transcripts)
2. WHEN a job completes successfully, THE Pipeline SHALL delete temporary files for that job
3. WHEN a job fails, THE Pipeline SHALL preserve temporary files for debugging
4. WHERE cleanup is configured, THE Pipeline SHALL delete all temporary files after batch completion
5. THE Pipeline SHALL ensure temporary files do not exceed available disk space before processing
