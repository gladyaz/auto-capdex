from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from models import JobStatus, VideoJob


STATE_VERSION = 1


class RetryManager:
    def save_job_state(self, state_file: str | Path, jobs: Iterable[VideoJob]) -> None:
        path = Path(state_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": STATE_VERSION,
            "jobs": [_job_to_dict(job) for job in jobs],
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def load_job_state(self, state_file: str | Path) -> list[VideoJob]:
        path = Path(state_file)
        if not path.exists():
            return []

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid job state JSON: {path}") from error

        if not isinstance(payload, dict):
            raise ValueError("Job state must be a JSON object")

        jobs_payload = payload.get("jobs", [])
        if not isinstance(jobs_payload, list):
            raise ValueError("Job state 'jobs' must be a list")

        return [_job_from_dict(job_payload) for job_payload in jobs_payload]

    def filter_resumable(self, jobs: Iterable[VideoJob]) -> list[VideoJob]:
        return [job for job in jobs if job.status != JobStatus.COMPLETED]


def _job_to_dict(job: VideoJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "video_path": str(job.video_path),
        "video_name": job.video_name,
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


def _job_from_dict(payload: Any) -> VideoJob:
    if not isinstance(payload, dict):
        raise ValueError("Each job state entry must be a JSON object")

    try:
        return VideoJob(
            job_id=str(payload["job_id"]),
            video_path=Path(payload["video_path"]),
            video_name=_optional_str(payload.get("video_name")),
            status=JobStatus(str(payload["status"])),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            updated_at=datetime.fromisoformat(str(payload["updated_at"])),
            error_message=_optional_str(payload.get("error_message")),
            audio_path=_optional_path_from_payload(payload.get("audio_path")),
            transcript_path=_optional_path_from_payload(payload.get("transcript_path")),
            translation_path=_optional_path_from_payload(payload.get("translation_path")),
            srt_path=_optional_path_from_payload(payload.get("srt_path")),
            output_video_path=_optional_path_from_payload(payload.get("output_video_path")),
        )
    except KeyError as error:
        raise ValueError(f"Job state is missing required field: {error.args[0]}") from error
    except ValueError as error:
        raise ValueError(f"Invalid job state entry: {error}") from error


def _optional_path(path: Path | None) -> str | None:
    return str(path) if path is not None else None


def _optional_path_from_payload(value: Any) -> Path | None:
    return Path(value) if value is not None else None


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


__all__ = ["RetryManager"]
