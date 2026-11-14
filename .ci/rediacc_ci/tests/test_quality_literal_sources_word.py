"""A registry value that is one plain lowercase word (the `releases` and `media` buckets) is a copy only where a bucket reference introduces it."""

from __future__ import annotations

import pathlib

from rediacc_ci import paths
from rediacc_ci.quality import literal_sources as ls
from rediacc_ci.well_known import CLAUDE_HAIKU_MODEL, MEDIA_BUCKET


def _scan(text: str) -> list[ls.Hit]:
    root = pathlib.Path(paths.repo_root())
    policy = ls.load_policy(root)
    entries = [ls.entry_for("WK_MEDIA_BUCKET", MEDIA_BUCKET)]
    return ls.Detectors(policy, entries).scan_line("x.py", 1, text)


def test_word_entry_kind() -> None:
    assert ls.entry_for("WK_X_BUCKET", MEDIA_BUCKET).kind == "word"
    assert ls.entry_for("WK_X", CLAUDE_HAIKU_MODEL).kind == "token"


def test_bucket_contexts_hit() -> None:
    b = MEDIA_BUCKET
    for line in (f"s3://{b}/videos/", f'BUCKET="{b}"', f"--bucket {b}", f'bucket: "{b}"'):
        assert [h.key for h in _scan(line)] == [b], line


def test_ordinary_uses_of_the_word_are_silent() -> None:
    b = MEDIA_BUCKET
    for line in (
        f'kind = "{b}"',
        f"import {b} from './{b}'",
        f"s3://{b}-old/x",
        f"{b}.rediacc.com/a",
    ):
        assert not [h for h in _scan(line) if h.detector == "word"], line
