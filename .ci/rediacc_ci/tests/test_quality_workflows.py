"""`rediacc_ci.quality.workflows` against the greps and awk programs it replaces.

WHY A DIFFERENTIAL. Four of the five banned patterns are handed to `grep -n` as
BASIC regular expressions, and one of them -- `script:[[:space:]]*|` -- depends
on `|` being LITERAL in BRE. Read as ERE it would match every line. Two of the
structural rules are awk state machines whose indentation arithmetic is
1-based and spaces-only. Running the real tools and comparing is the only form
of this test that can fail for the right reason.

The whole gate is covered by `.ci/shadow/w7p2-workflows.observations.jsonl` over
five distinct trees.
"""

import pathlib

import pytest

from rediacc_ci.quality import workflows as mod
from rediacc_ci.tests import differential as diff

BANNED_GREPS = [
    ("continue-on-error", 0),
    ("script:[[:space:]]*|", 1),
    ("pull_request_target", 2),
    ("secrets:[[:space:]]*inherit", 3),
    ("allow-unsafe-pr-checkout", 4),
]

LINES = [
    "    continue-on-error: true",
    "        script: |",
    "        script: return await require('./x.cjs')()",
    "  pull_request_target:",
    "    secrets: inherit",
    "    secrets:   inherit",
    "      allow-unsafe-pr-checkout: true",
    "      - uses: actions/checkout@v4",
    "# continue-on-error: true",
    "",
]


@pytest.mark.parametrize(("pattern", "index"), BANNED_GREPS)
@pytest.mark.parametrize("line", LINES)
def test_banned_patterns_match_basic_grep(
    tmp_path: pathlib.Path, pattern: str, index: int, line: str
) -> None:
    """The port's regex and the twin's BRE agree, line for line."""
    target = tmp_path / "w.yml"
    target.write_text(line + "\n", encoding="utf-8")
    code, _out, _err = diff.bash_streams("grep -n %s w.yml" % _shq(pattern), cwd=str(tmp_path))
    assert bool(mod.BANNED[index][0].search(line)) is (code == 0)


def _shq(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


# The block-scalar parser. Each fixture names the property it is here for.
BLOCK_FIXTURES = [
    "    steps:\n      - name: Thin\n        run: |\n          ./x.sh\n      - name: next\n",
    "      - name: X\n        run: |\n          # a comment\n          echo hi\n",
    "      - name: X\n        run: |\n          echo a\n\n          echo b\n",
    "      - name: X\n        run: |\n          echo a\n      - name: Y\n        run: echo b\n",
    "        run: echo hi\n",  # not a block scalar
    "        run: >\n          folded\n",  # the folded form counts too
    "jobs:\n  x:\n",  # nothing at all
    "        run: |\n          echo a\n",  # unnamed
]


@pytest.mark.parametrize("content", BLOCK_FIXTURES)
def test_block_parser_matches_the_twins_awk(tmp_path: pathlib.Path, content: str) -> None:
    target = tmp_path / "w.yml"
    target.write_text(content, encoding="utf-8")
    prog = tmp_path / "prog.awk"
    prog.write_text(_TWIN_AWK, encoding="utf-8")
    code, out, err = diff.bash_streams("awk -f prog.awk w.yml", cwd=str(tmp_path))
    assert code == 0, err
    expected = []
    for line in out.split("\n"):
        if line == "":
            continue
        start, count, name = line.split("\t", 2)
        expected.append((int(start), int(count), name))
    got = [(b.start, b.count, b.step) for b in mod.parse_run_blocks(mod.read_lines(target))]
    assert got == expected


# Lifted from `.ci/scripts/quality/check-workflows.sh`'s heredoc, unchanged.
_TWIN_AWK = r"""
function record() {
    if (inblock) {
        printf "%d\t%d\t%s\n", startline, count, sname
        inblock = 0
    }
}
{
    line = $0
    sub(/\r$/, "", line)
    if (line ~ /^[[:space:]]*$/) { next }
    match(line, /^ */)
    cur = RLENGTH
    if (inblock) {
        if (cur > keyindent) {
            rest = substr(line, cur + 1)
            if (substr(rest, 1, 1) != "#") count++
            next
        } else {
            record()
        }
    }
    if (line ~ /^[[:space:]]*(-[[:space:]]+)?name:[[:space:]]/) {
        nm = line
        sub(/^[[:space:]]*(-[[:space:]]+)?name:[[:space:]]*/, "", nm)
        sub(/[[:space:]]+$/, "", nm)
        stepname = nm
    }
    if (line ~ /^[[:space:]]*run:[[:space:]]*[|>]/) {
        keyindent = cur
        inblock = 1
        count = 0
        startline = NR
        sname = stepname
    }
}
END { record() }
"""

ENV_FIXTURES = [
    "    env:\n      SSH_KEY: $RUNNER_TEMP/renet/.ssh/id_rsa\n",  # run 29830623794
    "    env:\n      SECRET_X: $SOME_VAR\n",  # widened 2026-09-02
    "    env:\n      T: ${{ runner.temp }}\n",  # the correct form
    "    env:\n      # documents ${IN_FLIGHT_VERSION:-}\n",  # housekeeping.yml:72
    "    env:\n      A: 1\n    run: echo $HOME\n",  # dedented out of the mapping
    "    run: echo $HOME\n",  # no env: block
    "    env:\n\n      A: $B\n",  # a blank line inside the mapping
]


@pytest.mark.parametrize("content", ENV_FIXTURES)
def test_env_rule_matches_the_twins_awk(tmp_path: pathlib.Path, content: str) -> None:
    target = tmp_path / "w.yml"
    target.write_text(content, encoding="utf-8")
    prog = tmp_path / "env.awk"
    prog.write_text(_TWIN_ENV_AWK, encoding="utf-8")
    code, out, err = diff.bash_streams("awk -f env.awk w.yml", cwd=str(tmp_path))
    assert code == 0, err
    expected = [line for line in out.split("\n") if line != ""]
    got = ["%d:%s" % (number, line) for number, line in mod.env_shell_hits(mod.read_lines(target))]
    assert got == expected


_TWIN_ENV_AWK = r"""
/^[[:space:]]*env:[[:space:]]*$/ { inenv=1; envind=match($0, /[^ ]/); next }
inenv {
    ind = match($0, /[^ ]/)
    if ($0 ~ /^[[:space:]]*$/) next
    if (ind <= envind) { inenv=0 }
    else if ($0 ~ /^[[:space:]]*#/) next
    else if ($0 ~ /\$\{?[A-Za-z_][A-Za-z0-9_]*/ &&
             $0 !~ /\$\{\{/) { print NR ":" $0 }
}
"""

SLURP_FIXTURES = [
    'gh api x --paginate --slurp \\\n    --jq ".[]"\n',  # run 31321043543
    'gh api x --slurp --jq ".[]"\n',
    "gh api x --slurp\n",
    'gh api x --jq ".[]"\n',
    "# never combine --slurp with --jq\n",
    'gh api x --slurp \\\n# a comment resets the join\n--jq ".[]"\n',
]


@pytest.mark.parametrize("content", SLURP_FIXTURES)
def test_slurp_jq_matches_the_twins_awk(tmp_path: pathlib.Path, content: str) -> None:
    target = tmp_path / "s.sh"
    target.write_text(content, encoding="utf-8")
    prog = tmp_path / "slurp.awk"
    prog.write_text(_TWIN_SLURP_AWK, encoding="utf-8")
    code, out, err = diff.bash_streams("awk -f slurp.awk <s.sh", cwd=str(tmp_path))
    assert code == 0, err
    expected = [int(line) for line in out.split("\n") if line != ""]
    assert mod.slurp_jq_offenders(content) == expected


_TWIN_SLURP_AWK = r"""
/^[[:space:]]*#/ { joined = ""; next }
{ line = $0; n[++c] = NR
  if (joined != "") { joined = joined " " line } else { joined = line; start = NR }
  if (line ~ /\\[[:space:]]*$/) next
  if (joined ~ /--slurp/ && joined ~ /--jq/) print start
  joined = "" }
"""


def test_the_uses_anchor_blind_spot_is_pinned() -> None:
    """`^\\s+uses:\\s` misses the `- uses:` YAML list form.

    That is the twin's behaviour: `uses:` must follow WHITESPACE, so a step with
    no `name:` has its pin unchecked. Widening the pattern would be a verdict
    change on any tree carrying that spelling, so the port keeps it and this
    assertion is the record.
    """
    assert mod.USES_RE.search("        uses: actions/checkout@v4")
    assert not mod.USES_RE.search("      - uses: actions/checkout@v4")


# --- the .py widening, 2026-09-08 -------------------------------------------
# `check_gh_slurp_jq` walked `.ci/scripts` taking only `.sh`, so once W7 ported the
# quality gates to Python the scan stopped reading 72 files that mention `gh` -- and it
# reported nothing about it, because a matcher that stops matching finds no offenders and
# exits 0. The glob now takes both, and `slurp_jq_offenders` had to learn Python's
# continuation, which is a running BRACKET DEPTH rather than a trailing backslash.

_PY_OFFENDER = (
    "import subprocess\n"
    "subprocess.run(\n"
    "    [\n"
    '        "gh", "api", "repos/x/issues",\n'
    '        "--paginate", "--slurp",\n'
    '        "--jq", ".[]",\n'
    "    ],\n"
    ")\n"
)


def test_a_wrapped_python_gh_call_is_seen():
    """THE REGRESSION. A per-line `ends with an open bracket` test was written first and
    this refused it: the `"gh", "api", ...` line opens nothing, so a suffix test ends the
    join two lines before `--slurp` and `--jq` ever meet."""
    assert mod.slurp_jq_offenders(_PY_OFFENDER) == [2]


def test_the_bash_form_still_fires():
    """The corpus this was written against must not move. Depth and backslash are
    independent tests, ORed, so bash sees exactly what it saw before."""
    assert mod.slurp_jq_offenders(
        'gh api repos/x/issues --paginate --slurp \\\n    --jq ".[]"\n'
    ) == [1]


def test_a_wrapped_python_call_without_slurp_is_not_a_finding():
    """THE ANTI-SILENCER HALF, and the one that makes joining safe to widen: joining more
    lines together must not start inventing pairs. The same five-line call with no
    `--slurp` is clean."""
    clean = _PY_OFFENDER.replace('"--paginate", "--slurp",', '"--paginate",')
    assert mod.slurp_jq_offenders(clean) == []


def test_a_comment_still_resets_the_join():
    """Unchanged behaviour, asserted because the depth counter is reset in the same arm
    and a reset that forgot one of the two would leak a bracket across a comment."""
    assert mod.slurp_jq_offenders('gh api x --slurp \\\n# a comment\n    --jq ".[]"\n') == []
