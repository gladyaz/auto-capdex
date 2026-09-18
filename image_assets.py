from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path


# Poster/cover artwork shipped alongside the episodes. Videos are handled by
# VideoScanner; these extensions are copied verbatim and never treated as
# pipeline inputs.
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})


@dataclass(frozen=True)
class ImageCopyReport:
    """Outcome of copying one source drama folder's artwork."""

    copied: tuple[Path, ...] = ()
    failed: tuple[tuple[Path, str], ...] = ()


def find_image_files(folder: str | Path) -> list[Path]:
    """Return the image files directly inside `folder`, sorted by name."""
    path = Path(folder)
    if not path.is_dir():
        return []

    return sorted(
        (
            entry
            for entry in path.iterdir()
            if entry.is_file() and entry.suffix.lower() in IMAGE_EXTENSIONS
        ),
        key=lambda entry: entry.name,
    )


def copy_folder_images(
    source_folder: str | Path,
    destination_folder: str | Path,
    logger: logging.Logger | None = None,
) -> ImageCopyReport:
    """Copy every image in `source_folder` into `destination_folder`.

    Files are copied byte-for-byte with `shutil.copy2`: no re-encoding, no
    resizing, no OCR, and the original filename is preserved. The source
    folder is only ever read from. A failure on one image is logged and does
    not stop the remaining images or the video pipeline.
    """
    active_logger = logger or logging.getLogger(__name__)
    images = find_image_files(source_folder)
    if not images:
        return ImageCopyReport()

    destination = Path(destination_folder)
    copied: list[Path] = []
    failed: list[tuple[Path, str]] = []

    for image in images:
        try:
            destination.mkdir(parents=True, exist_ok=True)
            target = destination / image.name
            shutil.copy2(image, target)
        except OSError as error:
            active_logger.error("Failed to copy image %s: %s", image, error)
            failed.append((image, str(error)))
            continue

        active_logger.info("Copied image %s to %s", image, target)
        copied.append(target)

    return ImageCopyReport(copied=tuple(copied), failed=tuple(failed))


__all__ = [
    "IMAGE_EXTENSIONS",
    "ImageCopyReport",
    "copy_folder_images",
    "find_image_files",
]
