import logging
import unittest

from folder_titles import (
    FolderTitleTranslator,
    extract_episode_count,
    sanitize_windows_folder_name,
    split_numeric_prefix,
    to_indonesian_title_case,
)


class FakeTextTranslator:
    """Stands in for GoogleTranslateProvider.translate_text."""

    def __init__(self, mapping=None, error=None, result=None):
        self.mapping = mapping or {}
        self.error = error
        self.result = result
        self.calls = []

    def translate_text(self, text, source_language, target_language):
        self.calls.append((text, source_language, target_language))
        if self.error is not None:
            raise self.error
        if self.result is not None:
            return self.result
        return self.mapping.get(text, f"terjemahan {text}")


def _silent_logger():
    logger = logging.getLogger("folder_titles_tests")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


class SplitNumericPrefixTests(unittest.TestCase):
    def test_splits_numeric_prefix_from_title(self):
        self.assertEqual(split_numeric_prefix("143-老公突然有了读心术"), ("143-", "老公突然有了读心术"))

    def test_returns_empty_prefix_when_title_has_none(self):
        self.assertEqual(split_numeric_prefix("老公突然有了读心术"), ("", "老公突然有了读心术"))

    def test_does_not_split_digits_that_are_part_of_the_title(self):
        self.assertEqual(split_numeric_prefix("2025年的爱情"), ("", "2025年的爱情"))


class ExtractEpisodeCountTests(unittest.TestCase):
    def test_converts_fullwidth_episode_count_to_indonesian(self):
        title, suffix = extract_episode_count("网恋掉马那天全寝室沉默了（35集）")

        self.assertEqual(title, "网恋掉马那天全寝室沉默了")
        self.assertEqual(suffix, "(35 Episode)")

    def test_converts_halfwidth_episode_count(self):
        self.assertEqual(extract_episode_count("某剧(85集)"), ("某剧", "(85 Episode)"))

    def test_handles_quantifier_prefixed_episode_count(self):
        self.assertEqual(extract_episode_count("某剧（全85集）"), ("某剧", "(85 Episode)"))

    def test_returns_empty_suffix_when_no_episode_count(self):
        self.assertEqual(extract_episode_count("老公突然有了读心术"), ("老公突然有了读心术", ""))


class IndonesianTitleCaseTests(unittest.TestCase):
    def test_capitalizes_each_word_including_hyphenated_parts(self):
        self.assertEqual(
            to_indonesian_title_case("suamiku tiba-tiba bisa membaca pikiran"),
            "Suamiku Tiba-Tiba Bisa Membaca Pikiran",
        )

    def test_keeps_conjunctions_lowercase_unless_they_open_the_title(self):
        self.assertEqual(
            to_indonesian_title_case("di balik dendam dan cinta"),
            "Di Balik Dendam dan Cinta",
        )


class SanitizeWindowsFolderNameTests(unittest.TestCase):
    def test_replaces_every_windows_invalid_character(self):
        sanitized = sanitize_windows_folder_name('12-A<B>C:D"E/F\\G|H?I*J')

        for character in '<>:"/\\|?*':
            self.assertNotIn(character, sanitized)
        self.assertTrue(sanitized.startswith("12-"))

    def test_slashes_cannot_create_subdirectories(self):
        sanitized = sanitize_windows_folder_name("4-Cinta/Rahasia\\Terlarang")

        self.assertNotIn("/", sanitized)
        self.assertNotIn("\\", sanitized)
        self.assertEqual(sanitized, "4-Cinta-Rahasia-Terlarang")

    def test_preserves_useful_punctuation(self):
        self.assertEqual(
            sanitize_windows_folder_name("143-Suamiku, Sang CEO! (35 Episode)"),
            "143-Suamiku, Sang CEO! (35 Episode)",
        )

    def test_strips_trailing_dots_and_spaces(self):
        self.assertEqual(sanitize_windows_folder_name("Cinta Terakhir.  . "), "Cinta Terakhir")

    def test_strips_control_characters(self):
        self.assertEqual(sanitize_windows_folder_name("Cinta\x00\x1fRahasia"), "CintaRahasia")

    def test_escapes_windows_reserved_device_names(self):
        for reserved in ("CON", "prn", "AUX", "nul", "COM1", "lpt9"):
            with self.subTest(reserved=reserved):
                self.assertEqual(sanitize_windows_folder_name(reserved), f"_{reserved}")

    def test_escapes_reserved_device_name_with_extension(self):
        self.assertEqual(sanitize_windows_folder_name("COM3.drama"), "_COM3.drama")

    def test_falls_back_when_nothing_safe_remains(self):
        self.assertEqual(sanitize_windows_folder_name('<>|?*'), "untitled")

    def test_truncates_overlong_names(self):
        self.assertLessEqual(len(sanitize_windows_folder_name("A" * 400)), 120)


class FolderTitleTranslatorTests(unittest.TestCase):
    def test_translates_chinese_folder_title_into_indonesian(self):
        translator = FakeTextTranslator({"老公突然有了读心术": "suamiku tiba-tiba bisa membaca pikiran"})

        title = FolderTitleTranslator(translator).resolve("143-老公突然有了读心术")

        self.assertTrue(title.translated)
        self.assertEqual(title.output_name, "143-Suamiku Tiba-Tiba Bisa Membaca Pikiran")

    def test_preserves_numeric_prefix_and_episode_count(self):
        translator = FakeTextTranslator({"网恋掉马那天全寝室沉默了": "seisi asrama terdiam"})

        title = FolderTitleTranslator(translator).resolve("4-网恋掉马那天全寝室沉默了（35集）")

        self.assertEqual(title.output_name, "4-Seisi Asrama Terdiam (35 Episode)")

    def test_translates_only_the_title_portion(self):
        translator = FakeTextTranslator({"网恋掉马那天全寝室沉默了": "seisi asrama terdiam"})

        FolderTitleTranslator(translator).resolve("4-网恋掉马那天全寝室沉默了（35集）")

        self.assertEqual([call[0] for call in translator.calls], ["网恋掉马那天全寝室沉默了"])

    def test_uses_configured_source_and_target_languages(self):
        translator = FakeTextTranslator()

        FolderTitleTranslator(translator, source_language="zh-cn", target_language="id").resolve(
            "1-某剧"
        )

        self.assertEqual(translator.calls[0][1:], ("zh-cn", "id"))

    def test_sanitizes_translated_title_for_windows(self):
        translator = FakeTextTranslator(result='cinta: rahasia/terlarang?')

        title = FolderTitleTranslator(translator).resolve("7-某剧")

        self.assertEqual(title.output_name, "7-Cinta - Rahasia-Terlarang")

    def test_translates_once_per_folder_and_reuses_the_cached_title(self):
        translator = FakeTextTranslator()
        folder_translator = FolderTitleTranslator(translator)

        first = folder_translator.resolve("143-老公突然有了读心术")
        for _ in range(9):
            folder_translator.resolve("143-老公突然有了读心术")

        self.assertEqual(len(translator.calls), 1)
        self.assertEqual(folder_translator.translation_call_count, 1)
        self.assertEqual(folder_translator.resolve("143-老公突然有了读心术"), first)

    def test_falls_back_to_source_folder_name_when_translation_fails(self):
        translator = FakeTextTranslator(error=RuntimeError("googletrans timed out"))
        folder_translator = FolderTitleTranslator(translator, logger=_silent_logger())

        title = folder_translator.resolve("143-老公突然有了读心术")

        self.assertFalse(title.translated)
        self.assertEqual(title.output_name, "143-老公突然有了读心术")
        self.assertIn("googletrans timed out", title.error)

    def test_falls_back_when_translation_is_empty(self):
        translator = FakeTextTranslator(result="   ")
        folder_translator = FolderTitleTranslator(translator, logger=_silent_logger())

        title = folder_translator.resolve("143-老公突然有了读心术")

        self.assertFalse(title.translated)
        self.assertEqual(title.output_name, "143-老公突然有了读心术")

    def test_falls_back_when_provider_cannot_translate_text(self):
        folder_translator = FolderTitleTranslator(translator=None, logger=_silent_logger())

        title = folder_translator.resolve("143-老公突然有了读心术")

        self.assertFalse(title.translated)
        self.assertEqual(title.output_name, "143-老公突然有了读心术")

    def test_duplicate_translated_titles_get_distinct_folder_names(self):
        translator = FakeTextTranslator(result="cinta terlarang")
        folder_translator = FolderTitleTranslator(translator, logger=_silent_logger())

        first = folder_translator.resolve("禁忌之恋")
        second = folder_translator.resolve("不可以的爱")

        self.assertEqual(first.output_name, "Cinta Terlarang")
        self.assertEqual(second.output_name, "Cinta Terlarang-2")

    def test_duplicate_detection_is_case_insensitive_like_windows(self):
        translator = FakeTextTranslator({"甲": "cinta terlarang", "乙": "CINTA TERLARANG"})
        folder_translator = FolderTitleTranslator(translator, logger=_silent_logger())

        first = folder_translator.resolve("甲")
        second = folder_translator.resolve("乙")

        self.assertNotEqual(first.output_name.casefold(), second.output_name.casefold())

    def test_numeric_prefixes_keep_identical_titles_apart(self):
        translator = FakeTextTranslator(result="cinta terlarang")
        folder_translator = FolderTitleTranslator(translator)

        first = folder_translator.resolve("4-禁忌之恋")
        second = folder_translator.resolve("143-不可以的爱")

        self.assertEqual(first.output_name, "4-Cinta Terlarang")
        self.assertEqual(second.output_name, "143-Cinta Terlarang")


if __name__ == "__main__":
    unittest.main()
