"""`rediacc_ci.quality.ci_watch_recipe` against the awk, grep and bash it replaces.

WHAT IS WORTH TESTING HERE. The shadow ledger
`.ci/shadow/w7p2-ci-watch-recipe.observations.jsonl` drives the whole gate over
five distinct trees, one per broken check. What a ledger row cannot isolate is
the four detectors, and this gate is ALL detector: check A is an awk block
extractor, checks B and C are three greps whose false-positive boundaries were
each argued over, and the whole file exists because ONE of those greps was
racing its own pipe and reporting a clean bill of health over a real offender.

So each detector is re-run as the twin's own bash, over the twin's own fixtures,
and compared. The negative cases carry as much weight as the positive ones:
three of the twin's controls exist only to prove the detectors do NOT fire on the
sanctioned invocation, on a JSON value, or on a test assertion.
"""

import pathlib
import subprocess

from rediacc_ci import paths
from rediacc_ci.quality import ci_watch_recipe as cw
from rediacc_ci.tests import differential as diff

BASH_BLOCK_AWK = "/^```bash$/ { inblk=1; next } /^```$/ { if (inblk) exit } inblk { print }"
ADVICE_GREP = "grep -vE '\"(command|cmd)\"[[:space:]]*:|^[[:space:]]*check [0-9]+ '"

# The twin's two detectors, lifted from check-ci-watch-recipe.sh:101-113 into a
# driver that exits 0 when they say yes. Nothing is reworded; the `advice_only`
# body is the same grep -v as above.
TWIN_DETECTORS = r"""
advice_only() {
    grep -vE '"(command|cmd)"[[:space:]]*:|^[[:space:]]*check [0-9]+ ' "$1"
}
hands_out_loop() {
    local f="$1" statuses
    statuses="$(advice_only "$f" | grep -E '\.status')"
    [ -n "$statuses" ] || return 1
    [ -n "$(printf '%s\n' "$statuses" | grep -E '"completed"')" ] || return 1
    grep -q 'run_attempt' "$f" && return 1
    return 0
}
hands_out_banned() {
    [ -n "$(advice_only "$1" | grep -E 'gh run watch[^|;&]*--(exit-status|interval)')" ]
}
"$1" "$2"
"""


def _twin(fn: str, text: str, tmp_path: pathlib.Path) -> bool:
    """Run one of the twin's detectors over `text`. True when it says yes."""
    target = tmp_path / "subject.md"
    target.write_text(text, encoding="utf-8")
    proc = subprocess.run(
        ["bash", "-c", TWIN_DETECTORS, "driver", fn, str(target)],
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0


FIXTURES = {
    "bad": cw.FIXTURE_BAD,
    "good": cw.FIXTURE_GOOD,
    "data": cw.FIXTURE_DATA,
    "mute": cw.FIXTURE_MUTE,
    "loop-skill": cw.FIXTURE_LOOP_SKILL,
    "run-attempt": cw.FIXTURE_BAD + "and check run_attempt too\n",
    "status-only": "read .status and print it\n",
    "interval": "run `gh run watch 1 --interval 30`\n",
    "separator": "gh run watch 1 | tee log --exit-status\n",
}


def test_hands_out_loop_agrees_with_the_twin_on_every_fixture(tmp_path: pathlib.Path) -> None:
    """Nine inputs, both directions, against the twin's own shell function."""
    for name, text in FIXTURES.items():
        assert cw.hands_out_loop(text) == _twin("hands_out_loop", text, tmp_path), name


def test_hands_out_banned_agrees_with_the_twin_on_every_fixture(tmp_path: pathlib.Path) -> None:
    """Same nine inputs through the other detector."""
    for name, text in FIXTURES.items():
        assert cw.hands_out_banned(text) == _twin("hands_out_banned", text, tmp_path), name


def test_the_large_fixture_agrees_and_is_over_the_pipe_buffer(tmp_path: pathlib.Path) -> None:
    """The control the others could not be, run through the twin as well.

    Under the twin this input is the one that raced: at ~240 KB the producer
    BLOCKS on a full pipe, which is what let `grep -q`'s early exit kill it. The
    port has no pipe, so what is being asserted here is that both sides still
    agree on the answer at that size.
    """
    big = cw.fixture_big()
    assert len(big) > 64 * 1024
    assert cw.hands_out_banned(big) is True
    assert _twin("hands_out_banned", big, tmp_path) is True


def test_bash_block_matches_awk() -> None:
    """Including the `exit` on the closing fence, which drops every later block."""
    cases = (
        "intro\n```bash\nrun me\n```\ntail\n",
        "just prose\n",
        "```bash\nfirst\n```\n```bash\nsecond\n```\n",
        cw.FIXTURE_LOOP_SKILL,
        paths.from_root(".claude", "skills", "ci-watch", "SKILL.md").read_text(encoding="utf-8"),
    )
    for text in cases:
        proc = subprocess.run(
            ["awk", BASH_BLOCK_AWK],
            input=text.encode("utf-8"),
            capture_output=True,
            check=True,
        )
        assert cw.bash_block(text) == proc.stdout.decode("utf-8"), text[:40]


def test_advice_only_matches_the_twins_grep(tmp_path: pathlib.Path) -> None:
    """`grep -v` drops the line and keeps the rest, newline handling included."""
    for name, text in FIXTURES.items():
        target = tmp_path / "f.md"
        target.write_text(text, encoding="utf-8")
        proc = subprocess.run(
            ["bash", "-c", "%s '%s' || true" % (ADVICE_GREP, target)],
            capture_output=True,
            check=True,
        )
        want = proc.stdout.decode("utf-8").rstrip("\n")
        assert cw.advice_only(text).rstrip("\n") == want, name


def test_scan_files_matches_git_ls_files() -> None:
    """The three pathspecs, run by git, minus the evidence file.

    Not re-implemented as a walk: git's pathspec matching is not fnmatch, so
    `.claude/**/*.md` does not mean what it looks like, and a hand-rolled walk
    would scan a different set while the success line still read healthy.
    """
    root = paths.repo_root()
    # THE PATHSPECS COME FROM THE PORT'S OWN CONSTANT, not retyped here. Two reasons, and the second is why this changed on 2026-09-06. First, a copy can drift from the thing it is meant to check, which would leave this test asserting that the port agrees with a literal nobody runs. Second, `check:ci-pathspec-scope` reads every `git ls-files` call site and refuses a `**/` pathspec,
    # correctly: `*` already crosses `/` under git's default semantics, so `**/` DEMANDS a slash and silently skips everything directly under the prefix. The twin carries that defect deliberately and the port
    # carries it faithfully; spelling it a third time here made this file an
    # independent instance of the defect rather than a check on it.
    specs = " ".join("'%s'" % s for s in cw.SCAN_PATHSPECS)
    code, out, _err = diff.bash_streams(
        'git -C %s ls-files %s | grep -v "^%s$"' % (root, specs, cw.EVIDENCE_FILE)
    )
    assert code == 0
    want = [line for line in out.split("\n") if line != ""]
    assert cw.scan_files(root) == want
    assert len(want) > 50, len(want)


def test_assert_skill_passes_the_real_skill() -> None:
    """The mirror at the top of check A, against the file the gate actually reads."""
    text = paths.from_root(".claude", "skills", "ci-watch", "SKILL.md").read_text(encoding="utf-8")
    assert cw.assert_skill(text) is None


def test_selftest_runs_and_meets_its_floor() -> None:
    """The gate's own both-direction controls, over fixtures written by construction."""
    assert cw.selftest() == 0
