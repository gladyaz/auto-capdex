from __future__ import annotations

import itertools
import logging
import re
import threading
from dataclasses import dataclass, replace
from typing import Any, Optional


# Characters Windows forbids in any file or folder name. macOS/Linux tolerate
# most of them, but the pipeline also runs on a Windows office PC, so output
# folder names are sanitized for the strictest target regardless of host OS.
WINDOWS_INVALID_CHARACTERS = '<>:"/\\|?*'

# Replacements are chosen so a translated title stays readable instead of
# losing words: ':' and '/' normally separate clauses, '"' has a safe ASCII
# equivalent, and the remaining characters carry no meaning worth keeping.
# Mapping '/' and '\\' to '-' is also what stops a translated title from
# silently creating accidental subdirectories under the output folder.
_INVALID_CHARACTER_REPLACEMENTS = {
    "<": "",
    ">": "",
    ":": " -",
    '"': "'",
    "/": "-",
    "\\": "-",
    "|": "-",
    "?": "",
    "*": "",
}

# Windows refuses these names (with or without an extension) for legacy DOS
# device reasons, case-insensitively.
WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)

# Keeps the full output path comfortably inside Windows' 260 character MAX_PATH
# once the output root, episode filename and "_subtitled.mp4" suffix are added.
MAX_FOLDER_NAME_LENGTH = 120

FALLBACK_FOLDER_NAME = "untitled"

# A source prefix such as "4-", "12-", "143-" or "114-" identifies the drama in
# the operator's catalogue, so it is carried across untranslated.
_NUMERIC_PREFIX_PATTERN = re.compile(r"^(\d+[-_.\s]+)(?=\S)")

# "（35集）", "(35集)", "（全35集）" and a trailing bare "35集" all mean the same
# thing: the drama has 35 episodes.
_EPISODE_COUNT_PATTERN = re.compile(
    r"[（(]\s*(?:全|共)?\s*(\d+)\s*集\s*[)）]|(?:^|\s)(?:全|共)?\s*(\d+)\s*集\s*$"
)

# Indonesian title case keeps conjunctions and prepositions lowercase unless
# they open the title, which is how streaming platforms render drama titles.
_LOWERCASE_TITLE_WORDS = frozenset(
    {
        "adalah",
        "agar",
        "akan",
        "atas",
        "atau",
        "bagi",
        "dalam",
        "dan",
        "dari",
        "demi",
        "dengan",
        "di",
        "hingga",
        "jika",
        "karena",
        "ke",
        "kepada",
        "maka",
        "oleh",
        "pada",
        "pun",
        "saat",
        "secara",
        "sebagai",
        "sejak",
        "serta",
        "tanpa",
        "tentang",
        "terhadap",
        "untuk",
        "yang",
    }
)

_WHITESPACE_PATTERN = re.compile(r"\s+")
_CONTROL_CHARACTERS = frozenset(chr(code) for code in range(32)) | {chr(127)}


@dataclass(frozen=True)
class FolderTitle:
    """Resolved output folder name for one source drama folder."""

    source_name: str
    output_name: str
    translated: bool
    error: Optional[str] = None


def split_numeric_prefix(name: str) -> tuple[str, str]:
    """Split "143-老公突然有了读心术" into ("143-", "老公突然有了读心术")."""
    match = _NUMERIC_PREFIX_PATTERN.match(name)
    if match is None:
        return "", name
    return match.group(1), name[match.end() :]


def extract_episode_count(name: str) -> tuple[str, str]:
    """Split a Chinese episode-count marker off a title.

    Returns the remaining title and an Indonesian episode suffix such as
    "(85 Episode)", or an empty string when the title has no episode count.
    The marker is removed before translation so the translator never has to
    guess at "集", and the count is re-attached afterwards.
    """
    match = _EPISODE_COUNT_PATTERN.search(name)
    if match is None:
        return name, ""

    count = match.group(1) or match.group(2)
    remainder = f"{name[: match.start()]} {name[match.end() :]}"
    return _WHITESPACE_PATTERN.sub(" ", remainder).strip(), f"({count} Episode)"


def to_indonesian_title_case(text: str) -> str:
    """Capitalize a translated title the way a streaming catalogue would."""
    words = text.split()
    titled: list[str] = []
    for index, word in enumerate(words):
        if word.isupper() and len(word) > 1:
            titled.append(word)
            continue
        if index > 0 and word.casefold() in _LOWERCASE_TITLE_WORDS:
            titled.append(word.casefold())
            continue
        titled.append("-".join(_capitalize(part) for part in word.split("-")))
    return " ".join(titled)


def replace_invalid_characters(name: str) -> str:
    """Swap Windows-illegal characters for safe equivalents.

    This is the character-level half of `sanitize_windows_folder_name`. It is
    applied to a translated title *before* title casing so that a replaced
    separator (``/`` becoming ``-``) still gets both of its words capitalized.
    """
    cleaned = "".join(
        _INVALID_CHARACTER_REPLACEMENTS.get(character, "")
        if character in _INVALID_CHARACTER_REPLACEMENTS or character in _CONTROL_CHARACTERS
        else character
        for character in name
    )
    return _WHITESPACE_PATTERN.sub(" ", cleaned).strip()


def sanitize_windows_folder_name(name: str) -> str:
    """Make `name` safe to use as a single folder name on Windows."""
    cleaned = replace_invalid_characters(name)
    # Windows silently drops trailing dots and spaces, which would make the
    # created folder name differ from the one recorded in the manifest.
    cleaned = cleaned.rstrip(" .")
    if len(cleaned) > MAX_FOLDER_NAME_LENGTH:
        cleaned = cleaned[:MAX_FOLDER_NAME_LENGTH].rstrip(" .")
    # A name built only from separators left behind by replaced characters is
    # not a usable folder name, so treat it the same as an empty one.
    if not any(character.isalnum() for character in cleaned):
        return FALLBACK_FOLDER_NAME
    if _device_stem(cleaned) in WINDOWS_RESERVED_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned


class FolderTitleTranslator:
    """Translates drama folder names once per folder and keeps them unique.

    The translator reuses the pipeline's existing translation provider, caches
    every result by source folder name so a folder is only ever translated
    once no matter how many episodes it holds, and falls back to the sanitized
    source folder name when translation fails.
    """

    def __init__(
        self,
        translator: Any | None,
        source_language: str = "zh-cn",
        target_language: str = "id",
        logger: logging.Logger | None = None,
    ):
        self.translator = translator
        self.source_language = source_language
        self.target_language = target_language
        self.logger = logger or logging.getLogger(__name__)
        self.translation_call_count = 0
        self._cache: dict[str, FolderTitle] = {}
        self._claimed_names: dict[str, str] = {}
        self._lock = threading.Lock()

    def resolve(self, source_name: str) -> FolderTitle:
        with self._lock:
            cached = self._cache.get(source_name)
            if cached is not None:
                return cached

            title = self._build_title(source_name)
            title = replace(
                title,
                output_name=self._claim_name(title.output_name, source_name),
            )
            self._cache[source_name] = title
            return title

    def cached(self, source_name: str) -> FolderTitle | None:
        with self._lock:
            return self._cache.get(source_name)

    def _build_title(self, source_name: str) -> FolderTitle:
        prefix, remainder = split_numeric_prefix(source_name)
        body, episode_suffix = extract_episode_count(remainder)

        if not body.strip():
            return FolderTitle(
                source_name=source_name,
                output_name=sanitize_windows_folder_name(source_name),
                translated=False,
            )

        try:
            translated_text = self._translate(body.strip())
        except Exception as error:  # noqa: BLE001 - any provider failure falls back
            self.logger.error(
                "Folder title translation failed for %r, falling back to the "
                "source folder name: %s",
                source_name,
                error,
            )
            return FolderTitle(
                source_name=source_name,
                output_name=sanitize_windows_folder_name(source_name),
                translated=False,
                error=str(error),
            )

        title_text = to_indonesian_title_case(replace_invalid_characters(translated_text))
        candidate = f"{prefix}{title_text}"
        if episode_suffix:
            candidate = f"{candidate} {episode_suffix}"

        return FolderTitle(
            source_name=source_name,
            output_name=sanitize_windows_folder_name(candidate),
            translated=True,
        )

    def _translate(self, text: str) -> str:
        translate_text = getattr(self.translator, "translate_text", None)
        if not callable(translate_text):
            raise TypeError(
                "translation provider does not support translate_text()"
            )

        self.translation_call_count += 1
        translated = translate_text(text, self.source_language, self.target_language)
        translated = str(translated or "").strip()
        if not translated:
            raise ValueError("translation provider returned an empty title")
        return translated

    def _claim_name(self, output_name: str, source_name: str) -> str:
        # Windows paths are case-insensitive, so two titles differing only by
        # case would still collide on the operator's PC.
        key = output_name.casefold()
        owner = self._claimed_names.get(key)
        if owner is None or owner == source_name:
            self._claimed_names[key] = source_name
            return output_name

        for counter in itertools.count(2):
            candidate = sanitize_windows_folder_name(f"{output_name}-{counter}")
            candidate_key = candidate.casefold()
            if candidate_key not in self._claimed_names:
                self._claimed_names[candidate_key] = source_name
                self.logger.warning(
                    "Translated folder name %r already used by %r, writing %r instead",
                    output_name,
                    owner,
                    candidate,
                )
                return candidate

        raise AssertionError("unreachable")


def _capitalize(word: str) -> str:
    for index, character in enumerate(word):
        if character.isalpha():
            return word[:index] + character.upper() + word[index + 1 :].lower()
    return word


def _device_stem(name: str) -> str:
    return name.split(".", 1)[0].strip().upper()


__all__ = [
    "FALLBACK_FOLDER_NAME",
    "FolderTitle",
    "FolderTitleTranslator",
    "MAX_FOLDER_NAME_LENGTH",
    "WINDOWS_INVALID_CHARACTERS",
    "WINDOWS_RESERVED_NAMES",
    "extract_episode_count",
    "replace_invalid_characters",
    "sanitize_windows_folder_name",
    "split_numeric_prefix",
    "to_indonesian_title_case",
]
