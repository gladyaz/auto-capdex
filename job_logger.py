from __future__ import annotations

import json
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional

from models import JobStatus, VideoJob


Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobLogger:
    def __init__(
        self,
        batch_id: str | None = None,
        batch_start_time: datetime | None = None,
        clock: Clock = utc_now,
        input_folder: Path | None = None,
        output_folder: Path | None = None,
    ):
        self.batch_id = batch_id or str(uuid.uuid4())
        self.batch_start_time = batch_start_time or clock()
        self.clock = clock
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.log_entries: list[dict[str, object]] = []
        self.failed_jobs: list[dict[str, str]] = []

    def log_job_start(self, job: VideoJob) -> None:
        self.log_entries.append(
            {
                "timestamp": self._timestamp(),
                "event": "job_started",
                "job_id": job.job_id,
                "video_filename": job.video_path.name,
                "video_path": str(job.video_path),
                "status": job.status.value,
            }
        )

    def log_job_complete(self, job: VideoJob) -> None:
        self.log_entries.append(
            {
                "timestamp": self._timestamp(),
                "event": "job_completed",
                "job_id": job.job_id,
                "video_filename": job.video_path.name,
                "video_path": str(job.video_path),
                "status": job.status.value,
                "output_video_path": _optional_path(job.output_video_path),
            }
        )

    def log_job_failure(self, job: VideoJob, error: Exception) -> None:
        error_text = f"{error.__class__.__name__}: {error}"
        stack_trace = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
        failure = {
            "video_filename": job.video_path.name,
            "error": error_text,
        }
        self.failed_jobs.append(failure)
        self.log_entries.append(
            {
                "timestamp": self._timestamp(),
                "event": "job_failed",
                "job_id": job.job_id,
                "video_filename": job.video_path.name,
                "video_path": str(job.video_path),
                "status": JobStatus.FAILED.value,
                "error": error_text,
                "error_message": job.error_message,
                "stack_trace": stack_trace,
            }
        )

    def log_video_skip(self, video_path: str | Path, reason: str) -> None:
        path = Path(video_path)
        error_text = f"Skipped: {reason}"
        self.failed_jobs.append(
            {
                "video_filename": path.name,
                "error": error_text,
            }
        )
        self.log_entries.append(
            {
                "timestamp": self._timestamp(),
                "event": "video_skipped",
                "video_filename": path.name,
                "video_path": str(path),
                "status": "skipped",
                "error": error_text,
            }
        )

    def log_image_copied(self, image_path: str | Path, destination_path: str | Path) -> None:
        self.log_entries.append(
            {
                "timestamp": self._timestamp(),
                "event": "image_copied",
                "image_filename": Path(image_path).name,
                "image_path": str(image_path),
                "destination_path": str(destination_path),
                "status": "copied",
            }
        )

    def log_image_copy_failure(self, image_path: str | Path, reason: str) -> None:
        path = Path(image_path)
        error_text = f"Image copy failed: {reason}"
        self.failed_jobs.append(
            {
                "video_filename": path.name,
                "error": error_text,
            }
        )
        self.log_entries.append(
            {
                "timestamp": self._timestamp(),
                "event": "image_copy_failed",
                "image_filename": path.name,
                "image_path": str(path),
                "status": "failed",
                "error": error_text,
            }
        )

    def write_processing_log(self, log_file: str | Path) -> None:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = "".join(
            json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
            for entry in self.log_entries
        )
        path.write_text(content, encoding="utf-8")

    def write_failed_jobs(self, failed_file: str | Path) -> None:
        path = Path(failed_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = "".join(
            f"{failure['video_filename']}: {_single_line(failure['error'])}\n"
            for failure in self.failed_jobs
        )
        path.write_text(content, encoding="utf-8")

    def generate_batch_report(
        self,
        report_file: str | Path,
        jobs: Iterable[VideoJob],
        drama_folders: Iterable[Mapping[str, object]] | None = None,
    ) -> dict[str, object]:
        job_list = list(jobs)
        end_time = self.clock()
        success_count = sum(1 for job in job_list if job.status == JobStatus.COMPLETED)
        failure_count = sum(1 for job in job_list if job.status == JobStatus.FAILED)
        pending_count = len(job_list) - success_count - failure_count
        total_seconds = (end_time - self.batch_start_time).total_seconds()

        report: dict[str, object] = {
            "batch_id": self.batch_id,
            "start_time": self.batch_start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "input_folder": _optional_path(self.input_folder),
            "output_folder": _optional_path(self.output_folder),
            "job_count": len(job_list),
            "success_count": success_count,
            "failure_count": failure_count,
            "pending_count": pending_count,
            "success_rate": success_count / len(job_list) if job_list else 0.0,
            "total_processing_seconds": total_seconds,
            "drama_folders": [dict(folder) for folder in (drama_folders or [])],
            "jobs": [_job_to_dict(job) for job in job_list],
        }

        path = Path(report_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return report

    def _timestamp(self) -> str:
        return self.clock().isoformat()


def _job_to_dict(job: VideoJob) -> dict[str, Optional[str]]:
    return {
        "job_id": job.job_id,
        "video_path": str(job.video_path),
        "video_name": job.video_name,
        "output_name": job.output_name,
        "status": job.status.value,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "error_message": job.error_message,
        "audio_path": _optional_path(job.audio_path),
        "transcript_path": _optional_path(job.transcript_path),
        "translation_path": _optional_path(job.translation_path),
        "srt_path": _optional_path(job.srt_path),
        "output_video_path": _optional_path(job.output_video_path),
    }


def _optional_path(path: Path | None) -> Optional[str]:
    return str(path) if path is not None else None


def _single_line(value: str) -> str:
    return " | ".join(line.strip() for line in value.splitlines() if line.strip())


__all__ = ["JobLogger"]
