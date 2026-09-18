import logging
import os
import tempfile
import unittest
from pathlib import Path

from image_assets import copy_folder_images, find_image_files


# Small but non-trivial binary payloads so byte-for-byte copying is actually
# exercised instead of trivially-equal empty files.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4
JPEG_BYTES = b"\xff\xd8\xff\xe0" + bytes(range(255, -1, -1)) * 4 + b"\xff\xd9"
WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBPVP8 " + bytes(range(128))


def _silent_logger():
    logger = logging.getLogger("image_assets_tests")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


class FindImageFilesTests(unittest.TestCase):
    def test_finds_supported_image_extensions_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            for name in (
                "poster.jpg",
                "cover.png",
                "still.jpeg",
                "banner.webp",
                "episode.mp4",
                "notes.txt",
            ):
                (folder / name).write_bytes(b"x")

            found = [path.name for path in find_image_files(folder)]

        self.assertEqual(found, ["banner.webp", "cover.png", "poster.jpg", "still.jpeg"])

    def test_matches_extensions_case_insensitively(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            (folder / "POSTER.JPG").write_bytes(b"x")
            (folder / "Cover.PNG").write_bytes(b"x")

            found = [path.name for path in find_image_files(folder)]

        self.assertEqual(found, ["Cover.PNG", "POSTER.JPG"])

    def test_returns_empty_list_for_missing_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual(find_image_files(Path(temp_dir) / "missing"), [])


class CopyFolderImagesTests(unittest.TestCase):
    def test_copies_poster_jpg_preserving_bytes_and_filename(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "143-老公突然有了读心术"
            source.mkdir()
            (source / "poster.jpg").write_bytes(JPEG_BYTES)
            destination = root / "143-Suamiku Tiba-Tiba Bisa Membaca Pikiran"

            report = copy_folder_images(source, destination)

            self.assertEqual([path.name for path in report.copied], ["poster.jpg"])
            self.assertEqual(report.failed, ())
            self.assertEqual((destination / "poster.jpg").read_bytes(), JPEG_BYTES)

    def test_copies_cover_png_preserving_bytes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            source.mkdir()
            (source / "cover.png").write_bytes(PNG_BYTES)
            destination = root / "destination"

            report = copy_folder_images(source, destination)

            self.assertEqual([path.name for path in report.copied], ["cover.png"])
            self.assertEqual((destination / "cover.png").read_bytes(), PNG_BYTES)

    def test_copies_every_image_when_the_folder_has_several(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            source.mkdir()
            (source / "poster.jpg").write_bytes(JPEG_BYTES)
            (source / "thumbnail.png").write_bytes(PNG_BYTES)
            (source / "banner.webp").write_bytes(WEBP_BYTES)
            destination = root / "destination"

            report = copy_folder_images(source, destination)

            self.assertEqual(
                sorted(path.name for path in report.copied),
                ["banner.webp", "poster.jpg", "thumbnail.png"],
            )
            self.assertEqual((destination / "poster.jpg").read_bytes(), JPEG_BYTES)
            self.assertEqual((destination / "thumbnail.png").read_bytes(), PNG_BYTES)
            self.assertEqual((destination / "banner.webp").read_bytes(), WEBP_BYTES)

    def test_leaves_the_source_folder_untouched(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "143-老公突然有了读心术"
            source.mkdir()
            (source / "poster.jpg").write_bytes(JPEG_BYTES)
            (source / "001.mp4").write_bytes(b"video")
            before = sorted(path.name for path in source.iterdir())

            copy_folder_images(source, root / "destination")

            self.assertTrue(source.is_dir())
            self.assertEqual(sorted(path.name for path in source.iterdir()), before)
            self.assertEqual((source / "poster.jpg").read_bytes(), JPEG_BYTES)

    def test_does_not_create_destination_when_there_are_no_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            source.mkdir()
            (source / "001.mp4").write_bytes(b"video")
            destination = root / "destination"

            report = copy_folder_images(source, destination)

            self.assertEqual(report.copied, ())
            self.assertFalse(destination.exists())

    def test_reports_failures_instead_of_raising(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            source.mkdir()
            (source / "poster.jpg").write_bytes(JPEG_BYTES)
            # A plain file where the output folder should go makes every copy
            # fail deterministically, on any OS and for any user.
            destination = root / "destination"
            destination.write_bytes(b"not a folder")

            report = copy_folder_images(source, destination, logger=_silent_logger())

            self.assertEqual(report.copied, ())
            self.assertEqual([path.name for path, _ in report.failed], ["poster.jpg"])
            self.assertTrue(report.failed[0][1])

    def test_keeps_copying_remaining_images_after_one_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            source.mkdir()
            unreadable = source / "a-poster.jpg"
            unreadable.write_bytes(JPEG_BYTES)
            (source / "b-cover.png").write_bytes(PNG_BYTES)
            destination = root / "destination"

            os.chmod(unreadable, 0o000)
            try:
                if os.access(unreadable, os.R_OK):
                    self.skipTest("file permissions are not enforced for this user")
                report = copy_folder_images(source, destination, logger=_silent_logger())
            finally:
                os.chmod(unreadable, 0o644)

            self.assertEqual([path.name for path, _ in report.failed], ["a-poster.jpg"])
            self.assertEqual([path.name for path in report.copied], ["b-cover.png"])
            self.assertEqual((destination / "b-cover.png").read_bytes(), PNG_BYTES)


if __name__ == "__main__":
    unittest.main()
