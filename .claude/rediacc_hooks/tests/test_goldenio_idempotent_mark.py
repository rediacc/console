"""A second regolden over an unchanged port is a byte-identical no-op (#84358ce1).

`goldenio.diff_and_mark` stamps `intentional: <reason>` on a record whose answer moved. Before the fix, running the mark step a second time compared each such record against the golden the FIRST run had just written, found it equal, and rewrote it without the marker; a record that had flipped to silence moved into `_silent`, where no marker can live. The drift control (`test_golden_drift.py`) then saw an undeclared change against HEAD.
"""

from rediacc_hooks.tests import goldenio

BLOCK = ("2", "", "BLOCKED\n")
SILENT = ("0", "", "")

# The golden as HEAD had it: `a` silent, `b` refusing, `c` refusing, `d` silent.
OLD_ANSWERS = {"a": SILENT, "b": BLOCK, "c": BLOCK, "d": SILENT}
# The port after an intentional change: `a` now refuses, `b` now admits; `c`/`d` untouched, `e` new.
NEW_ANSWERS = {"a": BLOCK, "b": SILENT, "c": BLOCK, "d": SILENT, "e": ("0", "note\n", "")}
HEADER = {"source": "port"}


def _prefix_diff_and_mark(answers, old_silent, old_records, reason):
    """`diff_and_mark` exactly as it stood before #84358ce1, kept as the control."""
    silent, records, changed = set(), {}, []
    for key, value in answers.items():
        rc, out, err = value
        if key in old_silent:
            old = ("0", "", "")
        elif key in old_records:
            row = old_records[key]
            old = (
                row["rc"],
                goldenio.decode_field(row.get("out", "")),
                goldenio.decode_field(row.get("err", "")),
            )
        else:
            old = None
        is_changed = old is not None and old != value
        if goldenio.is_silent(rc, out, err) and not is_changed:
            silent.add(key)
            continue
        row = {"rc": rc, "out": goldenio.encode_field(out), "err": goldenio.encode_field(err)}
        if is_changed:
            row["intentional"] = reason
            changed.append(key)
        records[key] = row
    return silent, records, changed


def _regolden(path, answers, mark, reason):
    """One regolden.py `_record_guard` pass: read the file, mark, write it back."""
    _header, old_silent, old_records = goldenio.read_golden(path)
    silent, records, changed = mark(answers, old_silent, old_records, reason)
    goldenio.write_golden(path, HEADER, silent, records)
    return changed


def _head(path):
    silent, records, _ = _prefix_diff_and_mark(OLD_ANSWERS, set(), {}, "freeze")
    goldenio.write_golden(path, HEADER, silent, records)


def test_a_second_mark_is_byte_identical(tmp_path):
    path = tmp_path / "g.jsonl"
    _head(path)
    first = _regolden(path, NEW_ANSWERS, goldenio.diff_and_mark, "flip a and b")
    assert sorted(first) == ["a", "b"]
    once = path.read_bytes()
    _header, silent, records = goldenio.read_golden(path)
    assert records["a"]["intentional"] == "flip a and b"
    assert records["b"]["intentional"] == "flip a and b"
    assert "b" not in silent
    assert "intentional" not in records["c"]
    assert "intentional" not in records["e"]
    assert {"d"} == silent

    second = _regolden(path, NEW_ANSWERS, goldenio.diff_and_mark, "a different reason")
    assert second == []
    assert path.read_bytes() == once


def test_a_later_real_change_restamps_the_new_reason(tmp_path):
    """Keeping a marker never masks a new move: a record that moves again takes the NEW reason."""
    path = tmp_path / "g.jsonl"
    _head(path)
    _regolden(path, NEW_ANSWERS, goldenio.diff_and_mark, "first")
    moved = dict(NEW_ANSWERS, a=("2", "", "OTHER\n"))
    assert _regolden(path, moved, goldenio.diff_and_mark, "second") == ["a"]
    _header, _silent, records = goldenio.read_golden(path)
    assert records["a"]["intentional"] == "second"
    assert records["b"]["intentional"] == "first"


def test_control_the_pre_fix_mark_drops_the_marker(tmp_path):
    """CONTROL: the same two runs through the pre-fix code lose both markers, so the test above can fail."""
    path = tmp_path / "g.jsonl"
    _head(path)
    _regolden(path, NEW_ANSWERS, _prefix_diff_and_mark, "flip a and b")
    once = path.read_bytes()
    _regolden(path, NEW_ANSWERS, _prefix_diff_and_mark, "flip a and b")
    assert path.read_bytes() != once
    _header, silent, records = goldenio.read_golden(path)
    assert "intentional" not in records["a"]
    assert "b" in silent
