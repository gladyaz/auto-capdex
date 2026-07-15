from __future__ import annotations

import logging
import shutil
from pathlib import Path

from models import Config, JobStatus, VideoJob


class CleanupManager:
    def __init__(self, config: Config, logger: logging.Logger | None = None):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

    def cleanup_job_temp_files(self, job: VideoJob) -> list[Path]:
        if not self._should_cleanup_job(job):
            return []

        removed: list[Path] = []
        for path in self._job_temp_artifacts(job):
            if path.exists() and path.is_file():
                path.unlink()
                removed.append(path)
                self.logger.info("Deleted temp artifact: %s", path)

        return removed

    def cleanup_all_temp_files(self) -> None:
        temp_folder = self.config.temp_folder
        if temp_folder.exists():
            shutil.rmtree(temp_folder)
            self.logger.info("Deleted temp directory: %s", temp_folder)

    def _should_cleanup_job(self, job: VideoJob) -> bool:
        if job.status == JobStatus.COMPLETED:
            return self.config.cleanup_temp_on_success
        if job.status == JobStatus.FAILED:
            return self.config.cleanup_temp_on_failure
        return False

    def _job_temp_artifacts(self, job: VideoJob) -> tuple[Path, ...]:
        paths = (
            job.audio_path,
            job.transcript_path,
            job.translation_path,
        )
        return tuple(path for path in paths if path is not None)


__all__ = ["CleanupManager"]
