"""`rediacc_ci.quality.git_op_conditionals` against the greps it replaces.

WHY A DIFFERENTIAL AND NOT A TABLE OF EXPECTED STRINGS. This gate is six regexes, two of them extraction patterns whose exact reach decided whether a real defect was found or silently missed. The twin's own history is the argument: an adjacency-requiring extraction pattern (`git[[:space:]]+rev-parse`) passed every synthetic fixture and found ZERO findings on a tree that genuinely
had one, because the real defect wore `git -C "$dir" rev-parse`. A table of expected strings reproduces exactly that failure -- it asserts what the port does against itself. Running the real greps under bash is the only form that can fail for the right reason.

The bash fragments below are lifted from `.ci/scripts/quality/check-git-op-conditionals.sh` lines 101-157 with the variables substituted, and nothing else changed. They are NOT the whole gate: the whole gate is what the committed shadow ledger `.ci/shadow/w7p2-gitop.observations.jsonl` compares over five distinct trees. This file covers the seams that ledger cannot isolate.
"""

import pathlib
import subprocess

import pytest

from rediacc_ci.quality import git_op_conditionals as goc
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

# The twin's own `bad.sh` heredoc, pulled from the port rather than retyped: a retyped copy is a second thing to keep in step, and the point of these cases is that they are the SAME bytes the gate runs its inline controls on.
_CONTROL_BAD = next(text for name, text, _fire, _msg in goc._CONTROLS if name == "bad.sh")

# Every shape the extraction patterns have to survive. The comment on each line is the property it is there for.
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

    So a single `|| exit 0` clears BOTH captures on that line. That is the twin's behaviour and it is over-clearing on purpose; asserted here so a port that judged the matched text instead would fail rather than look stricter.
    """
    line = "A=$(git rev-parse HEAD); B=$(git rev-parse HEAD~1) || exit 0"
    assert len(_bash_captures(line, tmp_path)) == 2
    assert goc.scan_text(line + "\n", "f") == []


def test_the_dash_c_shape_is_found_which_an_adjacency_pattern_missed(
    tmp_path: pathlib.Path,
) -> None:
    """THE REGRESSION THAT HAS ALREADY HAPPENED ONCE.

    A first draft of this gate required `git` and its subcommand to be adjacent. Every synthetic fixture passed, and the real scan found nothing on a tree that genuinely had a defect. The mutation-proof is the assertion.
    """
    line = 'BRANCH=$(git -C "${CLAUDE_PROJECT_DIR:-.}" rev-parse --abbrev-ref HEAD 2>/dev/null)'
    assert _bash_captures(line, tmp_path) != []
    assert goc.scan_text(line + '\n[[ -z "$BRANCH" ]] && exit 0\n', "f") == ["f:BRANCH"]


def test_the_bare_shape_has_no_file_wide_exemption() -> None:
    """MEASURED, NOT ASSUMED, and the twin says so in eleven lines.

    "does a HEAD-literal comparison appear ANYWHERE in the file" was tried and PROVEN WRONG: check-submodule-branches.sh has an unrelated
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
    """A named path is exempt; the same bytes under another name are not.

    A one-sided assertion here would pass for a port that exempted EVERYTHING, which is why the second half exists.

    THE LIVE DICT IS EMPTY since W7 P5 batch G2 deleted the bash twin, which was its only entry, so this seeds its own and removes it in a `finally`. Asserting the dict is empty is the OTHER half: a stale entry excusing a file that no longer exists is the allowlist rot the port's docstring names.
    """
    assert goc.EXEMPT_PATHS == {}, "an exemption reappeared without a reason in the output"
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    quality = tmp_path / ".ci" / "scripts" / "quality"
    quality.mkdir(parents=True)
    body = _CONTROL_BAD
    (tmp_path / goc.EXEMPT_PLANT).write_text(body, encoding="utf-8")
    files = goc.scan_files(tmp_path)
    assert files == [goc.EXEMPT_PLANT]
    goc.EXEMPT_PATHS[goc.EXEMPT_PLANT] = "test fixture"
    try:
        assert files[0] in goc.EXEMPT_PATHS
        (quality / "check-something-else.sh").write_text(body, encoding="utf-8")
        assert ".ci/scripts/quality/check-something-else.sh" not in goc.EXEMPT_PATHS
        assert goc.scan_file(quality / "check-something-else.sh", "x") != []
    finally:
        del goc.EXEMPT_PATHS[goc.EXEMPT_PLANT]


def test_the_flat_quality_glob_would_match_nothing_with_a_double_star(
    tmp_path: pathlib.Path,
) -> None:
    """The vacuity that was found INSIDE this gate, pinned as a fact.

    `.ci/scripts/quality/**/*.sh` needs a genuine subdirectory, and that directory is FLAT. The gate reported "71 shell file(s) scanned" while the second glob contributed nothing at all.
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


# --------------------------------------------------------------------------- THE PYTHON HALF.
#
# Same philosophy as above: compare against the TWIN'S ACTUAL BYTES, not a retyped copy. While both copies existed, the awk program and `scan_python_file` were sliced out of the shell script at test time and EXECUTED, so a divergence failed here rather than waiting for the next ledger recording.
#
# THE TWIN IS NOW GONE, and what stands in for it is the output that harness produced on the twin's last day in the tree, one golden per case under `goldens/git-op-conditionals/`. Nothing in a golden is a hand-written expectation: each is the exit code and both streams of the real awk, and the provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the
# program that printed those bytes.
#
# THIS IS NOT PARANOIA. Writing the mirror produced exactly one such divergence on 2026-09-08 and it was invisible on this tree: the awk emitted `B\t\t<lineno>` for the bare shape, tab is IFS whitespace, bash `read` collapsed the empty field, and the twin printed `bare-statement-line-` with NO NUMBER
# while the port printed `bare-statement-line-2`. Neither side has a bare finding on the real tree, so both were "equal" and green. That divergence was repaired before the recording, and `the-bare-shape-and-its-line-number` is the golden that now holds the repaired answer in place.
#
# SIX OF THE TEN RECORDED CASES ARE EMPTY, because six of the ten shapes must NOT fire. A port that returned nothing at all would satisfy those six and fail the other four, and `test_the_recorded_python_corpus_fires_on_something` refuses the corpus outright if the non-empty half ever shrinks to nothing.

PY_SLUG = "git-op-conditionals"


def split_golden(text: str) -> tuple[int, str, str]:
    """A recorded twin render, back into its three parts."""
    exit_line, rest = text.split("\n", 1)
    stdout, stderr = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr


def recorded_findings(name: str) -> list[str]:
    """The sorted finding lines the twin's awk printed for one case."""
    returncode, stdout, stderr = split_golden(frozen.read(PY_SLUG, name))
    assert returncode == 0, "%s: the recorded harness exited %d: %s" % (name, returncode, stderr)
    return sorted(line for line in stdout.split("\n") if line)


# One entry per shape the python predicate has to get right. The comment is the
# property; the name is the golden holding the twin's own answer for it.
PY_CASES = [
    (
        "a-not-branch-truthiness-guard",
        'branch = hookio.git_out(["rev-parse", "--abbrev-ref", "HEAD"])\nif not branch:\n    pass\n',
    ),
    (
        "a-branch-equality-guard",
        (
            'branch = hookio.git_out(["rev-parse", "--abbrev-ref", "HEAD"])\n'
            'if branch == "HEAD":\n    pass\n'
        ),
    ),
    # THE SPLIT CALL: `git` on the head line, `rev-parse` on the continuation.
    (
        "a-split-call-across-lines",
        'remote = hookio.git_out(\n    ["rev-parse", "--abbrev-ref", "HEAD"], cwd=root\n)\n',
    ),
    # The bare shape, whose line number is the divergence described above.
    (
        "the-bare-shape-and-its-line-number",
        'def cb():\n    return hookio.git_out(["rev-parse", "--abbrev-ref", "HEAD"]) or "main"\n',
    ),
    # A compound truthiness guard, which a narrower `if var:` spelling missed.
    (
        "a-compound-truthiness-guard",
        (
            'p = hookio.git_out(["rev-parse", "--git-path", "x"])\n'
            "if p and pathlib.Path(p).is_file():\n    pass\n"
        ),
    ),
    # Fail-loud.
    (
        "a-fail-loud-subprocess-run",
        'sha = subprocess.run(["git", "rev-parse", "HEAD"], check=True).stdout\n',
    ),
    # `github_api` carries the letters `git` and is not the git CLI.
    (
        "github-api-is-not-the-git-cli",
        'b = github_api(["rev-parse", "--abbrev-ref", "HEAD"])\nif b == "main":\n    pass\n',
    ),
    # A control body is fixture territory; the def AFTER it is not.
    (
        "a-def-after-a-control-body",
        (
            "def selftest():\n"
            '    b = hookio.git_out(["rev-parse", "--abbrev-ref", "HEAD"])\n\n\n'
            'def main():\n    c = hookio.git_out(["rev-parse", "--abbrev-ref", "HEAD"])\n'
        ),
    ),
    # The over-join regression: brackets inside a regex constant.
    (
        "brackets-inside-a-regex-constant",
        (
            'A = (\n    r"(^|[;&|(]|&&"\n    + r"]*git["\n)\n'
            'b = hookio.git_out(["rev-parse", "HEAD"])\nif not b:\n    pass\n'
        ),
    ),
    # Not an identity command at all.
    (
        "not-an-identity-command",
        'status = hookio.git_out(["status", "--porcelain"])\nif status != "":\n    pass\n',
    ),
]


@pytest.mark.parametrize(("name", "body"), PY_CASES, ids=[c[0] for c in PY_CASES])
def test_python_predicate_matches_the_twins_recorded_awk(name: str, body: str) -> None:
    assert sorted(goc.scan_python_text(body, "case.py")) == recorded_findings(name)


def test_every_python_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(PY_SLUG, {name for name, _body in PY_CASES})


def test_the_recorded_python_corpus_fires_on_something() -> None:
    """A corpus of ten silences would be satisfied by a scanner that does nothing.

    Four of the ten shapes must produce a finding and six must not, and both halves are asserted here so that a recording which had collapsed to all-empty reds by name rather than turning every case above into a comparison of two empty lists.
    """
    fires = {name for name, _body in PY_CASES if recorded_findings(name)}
    assert fires == {
        "a-not-branch-truthiness-guard",
        "a-split-call-across-lines",
        "the-bare-shape-and-its-line-number",
        "a-def-after-a-control-body",
    }
    assert recorded_findings("the-bare-shape-and-its-line-number") == [
        "case.py:bare-statement-line-2"
    ], "the 2026-09-08 empty-field divergence is back"


def test_planted_defect_is_caught_by_the_python_goldens() -> None:
    """THE CONTROL ON THE GOLDENS. Scan line by line instead of on the joined text.

    A line scanner is the obvious implementation and it misses `a-split-call-across-lines`, where neither line carries both tokens. The mutation is a local re-scan of each line, never a change to the module.
    """
    name, body = next(c for c in PY_CASES if c[0] == "a-split-call-across-lines")
    line_by_line = sorted(
        finding
        for line in body.split("\n")
        for finding in goc.scan_python_text(line + "\n", "case.py")
    )
    assert line_by_line != recorded_findings(name), "the plant no longer diverges"
    # And the real, unmutated scanner still agrees with the recording.
    assert sorted(goc.scan_python_text(body, "case.py")) == recorded_findings(name)


def test_the_hooks_python_glob_needs_the_flat_spelling(tmp_path: pathlib.Path) -> None:
    """`**/*.py` DROPS every top-level module, including the one defining git_out.

    The sibling of the `.sh` case above, in the other direction. git's default pathspec is wildmatch without pathname mode, so the flat `*.py` recurses and the `**` form demands a literal slash. Getting this backwards costs SIX files here, one of which is `hookio.py`.
    """
    root = tmp_path / "r"
    (root / ".claude" / "rediacc_hooks" / "guards").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    (root / ".claude/rediacc_hooks/hookio.py").write_text("x = 1\n", encoding="utf-8")
    (root / ".claude/rediacc_hooks/guards/g.py").write_text("x = 1\n", encoding="utf-8")

    flat = goc.scan_files(root, (".claude/rediacc_hooks/*.py",))
    starred = goc.scan_files(root, (".claude/rediacc_hooks/**/*.py",))
    assert ".claude/rediacc_hooks/hookio.py" in flat
    assert ".claude/rediacc_hooks/hookio.py" not in starred
    assert goc.PY_SCAN_GLOBS[0] == ".claude/rediacc_hooks/*.py"


def test_the_split_call_is_found_which_a_line_scanner_missed() -> None:
    """The python analogue of the `-C` case: real, and invisible line by line."""
    body = 'remote = hookio.git_out(\n    ["rev-parse", "--abbrev-ref", "HEAD"], cwd=root\n)\n'
    assert goc.scan_python_text(body, "f.py") == ["f.py:remote"]
    # Line by line, NEITHER line carries both tokens -- which is the whole point.
    head, cont = body.split("\n")[:2]
    assert "rev-parse" not in head
    assert not goc._PY_GIT_TOKEN.search(cont)


@pytest.mark.parametrize("name", ["d/test-x.py", "d/test_x.py"])
def test_test_files_are_out_of_scope_with_either_separator(name: str) -> None:
    """This tree spells one of them with a HYPHEN, so a `test_`-only rule misses it."""
    body = 'b = hookio.git_out(["rev-parse", "--abbrev-ref", "HEAD"])\n'
    assert goc.scan_python_text(body, name) == []
    assert goc.scan_python_text(body, "d/x.py") == ["d/x.py:b"]
