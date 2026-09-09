r"""`rediacc_ci.quality.battery_clean_tree` against the shell it replaces.

RETARGETED 2026-09-09 (W7P3-BAT) WITH ITS SUBJECT. The gate polices the runner's
tracked-tree snapshot, the runner became `.ci/rediacc_ci/battery.py`, and both
implementations moved together. What changed here is the SHAPE TABLE and the
extractor being compared: the differential structure, and the reason for it, are
unchanged.

WHY A DIFFERENTIAL AND NOT A TABLE OF EXPECTED STRINGS. The extraction at the
heart of this gate is a short awk program with three conditions, two of them
anchored to column 1 and one of them applied only to the definition line. Whether
a given `tree_state` shape is extracted whole, extracted short, or missed
entirely is decided by awk, not by anything a reader can infer. A table of
expected strings would be a table of what the PORT does, asserted against
itself.

The committed ledger `.ci/shadow/w7p2-battery-clean-tree.observations.jsonl`
compares the WHOLE gate over five distinct trees. It cannot isolate the
extractor, because on a tree where extraction fails both sides simply print the
same refusal. This file takes the extractor apart, shape by shape.

THE AWK PROGRAM BELOW IS LIFTED FROM
`.ci/scripts/quality/check-battery-clean-tree.sh` unchanged.
"""

import pathlib

import pytest

from rediacc_ci.quality import battery_clean_tree as bct
from rediacc_ci.tests import differential as diff

# The twin's extractor, byte for byte. Substituting a variable would be a
# rewrite, and a rewrite is the one thing this comparison cannot tolerate.
_AWK = r"""awk '
    !inside && /^def tree_state\(/ {
        buf[++n] = $0
        if ($0 ~ /^def tree_state\(.*\)[^:]*:[ \t]*[^ \t#]/) exit
        inside = 1
        next
    }
    inside {
        if ($0 ~ /^[^ \t]/) exit
        buf[++n] = $0
    }
    END {
        while (n > 0 && buf[n] ~ /^[ \t]*$/) n--
        for (i = 1; i <= n; i++) print buf[i]
    }
' battery.py 2>/dev/null"""

# Every shape battery.py has held or could hold, plus the near-misses that decide
# whether this gate refuses. The comment on each line is the property it is there
# for; a case with no property is a case that will be deleted the first time
# someone tidies this file.
GUARD_SHAPES = [
    # The LIVE form: a multi-line def whose body ends where a flush-left comment
    # begins, which is exactly what follows tree_state in battery.py.
    (
        "def tree_state(root: pathlib.Path) -> str:\n"
        '    """doc"""\n'
        "    try:\n"
        '        proc = subprocess.run(["git", "status", "--porcelain"], cwd=str(root),\n'
        "            capture_output=True, text=True, check=False, timeout=120)\n"
        "    except (OSError, subprocess.SubprocessError):\n"
        '        return ""\n'
        '    return "\\n".join(sorted(proc.stdout.splitlines()))\n'
        "\n\n"
        "# ------\n"
        "class Report:\n"
    ),
    # The PRE-FIX form in the new language, which is the defect this gate exists
    # for: the same pipeline handed back to bash under check=True.
    bct.PREFIX_GUARD + "after = 1\n",
    "def tree_state(root):\n    return git_status()\n# a comment\nx = 1\n",  # comment ends it
    "def tree_state(root):\n    a = 1\n\n    return a\ndef other():\n",  # a BLANK line inside
    "def tree_state(root):\n    return 1\n\n\ndef other():\n",  # trailing blanks dropped
    "def tree_state(root):\n  git status\n",  # unterminated: runs to EOF
    "prelude\nmore\ndef tree_state(root):\n    return 1\ntail = 2\n",  # not the first line
    'def tree_state(root): return "git status"\nafter = 1\n',  # ONE-LINER: self-closing
    "def tree_state(root):  # git status\n    return 1\nx = 2\n",  # a comment is not a body
    "    def tree_state(root):\n        return 1\n",  # INDENTED definition: invisible
    "def  tree_state(root):\n    return 1\n",  # TWO spaces after def: invisible
    "def tree_state2(root):\n    return 1\n",  # a longer name: not this function
    "def my_tree_state(root):\n    return 1\n",  # a prefix: not anchored
    "# def tree_state(root):\n#     return 1\n",  # a comment: not a definition
    "nothing here at all\n",  # no definition
    "",  # an empty file
    "def tree_state(root):\n    return 1\ndef tree_state(root):\n    return 2\n",  # first wins
    "def tree_state(root):\n    return ')'\n",  # a stray paren inside
]


@pytest.mark.parametrize("text", GUARD_SHAPES)
def test_extract_guard_matches_awk(tmp_path: pathlib.Path, text: str) -> None:
    """The extractor and awk must agree on every shape, including the misses."""
    (tmp_path / "battery.py").write_text(text, encoding="utf-8")
    code, out, err = diff.bash_streams(_AWK, cwd=str(tmp_path))
    assert code == 0, err
    # `GUARD="$(awk ...)"` -- the command substitution strips trailing newlines,
    # and the port's caller does the same with `.rstrip("\n")`. Compared in that
    # form because that is the value the refusal test actually sees.
    assert bct.extract_guard(text).rstrip("\n") == out.rstrip("\n")


@pytest.mark.parametrize("text", GUARD_SHAPES)
def test_refusal_condition_matches_bash(tmp_path: pathlib.Path, text: str) -> None:
    """`[[ -z "$GUARD" ]] || ! [[ "$GUARD" =~ git[^A-Za-z0-9_]{0,8}status ]]`.

    BOTH DIRECTIONS. Half these shapes must produce a refusal and half must not;
    a table that only held misses would pass against a gate that refuses every
    battery.py in existence.

    THE PATTERN IS THE RE-KEY THE RETARGET TURNED ON. The twin used to test the
    literal substring `git status`, which is right for a shell pipeline and FALSE
    for the argv list battery.py writes.
    """
    (tmp_path / "battery.py").write_text(text, encoding="utf-8")
    code, out, err = diff.bash_streams(
        'GUARD="$(%s)"\n'
        'if [[ -z "$GUARD" ]] || ! [[ "$GUARD" =~ git[^A-Za-z0-9_]{0,8}status ]]; then '
        "echo REFUSE; else echo OK; fi" % _AWK,
        cwd=str(tmp_path),
    )
    assert code == 0, err
    guard = bct.extract_guard(text).rstrip("\n")
    port_refuses = guard == "" or not bct.GIT_STATUS_RE.search(guard)
    assert port_refuses == (out.strip() == "REFUSE")


def test_the_indented_definition_is_a_carried_blind_spot() -> None:
    """Pinned as a DECISION, not left to be inferred from the table above.

    `/^def tree_state\\(/` is anchored at column 1. A battery.py that indented its
    definition, or renamed it, would make this gate REFUSE rather than pass, which
    is the safe direction -- but it would refuse for a formatting reason while
    reporting that the guard was removed. The assertion exists so a later reader
    cannot mistake it for an accident, and so a loosened regex has to delete a
    named control.
    """
    assert bct.extract_guard("    def tree_state(root):\n        return 1\n") == ""
    assert bct.extract_guard("def  tree_state(root):\n    return 1\n") == ""
    assert bct.extract_guard("def tree_state(root):\n    return 1\n") != ""


def test_the_argv_spelling_is_why_the_substring_test_had_to_go() -> None:
    """The retarget's one real trap, pinned so it cannot be undone quietly.

    battery.py spells the snapshot `["git", "status", "--porcelain"]`. The twin's
    old condition was `"$GUARD" != *"git status"*`, which is FALSE against that
    text, so a gate carried over unchanged would have refused on a perfectly good
    guard while reporting that the guard was gone.
    """
    argv_spelling = '["git", "status", "--porcelain"]'
    assert "git status" not in argv_spelling
    assert bct.GIT_STATUS_RE.search(argv_spelling)
    assert bct.GIT_STATUS_RE.search("git status --porcelain")
    assert not bct.GIT_STATUS_RE.search('["git", "diff", "--name-only"]')


# ---------------------------------------------------------------------------
# The drive harness
# ---------------------------------------------------------------------------

# The twin's `drive`, with the guard source and repo passed exactly as it passes
# them: the two heredocs are QUOTED, so the driver's head and tail are literal,
# and the repo arrives as an argv rather than as an interpolated literal.
_DRIVE = """
cat > drive.py <<'HEAD'
import pathlib
import subprocess
import sys

HEAD
printf '%s\\n' "$SRC" >> drive.py
cat >> drive.py <<'TAIL'

try:
    T = tree_state(pathlib.Path(sys.argv[1]))
except BaseException as exc:
    print("ERR:%s: %s" % (type(exc).__name__, exc))
    raise SystemExit(1)
print("OUT:%s" % T)
TAIL
out="$(python3 drive.py "$REPO" 2>&1)" || rc=$?
printf 'rc=%s out=%s' "${rc:-0}" "${out#OUT:}"
"""

DRIVE_GUARDS = [
    # The live guard: quiet on clean, loud on dirty.
    (
        "def tree_state(root):\n"
        '    proc = subprocess.run(["git", "status", "--porcelain"], cwd=str(root),\n'
        "        capture_output=True, text=True, check=False)\n"
        '    return "\\n".join('
        'sorted(ln for ln in proc.stdout.splitlines() if not ln.startswith("??")))'
    ),
    # The pre-fix form: ABORTS on clean. The historical defect.
    bct.PREFIX_GUARD,
    # Blind: survives clean by seeing nothing at all.
    (
        "def tree_state(root):\n"
        '    subprocess.run(["git", "status"], cwd=str(root), capture_output=True)\n'
        '    return ""'
    ),
    # Reports untracked files too, so a clean checkout is not quiet.
    (
        "def tree_state(root):\n"
        '    proc = subprocess.run(["git", "status", "--porcelain"], cwd=str(root),\n'
        "        capture_output=True, text=True)\n"
        '    return "\\n".join(sorted(proc.stdout.splitlines()))'
    ),
    # A constant: wrong in both directions at once.
    (
        "def tree_state(root):\n"
        '    subprocess.run(["git", "status", "--porcelain"], cwd=str(root),\n'
        "        capture_output=True)\n"
        '    return "CONST"'
    ),
]


@pytest.mark.parametrize("guard", DRIVE_GUARDS)
@pytest.mark.parametrize("dirty", [False, True])
def test_drive_matches_bash(tmp_path: pathlib.Path, guard: str, dirty: bool) -> None:
    """`rc=<n> out=<value>`, produced by the twin's heredocs and by the port.

    Ten cases, because the interesting property is a 5x2 table: each guard shape
    against a clean tree AND a dirty one. A guard is only wrong in one of the two
    columns, and a test that drove only one column would bless half of them.
    """
    repo = tmp_path / ("dirty" if dirty else "clean")
    bct.make_repo(str(repo), dirty=dirty)
    work = tmp_path / "work"
    work.mkdir()
    code, out, err = diff.bash_streams(
        _DRIVE, cwd=str(work), env=diff.env_for(REPO=str(repo), SRC=guard)
    )
    assert code == 0, err
    assert bct.drive(str(work), guard, str(repo)) == out


def test_make_repo_builds_what_the_assertions_assume(tmp_path: pathlib.Path) -> None:
    """The FIXTURE, checked against git rather than against the port's intent.

    A "clean" repo that was not clean, or a "dirty" one that was not dirty, would
    make every assertion in this gate true for the wrong reason. This is the
    control on the control.
    """
    clean = tmp_path / "c"
    dirty = tmp_path / "d"
    bct.make_repo(str(clean), dirty=False)
    bct.make_repo(str(dirty), dirty=True)

    code, out, err = diff.bash_streams("git status --porcelain -uall", cwd=str(clean))
    assert code == 0, err
    assert out.rstrip("\n") == "?? untracked.txt"

    # `rstrip("\n")`, NOT `.strip()`. Porcelain status lines begin with a
    # two-character status field, and for a modified-but-unstaged file the first
    # of those two characters is a SPACE: the line is exactly " M tracked.txt".
    # `.strip()` eats that leading space off the first line only, which turned
    # this assertion into a sorting puzzle the first time it was written.
    code, out, err = diff.bash_streams("git status --porcelain -uall", cwd=str(dirty))
    assert code == 0, err
    assert sorted(out.rstrip("\n").split("\n")) == [" M tracked.txt", "?? untracked.txt"]


def test_the_untracked_file_is_why_the_pre_fix_guard_survived_review(
    tmp_path: pathlib.Path,
) -> None:
    """The historical defect, reproduced end to end rather than described.

    `grep -v '^??'` filters everything out exactly when there is nothing MODIFIED,
    so it aborts on a clean checkout and works on a developer's. That asymmetry is
    the whole reason the bug shipped and could not be reproduced locally, and it
    is the property the gate's PLANT relies on: if the pre-fix guard ever stopped
    aborting, the two assertions after it would be checking nothing.

    THE MARKER IS ASSERTED, not just the rc. The driver catches the exception and
    prints `ERR:<type>: <message>` rather than letting a traceback out, because a
    traceback carries the driver's own mktemp path and would differ between two
    runs of the same code.
    """
    clean = tmp_path / "c"
    dirty = tmp_path / "d"
    bct.make_repo(str(clean), dirty=False)
    bct.make_repo(str(dirty), dirty=True)
    work = tmp_path / "w"
    work.mkdir()
    aborted = bct.drive(str(work), bct.PREFIX_GUARD, str(clean))
    assert aborted.startswith("rc=1 out=ERR:CalledProcessError"), aborted
    assert bct.drive(str(work), bct.PREFIX_GUARD, str(dirty)).startswith("rc=0")
    assert "tracked.txt" in bct.drive(str(work), bct.PREFIX_GUARD, str(dirty))


def test_the_live_subject_is_still_extractable() -> None:
    """The gate reads a REAL file, and every case above reads a fixture.

    A rename of `tree_state` in battery.py would leave this whole suite green
    while every real run of the gate refused, which is the exact shape the gate's
    own `CANNOT VERIFY` exists to make loud.
    """
    live = pathlib.Path(diff.repo()) / bct.BATTERY_REL
    assert live.is_file()
    guard = bct.extract_guard(live.read_text(encoding="utf-8"))
    assert guard.startswith("def tree_state(")
    assert bct.GIT_STATUS_RE.search(guard)


def test_selftest_is_green() -> None:
    """The port's own plants and mirrors, driven from pytest.

    Not redundant with running `--selftest` from the shell: this is the call that
    fails the pytest suite when a control is deleted, which is the failure mode
    the flag on its own cannot catch (nobody runs it).
    """
    assert bct.selftest() == 0
