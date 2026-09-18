from __future__ import annotations

import argparse
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Iterable, TextIO

from audio_extractor import AudioExtractor
from cleanup import CleanupManager
from config_loader import load_config
from folder_titles import FolderTitleTranslator
from image_assets import copy_folder_images
from job_logger import JobLogger
from models import Config, JobStatus, VideoJob
from retry_manager import RetryManager
from subtitle_generator import SubtitleGenerator
from transcription import FasterWhisperProvider, TranscriptionService
from translation import GoogleTranslateProvider, TranslationService
from video_processor import VideoProcessor
from video_scanner import VideoScanner


@dataclass(frozen=True)
class PipelineSummary:
    total_count: int
    success_count: int
    failure_count: int
    pending_count: int
    total_processing_seconds: float


class PipelineRunner:
    def __init__(
        self,
        config: Config,
        scanner=None,
        audio_extractor=None,
        transcription_service=None,
        translation_service=None,
        subtitle_generator=None,
        video_processor=None,
        job_logger: JobLogger | None = None,
        retry_manager: RetryManager | None = None,
        cleanup_manager: CleanupManager | None = None,
        title_translator: FolderTitleTranslator | None = None,
        progress_writer: TextIO | None = sys.stdout,
    ):
        self.config = config
        self.scanner = scanner or VideoScanner()
        self.audio_extractor = audio_extractor or AudioExtractor(config=config)
        self.transcription_service = transcription_service or TranscriptionService(
            provider=FasterWhisperProvider(
                model_size=config.transcription_model_size,
                device=config.transcription_device,
                compute_type=config.transcription_compute_type,
                vad_filter=config.transcription_vad_filter,
                no_speech_threshold=config.transcription_no_speech_threshold,
                condition_on_previous_text=config.transcription_condition_on_previous_text,
                cpu_threads=config.transcription_cpu_threads,
                beam_size=config.transcription_beam_size,
                compression_ratio_threshold=config.transcription_compression_ratio_threshold,
                skip_intro_seconds=config.transcription_skip_intro_seconds,
                min_word_probability=config.transcription_min_word_probability,
            ),
            config=config,
        )
        self.translation_service = translation_service or TranslationService(
            provider=GoogleTranslateProvider(
                max_retries=config.translation_max_retries,
                retry_backoff_seconds=config.translation_retry_backoff_seconds,
            ),
            config=config,
        )
        self.subtitle_generator = subtitle_generator or SubtitleGenerator(config=config)
        self.video_processor = video_processor or VideoProcessor(config=config)
        self.job_logger = job_logger or JobLogger(
            input_folder=config.input_folder,
            output_folder=config.output_folder,
        )
        self.retry_manager = retry_manager or RetryManager()
        self.cleanup_manager = cleanup_manager or CleanupManager(config=config)
        # Drama folder titles reuse the subtitle translation provider already
        # configured above, so no additional provider or API key is involved.
        self.title_translator = title_translator or FolderTitleTranslator(
            translator=getattr(self.translation_service, "provider", None),
            source_language=config.translation_source_language,
            target_language=config.target_language,
        )
        self.progress_writer = progress_writer
        # Faster-whisper's compute_type/cpu_threads tuning already saturates the
        # machine's performance cores for one job; running transcribe() from two
        # threads at once would oversubscribe those cores instead of speeding
        # anything up, so this lock keeps whisper calls one-at-a-time while
        # ffmpeg/translation stages for other jobs still run concurrently.
        self._transcription_lock = threading.Lock()

    def run(self, resume: bool = False) -> PipelineSummary:
        started_at = time.monotonic()
        self._prepare_directories()

        state_file = self.config.output_folder / "job_state.json"
        jobs = self._load_or_scan_jobs(state_file, resume=resume)
        if not resume:
            # Resumed jobs already carry the output name chosen by the original
            # run; re-translating could pick a different Indonesian title and
            # scatter one drama across two output folders.
            jobs = self._apply_translated_output_folders(jobs)
        self._copy_drama_folder_images(jobs)

        total_jobs = len(jobs)
        pending_indices = [
            index for index, job in enumerate(jobs) if job.status != JobStatus.COMPLETED
        ]
        state_lock = threading.Lock()
        completed_count = 0

        def process_and_persist(index: int) -> None:
            nonlocal completed_count
            job = jobs[index]
            self.job_logger.log_job_start(job)

            try:
                updated_job = self._process_job(job)
                self.job_logger.log_job_complete(updated_job)
                self.cleanup_manager.cleanup_job_temp_files(updated_job)
            except Exception as error:
                updated_job = job.with_failure(str(error))
                self.job_logger.log_job_failure(updated_job, error)
                self.cleanup_manager.cleanup_job_temp_files(updated_job)

            with state_lock:
                jobs[index] = updated_job
                self.retry_manager.save_job_state(state_file, jobs)
                completed_count += 1
                self._write_progress(completed=completed_count, total=total_jobs, job=updated_job)

        with ThreadPoolExecutor(max_workers=self.config.concurrency_level) as executor:
            futures = [executor.submit(process_and_persist, index) for index in pending_indices]
            for future in futures:
                future.result()

        self._write_final_artifacts(jobs)
        summary = _build_summary(jobs, total_seconds=time.monotonic() - started_at)
        self._write_summary(summary)
        return summary

    def _prepare_directories(self) -> None:
        if not self.config.input_folder.exists():
            raise FileNotFoundError(f"Input folder does not exist: {self.config.input_folder}")
        if not self.config.input_folder.is_dir():
            raise NotADirectoryError(f"Input path is not a directory: {self.config.input_folder}")

        self.config.output_folder.mkdir(parents=True, exist_ok=True)
        self.config.temp_folder.mkdir(parents=True, exist_ok=True)

    def _load_or_scan_jobs(self, state_file: Path, resume: bool) -> list[VideoJob]:
        if resume:
            return self.retry_manager.load_job_state(state_file)

        jobs = self.scanner.scan(self.config.input_folder)
        for skipped_file in getattr(self.scanner, "skipped_files", []):
            self.job_logger.log_video_skip(
                skipped_file["video_path"],
                skipped_file["reason"],
            )
        return jobs

    def _apply_translated_output_folders(self, jobs: list[VideoJob]) -> list[VideoJob]:
        """Give each job an output name whose drama folder is Indonesian.

        Source folders are never renamed: only the job's output_name changes,
        which is what the SRT and burned-video writers build their paths from.
        Translation happens once per drama folder and is cached for every
        episode inside it.
        """
        updated = list(jobs)
        for index, job in enumerate(updated):
            source_folder = _drama_folder_name(job.video_name)
            if source_folder is None:
                continue

            title = self.title_translator.resolve(source_folder)
            if title.output_name == source_folder:
                continue

            updated[index] = replace(
                job,
                output_name=_replace_drama_folder(job.video_name, title.output_name),
            )
        return updated

    def _copy_drama_folder_images(self, jobs: Iterable[VideoJob]) -> None:
        """Copy poster/cover artwork into each translated output folder."""
        for source_folder, output_folder in _drama_folder_pairs(jobs):
            report = copy_folder_images(
                self.config.input_folder / source_folder,
                self.config.output_folder / output_folder,
            )
            for destination in report.copied:
                self.job_logger.log_image_copied(
                    self.config.input_folder / source_folder / destination.name,
                    destination,
                )
            for image_path, reason in report.failed:
                self.job_logger.log_image_copy_failure(image_path, reason)

    def _drama_folder_manifest(self, jobs: Iterable[VideoJob]) -> list[dict[str, object]]:
        manifest: list[dict[str, object]] = []
        for source_folder, output_folder in _drama_folder_pairs(jobs):
            entry: dict[str, object] = {
                "source_folder_name": source_folder,
                "translated_folder_name": output_folder,
            }
            title = self.title_translator.cached(source_folder)
            if title is not None:
                entry["title_translated"] = title.translated
                if title.error is not None:
                    entry["title_translation_error"] = title.error
            manifest.append(entry)
        return manifest

    def _process_job(self, job: VideoJob) -> VideoJob:
        job = self.audio_extractor.extract(job)
        with self._transcription_lock:
            transcription_result = self.transcription_service.transcribe(job)
        job = transcription_result.job
        translation_result = self.translation_service.translate(
            job,
            transcription_result.transcript,
        )
        job = translation_result.job
        job = self.subtitle_generator.generate(job, translation_result.translation)
        return self.video_processor.burn_subtitles(job)

    def _write_final_artifacts(self, jobs: Iterable[VideoJob]) -> None:
        self.job_logger.write_processing_log(self.config.output_folder / "processing.log")
        self.job_logger.write_failed_jobs(self.config.output_folder / "failed_jobs.txt")
        job_list = list(jobs)
        self.job_logger.generate_batch_report(
            self.config.output_folder / "batch_report.json",
            job_list,
            drama_folders=self._drama_folder_manifest(job_list),
        )

    def _write_progress(self, completed: int, total: int, job: VideoJob) -> None:
        if self.progress_writer is None:
            return

        percent = int((completed / total) * 100) if total else 100
        self.progress_writer.write(
            f"Completed {completed}/{total}: {job.video_path.name} ({percent}%)\n"
        )
        self.progress_writer.flush()

    def _write_summary(self, summary: PipelineSummary) -> None:
        if self.progress_writer is None:
            return

        self.progress_writer.write(
            "Summary: "
            f"{summary.success_count} succeeded, "
            f"{summary.failure_count} failed, "
            f"{summary.pending_count} pending, "
            f"{summary.total_processing_seconds:.2f}s total\n"
        )
        self.progress_writer.flush()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch Mandarin video subtitle pipeline",
    )
    parser.add_argument("--input", required=True, type=Path, help="Input folder containing .mp4 files")
    parser.add_argument("--output", required=True, type=Path, help="Output folder for processed files")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to config.yaml",
    )
    parser.add_argument("--resume", action="store_true", help="Resume from output/job_state.json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = replace(
        load_config(args.config),
        input_folder=args.input,
        output_folder=args.output,
    )
    summary = PipelineRunner(config=config).run(resume=args.resume)
    return 1 if summary.failure_count else 0


def _drama_folder_name(relative_name: str | None) -> str | None:
    """Return the top-level drama folder of a job's relative name, if any."""
    if not relative_name:
        return None

    parts = PurePosixPath(relative_name).parts
    return parts[0] if len(parts) > 1 else None


def _replace_drama_folder(relative_name: str, output_folder: str) -> str:
    parts = PurePosixPath(relative_name).parts
    return PurePosixPath(output_folder, *parts[1:]).as_posix()


def _drama_folder_pairs(jobs: Iterable[VideoJob]) -> list[tuple[str, str]]:
    """Map each source drama folder to its output folder, in scan order."""
    pairs: dict[str, str] = {}
    for job in jobs:
        source_folder = _drama_folder_name(job.video_name)
        if source_folder is None or source_folder in pairs:
            continue
        pairs[source_folder] = _drama_folder_name(job.output_name) or source_folder
    return list(pairs.items())


def _build_summary(jobs: Iterable[VideoJob], total_seconds: float) -> PipelineSummary:
    job_list = list(jobs)
    success_count = sum(1 for job in job_list if job.status == JobStatus.COMPLETED)
    failure_count = sum(1 for job in job_list if job.status == JobStatus.FAILED)
    pending_count = len(job_list) - success_count - failure_count
    return PipelineSummary(
        total_count=len(job_list),
        success_count=success_count,
        failure_count=failure_count,
        pending_count=pending_count,
        total_processing_seconds=total_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
