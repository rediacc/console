"""`rediacc_ci.core.blocker_validator` against the live `blocker-validator.sh`.

THE TWIN IS LIVE HERE, NOT FROZEN. `.ci/scripts/lib/blocker-validator.sh` is still sourced by eight real call sites (listed in the port's docstring), so running the real file is strictly better than a frozen copy: a copy could agree
with the port while both had drifted away from what those gates execute.

THE BASH DRIVERS ARE STRINGS IN THIS FILE and not scripts under `.ci/`. Ruling 7 freezes the tracked `.sh` count, and a driver is exactly the kind of file that gets added without anyone deciding to. It is also the honest place for it: the driver is part of the TEST, not part of the tree under test.

WHAT IS COMPARED AND WHAT IS NOT.
  * Byte for byte, streams separate, exit code included: every SINGLE-failure
    and every clean case.
  * As a sorted multiset: the MULTI-failure cases. The twin iterates
    `"${!_blocker_ref[@]}"`, a bash hash order, and this port iterates a dict's
    insertion order. Neither is sorted and neither is part of the contract (see
    behaviour 4 in the port's docstring), so comparing order here would pin an
    accident.

TWO DIVERGENCES ARE ASSERTED AS DIVERGENCES rather than smoothed over, because a test that expected them to match would be a test nobody could make pass: `test_the_twin_leaks_a_python_traceback_and_the_port_cannot` and the exit-code wording it carries. Both are described at the assertions.

THE PLANTED DEFECTS ARE REAL AND THEY RUN ON A COPY.
`test_a_planted_defect_in_the_port_is_caught` loads a MUTATED copy of `blocker_validator.py` out of a tmpdir under a different module name and requires the comparison to go red, then re-asserts the on-disk sha256 of the real module. Nothing under `.ci/` is ever written by this file.
"""

import hashlib
import importlib.util
import pathlib
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.core import allowlist
from rediacc_ci.core import blocker_validator as bv
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/lib/blocker-validator.sh"
PORT = ".ci/rediacc_ci/core/blocker_validator.py"

# The two drivers. Both take a list path and an optional comment character, both render the two tables the same way, and both exit with the function's rc.
#
# `printf '%s\n' "${!A[@]}" | sort` and NOT `${!A[@]}` in file order: the bash
# table has no order worth comparing, so both sides sort before printing and the
# comparison is about CONTENT. LC_ALL=C is pinned by `differential.BASE_ENV`, so
# the two sorts agree byte for byte.
#
# AND `while IFS= read -r k` RATHER THAN `for k in $(...)`, which is not style.
# The corpus below deliberately contains an entry token of `*`, the twin stores it correctly, and an unquoted command substitution in a `for` header then PATHNAME-EXPANDS it against the driver's cwd: the first cut of this driver exited 127 with `A[$k]: unbound variable` on that one case, which reads as a defect in the library and was a defect in the harness.
#
# `[[ -n "$k" ]] || continue` is the second harness-only guard, for the opposite
# end: `printf '%s\n' "${!A[@]}"` on an EMPTY table prints one blank line, and
# `${A[]}` is `bad array subscript` and another 127. No real entry token can be
# empty, because `allowlist.parse_text` drops a zero-length token, so the guard discards nothing the corpus can produce.
BASH_PAIRS = (
    """
set -uo pipefail
source %s
declare -A A B
parse_blockered_list "$1" A B "${2:-#}"
rc=$?
while IFS= read -r k; do [[ -n "$k" ]] || continue; printf 'allowed\\t%%s\\t%%s\\n' "$k" "${A[$k]}"; done < <(printf '%%s\\n' "${!A[@]}" | sort)
while IFS= read -r k; do [[ -n "$k" ]] || continue; printf 'blocker\\t%%s\\t%%s\\n' "$k" "${B[$k]}"; done < <(printf '%%s\\n' "${!B[@]}" | sort)
exit $rc
"""
    % TWIN
)

BASH_VERIFY = (
    """
set -uo pipefail
source %s
declare -A A B
parse_blockered_list "$1" A B "${2:-#}"
verify_all_blockers "$1" B
exit $?
"""
    % TWIN
)

BASH_REASON = (
    """
set -uo pipefail
source %s
validate_blocker_quality "$1" "$2" "$3"
exit $?
"""
    % TWIN
)

BASH_REPLAY = (
    """
set -uo pipefail
source %s
_blocker_emit "$(cat "$1")"
exit $?
"""
    % TWIN
)

PY = "PYTHONPATH=.ci python3 -m rediacc_ci.core.blocker_validator"

GOOD = "upstream pins plist through xmldom 0.8.x; build time only, needs a major migration"


def _sh(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


# --------------------------------------------------------------------------- The corpus ---------------------------------------------------------------------------

# (id, comment_char, text). Every list a real gate could hand either reader.
LISTS = [
    ("clean-grouped", "#", "# BLOCKER: %s\nA-1\nA-2\n" % GOOD),
    (
        "blank-line-resets-the-group",
        "#",
        "# BLOCKER: %s\nA-1\n\nA-2\n" % GOOD,
    ),
    ("inline-blocker", "#", "A-1  # BLOCKER: %s\n" % GOOD),
    ("plain-comment-preserves", "#", "# BLOCKER: %s\n# a note\nA-1\n" % GOOD),
    ("missing-reason", "#", "A-1\n"),
    ("low-effort-exact", "#", "# BLOCKER: tbd\nA-1\n"),
    ("low-effort-substring", "#", "# BLOCKER: not needed by this change, honestly\nA-1\n"),
    ("too-short", "#", "# BLOCKER: pinned\nA-1\n"),
    ("empty-file", "#", ""),
    ("comments-only", "#", "# nothing here\n"),
    ("slash-comment-char", "//", "// BLOCKER: %s\nA-1\n" % GOOD),
    # The `#` in a `//` list is DATA, not a comment. A reader that hard-coded the comment character parses this as one entry named `A` and no reason.
    ("slash-with-hash-in-entry", "//", "// BLOCKER: %s\nA#1\n" % GOOD),
    # Shell-hostile entry tokens. Every one of these crosses a `read`, an associative-array subscript and a `printf` on the bash side.
    ("hostile-entry-glob", "#", "# BLOCKER: %s\n*\n" % GOOD),
    ("hostile-entry-at", "#", "# BLOCKER: %s\n@\n" % GOOD),
    ("hostile-entry-quote", "#", "# BLOCKER: %s\nit's-a-pkg\n" % GOOD),
    ("hostile-entry-dollar", "#", "# BLOCKER: %s\n$HOME\n" % GOOD),
    # A reason with an interior tab. The twin transports rows as `entry<TAB>reason`
    # and reads them back with `IFS=$'\t' read -r key value`; TAB is IFS
    # WHITESPACE in bash, so this is the shape that would collapse if the reason could ever begin or end with one. It cannot: `parse_text` strips.
    ("reason-with-interior-tab", "#", "# BLOCKER: %s\tand\tmore words here\nA-1\n" % GOOD),
    ("unicode-reason", "#", "# BLOCKER: %s (éèü 中文)\nA-1\n" % GOOD),
    ("trailing-whitespace-entry", "#", "# BLOCKER: %s\nA-1   \n" % GOOD),
    ("crlf", "#", "# BLOCKER: %s\r\nA-1\r\n" % GOOD),
    (
        "duplicate-entry-last-wins",
        "#",
        "# BLOCKER: %s\nA-1\n\n# BLOCKER: %s two\nA-1\n" % (GOOD, GOOD),
    ),
]

MULTI_FAILURE = [
    ("two-bad", "#", "A-1\n\n# BLOCKER: tbd\nA-2\n"),
    ("three-bad", "#", "A-1\n\n# BLOCKER: wip\nA-2\n\n# BLOCKER: short\nA-3\n"),
]


@pytest.fixture
def listfile(tmp_path):
    def make(text: str, name: str = "list") -> str:
        target = tmp_path / name
        target.write_text(text, encoding="utf-8")
        return str(target)

    return make


def both_pairs(path: str, comment_char: str = "#"):
    old = diff.bash_streams(
        "bash -c %s bash %s %s" % (_sh(BASH_PAIRS), _sh(path), _sh(comment_char))
    )
    new = diff.bash_streams("%s pairs %s %s" % (PY, _sh(path), _sh(comment_char)))
    return old, new


def both_verify(path: str, comment_char: str = "#"):
    old = diff.bash_streams(
        "bash -c %s bash %s %s" % (_sh(BASH_VERIFY), _sh(path), _sh(comment_char))
    )
    new = diff.bash_streams("%s verify %s %s" % (PY, _sh(path), _sh(comment_char)))
    return old, new


# --------------------------------------------------------------------------- 1. parse_blockered_list, byte for byte ---------------------------------------------------------------------------


@pytest.mark.parametrize(("case", "cc", "text"), LISTS, ids=[c[0] for c in LISTS])
def test_parse_agrees_byte_for_byte(listfile, case, cc, text):
    path = listfile(text)
    old, new = both_pairs(path, cc)
    assert old == new, "case %s: %r != %r" % (case, old, new)


def test_a_missing_file_is_empty_tables_and_success(tmp_path):
    """The historical contract five gates rely on, on BOTH sides."""
    path = str(tmp_path / "does-not-exist")
    old, new = both_pairs(path)
    assert old == new
    assert old[0] == 0
    assert old[1] == ""
    assert old[2] == ""


def test_a_directory_is_also_empty_tables_and_success(tmp_path):
    """`[[ ! -f ]]` is true for a directory, and so is `not Path.is_file()`.

    Written as its own case because the obvious Python transliteration is `Path.exists()`, which is FALSE here and would send a directory into the reader, where it becomes an IsADirectoryError and a refusal the twin never makes.
    """
    target = tmp_path / "a-directory"
    target.mkdir()
    old, new = both_pairs(str(target))
    assert old == new
    assert old == (0, "", "")


# --------------------------------------------------------------------------- 2. verify_all_blockers ---------------------------------------------------------------------------


@pytest.mark.parametrize(("case", "cc", "text"), LISTS, ids=[c[0] for c in LISTS])
def test_verify_agrees_byte_for_byte(listfile, case, cc, text):
    path = listfile(text)
    old, new = both_verify(path, cc)
    assert old == new, "case %s: %r != %r" % (case, old, new)


@pytest.mark.parametrize(("case", "cc", "text"), MULTI_FAILURE, ids=[c[0] for c in MULTI_FAILURE])
def test_verify_agrees_as_a_multiset_when_more_than_one_entry_fails(listfile, case, cc, text):
    """ORDER IS NOT COMPARED HERE, and the reason is in the port's docstring.

    Multiplicity IS compared: sorting both sides' lines and requiring equality refuses "three occurrences equals one", which a set would allow.
    """
    path = listfile(text)
    old, new = both_verify(path, cc)
    assert old[0] == new[0] == 1
    assert sorted(old[1].splitlines()) == sorted(new[1].splitlines())
    assert sorted(old[2].splitlines()) == sorted(new[2].splitlines())
    # And the case is not vacuous: it really did produce more than one failure.
    assert len(old[2].splitlines()) >= 2, "case %s produced %d error line(s)" % (
        case,
        len(old[2].splitlines()),
    )


def test_verify_under_ci_moves_the_head_line_to_stdout_on_both_sides(listfile):
    """`CI=true` turns `x <m>` on stderr into `::error::<m>` on stdout.

    THE STREAM SWAP IS THE SUBJECT, so the two streams are never merged. This is the exact gap a W7 P4 cutover differential found in `profiler_coverage.py`: same words, same exit code, different stream, and the annotation is what surfaces a finding in the Actions UI.
    """
    path = listfile("# BLOCKER: tbd\nA-1\n")
    env = diff.env_for(CI="true")
    old = diff.bash_streams("bash -c %s bash %s '#'" % (_sh(BASH_VERIFY), _sh(path)), env=env)
    new = diff.bash_streams("%s verify %s '#'" % (PY, _sh(path)), env=env)
    assert old == new
    assert "::error::" in old[1], "CI=true did not produce an annotation on stdout"
    assert "::error::" not in old[2]


def test_an_empty_table_passes_without_calling_the_validator(listfile):
    """`audit.sh:52` declares its arrays with no initialiser and its list is empty.

    The twin's first cut of an emptiness guard here killed that gate on the spot.
    """
    tables = bv.parse_blockered_list(listfile(""))
    assert tables == bv.Tables({}, {})
    assert bv.verify_all_blockers("irrelevant", tables.blocker) is True


# --------------------------------------------------------------------------- 3. validate_blocker_quality ---------------------------------------------------------------------------

REASONS = [
    ("good", GOOD),
    ("banned-exact", "tbd"),
    ("banned-exact-with-punctuation", "TBD."),
    ("banned-substring", "skipped for now to keep this pr focused on the rename"),
    ("too-short", "pinned"),
    ("exactly-at-the-floor", "x" * allowlist.MIN_REASON_LENGTH),
    ("one-under-the-floor", "x" * (allowlist.MIN_REASON_LENGTH - 1)),
    ("empty", ""),
    ("newline-inside", "a reason that is long enough\nand carries a newline in it"),
    ("percent-and-format-tokens", "%s %d {} ${x} " + GOOD),
]


@pytest.mark.parametrize(("case", "reason"), REASONS, ids=[c[0] for c in REASONS])
def test_reason_agrees_byte_for_byte(case, reason):
    old = diff.bash_streams(
        "bash -c %s bash %s %s %s" % (_sh(BASH_REASON), _sh("E-1"), _sh(reason), _sh("some/list"))
    )
    new = diff.bash_streams("%s reason %s %s %s" % (PY, _sh("E-1"), _sh(reason), _sh("some/list")))
    assert old == new, "case %s: %r != %r" % (case, old, new)


def test_the_floor_is_a_reference_and_not_a_copy():
    """`BLOCKER_MIN_LENGTH` must BE the canonical, not equal a literal 30.

    A literal would pass an equality test today and drift the first time the canonical moved, which is the whole failure mode the 2026-09-09 collapse was performed to remove.
    """
    assert bv.BLOCKER_MIN_LENGTH is allowlist.MIN_REASON_LENGTH
    text = pathlib.Path(paths.from_root(PORT)).read_text(encoding="utf-8")
    assert "BLOCKER_MIN_LENGTH = allowlist.MIN_REASON_LENGTH" in text


def test_the_port_carries_no_phrase_table():
    """A tenth copy of the banned-phrase list must not appear here.

    `test_blocker_implementations.py:207` fails by name on any TRACKED file carrying ten or more of them as quoted literals; this asserts it locally so the failure arrives when the file is written rather than when it is added.
    """
    text = pathlib.Path(paths.from_root(PORT)).read_text(encoding="utf-8")
    hits = sum(
        1
        for phrase in allowlist.LOW_EFFORT_PHRASES
        if any(q + phrase + q in text for q in ("'", '"', "`"))
    )
    assert hits < 10, "the port carries %d canonical phrase(s) as quoted literals" % hits
    # PROSE MAY NAME THE MIRROR; CODE MAY NOT RE-DECLARE IT. The port's docstring explains at length why the twin keeps `LOW_EFFORT_BLOCKER_PATTERNS` and why that argument does not travel, so a bare substring test fails on the explanation. What must not exist is an ASSIGNMENT.
    for name in ("LOW_EFFORT_BLOCKER_PATTERNS", "LOW_EFFORT_BLOCKER_SUBSTRINGS"):
        assert ("%s = " % name) not in text, "the port re-declares %s" % name
        assert ("%s: " % name) not in text, "the port re-declares %s" % name


# --------------------------------------------------------------------------- 4. The RS frame, which is a control and not a formatting detail ---------------------------------------------------------------------------


def test_frame_writes_exactly_what_the_canonical_verify_rows_writes(tmp_path):
    """The two writers of the RS protocol, compared on real bytes.

    `frame()` is a transcription of `allowlist.main`'s `verify-rows` writer because that writer is welded to `sys.stdin`/`sys.stdout` inside a CLI verb. A transcription that nothing compares is a copy waiting to drift, so this runs the REAL module as a subprocess and requires the bytes to match.
    """
    listpath = str(tmp_path / "list")
    rows = "A-1\t\nA-2\ttbd\nA-3\t%s\n" % GOOD
    proc = subprocess.run(
        [sys.executable, "-m", "rediacc_ci.core.allowlist", "verify-rows", listpath],
        input=rows,
        capture_output=True,
        text=True,
        cwd=str(paths.repo_root()),
        env={"PYTHONPATH": str(paths.from_root(".ci")), "PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        check=False,
    )
    assert proc.returncode == 1, proc.stderr
    messages = [
        allowlist.missing_reason("A-1", listpath),
        allowlist.validate_reason("A-2", "tbd", listpath).message,
    ]
    assert bv.frame(messages) == proc.stdout
    assert proc.stdout.count(bv.BLOCKER_VALIDATOR_RS) == 2


def test_frame_and_replay_round_trip_a_forged_sentinel(capsys):
    """A BLOCKER reason that CONTAINS an RS line must not open a frame.

    This is the whole argument for a counted frame over a sentinel: the reason is text somebody writes, and a forged frame would let one rejection hide inside another rejection's message.
    """
    forged = "head line\n%s99\nsmuggled body\ntail line" % bv.BLOCKER_VALIDATOR_RS
    assert bv.replay_frames(bv.frame([forged])) is True
    out = capsys.readouterr()
    assert "smuggled body" in out.out
    assert "\x1e99" in out.out, "the forged line was consumed as a frame header"


@pytest.mark.parametrize(
    ("case", "stream"),
    [
        ("empty", ""),
        ("plain-text", "just a line"),
        ("count-then-nothing", "\x1e3\n"),
        ("two-frames", "\x1e1\nalpha\n\x1e2\nbeta\ngamma\n"),
        ("count-longer-than-body", "\x1e5\nalpha\n"),
    ],
    ids=["empty", "plain-text", "count-then-nothing", "two-frames", "count-longer-than-body"],
)
def test_replay_agrees_with_the_twins_reader(tmp_path, case, stream):
    """`_blocker_emit` and `replay_frames`, on the same bytes.

    The `empty` case is the one that matters: it is what proves the twin's zero-frame refusal is unreachable. A here-string appends a newline, so the reader sees ONE empty, unframed line and answers "unframed output ... : " rather than "reported a failure but emitted no message".
    """
    target = tmp_path / "framed"
    target.write_text(stream, encoding="utf-8")
    old = diff.bash_streams("bash -c %s bash %s" % (_sh(BASH_REPLAY), _sh(str(target))))
    new = diff.bash_streams("%s replay %s" % (PY, _sh(str(target))))
    assert old == new, "case %s: %r != %r" % (case, old, new)


def test_the_zero_frame_message_is_unreachable_on_both_sides(tmp_path, capsys):
    """Named, so the dead arm cannot be deleted as noise or promoted by accident."""
    target = tmp_path / "framed"
    target.write_text("", encoding="utf-8")
    old = diff.bash_streams("bash -c %s bash %s" % (_sh(BASH_REPLAY), _sh(str(target))))
    assert "unframed output" in old[1] + old[2]
    assert "emitted no message" not in old[1] + old[2]

    assert bv.replay_frames("") is False
    out = capsys.readouterr()
    assert "unframed output" in out.out + out.err
    assert "emitted no message" not in out.out + out.err


# --------------------------------------------------------------------------- 5. The two divergences, asserted AS divergences ---------------------------------------------------------------------------


def test_the_twin_leaks_a_python_traceback_and_the_port_cannot(tmp_path):
    """A broken reader: the twin prints 14 lines of traceback, the port prints two.

    THE PORT CANNOT REPRODUCE THIS BY CONSTRUCTION. The traceback belongs to a
    CHILD `python3 -m rediacc_ci.core.allowlist` that the port does not spawn;
    fabricating one would be inventing output rather than porting it. The divergence is pinned in both directions so neither side can change quietly.

    THE DEFECT IS THE TWIN'S AND IT IS NOT FIXED HERE: `.ci/scripts/lib/` is not this box's to edit. It is the same class as the `bws-env.sh` traceback leak found in the previous wave of this workstream.
    """
    target = tmp_path / "bad-utf8"
    target.write_bytes(b"# BLOCKER: %s\n\xff\xfe-entry\n" % GOOD.encode())
    old = diff.bash_streams("bash -c %s bash %s '#'" % (_sh(BASH_PAIRS), _sh(str(target))))
    new = diff.bash_streams("%s pairs %s '#'" % (PY, _sh(str(target))))

    assert old[0] == new[0] == 1
    assert "Traceback (most recent call last):" in old[2]
    assert "UnicodeDecodeError" in old[2]
    assert "Traceback (most recent call last):" not in new[2]

    # The refusal itself, which is the part a caller reads, is identical apart
    # from the parenthetical: the twin reports the CHILD'S EXIT CODE and the port
    # has no child, so it reports the exception type instead of claiming an exit code that never happened.
    assert "could not parse %s (exit 1)" % target in old[2]
    assert "could not parse %s (UnicodeDecodeError)" % target in new[2]
    tail = "  This is a broken reader, not an empty allowlist. Refusing to report zero entries."
    assert tail in old[2]
    assert tail in new[2]


def test_the_broken_reader_raises_rather_than_returning_empty_tables(tmp_path):
    """The port's in-process signal for the twin's `return 1`.

    Every bash caller invokes `parse_blockered_list` bare, under the `errexit` those gates run with, so `return 1` takes the script down. An exception is the same contract; returning empty tables would be the vacuity the twin's own "Refusing to report zero entries" line exists to refuse.
    """
    target = tmp_path / "bad-utf8"
    target.write_bytes(b"# BLOCKER: %s\n\xff\xfe-entry\n" % GOOD.encode())
    with pytest.raises(bv.BrokenReaderError):
        bv.parse_blockered_list(target)


# --------------------------------------------------------------------------- 6. The planted defects ---------------------------------------------------------------------------


def _digest(rel: str) -> str:
    return hashlib.sha256(pathlib.Path(paths.from_root(rel)).read_bytes()).hexdigest()


def _load_mutated(tmp_path, old: str, new: str, name: str):
    """Load a MUTATED COPY of the port under a fresh module name.

    The copy lives in a tmpdir and the real file is never opened for writing, so an aborted test cannot leave the tree broken. The copy still imports the real `rediacc_ci.core.allowlist`, which is the point: only the transport moves.
    """
    source = pathlib.Path(paths.from_root(PORT)).read_text(encoding="utf-8")
    assert old in source, "the plant did not land: %r is not in the port" % old
    target = tmp_path / ("%s.py" % name)
    target.write_text(source.replace(old, new, 1), encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_planted_defect_in_the_port_is_caught(tmp_path):
    """THE CONTROL FOR EVERY CASE ABOVE. A real mutation must be visible.

    Three plants, one per behaviour the corpus claims to prove, and each is a change a careless port would genuinely make.
    """
    before = _digest(PORT)

    # PLANT 1: the missing-file contract inverted, which is how a port turns an absent allowlist into a refusal five gates do not expect.
    m1 = _load_mutated(tmp_path, "if not path.is_file():", "if path.is_file() and False:", "bv_p1")
    assert bv.parse_blockered_list(tmp_path / "nope") == bv.Tables({}, {})
    # `ListNotFoundError` is a `FileNotFoundError`, so the port's own broken-reader arm catches it and re-raises. The type is named rather than `Exception`: a blind `raises` would also pass on an AttributeError from a mis-edited plant.
    with pytest.raises(m1.BrokenReaderError):
        m1.parse_blockered_list(tmp_path / "nope")

    # PLANT 2: the RS reader stops counting and treats every line as a header, which is precisely the forgery the counted frame exists to prevent.
    m2 = _load_mutated(tmp_path, "count = int(count_text)", "count = 0", "bv_p2")
    good_stream = bv.frame(["alpha\nbeta"])
    assert bv.replay_frames(good_stream) is True
    assert m2.replay_frames(good_stream) is False, (
        "a reader that counts zero lines per frame then meets the body as an "
        "unframed line must refuse; it did not, so the frame is not being read"
    )

    # PLANT 3: an entry with NO reason silently passes, which is the exact hole `verify_all_blockers` exists to close.
    m3 = _load_mutated(
        tmp_path,
        "        if not reason:\n            failures.append(allowlist.missing_reason(entry, file))\n            continue",
        "        if not reason:\n            continue",
        "bv_p3",
    )
    table = {"A-1": ""}
    assert bv.verify_all_blockers("some/list", table) is False
    assert m3.verify_all_blockers("some/list", table) is True, (
        "the mutation did not change the verdict, so this control proves nothing"
    )

    assert _digest(PORT) == before, "a planted defect was written to the real module"


def test_the_differential_itself_can_fail(listfile):
    """A comparison that compares nothing scores everything as equivalent."""
    path = listfile("# BLOCKER: tbd\nA-1\n")
    old, new = both_verify(path)
    assert old == new
    assert old != (new[0] + 1, new[1], new[2]), "the comparison ignores the exit code"
    assert old != (new[0], new[1] + "x", new[2]), "the comparison ignores stdout"
    assert old != (new[0], new[1], new[2] + "x"), "the comparison ignores stderr"
    assert old[0] == 1, "this case produced no failure to compare"
    assert old[2] != "", "this case wrote nothing to stderr, so there is nothing to compare"
