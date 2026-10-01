"""The `.ci` twin goldens (PLAN-retire-bash-oracles B3): well-formed, drift-controlled, and actually read.

WHAT A TWIN GOLDEN IS. `differential.twin_streams` answers a differential's bash side out of `.ci/rediacc_ci/tests/goldens/twins/<stem>.jsonl` instead of running the `.sh`, which is what lets the `.sh` be deleted. `regolden.py` writes them; the format is the hooks' (`.claude/rediacc_hooks/tests/goldenio.py`), loaded by path, so both trees have one reader and one writer.

THE FOUR CLAIMS HERE, each with a control that shows it can fail:

  1. DRIFT IS DECLARED. A golden HEAD already carries may not change without the moved record saying `intentional: <reason>` -- the same rule, and the same function (`goldenio.undeclared_drift`), as the hooks' `test_golden_drift.py`.
  2. THE HEADER NAMES ITS TWIN: a repo-relative `.sh` path, a 40-hex `twin_blob`, and a `source` of `bash` or `port`. A golden whose twin still exists must carry that file's CURRENT blob, or the freeze is stale and deleting the twin would discard behaviour the golden never saw.
  3. COMPARE MODE NEVER RUNS BASH. Proven by making `bash_streams` raise and still getting the recorded answer, which is the property the deletion relies on.
  4. A KEY THE GOLDEN LACKS FAILS, naming the verb. A missing answer is never read as "nothing to compare".
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.tests import differential as diff

ROOT = paths.repo_root()
GOLDENS = sorted(diff.GOLDEN_DIR.glob("*.jsonl"))
BLOB_RE = re.compile(r"^[0-9a-f]{40}$")


def _head_snapshot(path):
    rel = path.relative_to(ROOT).as_posix()
    proc = subprocess.run(
        ["git", "show", "HEAD:%s" % rel], cwd=str(ROOT), capture_output=True, check=False
    )
    if proc.returncode != 0:
        return None
    _header, silent, records = diff.goldenio.parse_golden_lines(
        proc.stdout.decode("utf-8", "surrogateescape").splitlines()
    )
    return silent, records


def test_the_goldens_are_seen() -> None:
    """ANTI-VACUITY: zero goldens would make every check below pass over nothing."""
    assert GOLDENS, (
        "no twin golden under %s; the checks below would compare nothing" % diff.GOLDEN_DIR
    )
    print("%d twin golden(s) under %s" % (len(GOLDENS), diff.GOLDEN_DIR.relative_to(ROOT)))


def test_golden_drift_is_always_intentional() -> None:
    offenders = {}
    compared = 0
    for path in GOLDENS:
        head = _head_snapshot(path)
        if head is None:
            continue
        compared += 1
        _header, new_silent, new_records = diff.goldenio.read_golden(path)
        bad = diff.goldenio.undeclared_drift(head[0], head[1], new_silent, new_records)
        if bad:
            offenders[path.name] = bad
    assert not offenders, (
        "these twin golden records changed since HEAD with no `intentional` reason: %s. "
        "regolden.py --source port --reason stamps a real change; a record that moved any other "
        "way is the silent re-record this control exists to refuse."
        % json.dumps(offenders, sort_keys=True)
    )
    print("%d golden(s) compared against HEAD, %d new" % (compared, len(GOLDENS) - compared))


def test_the_drift_control_can_fail() -> None:
    """On a REAL golden, not a toy: an undeclared edit of one record is caught, the same edit with a reason is not."""
    path = GOLDENS[0]
    _header, silent, records = diff.goldenio.read_golden(path)
    assert records, "%s has no non-silent record to mutate" % path.name
    key = min(records)
    moved = {k: dict(v) for k, v in records.items()}
    moved[key].pop("intentional", None)
    moved[key]["err"] = moved[key].get("err", "") + "planted\n"
    assert diff.goldenio.undeclared_drift(silent, records, silent, moved) == [key]
    moved[key]["intentional"] = "a Rule-T fix"
    assert diff.goldenio.undeclared_drift(silent, records, silent, moved) == []


@pytest.mark.parametrize("path", GOLDENS, ids=[p.stem for p in GOLDENS])
def test_the_header_names_its_twin(path) -> None:
    header, silent, records = diff.goldenio.read_golden(path)
    assert header is not None, "%s has no header line" % path.name
    twin = header.get("twin", "")
    assert twin.endswith(".sh"), "%s: twin %r" % (path.name, twin)
    assert not twin.startswith("/"), "%s: twin %r is absolute" % (path.name, twin)
    assert diff.golden_stem(twin) == path.stem, "%s is filed under the wrong name for %s" % (
        path.name,
        twin,
    )
    assert BLOB_RE.match(header.get("twin_blob", "")), "%s: twin_blob %r" % (
        path.name,
        header.get("twin_blob"),
    )
    assert header.get("source") in ("bash", "port"), "%s: source %r" % (
        path.name,
        header.get("source"),
    )
    assert header.get("case_count") == len(silent) + len(records), (
        "%s: header says %s case(s), the file holds %d"
        % (path.name, header.get("case_count"), len(silent) + len(records))
    )
    live = ROOT / twin
    if live.is_file():
        assert diff.blob_sha(twin) == header["twin_blob"], (
            "%s is STALE: %s changed after it was frozen (blob %s, golden %s). Re-freeze with "
            '`%s %s --source bash --reason "<why>"` before the twin is deleted.'
            % (path.name, twin, diff.blob_sha(twin), header["twin_blob"], diff.REGOLDEN_VERB, twin)
        )


def test_compare_mode_never_runs_bash(monkeypatch) -> None:
    """The deletion's precondition. `bash_streams` is made to raise; the golden still answers."""
    path = GOLDENS[0]
    header, silent, records = diff.goldenio.read_golden(path)
    key = min(records or silent)

    def refuse(*_a, **_k):
        raise AssertionError("compare mode ran bash")

    monkeypatch.setattr(diff, "bash_streams", refuse)
    monkeypatch.delenv(diff.REGOLDEN_ENV, raising=False)
    rc, _out, _err = diff.golden_answer(header["twin"], key)
    expected = 0 if key in silent else int(records[key]["rc"])
    assert rc == expected


def test_a_missing_key_fails_and_names_the_verb(monkeypatch) -> None:
    monkeypatch.delenv(diff.REGOLDEN_ENV, raising=False)
    header, _silent, _records = diff.goldenio.read_golden(GOLDENS[0])
    with pytest.raises(AssertionError, match="--source port"):
        diff.twin_streams(header["twin"], "bash %s --a-case-nobody-recorded" % header["twin"])


def test_fold_and_unfold_round_trip(tmp_path) -> None:
    """A golden recorded under one checkout, scratch dir and HOME reads back with THIS run's paths: fold then unfold is the identity, and fold leaves no machine path behind."""
    text = "%s/x %s/.ci/y %s %s/z" % (
        tmp_path,
        ROOT,
        diff.BASE_ENV["PATH"],
        diff.BASE_ENV["TMPDIR"],
    )
    folded = diff.fold(text, (str(tmp_path),))
    assert str(ROOT) not in folded, folded
    assert str(tmp_path) not in folded, folded
    assert diff.unfold(folded, (str(tmp_path),)) == text


def test_an_unknown_mode_is_refused(monkeypatch) -> None:
    monkeypatch.setenv(diff.REGOLDEN_ENV, "both")
    with pytest.raises(RuntimeError, match="expected 'bash' or 'port'"):
        diff.regolden_mode()
