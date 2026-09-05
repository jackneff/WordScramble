"""Custom vocabulary lists.

Any `.txt` file dropped in the lists directory (default `static/words/lists/`)
becomes a playable list: one word per line, any mix of lengths, no naming
convention to remember. The filename becomes the display name, so
`week-12.txt` shows up as "Week 12".

Unlike the built-in word pool, the directory is read on every request rather
than cached, so adding a list during the school week doesn't need a restart.
"""
import os
import re

from config import Config

# Filenames become slugs, so keep them to characters that are safe in a URL.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

# A word must be spellable with the tile UI: letters only, and long enough to
# scramble into something that isn't the answer.
_WORD_RE = re.compile(r"^[a-z]{3,12}$")

MAX_WORDS_PER_LIST = 500


def _display_name(slug):
    """`week-12` -> `Week 12`, `sight_words` -> `Sight Words`."""
    return slug.replace("-", " ").replace("_", " ").title()


def _read(path):
    """Read a list file, keeping only words the game can actually present."""
    words, seen = [], set()
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            word = line.strip().lower()
            if _WORD_RE.match(word) and word not in seen:
                seen.add(word)
                words.append(word)
            if len(words) >= MAX_WORDS_PER_LIST:
                break
    return words


def available_lists(lists_dir=None):
    """Every usable list, alphabetical by name.

    Files that are unreadable, empty, or badly named are skipped rather than
    raising - a malformed file shouldn't take the home page down.
    """
    directory = lists_dir or Config.LISTS_DIR
    if not os.path.isdir(directory):
        return []

    found = []
    for fname in sorted(os.listdir(directory)):
        stem, ext = os.path.splitext(fname)
        slug = stem.lower()
        if ext.lower() != ".txt" or not _SLUG_RE.match(slug):
            continue

        path = os.path.join(directory, fname)
        if not os.path.isfile(path):
            continue

        try:
            words = _read(path)
        except OSError:
            continue

        if words:
            found.append({"slug": slug, "name": _display_name(slug), "count": len(words)})

    return sorted(found, key=lambda entry: entry["name"])


def get_list_words(slug, lists_dir=None):
    """Words in one list, or None if there is no such list.

    The slug is matched against the enumerated directory rather than being
    joined onto a path, so a crafted value cannot escape the lists directory.
    """
    if not slug or not _SLUG_RE.match(str(slug).lower()):
        return None

    slug = str(slug).lower()
    directory = lists_dir or Config.LISTS_DIR
    if not any(entry["slug"] == slug for entry in available_lists(directory)):
        return None

    try:
        return _read(os.path.join(directory, slug + ".txt"))
    except OSError:
        return None


def get_list_name(slug, lists_dir=None):
    """Display name for a slug, or None if the list is gone."""
    for entry in available_lists(lists_dir):
        if entry["slug"] == slug:
            return entry["name"]
    return None
