"""`rediacc_ci.quality.claude_attribution` against the grep it replaces.

WHAT IS WORTH TESTING HERE. The shadow ledger
`.ci/shadow/w7p2-claude-attribution.observations.jsonl` drives the whole gate
over five distinct trees: attribution in the PR body, in a commit message, in a
commit author, all three at once, and an empty commit list. What a ledger row
cannot isolate is that the gate is ONE regular expression, written as a POSIX
ERE and evaluated by `grep -iE`, and that this port evaluates it with Python's
`re` instead.

Those two engines are not the same engine. `[[:space:]]` is six characters;
Python's `\\s` is more. So the pattern is TAKEN FROM THE TWIN'S OWN SOURCE and
run through the real `grep -iE`, and every case is compared against the port.
A pattern that had silently widened would still pass a hand-written expectation.

The trailer literal is assembled from parts, for the same reason the port
assembles it: `.claude/hooks/pre-bash/block-commit-meta.sh` refuses any shell
command whose text carries it, so a test that spelled it out could not be
written from a shell and could not be grepped for from one either.
"""

import re
import subprocess

from rediacc_ci import paths
from rediacc_ci.quality import claude_attribution as ca

TWIN = paths.from_root(".ci", "scripts", "quality", "check-claude-attribution.sh")
TRAILER = "Co-" + "Authored-By"


def twin_pattern() -> str:
    """The ERE the twin actually carries, read from its source.

    Read rather than copied so a change to the twin reds this test instead of
    drifting past it. That is the whole point of a differential port.
    """
    body = TWIN.read_text(encoding="utf-8")
    found = re.search(r'^CLAUDE_PATTERN="(.+)"$', body, re.MULTILINE)
    assert found is not None, "the twin no longer declares CLAUDE_PATTERN on one line"
    return found.group(1)


def _grep(pattern: str, text: str, extra: str = "-iE") -> bool:
    """`grep <extra> <pattern>` over `text`. True when it matches."""
    proc = subprocess.run(
        ["grep", extra, pattern],
        input=text.encode("utf-8"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode == 0


CASES = (*ca.MUST_MATCH, *ca.MUST_NOT_MATCH)


def test_the_pattern_agrees_with_the_twins_grep_on_every_case() -> None:
    """Fourteen inputs, both directions, against the twin's own ERE and real grep."""
    pattern = twin_pattern()
    for text in CASES:
        want = _grep(pattern, text)
        assert bool(ca.CLAUDE_PATTERN.search(text)) == want, (text, want)


def test_the_ported_pattern_is_the_twins_pattern_modulo_the_class_spelling() -> None:
    """`[[:space:]]` is the only thing that had to change, and it changed nowhere else.

    Asserted structurally rather than by eye: substituting the ERE's class for
    the port's spelling must reproduce the port's pattern exactly, so a second
    difference could not hide inside the first.
    """
    ere = twin_pattern()
    rebuilt = ere.replace("[[:space:]]", ca.SPACE)
    assert rebuilt == ca.CLAUDE_PATTERN.pattern


def test_the_author_check_agrees_with_the_twins_grep() -> None:
    """`grep -qiE "(claude|anthropic)"` over `"$NAME $EMAIL"`."""
    for name, email in (
        ("Someone", "noreply@anthropic.com"),
        ("Claude", "someone@example.invalid"),
        ("Muhammed Fatih Bayraktar", "muhammed@rediacc.com"),
        ("A Human", "human@example.invalid"),
    ):
        joined = "%s %s" % (name, email)
        want = _grep("(claude|anthropic)", joined)
        assert bool(ca.AUTHOR_PATTERN.search(joined)) == want, joined


def test_first_match_is_the_line_grep_head_1_would_print() -> None:
    """`grep -iE ... | head -1` prints a LINE, and the twin quotes it whole."""
    pattern = twin_pattern()
    text = "intro\n%s: Claude <a>\nmore\n%s: Claude <b>\n" % (TRAILER, TRAILER)
    proc = subprocess.run(
        ["bash", "-c", 'grep -iE "$1" | head -1', "driver", pattern],
        input=text.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    want = proc.stdout.decode("utf-8").rstrip("\n")
    assert ca.first_match(text) == want
    assert want == "%s: Claude <a>" % TRAILER


def test_is_blank_matches_the_twins_parameter_expansion() -> None:
    """`[[ -z "${COMMITS//[[:space:]]/}" ]]`, evaluated by bash itself.

    This is the anti-vacuity test on the commit list, so getting it wrong in the
    lenient direction would clear a PR whose commits were never read.
    """
    for payload in ("", "  \n\t\n", "abc123\n", "a b\n", "\v\f\r"):
        proc = subprocess.run(
            ["bash", "-c", 'C="$1"; [[ -z "${C//[[:space:]]/}" ]]', "driver", payload],
            check=False,
        )
        assert ca.is_blank(payload) is (proc.returncode == 0), repr(payload)


def test_split_commits_matches_unquoted_word_splitting() -> None:
    """`for SHA in $COMMITS` splits on IFS whitespace and drops empties."""
    for payload in ("a\nb\nc", "  a   b  ", "", "single"):
        proc = subprocess.run(
            ["bash", "-c", 'for s in $1; do printf "%s\\n" "$s"; done', "driver", payload],
            capture_output=True,
            check=True,
        )
        want = [line for line in proc.stdout.decode("utf-8").split("\n") if line != ""]
        assert ca.split_commits(payload) == want, repr(payload)


def test_selftest_runs_and_meets_its_floor() -> None:
    """The gate's own both-direction controls, with no token and no network."""
    assert ca.selftest() == 0
