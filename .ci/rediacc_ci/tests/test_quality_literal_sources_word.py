"""A registry value that is one plain lowercase word (the `releases` and `media` buckets) is a copy only where a bucket reference introduces it."""

from __future__ import annotations

import pathlib

from rediacc_ci import paths
from rediacc_ci.quality import literal_sources as ls


def _scan(text: str) -> list[ls.Hit]:
    root = pathlib.Path(paths.repo_root())
    policy = ls.load_policy(root)
    entries = [ls.entry_for("WK_MEDIA_BUCKET", "media")]
    return ls.Detectors(policy, entries).scan_line("x.py", 1, text)


def test_word_entry_kind() -> None:
    assert ls.entry_for("WK_X_BUCKET", "media").kind == "word"
    assert ls.entry_for("WK_X", "claude-haiku-5-5").kind == "token"


def test_bucket_contexts_hit() -> None:
    for line in ('s3://media/videos/', 'BUCKET="media"', "--bucket media", 'bucket: "media"'):
        assert [h.key for h in _scan(line)] == ["media"], line


def test_ordinary_uses_of_the_word_are_silent() -> None:
    for line in ('kind = "media"', "import media from './media'", "s3://media-old/x", "media.rediacc.com/a"):
        assert not [h for h in _scan(line) if h.detector == "word"], line
