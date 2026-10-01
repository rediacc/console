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


# --------------------------------------------------------------------------- Host variance (differential.host_fold / host_unfold) ---------------------------------------------------------------------------
#
# Each rule has the same two controls: (a) the variant a second host prints is ACCEPTED after the golden is unfolded there, and (b) a real difference on the same line is still REFUSED. The recorder and the comparer are spelled out as data, so neither control depends on who runs the suite.

RECORDER = ("developer", "developer")
RUNNER = ("runner", "runner")
BASH_53 = ("arithmetic syntax error", "integer expected")
BASH_52 = ("syntax error", "integer expression expected")
LS_HERE = "-rw-r--r-- 1 developer developer 32 <MTIME> renet-linux-amd64\n"
LS_THERE = "-rw-r--r-- 1 runner runner 32 <MTIME> renet-linux-amd64\n"


def _carry(text: str, recorder=RECORDER, comparer=RUNNER, to=BASH_52) -> str:
    """A golden recorded on one host, read back on another: what the comparer's call site sees."""
    return diff.host_unfold(diff.host_fold(text, recorder), comparer, to)


def test_ls_owner_and_group_fold_to_the_comparing_host() -> None:
    assert diff.host_fold(LS_HERE, RECORDER) == (
        "-rw-r--r-- 1 <USER> <GROUP> 32 <MTIME> renet-linux-amd64\n"
    )
    assert _carry(LS_HERE) == LS_THERE
    # A container user with no passwd entry: `ls` prints the bare ids, and so does the unfold.
    assert _carry(LS_HERE, comparer=("1001", "1001")) == LS_THERE.replace("runner", "1001")


def test_ls_fold_still_refuses_a_real_difference() -> None:
    # A different size or file name on the same line is compared verbatim.
    assert _carry(LS_HERE) != LS_THERE.replace(" 32 ", " 33 ")
    assert _carry(LS_HERE) != LS_THERE.replace("amd64", "arm64")
    # A file owned by someone OTHER than the recorder is not the recorder's identity: it stays literal, so a port whose file lands owned by the runner fails against a golden that said root.
    owned_by_root = LS_HERE.replace("developer developer", "root root")
    assert diff.host_fold(owned_by_root, RECORDER) == owned_by_root
    assert _carry(owned_by_root) != LS_THERE
    # Outside the two ls columns the user name is plain text, never folded.
    prose = "developer developer 32 renet\n"
    assert diff.host_fold(prose, RECORDER) == prose


def test_bash_arithmetic_clause_follows_the_comparing_bash() -> None:
    line = '<shell>: [[: 1 2: arithmetic syntax error in expression (error token is "2")\n'
    assert _carry(line) == line.replace("arithmetic syntax error", "syntax error")
    assert _carry(line, to=BASH_53) == line
    for continuation in (
        ': operand expected (error token is "+ ")',
        ': invalid arithmetic operator (error token is ";ls")',
    ):
        shaped = "((: x: arithmetic syntax error%s\n" % continuation
        assert _carry(shaped) == shaped.replace("arithmetic syntax error", "syntax error")


def test_bash_arithmetic_fold_still_refuses_a_real_difference() -> None:
    line = '[[: 1 2: arithmetic syntax error in expression (error token is "2")\n'
    assert _carry(line) != line.replace("arithmetic syntax error", "syntax error").replace(
        '"2"', '"3"'
    )
    # A 5.3 spelling from a port that HARDCODES it is refused on a 5.2 host: the golden now says what this bash says.
    assert _carry(line) != line
    # The parser's own complaint is not the arithmetic clause and is not folded.
    parse = "bash: -c: line 1: syntax error near unexpected token `)'\n"
    assert diff.host_fold(parse, RECORDER) == parse


def test_bash_integer_phrase_follows_the_comparing_bash() -> None:
    line = "[: abc: integer expected\n"
    assert _carry(line) == "[: abc: integer expression expected\n"
    assert _carry(line) != "[: abd: integer expression expected\n"
    assert diff.host_fold("an integer expected here\n", RECORDER) == "an integer expected here\n"


def test_golden_answer_unfolds_for_the_host_reading_it(monkeypatch) -> None:
    """End to end through the real reader and a real golden: the recorder's identity is a token on disk, and the reader puts THIS host's back. Anti-vacuity: the corpus must actually carry a token, or the rule is exercised by nothing real."""
    from rediacc_ci.core import bash_dialect  # noqa: PLC0415

    carried = [p for p in GOLDENS if diff.USER_MARK in p.read_text(encoding="utf-8")]
    assert carried, "no twin golden carries %s; the ls rule guards nothing" % diff.USER_MARK
    path = carried[0]
    header, _silent, records = diff.goldenio.read_golden(path)
    key = next(k for k, v in sorted(records.items()) if diff.USER_MARK in v.get("out", ""))
    monkeypatch.delenv(diff.REGOLDEN_ENV, raising=False)
    monkeypatch.setattr(diff, "host_identity", lambda: ("runner", "runner"))
    monkeypatch.setattr(bash_dialect, "arith_syntax_error", lambda _env=None: "syntax error")
    _rc, out, _err = diff.golden_answer(header["twin"], key)
    assert " runner runner " in out
    assert diff.USER_MARK not in out
    assert diff.GROUP_MARK not in out


@pytest.mark.parametrize("path", GOLDENS, ids=[p.stem for p in GOLDENS])
def test_no_golden_carries_a_recorders_ls_identity(path) -> None:
    """Every `ls -l` line in a golden names its owner and group as tokens. A literal one is a golden written before the rule (or by hand), and fails on every host whose user differs from the recorder's."""
    _header, _silent, records = diff.goldenio.read_golden(path)
    literal: list[str] = []
    for key, row in sorted(records.items()):
        for field in ("out", "err"):
            text = diff.goldenio.decode_field(row.get(field, ""))
            literal.extend(
                "%s %s: %s %s" % (key, field, m["owner"], m["group"])
                for m in diff.LS_LONG_RE.finditer(text)
                if (m["owner"], m["group"]) != (diff.USER_MARK, diff.GROUP_MARK)
            )
    assert not literal, "%s carries literal ls owners: %s" % (path.name, literal[:5])


# The `-c` traceback of `test.test-install-sh-config`, as each interpreter renders it (measured: 3.14.4 here, 3.12.3 in ubuntu:24.04, the runner's image).
TB_314 = (
    "Traceback (most recent call last):\n"
    '  File "<string>", line 1, in <module>\n'
    "    import json,sys; print(json.load(open(sys.argv[1]))['account']['updateChannel'])\n"
    "                           ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^\n"
    "KeyError: 'updateChannel'\n"
)
TB_312 = (
    "Traceback (most recent call last):\n"
    '  File "<string>", line 1, in <module>\n'
    "KeyError: 'updateChannel'\n"
)


def test_python_traceback_mask_absorbs_the_interpreter_rendering() -> None:
    assert diff.mask_python_traceback(TB_314) == diff.mask_python_traceback(TB_312) == TB_312
    # Text around the traceback is untouched, and a ruler-shaped line OUTSIDE one is kept.
    around = "before\n    indented prose\n" + TB_314 + "  ~~~^^\nafter\n"
    assert (
        diff.mask_python_traceback(around)
        == "before\n    indented prose\n" + TB_312 + "  ~~~^^\nafter\n"
    )


def test_python_traceback_mask_still_refuses_a_real_difference() -> None:
    masked = diff.mask_python_traceback(TB_314)
    assert masked != diff.mask_python_traceback(TB_312.replace("updateChannel", "accountServer"))
    assert masked != diff.mask_python_traceback(TB_312.replace("KeyError", "TypeError"))
    assert masked != diff.mask_python_traceback(TB_312.replace("line 1", "line 2"))
    # A real file's frame keeps its source echo: only a `-c` snippet's is version-dependent.
    file_frame = TB_312.replace(
        '  File "<string>", line 1, in <module>\n',
        '  File "/x/check.py", line 9, in main\n    value = cfg["updateChannel"]\n',
    )
    assert "value = cfg" in diff.mask_python_traceback(file_frame)
    assert diff.mask_python_traceback(file_frame) != diff.mask_python_traceback(
        file_frame.replace("value = cfg", "value = conf")
    )
