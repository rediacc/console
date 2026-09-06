r"""`rediacc_ci.quality.battery_clean_tree` against the shell it replaces.

WHY A DIFFERENTIAL AND NOT A TABLE OF EXPECTED STRINGS. The extraction at the
heart of this gate is a four-line awk program with three regexes, two of them
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
`.ci/scripts/quality/check-battery-clean-tree.sh` lines 64-67 unchanged.
"""

import pathlib

import pytest

from rediacc_ci.quality import battery_clean_tree as bct
from rediacc_ci.tests import differential as diff

# The twin's extractor, byte for byte. Substituting a variable would be a
# rewrite, and a rewrite is the one thing this comparison cannot tolerate.
_AWK = r"""awk '
    /^tree_state\(\) \{/ { print; if ($0 ~ /\}[[:space:]]*$/) exit; inside = 1; next }
    inside { print; if ($0 ~ /^\}/) exit }
' run-all.sh 2>/dev/null"""

# Every shape run-all.sh has held or could hold, plus the near-misses that decide
# whether this gate refuses. The comment on each line is the property it is there
# for; a case with no property is a case that will be deleted the first time
# someone tidies this file.
GUARD_SHAPES = [
    # The LIVE form, run-all.sh:349. A one-liner, so the self-closing branch is
    # the branch that runs every day.
    (
        'tree_state() { (cd "$B" && { git status --porcelain 2>/dev/null || true; }'
        " | { grep -v '^??' || true; } | sort); }\ncd \"$GATES_DIR\"\n"
    ),
    # The PRE-FIX form, which is the defect this gate exists for.
    "tree_state() { (cd \"$B\" && git status --porcelain | grep -v '^??' | sort); }\nafter\n",
    "tree_state() {\n  git status --porcelain\n}\nafter\n",  # multi-line
    "tree_state() {\n  (\n    git status\n  )\n}\nafter\n",  # an indented `}` inside
    "tree_state() {\n  git status\n",  # unterminated: runs to EOF
    "prelude\nmore\ntree_state() { git status; }\ntail\n",  # not the first line
    "tree_state() { git status; } \nafter\n",  # trailing space after the brace
    "tree_state() { git status; }\t\nafter\n",  # a trailing TAB
    "  tree_state() { git status; }\n",  # INDENTED definition: invisible
    "tree_state () { git status; }\n",  # space before the parens: invisible
    "tree_state(){ git status; }\n",  # no space before the brace: invisible
    "tree_state()  { git status; }\n",  # TWO spaces: invisible
    "my_tree_state() { git status; }\n",  # a longer name: not anchored
    "# tree_state() { git status; }\n",  # a comment: not at column 1
    "nothing here at all\n",  # no definition
    "",  # an empty file
    "tree_state() {\n  git status\n}\ntree_state() {\n  second\n}\n",  # two: the first wins
    "tree_state() {\n  echo )\n}\n",  # a stray paren inside
]


@pytest.mark.parametrize("text", GUARD_SHAPES)
def test_extract_guard_matches_awk(tmp_path: pathlib.Path, text: str) -> None:
    """The extractor and awk must agree on every shape, including the misses."""
    (tmp_path / "run-all.sh").write_text(text, encoding="utf-8")
    code, out, err = diff.bash_streams(_AWK, cwd=str(tmp_path))
    assert code == 0, err
    # `GUARD="$(awk ...)"` -- the command substitution strips trailing newlines,
    # and the port's caller does the same with `.rstrip("\n")`. Compared in that
    # form because that is the value the refusal test actually sees.
    assert bct.extract_guard(text).rstrip("\n") == out.rstrip("\n")


@pytest.mark.parametrize("text", GUARD_SHAPES)
def test_refusal_condition_matches_bash(tmp_path: pathlib.Path, text: str) -> None:
    """`[[ -z "$GUARD" || "$GUARD" != *"git status"* ]]`, over the same table.

    BOTH DIRECTIONS. Half these shapes must produce a refusal and half must not;
    a table that only held misses would pass against a gate that refuses every
    run-all.sh in existence.
    """
    (tmp_path / "run-all.sh").write_text(text, encoding="utf-8")
    code, out, err = diff.bash_streams(
        'GUARD="$(%s)"\n'
        'if [[ -z "$GUARD" || "$GUARD" != *"git status"* ]]; then echo REFUSE; '
        "else echo OK; fi" % _AWK,
        cwd=str(tmp_path),
    )
    assert code == 0, err
    guard = bct.extract_guard(text).rstrip("\n")
    port_refuses = guard == "" or "git status" not in guard
    assert port_refuses == (out.strip() == "REFUSE")


def test_the_indented_definition_is_a_carried_blind_spot() -> None:
    """Pinned as a DECISION, not left to be inferred from the table above.

    `/^tree_state\\(\\) \\{/` is anchored at column 1 and demands exactly one
    space. A run-all.sh that indented its definition, or wrote `tree_state ()`,
    would make this gate REFUSE rather than pass, which is the safe direction --
    but it would refuse for a formatting reason while reporting that the guard
    was removed. The assertion exists so a later reader cannot mistake it for an
    accident, and so a loosened regex has to delete a named control.
    """
    assert bct.extract_guard("  tree_state() { git status; }\n") == ""
    assert bct.extract_guard("tree_state () { git status; }\n") == ""
    assert bct.extract_guard("tree_state() { git status; }\n") != ""


# ---------------------------------------------------------------------------
# The drive harness
# ---------------------------------------------------------------------------

# The twin's `drive`, with the guard source and repo interpolated exactly as its
# unquoted heredoc does.
_DRIVE = """
cat > drive.sh <<DRIVE
set -euo pipefail
BATTERY_REPO_ROOT="$REPO"
$SRC
T="\\$(tree_state)"
echo "OUT:\\$T"
DRIVE
out="$(bash drive.sh 2>&1)" || rc=$?
printf 'rc=%s out=%s' "${rc:-0}" "${out#OUT:}"
"""

DRIVE_GUARDS = [
    # The live one-liner: quiet on clean, loud on dirty.
    (
        'tree_state() { (cd "$BATTERY_REPO_ROOT" && { git status --porcelain 2>/dev/null'
        " || true; } | { grep -v '^??' || true; } | sort); }"
    ),
    # The pre-fix form: ABORTS on clean. The historical defect.
    bct.PREFIX_GUARD,
    # Blind: survives clean by seeing nothing at all.
    'tree_state() { (cd "$BATTERY_REPO_ROOT" && git status --porcelain >/dev/null 2>&1; true); }',
    # Reports untracked files too, so a clean checkout is not quiet.
    'tree_state() { (cd "$BATTERY_REPO_ROOT" && git status --porcelain | sort); }',
    # A constant: wrong in both directions at once.
    'tree_state() { (cd "$BATTERY_REPO_ROOT" && git status --porcelain >/dev/null 2>&1; echo CONST); }',
]


@pytest.mark.parametrize("guard", DRIVE_GUARDS)
@pytest.mark.parametrize("dirty", [False, True])
def test_drive_matches_bash(tmp_path: pathlib.Path, guard: str, dirty: bool) -> None:
    """`rc=<n> out=<value>`, produced by the twin's heredoc and by the port.

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
    """
    clean = tmp_path / "c"
    dirty = tmp_path / "d"
    bct.make_repo(str(clean), dirty=False)
    bct.make_repo(str(dirty), dirty=True)
    work = tmp_path / "w"
    work.mkdir()
    assert bct.drive(str(work), bct.PREFIX_GUARD, str(clean)) == "rc=1 out="
    assert bct.drive(str(work), bct.PREFIX_GUARD, str(dirty)).startswith("rc=0")
    assert "tracked.txt" in bct.drive(str(work), bct.PREFIX_GUARD, str(dirty))


def test_selftest_is_green() -> None:
    """The port's own plants and mirrors, driven from pytest.

    Not redundant with running `--selftest` from the shell: this is the call that
    fails the pytest suite when a control is deleted, which is the failure mode
    the flag on its own cannot catch (nobody runs it).
    """
    assert bct.selftest() == 0
