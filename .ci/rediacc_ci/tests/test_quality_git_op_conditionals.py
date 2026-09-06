"""`rediacc_ci.quality.git_op_conditionals` against the greps it replaces.

WHY A DIFFERENTIAL AND NOT A TABLE OF EXPECTED STRINGS. This gate is six
regexes, two of them extraction patterns whose exact reach decided whether a real
defect was found or silently missed. The twin's own history is the argument: an
adjacency-requiring extraction pattern (`git[[:space:]]+rev-parse`) passed every
synthetic fixture and found ZERO findings on a tree that genuinely had one,
because the real defect wore `git -C "$dir" rev-parse`. A table of expected
strings reproduces exactly that failure -- it asserts what the port does against
itself. Running the real greps under bash is the only form that can fail for the
right reason.

The bash fragments below are lifted from
`.ci/scripts/quality/check-git-op-conditionals.sh` lines 101-157 with the
variables substituted, and nothing else changed. They are NOT the whole gate: the
whole gate is what the committed shadow ledger
`.ci/shadow/w7p2-gitop.observations.jsonl` compares over five distinct trees.
This file covers the seams that ledger cannot isolate.
"""

import pathlib
import subprocess

import pytest

from rediacc_ci.quality import git_op_conditionals as goc
from rediacc_ci.tests import differential as diff

# The twin's own `bad.sh` heredoc, pulled from the port rather than retyped: a
# retyped copy is a second thing to keep in step, and the point of these cases is
# that they are the SAME bytes the gate runs its inline controls on.
_CONTROL_BAD = next(text for name, text, _fire, _msg in goc._CONTROLS if name == "bad.sh")

# Every shape the extraction patterns have to survive. The comment on each line
# is the property it is there for.
LINES = [
    "BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)",  # the 2026-08-28 defect
    'BRANCH=$(git -C "${CLAUDE_PROJECT_DIR:-.}" rev-parse --abbrev-ref HEAD)',  # the -C shape
    "B=$(git symbolic-ref --short -q HEAD) || exit 0",  # a guarded capture
    "B=$(git branch --show-current)",  # the third identity subcommand
    "s=$(git status --porcelain)",  # NOT an identity command
    "s=$(git rev-parse HEAD)",  # an identity, no --abbrev-ref
    'b="$(git rev-parse --abbrev-ref HEAD)"',  # quoted $( ): not the assignment shape
    "if ! sha=$(git rev-parse HEAD); then",  # guard 0
    "elif sha=$(git rev-parse HEAD); then",  # guard 0, elif
    "while x=$(git rev-parse HEAD); do",  # guard 0, while
    "sha=$(git rev-parse HEAD) || exit 1",  # guard 1
    "sha=$(git rev-parse HEAD) || return",  # guard 1, bare return
    "sha=$(git rev-parse HEAD) || :",  # guard 1, the colon builtin
    'sha=$(git rev-parse HEAD) || echo "main"',  # NOT guard 1
    "# BRANCH=$(git rev-parse --abbrev-ref HEAD)",  # a comment is still extracted
    "A=$(git rev-parse HEAD); B=$(git rev-parse HEAD~1)",  # two on one line
    'git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main"',  # the bare shape
    "git rev-parse --abbrev-ref HEAD || echo main",  # the bare shape, unquoted
    "git rev-parse --abbrev-ref HEAD",  # bare, no fallback: NOT the shape
    "echo ok",  # nothing at all
]


def _bash_captures(line: str, tmp_path: pathlib.Path) -> list[str]:
    (tmp_path / "f").write_text(line + "\n", encoding="utf-8")
    script = (
        "grep -noE '[A-Za-z_][A-Za-z0-9_]*=\\$\\(git\\b[^)]*\\b"
        "(rev-parse|symbolic-ref|branch)\\b[^)]*\\)' f || true"
    )
    code, out, err = diff.bash_streams(script, cwd=str(tmp_path))
    assert code == 0, err
    return [entry for entry in out.split("\n") if entry]


def _py_captures(line: str) -> list[str]:
    return ["1:" + m.group(0) for m in goc._CAPTURE.finditer(line)]


def _bash_bare(line: str, tmp_path: pathlib.Path) -> list[str]:
    (tmp_path / "f").write_text(line + "\n", encoding="utf-8")
    script = (
        "grep -noE 'git\\b[^|;&]*\\brev-parse\\b[^|;&]*--abbrev-ref"
        "[^|;&]*\\bHEAD\\b[^|;&]*\\|\\|[[:space:]]*echo\\b' f || true"
    )
    code, out, err = diff.bash_streams(script, cwd=str(tmp_path))
    assert code == 0, err
    return [entry for entry in out.split("\n") if entry]


def _py_bare(line: str) -> list[str]:
    return ["1:" + m.group(0) for m in goc._BARE.finditer(line)]


@pytest.mark.parametrize("line", LINES)
def test_capture_extraction_matches_grep(line: str, tmp_path: pathlib.Path) -> None:
    """Line numbers and matched text. `grep -o` can emit several per line."""
    assert _py_captures(line) == _bash_captures(line, tmp_path)


@pytest.mark.parametrize("line", LINES)
def test_bare_statement_extraction_matches_grep(line: str, tmp_path: pathlib.Path) -> None:
    assert _py_bare(line) == _bash_bare(line, tmp_path)


GUARD_LINES = [
    "sha=$(git rev-parse HEAD) || exit 1",
    "sha=$(git rev-parse HEAD) || exit",
    "sha=$(git rev-parse HEAD) || return 2",
    "sha=$(git rev-parse HEAD) || continue",
    "sha=$(git rev-parse HEAD) || true",
    "sha=$(git rev-parse HEAD) || :",
    "sha=$(git rev-parse HEAD) ||exit",  # no space after ||
    'sha=$(git rev-parse HEAD) || echo "x"',  # NOT a handler
    "sha=$(git rev-parse HEAD) || exitcode=1",  # NOT a handler: a longer word
    "sha=$(git rev-parse HEAD)",  # no handler at all
]


@pytest.mark.parametrize("line", GUARD_LINES)
def test_failure_handler_guard_matches_grep(line: str, tmp_path: pathlib.Path) -> None:
    """`|| exitcode=1` must NOT clear a finding. That is the whole word test."""
    (tmp_path / "f").write_text(line + "\n", encoding="utf-8")
    script = "grep -qE '\\|\\|[[:space:]]*(exit|return|continue|true|:)([[:space:]]|$)' f"
    code, _out, _err = diff.bash_streams(script, cwd=str(tmp_path))
    assert bool(goc._GUARD_HANDLER.search(line)) == (code == 0)


HEAD_GUARD_BODIES = [
    '[[ "$B" == "HEAD" ]]',
    '[ "$B" = "HEAD" ]',
    '[[ "$B"=="HEAD" ]]',  # no spaces
    '[[ "$B" == "main" ]]',  # a different literal
    '[[ "$OTHER" == "HEAD" ]]',  # a different variable
    '[[ $B == "HEAD" ]]',  # unquoted left side: NOT matched
    "# the value can be the literal HEAD",  # prose only
]


@pytest.mark.parametrize("body", HEAD_GUARD_BODIES)
def test_head_literal_guard_matches_grep(body: str, tmp_path: pathlib.Path) -> None:
    (tmp_path / "f").write_text(body + "\n", encoding="utf-8")
    script = 'grep -qE "\\"\\\\\\$B\\"[[:space:]]*(==|=)[[:space:]]*\\"HEAD\\"" f'
    code, _out, _err = diff.bash_streams(script, cwd=str(tmp_path))
    assert bool(goc.head_literal_guard("B").search(body)) == (code == 0)


def test_two_captures_on_one_line_share_the_lines_guard(tmp_path: pathlib.Path) -> None:
    """`grep -o` emits both; the loop re-reads the FULL line for both.

    So a single `|| exit 0` clears BOTH captures on that line. That is the
    twin's behaviour and it is over-clearing on purpose; asserted here so a port
    that judged the matched text instead would fail rather than look stricter.
    """
    line = "A=$(git rev-parse HEAD); B=$(git rev-parse HEAD~1) || exit 0"
    assert len(_bash_captures(line, tmp_path)) == 2
    assert goc.scan_text(line + "\n", "f") == []


def test_the_dash_c_shape_is_found_which_an_adjacency_pattern_missed(
    tmp_path: pathlib.Path,
) -> None:
    """THE REGRESSION THAT HAS ALREADY HAPPENED ONCE.

    A first draft of this gate required `git` and its subcommand to be adjacent.
    Every synthetic fixture passed, and the real scan found nothing on a tree
    that genuinely had a defect. The mutation-proof is the assertion.
    """
    line = 'BRANCH=$(git -C "${CLAUDE_PROJECT_DIR:-.}" rev-parse --abbrev-ref HEAD 2>/dev/null)'
    assert _bash_captures(line, tmp_path) != []
    assert goc.scan_text(line + '\n[[ -z "$BRANCH" ]] && exit 0\n', "f") == ["f:BRANCH"]


def test_the_bare_shape_has_no_file_wide_exemption() -> None:
    """MEASURED, NOT ASSUMED, and the twin says so in eleven lines.

    "does a HEAD-literal comparison appear ANYWHERE in the file" was tried and
    PROVEN WRONG: check-submodule-branches.sh has an unrelated
    `"$sm_branch" == "HEAD"` on a DIFFERENT variable elsewhere, which cleared the
    finding even with the real unguarded shape reintroduced verbatim.
    """
    body = (
        'git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main"\n'
        '[[ "$sm_branch" == "HEAD" ]] && return 1\n'
    )
    assert goc.scan_text(body, "f") == ["f:bare-statement-line-1"]


def test_the_exemption_is_by_name_and_fires_in_one_direction_only(
    tmp_path: pathlib.Path,
) -> None:
    """The bash twin is exempt; the same bytes under another name are not.

    A one-sided assertion here would pass for a port that exempted EVERYTHING,
    which is why the second half exists.
    """
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    quality = tmp_path / ".ci" / "scripts" / "quality"
    quality.mkdir(parents=True)
    body = _CONTROL_BAD
    (quality / "check-git-op-conditionals.sh").write_text(body, encoding="utf-8")
    files = goc.scan_files(tmp_path)
    assert files == [".ci/scripts/quality/check-git-op-conditionals.sh"]
    assert files[0] in goc.EXEMPT_PATHS
    (quality / "check-something-else.sh").write_text(body, encoding="utf-8")
    assert ".ci/scripts/quality/check-something-else.sh" not in goc.EXEMPT_PATHS
    assert goc.scan_file(quality / "check-something-else.sh", "x") != []


def test_the_flat_quality_glob_would_match_nothing_with_a_double_star(
    tmp_path: pathlib.Path,
) -> None:
    """The vacuity that was found INSIDE this gate, pinned as a fact.

    `.ci/scripts/quality/**/*.sh` needs a genuine subdirectory, and that
    directory is FLAT. The gate reported "71 shell file(s) scanned" while the
    second glob contributed nothing at all.
    """
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    quality = tmp_path / ".ci" / "scripts" / "quality"
    quality.mkdir(parents=True)
    (quality / "check-x.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True, capture_output=True)
    wide = subprocess.run(
        ["git", "-C", str(tmp_path), "ls-files", ".ci/scripts/quality/**/*.sh"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert wide.stdout.strip() == "", "the ** spelling has stopped dropping flat files"
    assert goc.scan_files(tmp_path) == [".ci/scripts/quality/check-x.sh"]


def test_untracked_files_are_in_scope(tmp_path: pathlib.Path) -> None:
    """Deliberate: a hook added but not committed is already running locally."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    hooks = tmp_path / ".claude" / "hooks" / "pre-bash"
    hooks.mkdir(parents=True)
    (hooks / "new.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    assert goc.scan_files(tmp_path) == [".claude/hooks/pre-bash/new.sh"]


def test_selftest_is_green() -> None:
    """The gate's own controls, driven in-process. Exit 0 or the port is broken."""
    assert goc.selftest() == 0
