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

# A pasted list might be one word per line, comma-separated, or just spaced
# out, so treat all three as separators.
_SEPARATORS = re.compile(r"[\s,;]+")

MAX_WORDS_PER_LIST = 500
MAX_SLUG_LENGTH = 40


class ListError(Exception):
    """A list could not be saved; the message is safe to show a parent."""


def _display_name(slug):
    """`week-12` -> `Week 12`, `sight_words` -> `Sight Words`."""
    return slug.replace("-", " ").replace("_", " ").title()


def slugify(name):
    """Turn a parent's list name into a safe filename stem.

    Returns None when nothing usable is left, so the caller can complain
    rather than writing a file with a surprising name.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    slug = slug[:MAX_SLUG_LENGTH].strip("-")
    return slug if slug and _SLUG_RE.match(slug) else None


def parse_words(text):
    """Extract usable words from pasted or uploaded text.

    Returns (words, skipped_count). Lines beginning with `#` are treated as
    comments; everything else is split on whitespace, commas and semicolons so
    a list copied out of an email works as-is.
    """
    words, seen, skipped = [], set(), 0

    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        for token in _SEPARATORS.split(line.lower()):
            if not token:
                continue
            if not _WORD_RE.match(token):
                skipped += 1
                continue
            if token in seen:
                continue
            if len(words) >= MAX_WORDS_PER_LIST:
                skipped += 1
                continue
            seen.add(token)
            words.append(token)

    return words, skipped


def _read(path):
    """Read a list file, keeping only words the game can actually present."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        words, _ = parse_words(handle.read())
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


def list_exists(slug, lists_dir=None):
    return any(entry["slug"] == slug for entry in available_lists(lists_dir))


def save_list(name, text, lists_dir=None):
    """Create or replace a list from pasted or uploaded text.

    The filename is derived from the parent's chosen name, never from an
    uploaded filename, so nothing a browser sends decides where we write.
    Raises ListError with a message meant for the screen.
    """
    slug = slugify(name)
    if not slug:
        raise ListError("Give the list a name using letters or numbers.")

    words, skipped = parse_words(text)
    if not words:
        raise ListError(
            "No usable words found. Words need to be 3-12 letters, "
            "one per line or separated by commas."
        )

    directory = lists_dir or Config.LISTS_DIR
    os.makedirs(directory, exist_ok=True)

    replaced = list_exists(slug, directory)
    path = os.path.join(directory, slug + ".txt")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(words) + "\n")

    return {
        "slug": slug,
        "name": _display_name(slug),
        "count": len(words),
        "skipped": skipped,
        "replaced": replaced,
    }


def delete_list(slug, lists_dir=None):
    """Delete a list. Returns True if a file was removed.

    Like get_list_words, the slug is matched against the enumerated directory
    rather than joined onto a path.
    """
    if not slug or not _SLUG_RE.match(str(slug).lower()):
        return False

    slug = str(slug).lower()
    directory = lists_dir or Config.LISTS_DIR
    if not list_exists(slug, directory):
        return False

    try:
        os.remove(os.path.join(directory, slug + ".txt"))
    except OSError:
        return False
    return True
