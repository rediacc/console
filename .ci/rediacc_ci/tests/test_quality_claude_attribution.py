"""`rediacc_ci.quality.claude_attribution` against the grep it replaces.

WHAT IS WORTH TESTING HERE. The shadow ledger `.ci/shadow/w7p2-claude-attribution.observations.jsonl` drives the whole gate over five distinct trees: attribution in the PR body, in a commit message, in a commit author, all three at once, and an empty commit list. What a ledger row cannot isolate is that the gate is ONE regular expression, written as a POSIX ERE and evaluated by
`grep -iE`, and that this port evaluates it with Python's `re` instead.

Those two engines are not the same engine. `[[:space:]]` is six characters;
Python's `\\s` is more. So the pattern is TAKEN FROM THE TWIN'S OWN SOURCE and run through the real `grep -iE`, and every case is compared against the port. A pattern that had silently widened would still pass a hand-written expectation.

WHERE THE TWIN'S SOURCE NOW LIVES. `.ci/scripts/quality/check-claude-attribution.sh` was deleted once the ledger asserted equivalence over five distinct trees, so the two lines this file used to read out of it are recorded in `goldens/claude-attribution/` instead: the `CLAUDE_PATTERN=` declaration and the author-check call site, each captured as the exit code and bytes a real
`grep -n` printed against the tracked script on its last day in the tree. The provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program those lines came from. What is NOT frozen is the comparison itself: the ERE recovered from the golden is still handed to the real `grep -iE`, so the engine difference this file exists to police is measured on every
run rather than recorded.

The trailer literal is assembled from parts, for the same reason the port assembles it: `.claude/hooks/pre-bash/block-commit-meta.sh` refuses any shell command whose text carries it, so a test that spelled it out could not be written from a shell and could not be grepped for from one either.
"""

import re
import subprocess

from rediacc_ci.quality import claude_attribution as ca
from rediacc_ci.tests import frozen

SLUG = "claude-attribution"
TRAILER = "Co-" + "Authored-By"

CASE_NAMES = {"the-pattern-declaration", "the-author-pattern-call-site"}


def golden_line(name: str) -> str:
    """The single `grep -n` hit a golden recorded, without its line number."""
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    assert exit_line == "exit: 0", "%s: the twin's grep found nothing" % name
    stdout = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)[0]
    lines = [line for line in stdout.split("\n") if line != ""]
    assert len(lines) == 1, "%s recorded %d hits, not one" % (name, len(lines))
    return lines[0].split(":", 1)[1]


def twin_pattern() -> str:
    """The ERE the twin carried, recovered from its recorded declaration.

    Recovered from the recording rather than retyped so that the pattern under test is the twin's bytes and not a reader's transcription of them. That is the whole point of a differential port, and the only thing deleting the twin changed is where the bytes are read from.
    """
    found = re.match(r'^CLAUDE_PATTERN="(.+)"$', golden_line("the-pattern-declaration"))
    assert found is not None, "the recorded declaration is not one-line CLAUDE_PATTERN"
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

    Asserted structurally rather than by eye: substituting the ERE's class for the port's spelling must reproduce the port's pattern exactly, so a second difference could not hide inside the first.
    """
    ere = twin_pattern()
    rebuilt = ere.replace("[[:space:]]", ca.SPACE)
    assert rebuilt == ca.CLAUDE_PATTERN.pattern


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a golden nothing reads is a recording of a line that stopped being compared, and a name with no golden would pass by never being read at all."""
    frozen.assert_corpus(SLUG, CASE_NAMES)


def test_the_recorded_declaration_is_not_an_empty_recording() -> None:
    """A golden of a grep that found nothing would make every case below vacuous.

    The declaration golden is asserted to carry all four alternatives the gate is built from, so a recording that had captured an empty match, or a later one-line summary, reds here by name rather than quietly turning `twin_pattern` into an empty ERE that matches everything.
    """
    pattern = twin_pattern()
    for fragment in (TRAILER, "Generated with", "Generated", "noreply@anthropic"):
        assert fragment in pattern, fragment
    assert pattern.count("|") == 3, pattern


def test_planted_defect_is_caught_by_the_recorded_pattern() -> None:
    """THE CONTROL ON THE GOLDEN. Widen the port's pattern and watch the agreement break.

    `Generated with[[:space:]]+\\[?Claude` requires the word "Claude" after the bracket, and dropping that requirement is the widening a reader makes without noticing. The mutation is applied to a LOCAL copy of the compiled pattern; the module's own is never reassigned.
    """
    pattern = twin_pattern()
    widened = re.compile(
        ca.CLAUDE_PATTERN.pattern.replace("Generated with%s+\\[?Claude" % ca.SPACE, "Generated"),
        re.IGNORECASE,
    )
    assert widened.pattern != ca.CLAUDE_PATTERN.pattern, "the plant's anchor moved"
    disagreed = [text for text in CASES if bool(widened.search(text)) != _grep(pattern, text)]
    assert disagreed, "the widened pattern still agreed with the twin's grep everywhere"
    # And the real, unmutated pattern still agrees on every one of them.
    for text in disagreed:
        assert bool(ca.CLAUDE_PATTERN.search(text)) == _grep(pattern, text), text


def test_the_author_check_agrees_with_the_twins_grep() -> None:
    """`grep -qiE "(claude|anthropic)"` over `"$NAME $EMAIL"`, as the twin spelled it.

    The ERE is recovered from the recorded call site rather than retyped, so a recording that captured a different line reds here instead of silently testing a pattern the gate never used.
    """
    call_site = golden_line("the-author-pattern-call-site")
    found = re.search(r'grep -qiE "([^"]+)"', call_site)
    assert found is not None, "the recorded call site no longer carries an inline ERE"
    author_ere = found.group(1)
    assert author_ere == "(claude|anthropic)"
    for name, email in (
        ("Someone", "noreply@anthropic.com"),
        ("Claude", "someone@example.invalid"),
        ("Muhammed Fatih Bayraktar", "muhammed@rediacc.com"),
        ("A Human", "human@example.invalid"),
    ):
        joined = "%s %s" % (name, email)
        want = _grep(author_ere, joined)
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

    This is the anti-vacuity test on the commit list, so getting it wrong in the lenient direction would clear a PR whose commits were never read.
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
