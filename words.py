"""Word list loading, selection and scrambling.

Words live in `static/words/words_<length>.txt`, one word per line, grouped by
length so rounds can be built from a deliberate mix of easy and hard words.
"""
import os
import random
import re

from config import Config

# Share of a round drawn from each word length. Values are weights, not
# guarantees: a round is filled proportionally and any shortfall (a length with
# too few words, or rounding) is topped up from the remaining pool.
LENGTH_WEIGHTS = {3: 0.10, 4: 0.25, 5: 0.30, 6: 0.20, 7: 0.10, 8: 0.05}

_FILENAME_RE = re.compile(r"^words_(\d+)\.txt$")

_cache = None


def load_words(words_dir=None, force=False):
    """Return {length: [word, ...]}, read from disk once and then cached."""
    global _cache
    if _cache is not None and not force:
        return _cache

    directory = words_dir or Config.WORDS_DIR
    by_length = {}
    for fname in sorted(os.listdir(directory)):
        match = _FILENAME_RE.match(fname)
        if not match:
            continue
        with open(os.path.join(directory, fname), encoding="utf-8") as handle:
            words = [w.strip().lower() for w in handle if w.strip()]
        if words:
            by_length[int(match.group(1))] = words

    if not by_length:
        raise RuntimeError("No word lists found in " + directory)

    _cache = by_length
    return _cache


def pick_words(count, by_length=None):
    """Pick `count` distinct words spread across lengths by LENGTH_WEIGHTS.

    Lengths are allocated proportionally rather than one-per-bucket, so a small
    round is not forced to include every length.
    """
    if count <= 0:
        return []

    by_length = by_length or load_words()
    selected = []
    used = set()

    # Largest-remainder allocation so the counts sum to exactly `count`.
    quotas = {}
    remainders = []
    for length, weight in LENGTH_WEIGHTS.items():
        exact = count * weight
        quotas[length] = int(exact)
        remainders.append((exact - int(exact), length))
    for _, length in sorted(remainders, reverse=True):
        if sum(quotas.values()) >= count:
            break
        quotas[length] += 1

    for length, quota in quotas.items():
        pool = by_length.get(length, [])
        if not pool or quota <= 0:
            continue
        for word in random.sample(pool, min(quota, len(pool))):
            selected.append(word)
            used.add(word)

    # Top up if any length was short of its quota.
    if len(selected) < count:
        leftovers = [w for pool in by_length.values() for w in pool if w not in used]
        random.shuffle(leftovers)
        selected.extend(leftovers[: count - len(selected)])

    random.shuffle(selected)
    return selected[:count]


def scramble(word):
    """Shuffle a word's letters, never returning the original spelling.

    Words whose letters can only form one arrangement (for example "aaa") are
    returned unchanged.
    """
    letters = list(word)
    if len(set(letters)) < 2:
        return word
    shuffled = word
    while shuffled == word:
        random.shuffle(letters)
        shuffled = "".join(letters)
    return shuffled
