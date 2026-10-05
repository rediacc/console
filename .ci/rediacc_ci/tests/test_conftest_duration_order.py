"""PF18: the duration-ordered collection's fallbacks (the happy path is in test_xdist_groups.py)."""

import json

from rediacc_ci import xdist_groups


def _write(tmp_path, text):
    path = tmp_path / "lane-durations.json"
    path.write_text(text, encoding="utf-8")
    return path


def test_corrupt_source_falls_back_to_no_durations(tmp_path) -> None:
    for text in ("{not json", "[]", "null", json.dumps({"units": "x"}), ""):
        assert xdist_groups.unit_durations(_write(tmp_path, text)) == ({}, 0.0), text


def test_non_numeric_entries_are_skipped(tmp_path) -> None:
    doc = {"units": {"pytest:a.py": "slow", "pytest:b.py": 7}}
    durations, _ = xdist_groups.unit_durations(_write(tmp_path, json.dumps(doc)))
    assert durations == {"b.py": 7.0}


def test_no_durations_keeps_collection_order() -> None:
    files = ["c.py", "a.py", "b.py", "a.py"]
    assert xdist_groups.order_longest_first(files, {}, 0.0) == [0, 1, 2, 3]


def test_unknown_file_is_priced_at_the_default_between_known_ones() -> None:
    files = ["short.py", "unknown.py", "long.py"]
    order = xdist_groups.order_longest_first(files, {"short.py": 1.0, "long.py": 50.0}, 10.0)
    assert [files[i] for i in order] == ["long.py", "unknown.py", "short.py"]
